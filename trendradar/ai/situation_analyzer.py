# coding=utf-8
"""
AI 态势解读模块

职责：
- 每小时聚合 24 小时内新闻数据，调用推理模型进行宏观态势解读
- 结果缓存供 API 查询
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from trendradar.ai.client import AIClient

logger = logging.getLogger(__name__)

_latest_analysis: Dict[str, Any] = {}
_analysis_time: float = 0.0
_cache_lock = threading.Lock()

SYSTEM_PROMPT_EXTRA = """
你正在分析的是过去 24 小时内采集的期货相关新闻。请聚焦于：
- 整体市场情绪和热点方向
- 主要品种的多空力量对比
- 跨品种、跨板块的联动效应
- 潜在的政策、宏观事件影响
- 短期趋势判断和风险提示
"""


def _load_prompt_template() -> tuple:
    config_dir = Path(__file__).parent.parent.parent / "config"
    prompt_path = config_dir / "ai_analysis_prompt.txt"

    if not prompt_path.exists():
        logger.warning("AI 分析提示词文件不存在: %s", prompt_path)
        return "", ""

    content = prompt_path.read_text(encoding="utf-8")

    system_prompt = ""
    user_prompt = ""

    if "[system]" in content and "[user]" in content:
        parts = content.split("[user]")
        system_part = parts[0]
        user_part = parts[1] if len(parts) > 1 else ""

        if "[system]" in system_part:
            system_prompt = system_part.split("[system]")[1].strip()

        user_prompt = user_part.strip()

    return system_prompt, user_prompt


def _build_user_prompt(
    news_data: List[Dict],
    stats: Dict[str, Any],
    symbol_stats: Dict[str, Any],
) -> str:
    """构建态势解读的用户提示词。"""
    lines = []

    lines.append("## 24 小时新闻态势概览")
    lines.append(f"- 新闻总数：{stats.get('overview', {}).get('total_articles', 0)} 条")
    lines.append(f"- 已 AI 解读：{stats.get('overview', {}).get('interpreted_count', 0)} 条")
    lines.append("")

    # 来源分布
    source_stats = stats.get("source_stats", [])
    if source_stats:
        lines.append("## 新闻来源分布")
        for item in source_stats[:10]:
            lines.append(f"- {item.get('source_name', '')}：{item.get('count', 0)} 条")
        lines.append("")

    # 品种多空
    direction_stats = symbol_stats.get("direction_stats", [])
    if direction_stats:
        lines.append("## 品种多空分布")
        for item in direction_stats:
            lines.append(f"- {item.get('direction', '')}：{item.get('count', 0)} 次")
        lines.append("")

    top_symbols = symbol_stats.get("top_symbols", [])
    if top_symbols:
        lines.append("## 热门品种 TOP 10")
        for item in top_symbols[:10]:
            lines.append(
                f"- {item.get('symbol_name', '')}({item.get('symbol_code', '')})："
                f"提及 {item.get('mention_count', 0)} 次，"
                f"平均强度 {item.get('avg_strength', 0)}"
            )
        lines.append("")

    # 新闻标题列表（最多 60 条）
    if news_data:
        lines.append("## 24 小时内新闻列表（最新在前）")
        for article in news_data[:60]:
            source = article.get("source_name", "")
            title = article.get("title", "")
            ai_summary = article.get("ai_one_line_summary", "")
            keywords = article.get("keywords", [])
            kw_str = "、".join(keywords[:5]) if keywords else ""
            line = f"- [{source}] {title}"
            if ai_summary:
                line += f"（AI 摘要：{ai_summary}）"
            if kw_str:
                line += f" [关键词：{kw_str}]"
            lines.append(line)

    return "\n".join(lines)


def _parse_response(response: str) -> Dict[str, Any]:
    text = (response or "").strip()
    if not text:
        return {}

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        return {}


def run_situation_analysis() -> Dict[str, Any]:
    """执行一次态势分析，更新全局缓存。"""
    global _latest_analysis, _analysis_time

    try:
        from trendradar.storage import news_repository
        from trendradar.storage import ai_model_repository
        from trendradar.core import load_config
    except Exception as e:
        logger.warning("态势分析：导入模块失败: %s", e)
        return {"success": False, "error": str(e)}

    # 获取数据
    try:
        news_data = news_repository.get_articles_for_situation_analysis(limit=80)
        stats = news_repository.get_situation_stats()
        symbol_stats = news_repository.get_situation_symbol_stats()
    except Exception as e:
        logger.warning("态势分析：数据查询失败: %s", e)
        return {"success": False, "error": str(e)}

    total = stats.get("overview", {}).get("total_articles", 0)
    if total == 0:
        logger.info("态势分析：24 小时内无新闻，跳过")
        return {"success": False, "error": "24 小时内无新闻"}

    # 获取 AI 配置（优先使用推理模型）
    try:
        runtime_configs = ai_model_repository.build_runtime_ai_configs()
        ai_config = runtime_configs.get("reasoning", {})
        if not ai_config.get("MODEL"):
            ai_config = runtime_configs.get("shared", {})
    except Exception:
        config = load_config()
        ai_config = config.get("AI", {})

    if not ai_config.get("MODEL") or not ai_config.get("API_KEY"):
        logger.info("态势分析：未配置 AI 模型，跳过")
        return {"success": False, "error": "未配置 AI 模型"}

    # 加载提示词
    system_prompt, user_template = _load_prompt_template()
    if not user_template:
        return {"success": False, "error": "提示词加载失败"}

    system_prompt = system_prompt + "\n\n" + SYSTEM_PROMPT_EXTRA.strip()
    user_prompt = _build_user_prompt(news_data, stats, symbol_stats)

    # 创建客户端
    client = AIClient(
        {
            **ai_config,
            "TEMPERATURE": 0.6,
            "MAX_TOKENS": 3000,
            "TIMEOUT": 180,
            "NUM_RETRIES": 1,
        }
    )

    valid, error = client.validate_config()
    if not valid:
        logger.warning("态势分析：模型不可用: %s", error)
        return {"success": False, "error": f"模型不可用: {error}"}

    logger.info("态势分析开始：%d 条新闻，模型 %s", total, ai_config.get("MODEL", ""))

    try:
        response = client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            max_tokens=3000,
        )
    except Exception as e:
        logger.warning("态势分析：AI 调用失败: %s", e)
        return {"success": False, "error": str(e)}

    parsed = _parse_response(response)

    result = {
        "core_trends": parsed.get("core_trends", ""),
        "sentiment_controversy": parsed.get("sentiment_controversy", ""),
        "signals": parsed.get("signals", ""),
        "rss_insights": parsed.get("rss_insights", ""),
        "outlook_strategy": parsed.get("outlook_strategy", ""),
        "success": True,
        "total_articles": total,
        "analyzed_at": time.time(),
    }

    with _cache_lock:
        _latest_analysis = result
        _analysis_time = time.time()

    logger.info("态势分析完成：%d 条新闻已分析", total)
    return result


def get_latest_analysis() -> Dict[str, Any]:
    """获取最新的态势分析缓存。"""
    with _cache_lock:
        if not _latest_analysis:
            return {"success": False, "error": "暂无分析结果", "analyzed_at": 0}
        return dict(_latest_analysis)
