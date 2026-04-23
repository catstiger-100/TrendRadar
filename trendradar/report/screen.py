# coding=utf-8
"""
实时大屏渲染模块

基于单文件 HTML 模板生成 screen.html，并注入真实的 TrendRadar 数据。
"""

from __future__ import annotations

import base64
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from trendradar.ai.formatter import _format_list_content
from trendradar.core.analyzer import calculate_news_weight
from trendradar.report.helpers import clean_title, html_escape


SCREEN_TEMPLATE_PATH = Path(__file__).resolve().parent / "screen_template.html"
DEFAULT_FREQUENCY_FILE = "config/frequency_words.txt"
TONE_CLASSES = ["tone-cyan", "tone-purple", "tone-green", "tone-red", "tone-amber"]


def _resolve_frequency_file(frequency_file: Optional[str] = None) -> str:
    if frequency_file:
        return frequency_file
    return os.environ.get("FREQUENCY_WORDS_PATH", DEFAULT_FREQUENCY_FILE)


def _build_date_label(now: datetime) -> str:
    weekday_map = {
        0: "星期一",
        1: "星期二",
        2: "星期三",
        3: "星期四",
        4: "星期五",
        5: "星期六",
        6: "星期日",
    }
    return f"{now.year}年{now.month}月{now.day}日 {weekday_map[now.weekday()]}"


def _build_mode_label(mode: str) -> str:
    return {
        "daily": "当日汇总",
        "current": "当前榜单",
        "incremental": "增量更新",
    }.get(mode, mode)


def _load_logo_data_uri() -> str:
    candidates = [
        Path("output/static/logo.png"),
        Path("output/static/images/logo.png"),
    ]
    for path in candidates:
        if path.exists():
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
    return "./static/logo.png"


def _parse_frequency_modules(
    frequency_file: Optional[str] = None,
) -> Tuple[List[str], Dict[str, str]]:
    path = Path(_resolve_frequency_file(frequency_file))
    if not path.exists():
        return [], {}

    ordered_categories: List[str] = []
    category_to_module: Dict[str, str] = {}
    current_module = "未分类"

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#"):
            text = line.lstrip("#").strip()
            if text and "═" not in text and "─" not in text:
                current_module = text
            continue

        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            if section_name.upper() in ("GLOBAL_FILTER", "WORD_GROUPS"):
                continue
            ordered_categories.append(section_name)
            category_to_module[section_name] = current_module

    return ordered_categories, category_to_module


def _extract_lead_tag(text: str) -> str:
    if not text:
        return "「趋势聚焦」"

    tag_match = re.search(r"全网霸屏|高位共振|风险脉冲|主线升温|强势发酵", text)
    if tag_match:
        return f"「{tag_match.group(0)}」"
    return "「趋势聚焦」"


def _ai_html(text: str) -> str:
    if not text:
        return "暂无分析结果"
    formatted = _format_list_content(text)
    return html_escape(formatted).replace("\n", "<br>")


def _build_ai_panels(ai_analysis: Optional[Any]) -> List[Dict[str, str]]:
    if not ai_analysis or not getattr(ai_analysis, "success", False):
        return [
            {
                "title": "核心热点态势",
                "badge": "AI 未启用",
                "html": "当前运行未生成 AI 热点分析。",
            }
        ]

    core_trends = getattr(ai_analysis, "core_trends", "") or ""
    sentiment = getattr(ai_analysis, "sentiment_controversy", "") or ""
    signals = getattr(ai_analysis, "signals", "") or ""
    outlook = getattr(ai_analysis, "outlook_strategy", "") or ""
    standalone = getattr(ai_analysis, "standalone_summaries", {}) or {}

    panels = [
        {
            "title": "核心热点态势",
            "badge": _extract_lead_tag(core_trends),
            "html": _ai_html(core_trends),
        },
        {
            "title": "舆论风向争议",
            "badge": "",
            "html": _ai_html(sentiment),
        },
        {
            "title": "异动与弱信号",
            "badge": "",
            "html": _ai_html(signals),
        },
        {
            "title": "研判策略建议",
            "badge": "",
            "html": _ai_html(outlook),
        },
    ]

    if standalone:
        standalone_html = "<br><br>".join(
            f"<strong>{html_escape(name)}</strong><br>{_ai_html(summary)}"
            for name, summary in standalone.items()
            if summary
        )
        if standalone_html:
            panels.append(
                {
                    "title": "独立源点速览",
                    "badge": "",
                    "html": standalone_html,
                }
            )

    return [panel for panel in panels if panel["html"]]


def _score_title(
    item: Dict[str, Any],
    rank_threshold: int,
    weight_config: Dict[str, float],
) -> float:
    return calculate_news_weight(item, rank_threshold, weight_config)


