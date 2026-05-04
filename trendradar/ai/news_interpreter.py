# coding=utf-8
"""
AI 新闻解读模块。

职责：
- 使用“快速模型”对新闻进行期货视角解读
- 结果落到新闻表和新闻-品种关联表
- 采用单线程后台 worker，避免并发打 AI 接口
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Any, Dict, List

from trendradar.ai.client import AIClient
from trendradar.core import load_config
from trendradar.storage import futures_symbol_repository
from trendradar.storage import news_repository

logger = logging.getLogger(__name__)

_task_queue: "queue.Queue[int]" = queue.Queue()
_queue_seen: set[int] = set()
_queue_lock = threading.Lock()
_worker_started = False
_worker_lock = threading.Lock()

DEFAULT_SYMBOLS: List[Dict[str, str]] = [
    {"name": "黄金", "code": "AU", "sector": "贵金属", "exchange": "上海期货交易所"},
    {"name": "白银", "code": "AG", "sector": "贵金属", "exchange": "上海期货交易所"},
    {"name": "铜", "code": "CU", "sector": "有色", "exchange": "上海期货交易所"},
    {"name": "铝", "code": "AL", "sector": "有色", "exchange": "上海期货交易所"},
    {"name": "锌", "code": "ZN", "sector": "有色", "exchange": "上海期货交易所"},
    {"name": "镍", "code": "NI", "sector": "有色", "exchange": "上海期货交易所"},
    {"name": "氧化铝", "code": "AO", "sector": "有色", "exchange": "上海期货交易所"},
    {"name": "工业硅", "code": "SI", "sector": "有色", "exchange": "广州期货交易所"},
    {"name": "碳酸锂", "code": "LC", "sector": "有色", "exchange": "广州期货交易所"},
    {"name": "原油", "code": "SC", "sector": "化工", "exchange": "上海国际能源交易中心"},
    {"name": "燃料油", "code": "FU", "sector": "化工", "exchange": "上海期货交易所"},
    {"name": "低硫燃料油", "code": "LU", "sector": "化工", "exchange": "上海国际能源交易中心"},
    {"name": "沥青", "code": "BU", "sector": "化工", "exchange": "上海期货交易所"},
    {"name": "天然橡胶", "code": "RU", "sector": "化工", "exchange": "上海期货交易所"},
    {"name": "甲醇", "code": "MA", "sector": "化工", "exchange": "郑州商品交易所"},
    {"name": "尿素", "code": "UR", "sector": "化工", "exchange": "郑州商品交易所"},
    {"name": "对二甲苯", "code": "PX", "sector": "化工", "exchange": "郑州商品交易所"},
    {"name": "精对苯二甲酸", "code": "TA", "sector": "化工", "exchange": "郑州商品交易所"},
    {"name": "线型低密度聚乙烯", "code": "L", "sector": "化工", "exchange": "大连商品交易所"},
    {"name": "聚氯乙烯", "code": "V", "sector": "化工", "exchange": "大连商品交易所"},
    {"name": "聚丙烯", "code": "PP", "sector": "化工", "exchange": "大连商品交易所"},
    {"name": "乙二醇", "code": "EG", "sector": "化工", "exchange": "大连商品交易所"},
    {"name": "苯乙烯", "code": "EB", "sector": "化工", "exchange": "大连商品交易所"},
    {"name": "焦煤", "code": "JM", "sector": "煤炭", "exchange": "大连商品交易所"},
    {"name": "焦炭", "code": "J", "sector": "煤炭", "exchange": "大连商品交易所"},
    {"name": "铁矿石", "code": "I", "sector": "黑色", "exchange": "大连商品交易所"},
    {"name": "螺纹钢", "code": "RB", "sector": "黑色", "exchange": "上海期货交易所"},
    {"name": "热轧卷板", "code": "HC", "sector": "黑色", "exchange": "上海期货交易所"},
    {"name": "玻璃", "code": "FG", "sector": "建材", "exchange": "郑州商品交易所"},
    {"name": "纯碱", "code": "SA", "sector": "建材", "exchange": "郑州商品交易所"},
    {"name": "豆粕", "code": "M", "sector": "农产品", "exchange": "大连商品交易所"},
    {"name": "豆油", "code": "Y", "sector": "农产品", "exchange": "大连商品交易所"},
    {"name": "棕榈油", "code": "P", "sector": "农产品", "exchange": "大连商品交易所"},
    {"name": "玉米", "code": "C", "sector": "农产品", "exchange": "大连商品交易所"},
    {"name": "生猪", "code": "LH", "sector": "农产品", "exchange": "大连商品交易所"},
    {"name": "棉花", "code": "CF", "sector": "农产品", "exchange": "郑州商品交易所"},
    {"name": "白糖", "code": "SR", "sector": "农产品", "exchange": "郑州商品交易所"},
    {"name": "沪深300股指期货", "code": "IF", "sector": "金融", "exchange": "中国金融期货交易所"},
    {"name": "中证500股指期货", "code": "IC", "sector": "金融", "exchange": "中国金融期货交易所"},
    {"name": "中证1000股指期货", "code": "IM", "sector": "金融", "exchange": "中国金融期货交易所"},
    {"name": "10年期国债期货", "code": "T", "sector": "金融", "exchange": "中国金融期货交易所"},
]

SYSTEM_PROMPT = """
你是一名资深中国期货分析师，擅长从宏观、产业链、供需、政策、情绪和资金风格角度，
判断一条新闻对国内期货品种的影响。

