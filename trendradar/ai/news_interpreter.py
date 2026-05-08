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
import os
import queue
import re
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
_workers_started = False
_worker_lock = threading.Lock()

INTERPRET_WORKERS = max(1, min(8, int(os.environ.get("NEWS_AI_INTERPRET_WORKERS", "3") or 3)))
AI_CONCURRENCY = max(1, min(INTERPRET_WORKERS, int(os.environ.get("NEWS_AI_INTERPRET_CONCURRENCY", "2") or 2)))
INPUT_CONTENT_CHARS = max(0, int(os.environ.get("NEWS_AI_INTERPRET_CONTENT_CHARS", "800") or 800))
INPUT_SUMMARY_CHARS = max(0, int(os.environ.get("NEWS_AI_INTERPRET_SUMMARY_CHARS", "300") or 300))
OUTPUT_MAX_TOKENS = max(80, int(os.environ.get("NEWS_AI_INTERPRET_MAX_TOKENS", "180") or 180))
AI_TIMEOUT_SECONDS = max(5, int(os.environ.get("NEWS_AI_INTERPRET_TIMEOUT", "12") or 12))
AI_NUM_RETRIES = max(0, int(os.environ.get("NEWS_AI_INTERPRET_RETRIES", "0") or 0))
AI_TEMPERATURE = float(os.environ.get("NEWS_AI_INTERPRET_TEMPERATURE", "0.1") or 0.1)
_ai_semaphore = threading.BoundedSemaphore(AI_CONCURRENCY)

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
你是期货新闻快读助手。只输出 JSON，不要解释。
"""

USER_PROMPT_TEMPLATE = """
标题:
{title}

摘要:
{summary}

正文片段:
{content}

候选品种(名称|代码):
{symbols}