def _build_news_payload(
    report_data: Dict[str, Any],
    ordered_categories: List[str],
    category_to_module: Dict[str, str],
    rank_threshold: int,
    weight_config: Dict[str, float],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    stats = report_data.get("stats", []) or []

    stat_map = {stat.get("word", ""): stat for stat in stats}
    categories_payload: List[Dict[str, Any]] = []
    for category_name in ordered_categories:
        stat = stat_map.get(category_name)
        if stat and stat.get("count", 0) > 0:
            categories_payload.append(
                {
                    "name": category_name,
                    "count": stat.get("count", 0),
                    "module": category_to_module.get(category_name, "未分类"),
                }
            )

    for stat in stats:
        name = stat.get("word", "")
        if name and name not in {item["name"] for item in categories_payload}:
            categories_payload.append(
                {
                    "name": name,
                    "count": stat.get("count", 0),
                    "module": category_to_module.get(name, "未分类"),
                }
            )

    news_items: List[Dict[str, Any]] = []
    source_seen = set()

    for stat in categories_payload:
        category_name = stat["name"]
        titles = (stat_map.get(category_name) or {}).get("titles", [])
        for index, title_data in enumerate(titles, 1):
            item = {
                "id": f"{category_name}-{index}",
                "title": clean_title(title_data.get("title", "")),
                "url": title_data.get("mobile_url") or title_data.get("url") or "",
                "source_name": clean_title(title_data.get("source_name", "未知来源")),
                "time_display": clean_title(title_data.get("time_display", "")),
                "ranks": title_data.get("ranks", []) or [99],
                "is_new": bool(title_data.get("is_new", False)),
                "count": int(title_data.get("count", 1) or 1),
                "category": category_name,
                "module": stat["module"],
            }
            item["heat_score"] = round(
                _score_title(item, rank_threshold, weight_config),
                2,
            )
            item["summary"] = (
                f"命中「{html_escape(category_name)}」模块，综合热度 {item['heat_score']:.1f}，"
                f"累计出现 {item['count']} 次。"
            )
            if item["title"] and (item["category"], item["title"], item["source_name"]) not in source_seen:
                news_items.append(item)
                source_seen.add((item["category"], item["title"], item["source_name"]))

    news_items.sort(
        key=lambda x: (
            -x["heat_score"],
            min(x["ranks"]) if x["ranks"] else 999,
            -x["count"],
        )
    )

    categories_payload.sort(key=lambda x: (-x["count"], ordered_categories.index(x["name"]) if x["name"] in ordered_categories else 999))
    return categories_payload, news_items


def _build_keywords_payload(
    categories_payload: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    module_order: Dict[str, int] = {}
    keywords = []

    for item in categories_payload:
        module_name = item.get("module", "未分类")
        if module_name not in module_order:
            module_order[module_name] = len(module_order)
        tone_class = TONE_CLASSES[module_order[module_name] % len(TONE_CLASSES)]
        keywords.append(
            {
                "name": item["name"],
                "category": item["name"],
                "module": module_name,
                "count": item["count"],
                "toneClass": tone_class,
            }
        )

    keywords.sort(key=lambda x: (-x["count"], x["name"]))
    return keywords


def _build_source_distribution(news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counter: Dict[str, int] = defaultdict(int)
    for item in news_items:
        counter[item["source_name"]] += 1
    return [
        {"name": name, "value": count}
        for name, count in sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    ]


def _build_rss_payload(rss_items: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    items = []
    for index, item in enumerate(rss_items or [], 1):
        if index > 6:
            break
        items.append(
            {
                "title": clean_title(item.get("title", "")),
                "url": item.get("url", ""),
                "source_name": clean_title(item.get("source_name", "RSS")),
                "time_display": clean_title(item.get("time_display", "")),
                "is_new": bool(item.get("is_new", False)),
            }
        )
    return {
        "title": "RSS 新增更新",
        "subtitle": "订阅源最新动态",
        "items": items,
    }


def build_screen_payload(
    report_data: Dict[str, Any],
    total_titles: int,
    mode: str = "daily",
    *,
    get_time_func: Optional[Callable[[], datetime]] = None,
    rss_items: Optional[List[Dict[str, Any]]] = None,
    ai_analysis: Optional[Any] = None,
    frequency_file: Optional[str] = None,
    rank_threshold: int = 3,
    weight_config: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    now = get_time_func() if get_time_func else datetime.now()
    ordered_categories, category_to_module = _parse_frequency_modules(frequency_file)
    effective_weights = weight_config or {
        "RANK_WEIGHT": 0.5,
        "FREQUENCY_WEIGHT": 0.3,
        "HOTNESS_WEIGHT": 0.2,
    }

    categories_payload, news_items = _build_news_payload(
        report_data,
        ordered_categories,
        category_to_module,
        rank_threshold,
        effective_weights,
    )
    source_distribution = _build_source_distribution(news_items)
    keywords = _build_keywords_payload(categories_payload)
    hot_news_count = len(news_items)

    return {
        "meta": {
            "title": "恒银智能舆情监控",
            "subtitle": f"刷新时间：{now.strftime('%m/%d %H:%M')}",
            "refreshTime": now.strftime("%m/%d %H:%M"),
            "reportType": _build_mode_label(mode),
            "updateTime": now.strftime("%m-%d %H:%M"),
            "dateLabel": _build_date_label(now),
        },
        "stats": {
            "newsTotal": total_titles,
            "hotNews": hot_news_count,
            "reportType": _build_mode_label(mode),
            "updateTime": now.strftime("%m-%d %H:%M"),
        },
        "categories": categories_payload,
        "news": news_items,
        "ai_panels": _build_ai_panels(ai_analysis),
        "rss_updates": _build_rss_payload(rss_items),
        "source_distribution": source_distribution,
        "keywords": keywords,
    }


def _build_runtime_block() -> str:
    return """
    const FALLBACK_PAYLOAD = {
      meta: {
        title: '恒银智能舆情监控',
        subtitle: '刷新时间：--/-- --:--',
        refreshTime: '--/-- --:--',
        reportType: '当前榜单',
        updateTime: '-- --:--',
        dateLabel: '----年--月--日 星期-',
      },
      stats: {
        newsTotal: 0,
        hotNews: 0,
        reportType: '当前榜单',
        updateTime: '-- --:--',
      },
      categories: [],
      news: [],
      ai_panels: [],
      rss_updates: {
        title: 'RSS 新增更新',
        subtitle: '暂无新增订阅动态',
        items: [],
      },
      source_distribution: [],
      keywords: [],
    }

    const rawScreenPayload = globalThis.__TRENDRADAR_SCREEN__ || FALLBACK_PAYLOAD
    const rawMockApi = rawScreenPayload

    function pad(num) {
      return String(num).padStart(2, '0')
    }

    function formatRankText(ranks) {
      const values = Array.isArray(ranks) && ranks.length ? ranks : [99]
      const min = Math.min(...values)
      const max = Math.max(...values)
      return min === max ? `${min}` : `${min}-${max}`
    }

    function sortByTimeDesc(items) {
      return [...items].sort((a, b) => {
        const parseStart = (str) => {
          if (!str) return ''
          const s = str.trim()
          // 时间范围格式: "08:20~09:30"
          if (s.includes('~')) return s.split('~')[0].trim()
          // 日期时间格式: "12-29 08:20" (RSS)
          return s
        }
        const ta = parseStart(a.time_display)
        const tb = parseStart(b.time_display)
        if (tb > ta) return 1
        if (tb < ta) return -1
        return 0
      })
    }

    function adaptDashboardData(raw) {
      const categories = Array.isArray(raw.categories) ? raw.categories : []
      const news = Array.isArray(raw.news) ? [...raw.news] : []
      const newsByCategory = {
        '全部资讯': sortByTimeDesc(news).map((item, index) => ({
          ...item,
          categoryRank: index + 1,
        })),
      }

      categories.forEach((category) => {
        newsByCategory[category.name] = sortByTimeDesc(
          news.filter((item) => item.category === category.name)
        ).map((item, index) => ({
          ...item,
          categoryRank: index + 1,
        }))
      })

      return {
        categories: [{ name: '全部资讯', count: news.length }, ...categories],
        newsByCategory,
        sourceChartData: Array.isArray(raw.source_distribution) ? raw.source_distribution : [],
        keywordCloud: Array.isArray(raw.keywords) ? raw.keywords : [],
        aiPanels: Array.isArray(raw.ai_panels) ? raw.ai_panels : [],
        rssState: raw.rss_updates || FALLBACK_PAYLOAD.rss_updates,
        meta: raw.meta || FALLBACK_PAYLOAD.meta,
        stats: raw.stats || FALLBACK_PAYLOAD.stats,
      }
    }

    globalThis.rawMockApi = rawMockApi
    globalThis.adaptDashboardData = adaptDashboardData
"""


def render_screen_content(
    report_data: Dict[str, Any],
    total_titles: int,
    mode: str = "daily",
    *,
    get_time_func: Optional[Callable[[], datetime]] = None,
    rss_items: Optional[List[Dict[str, Any]]] = None,
    ai_analysis: Optional[Any] = None,
    frequency_file: Optional[str] = None,
    rank_threshold: int = 3,
    weight_config: Optional[Dict[str, float]] = None,
) -> str:
    template = SCREEN_TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = build_screen_payload(
        report_data,
        total_titles,
        mode,
        get_time_func=get_time_func,
        rss_items=rss_items,
        ai_analysis=ai_analysis,
        frequency_file=frequency_file,
        rank_threshold=rank_threshold,
        weight_config=weight_config,
    )

    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    inject_script = f"<script>globalThis.__TRENDRADAR_SCREEN__ = {payload_json};</script>\n  <script>"
    template = template.replace("<script>\n    const { createApp", inject_script + "\n    const { createApp", 1)

    template = re.sub(
        r"const CATEGORY_COUNTS = \[[\s\S]*?globalThis\.adaptDashboardData = adaptDashboardData",
        _build_runtime_block().strip(),
        template,
        count=1,
    )

    template = template.replace('src="./static/logo.png"', f'src="{_load_logo_data_uri()}"')
    return template