你的输出必须严格是 JSON，不要输出任何多余文字。
"""

USER_PROMPT_TEMPLATE = """
请基于下面这条新闻，做期货角度的快速解读：

新闻标题：
{title}

新闻摘要：
{summary}

新闻正文：
{content}

可选期货品种清单（名称|代码|板块|交易所）：
{symbols}

请完成以下任务：
1. 找出与这条新闻最相关的期货品种，最多返回 3 个；
2. 对每个品种判断方向：看多、看空、中性；
3. 对每个品种判断影响强度：1 到 5 的整数，5 为最强；
4. 生成一句期货分析师视角的一句话解读，不超过 50 个汉字。

输出 JSON 格式如下：
{{
  "one_line_summary": "不超过50字的一句话解读",
  "symbols": [
    {{
      "name": "品种名称",
      "code": "品种代码",
      "direction": "看多/看空/中性",
      "strength": 1
    }}
  ]
}}

注意：
- 只允许从提供的品种清单中选择；
- 如果新闻和期货相关性弱，可以返回空数组；
- strength 必须是 1~5 的整数；
- direction 只能是：看多、看空、中性。
"""


def enqueue_article_interpretation(article_ids: List[int]) -> None:
    _ensure_worker_started()
    queued = 0
    with _queue_lock:
        for article_id in article_ids:
            if not article_id or article_id in _queue_seen:
                continue
            _queue_seen.add(article_id)
            _task_queue.put(article_id)
            queued += 1
    if queued:
        logger.info("AI 新闻解读任务已入队: %s 条", queued)


def _ensure_worker_started() -> None:
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(
            target=_worker_loop,
            name="news-ai-interpreter",
            daemon=True,
        )
        thread.start()
        _worker_started = True
        logger.info("AI 新闻解读 worker 已启动")


def _worker_loop() -> None:
    while True:
        article_id = _task_queue.get()
        try:
            _process_single_article(article_id)
        except Exception as exc:
            logger.warning("AI 新闻解读失败: article_id=%s error=%s", article_id, exc)
        finally:
            with _queue_lock:
                _queue_seen.discard(article_id)
            _task_queue.task_done()


def _process_single_article(article_id: int) -> None:
    article = news_repository.get_article_for_ai_interpretation(article_id)
    if not article:
        return

    status = article.get("ai_interpret_status", "")
    if status == "已解读":
        return

    config = load_config()
    ai_config = (config.get("AI_FAST", {}) or {}) if (config.get("AI_FAST", {}) or {}).get("MODEL") else config.get("AI", {})
    if not ai_config.get("MODEL") or not ai_config.get("API_KEY"):
        logger.info("AI 新闻解读跳过: 未配置快速模型或通用 AI 模型")
        return

    symbols = futures_symbol_repository.list_symbols() or DEFAULT_SYMBOLS
    if not symbols:
        logger.info("AI 新闻解读跳过: 未配置期货品种")
        return

    client = AIClient(
        {
            **ai_config,
            "TEMPERATURE": 0.2,
            "MAX_TOKENS": 600,
            "TIMEOUT": 45,
            "NUM_RETRIES": 1,
        }
    )
    valid, error = client.validate_config()
    if not valid:
        logger.info("AI 新闻解读跳过，快速模型不可用: %s", error)
        return

    logger.info("AI 新闻解读开始: article_id=%s model=%s", article_id, ai_config.get("MODEL", ""))
    news_repository.mark_article_ai_interpret_status(article_id, "解读中")
    prompt = USER_PROMPT_TEMPLATE.format(
        title=article.get("title", "") or "",
        summary=article.get("summary", "") or "",
        content=article.get("content", "") or "",
        symbols=_serialize_symbols(symbols),
    )
    response = client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": prompt.strip()},
        ],
        temperature=0.2,
        max_tokens=600,
    )

    parsed = _parse_response(response)
    one_line_summary = _normalize_one_line_summary(parsed.get("one_line_summary", ""))
    matched_symbols = _normalize_symbol_matches(parsed.get("symbols", []), symbols)

    news_repository.save_article_ai_interpretation(
        article_id=article_id,
        one_line_summary=one_line_summary,
        raw_result=response,
        symbol_matches=matched_symbols,
    )
    logger.info("AI 新闻解读完成: article_id=%s symbols=%s", article_id, len(matched_symbols))


def enqueue_pending_interpretations(limit: int = 50) -> int:
    article_ids = news_repository.get_pending_ai_interpretation_article_ids(limit=limit)
    enqueue_article_interpretation(article_ids)
    return len(article_ids)


def _serialize_symbols(symbols: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"- {item.get('name', '')}|{item.get('code', '')}|{item.get('sector', '')}|{item.get('exchange', '')}"
        for item in symbols
    )


def _parse_response(response: str) -> Dict[str, Any]:
    text = (response or "").strip()
    if not text:
        return {"one_line_summary": "", "symbols": []}

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
        raise


def _normalize_one_line_summary(summary: str) -> str:
    text = str(summary or "").strip()
    if len(text) <= 50:
        return text
    return text[:50].rstrip()


def _normalize_symbol_matches(raw_symbols: Any, all_symbols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    symbol_map = {
        (item.get("name", "") or "").strip(): item
        for item in all_symbols
    }
    code_map = {
        (item.get("code", "") or "").strip().upper(): item
        for item in all_symbols
    }

    normalized: List[Dict[str, Any]] = []
    for raw_item in list(raw_symbols or [])[:3]:
        if not isinstance(raw_item, dict):
            continue
        raw_name = str(raw_item.get("name", "") or "").strip()
        raw_code = str(raw_item.get("code", "") or "").strip().upper()
        matched = symbol_map.get(raw_name) or code_map.get(raw_code)
        if not matched:
            continue

        direction = str(raw_item.get("direction", "") or "").strip()
        if direction not in ("看多", "看空", "中性"):
            direction = "中性"

        try:
            strength = int(raw_item.get("strength", 3))
        except Exception:
            strength = 3
        strength = min(5, max(1, strength))

        item = {
            "symbol_name": matched.get("name", "") or "",
            "symbol_code": matched.get("code", "") or "",
            "direction": direction,
            "strength": strength,
        }
        if item not in normalized:
            normalized.append(item)
    normalized.sort(key=lambda item: (-item["strength"], item["symbol_code"]))
    return normalized