做快速粗略解读，最多选 3 个品种，弱相关则 symbols=[]。
每个品种必须同时返回候选清单里的 name 和 code，不确定就不要返回该品种。
方向只能是 看多/看空/中性，strength 为 1-5。
一句话不超过 50 个汉字。
返回:
{{
  "one_line_summary": "",
  "symbols": [
    {{"name": "", "code": "", "direction": "看多", "strength": 3}}
  ]
}}
"""


def enqueue_article_interpretation(article_ids: List[int]) -> None:
    if not _is_auto_interpret_enabled():
        logger.info("AI 新闻解读自动入队已跳过: 自动解读开关未开启")
        return
    enqueue_article_interpretation_force(article_ids)


def enqueue_article_interpretation_force(article_ids: List[int]) -> None:
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
    global _workers_started
    if _workers_started:
        return
    with _worker_lock:
        if _workers_started:
            return
        for index in range(INTERPRET_WORKERS):
            thread = threading.Thread(
                target=_worker_loop,
                name=f"news-ai-interpreter-{index + 1}",
                daemon=True,
            )
            thread.start()
        _workers_started = True
        logger.info(
            "AI 新闻解读 worker 已启动: workers=%s ai_concurrency=%s",
            INTERPRET_WORKERS,
            AI_CONCURRENCY,
        )


def _worker_loop() -> None:
    while True:
        article_id = _task_queue.get()
        try:
            _process_single_article(article_id)
        except Exception as exc:
            logger.warning("AI 新闻解读失败: article_id=%s error=%s", article_id, exc)
            try:
                news_repository.mark_article_ai_interpret_status(article_id, news_repository.AI_INTERPRET_STATUS_FAILED)
            except Exception:
                pass
        finally:
            with _queue_lock:
                _queue_seen.discard(article_id)
            _task_queue.task_done()


def _process_single_article(article_id: int) -> Dict[str, Any]:
    article = news_repository.get_article_for_ai_interpretation(article_id)
    if not article:
        return {"success": False, "reason": "文章不存在"}

    status = article.get("ai_interpret_status", "")
    if status == "已解读":
        return {"success": False, "reason": "已解读，无需重复处理"}
    if status == "解读中":
        return {"success": False, "reason": "正在解读中，请稍后再试"}

    cache_key = _build_interpret_cache_key(article)
    cached = news_repository.get_ai_interpret_cache(cache_key)
    if cached:
        news_repository.save_article_ai_interpretation(
            article_id=article_id,
            one_line_summary=cached.get("one_line_summary", ""),
            raw_result=cached.get("raw_result", ""),
            symbol_matches=cached.get("symbols", []),
        )
        logger.info("AI 新闻解读命中缓存: article_id=%s", article_id)
        return {
            "success": True,
            "one_line_summary": cached.get("one_line_summary", ""),
            "symbols": cached.get("symbols", []),
            "cached": True,
        }

    config = load_config()
    ai_config = config.get("AI_FAST", {}) or {}
    if not ai_config.get("MODEL") or not ai_config.get("API_KEY"):
        logger.info("AI 新闻解读跳过: 未配置快速模型")
        return {"success": False, "reason": "未配置快速 AI 模型"}

    symbols = futures_symbol_repository.list_symbols() or DEFAULT_SYMBOLS
    if not symbols:
        logger.info("AI 新闻解读跳过: 未配置期货品种")
        return {"success": False, "reason": "未配置期货品种"}

    client = AIClient(
        {
            **ai_config,
            "TEMPERATURE": AI_TEMPERATURE,
            "MAX_TOKENS": OUTPUT_MAX_TOKENS,
            "TIMEOUT": AI_TIMEOUT_SECONDS,
            "NUM_RETRIES": AI_NUM_RETRIES,
        }
    )
    valid, error = client.validate_config()
    if not valid:
        logger.info("AI 新闻解读跳过，快速模型不可用: %s", error)
        return {"success": False, "reason": f"模型不可用: {error}"}

    logger.info("AI 新闻解读开始: article_id=%s model=%s", article_id, ai_config.get("MODEL", ""))
    news_repository.mark_article_ai_interpret_status(article_id, "解读中")
    prompt_article = _build_prompt_article(article)
    prompt = USER_PROMPT_TEMPLATE.format(
        title=prompt_article.get("title", ""),
        summary=prompt_article.get("summary", ""),
        content=prompt_article.get("content", ""),
        symbols=_serialize_symbols(symbols),
    )
    try:
        with _ai_semaphore:
            response = client.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT.strip()},
                    {"role": "user", "content": prompt.strip()},
                ],
                temperature=AI_TEMPERATURE,
                max_tokens=OUTPUT_MAX_TOKENS,
                timeout=AI_TIMEOUT_SECONDS,
                num_retries=AI_NUM_RETRIES,
            )
    except Exception:
        news_repository.mark_article_ai_interpret_status(article_id, news_repository.AI_INTERPRET_STATUS_FAILED)
        raise

    parsed = _parse_response(response)
    one_line_summary = _normalize_one_line_summary(parsed.get("one_line_summary", ""))
    matched_symbols = _normalize_symbol_matches(parsed.get("symbols", []), symbols)
    news_repository.save_ai_interpret_cache(
        cache_key=cache_key,
        one_line_summary=one_line_summary,
        raw_result=response,
        symbol_matches=matched_symbols,
    )

    news_repository.save_article_ai_interpretation(
        article_id=article_id,
        one_line_summary=one_line_summary,
        raw_result=response,
        symbol_matches=matched_symbols,
    )
    logger.info("AI 新闻解读完成: article_id=%s symbols=%s", article_id, len(matched_symbols))
    return {
        "success": True,
        "one_line_summary": one_line_summary,
        "symbols": matched_symbols,
    }


def interpret_article_now(article_id: int) -> Dict[str, Any]:
    """立即解读单篇文章（同步，不走队列），供手动触发使用。"""
    return _process_single_article(article_id)


def enqueue_pending_interpretations(limit: int = 50) -> int:
    if not _is_auto_interpret_enabled():
        logger.info("AI 新闻解读补跑任务已跳过: 自动解读开关未开启")
        return 0
    article_ids = news_repository.get_pending_ai_interpretation_article_ids(limit=limit)
    enqueue_article_interpretation_force(article_ids)
    return len(article_ids)


def _serialize_symbols(symbols: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"- {item.get('name', '')}|{item.get('code', '')}"
        for item in symbols
    )


def _build_prompt_article(article: Dict[str, Any]) -> Dict[str, str]:
    return {
        "title": _compact_text(article.get("title", ""), 160),
        "summary": _compact_text(article.get("summary", ""), INPUT_SUMMARY_CHARS),
        "content": _compact_text(article.get("content", ""), INPUT_CONTENT_CHARS),
    }


def _compact_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _build_interpret_cache_key(article: Dict[str, Any]) -> str:
    import hashlib

    prompt_article = _build_prompt_article(article)
    normalized = "\n".join(
        [
            prompt_article.get("title", "").lower(),
            prompt_article.get("summary", "").lower(),
            prompt_article.get("content", "").lower(),
        ]
    )
    normalized = re.sub(r"\s+", "", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _sanitize_json_strings(text: str) -> str:
    """Escape unescaped control characters inside JSON string values.

    LLMs occasionally emit raw newlines, tabs, or carriage returns inside
    JSON string values, which breaks the parser.  This scans character by
    character so it correctly handles backslash-escaped quotes inside strings.
    """
    result: list[str] = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            result.append(ch)
            continue
        if ch == "\\":
            escape_next = True
            result.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == "\n":
                result.append("\\n")
                continue
            if ch == "\r":
                result.append("\\r")
                continue
            if ch == "\t":
                result.append("\\t")
                continue
            if ord(ch) < 0x20:
                result.append(f"\\u{ord(ch):04x}")
                continue
        result.append(ch)
    return "".join(result)


def _parse_response(response: str) -> Dict[str, Any]:
    text = (response or "").strip()
    if not text:
        return {"one_line_summary": "", "symbols": []}

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    text = _sanitize_json_strings(text)

    try:
        return json.loads(text, strict=False)
    except Exception:
        logger.warning(
            "AI 新闻解读 JSON 解析失败，原始响应(前500字符): %s",
            text[:500],
        )
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
        if raw_name:
            matched = symbol_map.get(raw_name)
            if not matched:
                continue
            matched_code = str(matched.get("code", "") or "").strip().upper()
            if raw_code and matched_code and raw_code != matched_code:
                continue
        else:
            matched = code_map.get(raw_code)
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


def _is_auto_interpret_enabled() -> bool:
    try:
        from trendradar.storage import ai_model_repository
        settings = ai_model_repository.get_settings()
        return bool(settings.get("auto_interpret_enabled", False))
    except Exception:
        return False
