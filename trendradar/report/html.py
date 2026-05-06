# coding=utf-8
"""
HTML 报告渲染模块

提供 HTML 格式的热点新闻报告生成功能
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from trendradar.report.helpers import html_escape
from trendradar.utils.time import convert_time_for_display
from trendradar.ai.formatter import render_ai_analysis_html_rich


def render_html_content(
    report_data: Dict,
    total_titles: int,
    mode: str = "daily",
    update_info: Optional[Dict] = None,
    *,
    region_order: Optional[List[str]] = None,
    get_time_func: Optional[Callable[[], datetime]] = None,
    rss_items: Optional[List[Dict]] = None,
    rss_new_items: Optional[List[Dict]] = None,
    display_mode: str = "keyword",
    standalone_data: Optional[Dict] = None,
    ai_analysis: Optional[Any] = None,
    show_new_section: bool = True,
) -> str:
    """渲染HTML内容

    Args:
        report_data: 报告数据字典，包含 stats, new_titles, failed_ids, total_new_count
        total_titles: 新闻总数
        mode: 报告模式 ("daily", "current", "incremental")
        update_info: 更新信息（可选）
        region_order: 区域显示顺序列表
        get_time_func: 获取当前时间的函数（可选，默认使用 datetime.now）
        rss_items: RSS 统计条目列表（可选）
        rss_new_items: RSS 新增条目列表（可选）
        display_mode: 显示模式 ("keyword"=按关键词分组, "platform"=按平台分组)
        standalone_data: 独立展示区数据（可选），包含 platforms 和 rss_feeds
        ai_analysis: AI 分析结果对象（可选），AIAnalysisResult 实例
        show_new_section: 是否显示新增热点区域

    Returns:
        渲染后的 HTML 字符串
    """
    # 默认区域顺序
    default_region_order = ["hotlist", "rss", "new_items", "standalone", "ai_analysis"]
    if region_order is None:
        region_order = default_region_order

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>热点新闻分析</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js" integrity="sha512-BNaRQnYJYiPSqHHDb58B0yaPfCu+Wgds8Gp/gU33kqBtgNS4tSPHuGibyoeqMV/TJlSKda6FXzoEyYGjTe+vXA==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            html { scroll-behavior: smooth; }

            :root {
                --bg: #f3f1ec;
                --surface: #ffffff;
                --surface-alt: #fafafb;
                --text: #1a1a24;
                --text-secondary: #5c5c68;
                --text-muted: #9494a0;
                --border: #eaeaef;
                --border-light: #f3f3f7;
                --accent: #4f46e5;
                --accent-deep: #4338ca;
                --accent-soft: #eef2ff;
                --gold: #b45309;
                --gold-bg: #fffbeb;
                --gold-border: #fde68a;
                --red: #dc2626;
                --red-soft: #fef2f2;
                --emerald: #059669;
                --emerald-soft: #ecfdf5;
                --amber: #d97706;
                --amber-bg: #fffbeb;
                --radius-sm: 8px;
                --radius: 12px;
                --radius-lg: 20px;
                --shadow-sm: 0 1px 2px rgba(0,0,0,0.03);
                --shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04);
                --shadow-lg: 0 1px 2px rgba(0,0,0,0.03), 0 8px 24px rgba(0,0,0,0.05), 0 20px 56px rgba(0,0,0,0.06);
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans SC', system-ui, sans-serif;
                padding: 24px;
                padding: max(24px, env(safe-area-inset-top)) max(24px, env(safe-area-inset-right)) max(24px, env(safe-area-inset-bottom)) max(24px, env(safe-area-inset-left));
                background: var(--bg);
                background-image:
                    radial-gradient(ellipse at 15% 40%, rgba(79, 70, 229, 0.03) 0%, transparent 55%),
                    radial-gradient(ellipse at 85% 15%, rgba(99, 102, 241, 0.02) 0%, transparent 50%);
                color: var(--text);
                line-height: 1.6;
                -webkit-tap-highlight-color: rgba(79, 70, 229, 0.08);
                -webkit-text-size-adjust: 100%;
                -webkit-font-smoothing: antialiased;
                min-height: 100vh;
            }

            .container {
                max-width: 640px;
                width: 100%;
                margin: 0 auto;
                background: var(--surface);
                border-radius: var(--radius-lg);
                overflow: hidden;
                box-shadow: var(--shadow-lg);
            }

            /* ── Header ── */
            .header {
                background: linear-gradient(160deg, #0f0d2e 0%, #1e1b4b 25%, #312e81 55%, #4338ca 80%, #4f46e5 100%);
                color: white;
                padding: 44px 36px 36px;
                text-align: center;
                position: relative;
                overflow: hidden;
            }

            .header::before {
                content: '';
                position: absolute;
                inset: 0;
                background:
                    radial-gradient(ellipse at 25% 30%, rgba(255,255,255,0.06) 0%, transparent 55%),
                    radial-gradient(ellipse at 75% 65%, rgba(165, 180, 252, 0.08) 0%, transparent 45%),
                    radial-gradient(ellipse at 60% 15%, rgba(255,255,255,0.03) 0%, transparent 35%);
                pointer-events: none;
            }

            .header::after {
                content: '';
                position: absolute;
                bottom: 0;
                left: 5%;
                right: 5%;
                height: 1px;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
            }

            .header > * { position: relative; z-index: 1; }

            .save-buttons {
                display: flex;
                gap: 8px;
                justify-content: flex-end;
                margin-bottom: 20px;
            }

            .save-btn {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: rgba(255,255,255,0.9);
                padding: 8px 18px;
                border-radius: 100px;
                cursor: pointer;
                font-size: 13px;
                font-weight: 500;
                letter-spacing: 0.01em;
                transition: all 0.25s ease;
                backdrop-filter: blur(12px);
                white-space: nowrap;
            }

            .save-btn:hover {
                background: rgba(255, 255, 255, 0.18);
                border-color: rgba(255, 255, 255, 0.28);
                color: white;
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }

            .save-btn:active {
                transform: translateY(0) scale(0.97);
            }

            .save-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }

            .header-title {
                font-size: 24px;
                font-weight: 700;
                letter-spacing: 0.02em;
                margin: 0 0 24px 0;
                text-shadow: 0 2px 8px rgba(0,0,0,0.15);
            }

            .header-info {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 10px;
            }

            .info-item {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: var(--radius);
                padding: 14px 8px;
                text-align: center;
                backdrop-filter: blur(4px);
                transition: background 0.3s ease;
            }

            .info-label {
                display: block;
                font-size: 10px;
                font-weight: 500;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                opacity: 0.6;
                margin-bottom: 6px;
            }

            .info-value {
                font-weight: 700;
                font-size: 17px;
                letter-spacing: 0.01em;
            }

            /* ── Content ── */
            .content {
                padding: 28px 28px 32px;
            }

            /* ── Word Group ── */
            .word-group {
                margin-bottom: 36px;
            }

            .word-group:last-child { margin-bottom: 0; }

            .word-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 18px;
                padding-left: 14px;
                border-left: 3px solid var(--accent);
            }

            .word-info {
                display: flex;
                align-items: baseline;
                gap: 10px;
            }

            .word-name {
                font-size: 18px;
                font-weight: 700;
                color: var(--text);
                letter-spacing: 0.01em;
            }

            .word-count {
                font-size: 13px;
                font-weight: 600;
                color: var(--text-muted);
                background: var(--surface-alt);
                padding: 3px 10px;
                border-radius: 100px;
            }

            .word-count.hot {
                color: #b91c1c;
                background: #fef2f2;
            }

            .word-count.warm {
                color: #c2410c;
                background: #fff7ed;
            }

            .word-index {
                font-size: 11px;
                font-weight: 500;
                color: var(--text-muted);
                letter-spacing: 0.03em;
            }

            /* ── News Item ── */
            .news-item {
                margin-bottom: 10px;
                padding: 14px 16px;
                background: var(--surface-alt);
                border: 1px solid var(--border-light);
                border-radius: var(--radius);
                position: relative;
                display: flex;
                gap: 14px;
                align-items: flex-start;
                transition: all 0.2s ease;
            }

            .news-item:hover {
                background: #f5f5fa;
                border-color: #e0e0ee;
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.04);
            }

            .news-item:last-child { margin-bottom: 0; }

            /* Top rank accents */
            .news-item.top-1 { border-left: 3px solid #f59e0b; background: linear-gradient(90deg, #fffbeb 0%, var(--surface-alt) 20%); }
            .news-item.top-2 { border-left: 3px solid #94a3b8; background: linear-gradient(90deg, #f8fafc 0%, var(--surface-alt) 20%); }
            .news-item.top-3 { border-left: 3px solid #d4a574; background: linear-gradient(90deg, #fdf6f0 0%, var(--surface-alt) 20%); }

            .news-item.new::after {
                content: "NEW";
                position: absolute;
                top: 12px;
                right: 12px;
                background: linear-gradient(135deg, #f59e0b, #d97706);
                color: white;
                font-size: 8px;
                font-weight: 800;
                padding: 3px 8px;
                border-radius: 100px;
                letter-spacing: 0.06em;
                box-shadow: 0 2px 6px rgba(245, 158, 11, 0.3);
            }

            .news-number {
                color: var(--text-muted);
                font-size: 12px;
                font-weight: 700;
                min-width: 26px;
                width: 26px;
                height: 26px;
                text-align: center;
                flex-shrink: 0;
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-variant-numeric: tabular-nums;
                margin-top: 1px;
            }

            .news-content {
                flex: 1;
                min-width: 0;
                padding-right: 32px;
                overflow-wrap: break-word;
                word-break: break-word;
            }

            .news-item.new .news-content { padding-right: 52px; }

            .news-header {
                display: flex;
                align-items: center;
                gap: 6px;
                margin-bottom: 8px;
                flex-wrap: wrap;
            }

            .source-name {
                font-size: 11px;
                font-weight: 600;
                color: var(--text-muted);
                background: var(--surface);
                padding: 3px 8px;
                border-radius: 6px;
                border: 1px solid var(--border);
            }

            .keyword-tag {
                font-size: 11px;
                font-weight: 600;
                color: var(--accent);
                background: var(--accent-soft);
                padding: 3px 8px;
                border-radius: 6px;
            }

            .rank-num {
                color: white;
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 100px;
                min-width: 22px;
                text-align: center;
                letter-spacing: 0.02em;
            }

            .rank-num { background: #94a3b8; }
            .rank-num.top { background: linear-gradient(135deg, #f59e0b, #d97706); }
            .rank-num.high { background: #ef4444; }

            .time-info {
                font-size: 11px;
                font-weight: 500;
                color: var(--text-muted);
            }

            .count-info {
                font-size: 11px;
                font-weight: 600;
                color: var(--emerald);
                background: var(--emerald-soft);
                padding: 2px 8px;
                border-radius: 100px;
            }

            .news-title {
                font-size: 15px;
                line-height: 1.55;
                color: var(--text);
                margin: 0;
            }

            .news-link {
                color: var(--text);
                text-decoration: none;
                padding: 2px 0;
                display: inline;
                transition: color 0.2s ease;
                background: linear-gradient(var(--accent), var(--accent)) left bottom / 0% 1.5px no-repeat;
                transition: background-size 0.3s ease, color 0.2s ease;
            }

            .news-link:hover {
                color: var(--accent);
                background-size: 100% 1.5px;
            }

            .news-link:active { opacity: 0.7; }
            .news-link:visited { color: #7c3aed; }

            /* ── Section Divider ── */
            .section-divider {
                margin-top: 40px;
                padding-top: 28px;
                border-top: 1px solid var(--border);
                position: relative;
            }

            .section-divider::before {
                content: '';
                position: absolute;
                top: -1px;
                left: 0;
                width: 60px;
                height: 2px;
                background: var(--accent);
                border-radius: 1px;
            }

            /* ── New Hotspots Section ── */
            .new-section { margin-top: 40px; }

            .new-section-title {
                font-size: 17px;
                font-weight: 700;
                color: var(--text);
                margin: 0 0 20px 0;
                padding-left: 14px;
                border-left: 3px solid #f59e0b;
            }

            .new-source-group { margin-bottom: 24px; }
            .new-source-group:last-child { margin-bottom: 0; }

            .new-source-title {
                font-size: 13px;
                font-weight: 600;
                color: var(--text-secondary);
                margin: 0 0 12px 0;
                padding-bottom: 8px;
                border-bottom: 1px solid var(--border-light);
                letter-spacing: 0.02em;
            }

            .new-item {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 10px 12px;
                margin-bottom: 6px;
                background: var(--surface-alt);
                border-radius: var(--radius-sm);
                transition: background 0.2s ease;
            }

            .new-item:last-child { margin-bottom: 0; }
            .new-item:hover { background: #f5f5fa; }

            .new-item-number {
                font-size: 11px;
                font-weight: 700;
                color: var(--text-muted);
                min-width: 20px;
                width: 20px;
                height: 20px;
                text-align: center;
                flex-shrink: 0;
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 6px;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .new-item-rank {
                color: white;
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 100px;
                min-width: 22px;
                text-align: center;
                flex-shrink: 0;
                letter-spacing: 0.02em;
                background: #94a3b8;
            }

            .new-item-rank.top { background: linear-gradient(135deg, #f59e0b, #d97706); }
            .new-item-rank.high { background: #ef4444; }

            .new-item-content {
                flex: 1;
                min-width: 0;
                overflow-wrap: break-word;
                word-break: break-word;
            }

            .new-item-title {
                font-size: 14px;
                line-height: 1.5;
                color: var(--text);
                margin: 0;
            }

            /* ── Error Section ── */
            .error-section {
                background: var(--red-soft);
                border: 1px solid #fecaca;
                border-radius: var(--radius);
                padding: 18px 20px;
                margin-bottom: 24px;
            }

            .error-title {
                color: var(--red);
                font-size: 14px;
                font-weight: 700;
                margin: 0 0 10px 0;
                display: flex;
                align-items: center;
                gap: 6px;
            }

            .error-list {
                list-style: none;
                padding: 0;
                margin: 0;
            }

            .error-item {
                color: #991b1b;
                font-size: 13px;
                padding: 4px 0;
                font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace;
                border-bottom: 1px solid #fecaca;
            }

            .error-item:last-child { border-bottom: none; }

            /* ── Footer ── */
            .footer {
                padding: 24px 28px;
                background: var(--surface-alt);
                border-top: 1px solid var(--border);
                text-align: center;
            }

            .footer-content {
                font-size: 12px;
                color: var(--text-muted);
                line-height: 1.8;
                letter-spacing: 0.02em;
            }

            .footer-link {
                color: var(--accent);
                text-decoration: none;
                font-weight: 600;
                transition: color 0.2s ease;
            }

            .footer-link:hover { color: var(--accent-deep); }

            .project-name {
                font-weight: 700;
                color: var(--text-secondary);
            }

            /* ── RSS Section ── */
            .rss-section { margin-top: 32px; }

            .rss-section-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 18px;
            }

            .rss-section-title {
                font-size: 17px;
                font-weight: 700;
                color: var(--emerald);
                padding-left: 14px;
                border-left: 3px solid var(--emerald);
            }

            .rss-section-count {
                font-size: 13px;
                font-weight: 500;
                color: var(--text-muted);
            }

            .feed-group { margin-bottom: 24px; }
            .feed-group:last-child { margin-bottom: 0; }

            .feed-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 12px;
                padding-bottom: 8px;
                border-bottom: 1px solid var(--border);
            }

            .feed-name {
                font-size: 15px;
                font-weight: 700;
                color: var(--emerald);
            }

            .feed-count {
                font-size: 12px;
                font-weight: 500;
                color: var(--text-muted);
            }

            .rss-item {
                margin-bottom: 8px;
                padding: 14px 16px;
                background: #f0fdf6;
                border: 1px solid #d1fae5;
                border-radius: var(--radius-sm);
                border-left: 3px solid #10b981;
                transition: background 0.2s ease;
            }

            .rss-item:hover { background: #e6f9f0; }
            .rss-item:last-child { margin-bottom: 0; }

            .rss-meta {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 6px;
                flex-wrap: wrap;
            }

            .rss-time { font-size: 12px; color: var(--text-muted); font-weight: 500; }

            .rss-author {
                font-size: 11px;
                font-weight: 600;
                color: var(--emerald);
                background: #d1fae5;
                padding: 2px 8px;
                border-radius: 100px;
            }

            .rss-title { font-size: 14px; line-height: 1.55; margin-bottom: 4px; }

            .rss-link {
                color: var(--text);
                text-decoration: none;
                font-weight: 600;
                transition: color 0.2s ease;
            }

            .rss-link:hover { color: var(--emerald); }

            .rss-summary {
                font-size: 13px;
                color: var(--text-muted);
                line-height: 1.6;
                margin: 0;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }

            /* ── Standalone Section ── */
            .standalone-section { margin-top: 32px; }

            .standalone-section-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 18px;
            }

            .standalone-section-title {
                font-size: 17px;
                font-weight: 700;
                color: var(--emerald);
                padding-left: 14px;
                border-left: 3px solid var(--emerald);
            }

            .standalone-section-count {
                font-size: 13px;
                font-weight: 500;
                color: var(--text-muted);
            }

            .standalone-group { margin-bottom: 36px; }
            .standalone-group:last-child { margin-bottom: 0; }

            .standalone-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 18px;
                padding-left: 14px;
                border-left: 3px solid var(--text-muted);
            }

            .standalone-name {
                font-size: 18px;
                font-weight: 700;
                color: var(--text);
            }

            .standalone-count {
                font-size: 13px;
                font-weight: 500;
                color: var(--text-muted);
            }

            /* ── AI Section ── */
            .ai-section {
                margin-top: 32px;
                padding: 24px;
                background: linear-gradient(160deg, #f8faff 0%, #eef2ff 100%);
                border-radius: var(--radius);
                border: 1px solid #dde4ff;
            }

            .ai-section-header {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 18px;
            }

            .ai-section-title {
                font-size: 17px;
                font-weight: 700;
                color: #3730a3;
            }

            .ai-section-badge {
                background: var(--accent);
                color: white;
                font-size: 10px;
                font-weight: 700;
                padding: 3px 10px;
                border-radius: 100px;
                letter-spacing: 0.04em;
            }

            .ai-block {
                margin-bottom: 12px;
                padding: 16px 18px;
                background: white;
                border-radius: var(--radius-sm);
                border: 1px solid #e8ecfb;
                box-shadow: var(--shadow-sm);
            }

            .ai-block:last-child { margin-bottom: 0; }

            .ai-block-title {
                font-size: 14px;
                font-weight: 700;
                color: #3730a3;
                margin-bottom: 8px;
            }

            .ai-block-content {
                font-size: 13px;
                line-height: 1.7;
                color: #3f3f5c;
                white-space: pre-wrap;
            }

            .ai-error {
                padding: 14px 18px;
                background: var(--red-soft);
                border: 1px solid #fecaca;
                border-radius: var(--radius-sm);
                color: #991b1b;
                font-size: 13px;
                line-height: 1.6;
            }

            /* ── Back to Top ── */
            .back-to-top {
                position: fixed;
                bottom: 28px;
                right: 28px;
                width: 44px;
                height: 44px;
                border-radius: 50%;
                background: var(--accent);
                color: white;
                border: none;
                cursor: pointer;
                font-size: 18px;
                font-weight: 700;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 16px rgba(79, 70, 229, 0.35);
                opacity: 0;
                transform: translateY(16px);
                transition: opacity 0.3s ease, transform 0.3s ease, background 0.2s ease;
                pointer-events: none;
                z-index: 1000;
                -webkit-tap-highlight-color: transparent;
            }

            .back-to-top.visible {
                opacity: 1;
                transform: translateY(0);
                pointer-events: auto;
            }

            .back-to-top:hover { background: var(--accent-deep); }

            .back-to-top:active {
                background: #3730a3;
                transform: translateY(0) scale(0.93);
            }

            @media (min-width: 769px) {
                .back-to-top { right: calc(50% - 320px + 28px); }
            }

            /* ── Mobile ── */
            @media (max-width: 480px) {
                body {
                    padding: 8px;
                    padding: max(8px, env(safe-area-inset-top)) max(8px, env(safe-area-inset-right)) max(8px, env(safe-area-inset-bottom)) max(8px, env(safe-area-inset-left));
                }
                .container { border-radius: 16px; }
                .header { padding: 28px 20px 24px; }
                .header-title { font-size: 20px; margin-bottom: 18px; }
                .header-info { grid-template-columns: 1fr 1fr; gap: 8px; }
                .info-item { padding: 12px 6px; }
                .info-value { font-size: 15px; }
                .info-label { font-size: 9px; }

                .save-buttons {
                    flex-direction: column;
                    width: 100%;
                    margin-bottom: 16px;
                }
                .save-btn {
                    width: 100%;
                    padding: 12px 16px;
                    font-size: 14px;
                    min-height: 44px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .content { padding: 20px 16px; }

                .word-header { padding-left: 10px; border-left-width: 2px; flex-wrap: wrap; gap: 8px; }
                .word-name { font-size: 16px; }
                .word-count { font-size: 12px; padding: 2px 8px; }

                .news-header { gap: 4px; }
                .news-content { padding-right: 28px; }
                .news-item { gap: 10px; padding: 12px; }
                .news-item.new .news-content { padding-right: 46px; }
                .news-number { width: 24px; height: 24px; font-size: 11px; border-radius: 6px; }
                .news-title { font-size: 14px; }

                .news-item.new::after {
                    font-size: 7px;
                    padding: 2px 6px;
                    top: 8px;
                    right: 8px;
                }

                .new-section-title { font-size: 15px; padding-left: 10px; border-left-width: 2px; }
                .new-source-title { font-size: 12px; }
                .new-item { gap: 8px; padding: 8px 10px; }
                .new-item-title { font-size: 13px; }
                .new-item-number { width: 18px; height: 18px; font-size: 10px; }

                .error-section { padding: 14px 16px; }

                .rss-item { padding: 12px; }
                .rss-title { font-size: 13px; }
                .rss-meta { gap: 6px; }

                .ai-section { padding: 18px; }
                .ai-section-title { font-size: 15px; }
                .ai-block { padding: 12px 14px; }
                .ai-block-content { font-size: 13px; }

                .section-divider { margin-top: 32px; padding-top: 20px; }
                .section-divider::before { width: 40px; }

                .footer { padding: 18px 20px; }

                .back-to-top { bottom: 20px; right: 20px; width: 40px; height: 40px; font-size: 16px; }
            }

            @media (max-width: 360px) {
                body { padding: 4px; }
                .header { padding: 20px 14px 18px; }
                .header-title { font-size: 18px; }
                .header-info { grid-template-columns: 1fr; gap: 6px; }
                .info-item { padding: 10px 6px; }
                .content { padding: 16px 12px; }
                .news-content { padding-right: 24px; }
                .news-item.new .news-content { padding-right: 42px; }
                .news-title { font-size: 13px; }
                .word-name { font-size: 15px; }
                .save-btn { padding: 10px 12px; font-size: 13px; min-height: 40px; }
            }

            /* ── Dark Mode ── */
            @media (prefers-color-scheme: dark) {
                :root {
                    --bg: #111118;
                    --surface: #1a1a24;
                    --surface-alt: #1f1f2c;
                    --text: #e4e4ec;
                    --text-secondary: #b0b0be;
                    --text-muted: #787890;
                    --border: #2a2a3a;
                    --border-light: #242436;
                    --accent: #818cf8;
                    --accent-deep: #6366f1;
                    --accent-soft: #1e1e3a;
                    --red: #f87171;
                    --red-soft: #2a1518;
                    --emerald: #34d399;
                    --emerald-soft: #0f2620;
                    --gold-bg: #2a2010;
                    --gold-border: #4a3510;
                    --shadow-sm: 0 1px 2px rgba(0,0,0,0.2);
                    --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 4px 12px rgba(0,0,0,0.25);
                    --shadow-lg: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.35), 0 20px 56px rgba(0,0,0,0.4);
                }

                body { background: var(--bg); background-image: none; }

                .header {
                    background: linear-gradient(160deg, #0a0a18 0%, #12122a 30%, #1a1850 60%, #1e1b5e 100%);
                }

                .info-item { background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.04); }

                .news-item { background: var(--surface-alt); border-color: var(--border); }
                .news-item:hover { background: #262638; border-color: #363656; }
                .news-item.top-1 { border-left-color: #f59e0b; background: linear-gradient(90deg, #2a2010 0%, var(--surface-alt) 20%); }
                .news-item.top-2 { border-left-color: #94a3b8; background: linear-gradient(90deg, #1e2430 0%, var(--surface-alt) 20%); }
                .news-item.top-3 { border-left-color: #b07540; background: linear-gradient(90deg, #2a1f15 0%, var(--surface-alt) 20%); }

                .source-name { background: var(--surface); border-color: var(--border); color: var(--text-muted); }
                .keyword-tag { background: #1e1e3a; }
                .news-link { color: var(--text); }
                .news-link:hover { color: var(--accent); }
                .news-number { background: var(--surface); border-color: var(--border); }
                .word-count { background: var(--surface); }
                .word-count.hot { background: #2a1518; }
                .word-count.warm { background: #2a1a10; }

                .new-item { background: var(--surface-alt); }
                .new-item:hover { background: #262638; }
                .new-item-number { background: var(--surface); border-color: var(--border); }

                .rss-item { background: #0f2620; border-color: #1a4035; }
                .rss-item:hover { background: #143528; }
                .rss-author { background: #1a4035; }

                .ai-section { background: linear-gradient(160deg, #151528 0%, #1a1a38 100%); border-color: #2a2a48; }
                .ai-block { background: var(--surface); border-color: #2a2a3a; }
                .ai-block-title { color: #a5b4fc; }
                .ai-block-content { color: #b0b0be; }

                .error-section { background: #2a1518; border-color: #4a2022; }
                .error-item { border-color: #4a2022; }

                .footer { background: var(--surface-alt); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="save-buttons">
                    <button class="save-btn" onclick="saveAsImage()">保存为图片</button>
                    <button class="save-btn" onclick="saveAsMultipleImages()">分段保存</button>
                </div>
                <div class="header-title">热点新闻分析</div>
                <div class="header-info">
                    <div class="info-item">
                        <span class="info-label">报告类型</span>
                        <span class="info-value">"""

    # 处理报告类型显示（根据 mode 直接显示）
    if mode == "current":
        html += "当前榜单"
    elif mode == "incremental":
        html += "增量分析"
    else:
        html += "全天汇总"

    html += """</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">新闻总数</span>
                        <span class="info-value">"""

    html += f"{total_titles} 条"

    # 计算筛选后的热点新闻数量
    hot_news_count = sum(len(stat["titles"]) for stat in report_data["stats"])

    html += """</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">热点新闻</span>
                        <span class="info-value">"""

    html += f"{hot_news_count} 条"

    html += """</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">生成时间</span>
                        <span class="info-value">"""

    # 使用提供的时间函数或默认 datetime.now
    if get_time_func:
        now = get_time_func()
    else:
        now = datetime.now()
    html += now.strftime("%m-%d %H:%M")

    html += """</span>
                    </div>
                </div>
            </div>

            <div class="content">"""

    # 处理失败ID错误信息
    if report_data["failed_ids"]:
        html += """
                <div class="error-section">
                    <div class="error-title">⚠️ 请求失败的平台</div>
                    <ul class="error-list">"""
        for id_value in report_data["failed_ids"]:
            html += f'<li class="error-item">{html_escape(id_value)}</li>'
        html += """
                    </ul>
                </div>"""

    # 生成热点词汇统计部分的HTML
    stats_html = ""
    if report_data["stats"]:
        total_count = len(report_data["stats"])

        for i, stat in enumerate(report_data["stats"], 1):
            count = stat["count"]

            # 确定热度等级
            if count >= 10:
                count_class = "hot"
            elif count >= 5:
                count_class = "warm"
            else:
                count_class = ""

            escaped_word = html_escape(stat["word"])

            stats_html += f"""
                <div class="word-group">
                    <div class="word-header">
                        <div class="word-info">
                            <div class="word-name">{escaped_word}</div>
                            <div class="word-count {count_class}">{count} 条</div>
                        </div>
                        <div class="word-index">{i}/{total_count}</div>
                    </div>"""

            # 处理每个词组下的新闻标题，给每条新闻标上序号
            for j, title_data in enumerate(stat["titles"], 1):
                is_new = title_data.get("is_new", False)
                ranks = title_data.get("ranks", [])
                min_rank = min(ranks) if ranks else 99
                if min_rank == 1:
                    top_class = "top-1"
                elif min_rank == 2:
                    top_class = "top-2"
                elif min_rank == 3:
                    top_class = "top-3"
                else:
                    top_class = ""
                item_class = " ".join(filter(None, ["new" if is_new else "", top_class]))

                stats_html += f"""
                    <div class="news-item {item_class}">
                        <div class="news-number">{j}</div>
                        <div class="news-content">
                            <div class="news-header">"""

                # 根据 display_mode 决定显示来源还是关键词
                if display_mode == "keyword":
                    # keyword 模式：显示来源
                    stats_html += f'<span class="source-name">{html_escape(title_data["source_name"])}</span>'
                else:
                    # platform 模式：显示关键词
                    matched_keyword = title_data.get("matched_keyword", "")
                    if matched_keyword:
                        stats_html += f'<span class="keyword-tag">[{html_escape(matched_keyword)}]</span>'

                # 处理排名显示
                ranks = title_data.get("ranks", [])
                if ranks:
                    min_rank = min(ranks)
                    max_rank = max(ranks)
                    rank_threshold = title_data.get("rank_threshold", 10)

                    # 确定排名等级
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= rank_threshold:
                        rank_class = "high"
                    else:
                        rank_class = ""

                    if min_rank == max_rank:
                        rank_text = str(min_rank)
                    else:
                        rank_text = f"{min_rank}-{max_rank}"

                    stats_html += f'<span class="rank-num {rank_class}">{rank_text}</span>'

                # 处理时间显示
                time_display = title_data.get("time_display", "")
                if time_display:
                    # 简化时间显示格式，将波浪线替换为~
                    simplified_time = (
                        time_display.replace(" ~ ", "~")
                        .replace("[", "")
                        .replace("]", "")
                    )
                    stats_html += (
                        f'<span class="time-info">{html_escape(simplified_time)}</span>'
                    )

                # 处理出现次数
                count_info = title_data.get("count", 1)
                if count_info > 1:
                    stats_html += f'<span class="count-info">{count_info}次</span>'

                stats_html += """
                            </div>
                            <div class="news-title">"""

                # 处理标题和链接
                escaped_title = html_escape(title_data["title"])
                link_url = title_data.get("mobile_url") or title_data.get("url", "")

                if link_url:
                    escaped_url = html_escape(link_url)
                    stats_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    stats_html += escaped_title

                stats_html += """
                            </div>
                        </div>
                    </div>"""

            stats_html += """
                </div>"""

    # 给热榜统计添加外层包装
    if stats_html:
        stats_html = f"""
                <div class="hotlist-section">{stats_html}
                </div>"""

    # 生成新增新闻区域的HTML
    new_titles_html = ""
    if show_new_section and report_data["new_titles"]:
        new_titles_html += f"""
                <div class="new-section">
                    <div class="new-section-title">本次新增热点 (共 {report_data['total_new_count']} 条)</div>"""

        for source_data in report_data["new_titles"]:
            escaped_source = html_escape(source_data["source_name"])
            titles_count = len(source_data["titles"])

            new_titles_html += f"""
                    <div class="new-source-group">
                        <div class="new-source-title">{escaped_source} · {titles_count}条</div>"""

            # 为新增新闻也添加序号
            for idx, title_data in enumerate(source_data["titles"], 1):
                ranks = title_data.get("ranks", [])

                # 处理新增新闻的排名显示
                rank_class = ""
                if ranks:
                    min_rank = min(ranks)
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= title_data.get("rank_threshold", 10):
                        rank_class = "high"

                    if len(ranks) == 1:
                        rank_text = str(ranks[0])
                    else:
                        rank_text = f"{min(ranks)}-{max(ranks)}"
                else:
                    rank_text = "?"

                new_titles_html += f"""
                        <div class="new-item">
                            <div class="new-item-number">{idx}</div>
                            <div class="new-item-rank {rank_class}">{rank_text}</div>
                            <div class="new-item-content">
                                <div class="new-item-title">"""

                # 处理新增新闻的链接
                escaped_title = html_escape(title_data["title"])
                link_url = title_data.get("mobile_url") or title_data.get("url", "")

                if link_url:
                    escaped_url = html_escape(link_url)
                    new_titles_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    new_titles_html += escaped_title

                new_titles_html += """
                                </div>
                            </div>
                        </div>"""

            new_titles_html += """
                    </div>"""

        new_titles_html += """
                </div>"""

    # 生成 RSS 统计内容
    def render_rss_stats_html(stats: List[Dict], title: str = "RSS 订阅更新") -> str:
        """渲染 RSS 统计区块 HTML

        Args:
            stats: RSS 分组统计列表，格式与热榜一致：
                [
                    {
                        "word": "关键词",
                        "count": 5,
                        "titles": [
                            {
                                "title": "标题",
                                "source_name": "Feed 名称",
                                "time_display": "12-29 08:20",
                                "url": "...",
                                "is_new": True/False
                            }
                        ]
                    }
                ]
            title: 区块标题

        Returns:
            渲染后的 HTML 字符串
        """
        if not stats:
            return ""

        # 计算总条目数
        total_count = sum(stat.get("count", 0) for stat in stats)
        if total_count == 0:
            return ""

        rss_html = f"""
                <div class="rss-section">
                    <div class="rss-section-header">
                        <div class="rss-section-title">{title}</div>
                        <div class="rss-section-count">{total_count} 条</div>
                    </div>"""

        # 按关键词分组渲染（与热榜格式一致）
        for stat in stats:
            keyword = stat.get("word", "")
            titles = stat.get("titles", [])
            if not titles:
                continue

            keyword_count = len(titles)

            rss_html += f"""
                    <div class="feed-group">
                        <div class="feed-header">
                            <div class="feed-name">{html_escape(keyword)}</div>
                            <div class="feed-count">{keyword_count} 条</div>
                        </div>"""

            for title_data in titles:
                item_title = title_data.get("title", "")
                url = title_data.get("url", "")
                time_display = title_data.get("time_display", "")
                source_name = title_data.get("source_name", "")
                is_new = title_data.get("is_new", False)

                rss_html += """
                        <div class="rss-item">
                            <div class="rss-meta">"""

                if time_display:
                    rss_html += f'<span class="rss-time">{html_escape(time_display)}</span>'

                if source_name:
                    rss_html += f'<span class="rss-author">{html_escape(source_name)}</span>'

                if is_new:
                    rss_html += '<span class="rss-author" style="color: #dc2626;">NEW</span>'

                rss_html += """
                            </div>
                            <div class="rss-title">"""

                escaped_title = html_escape(item_title)
                if url:
                    escaped_url = html_escape(url)
                    rss_html += f'<a href="{escaped_url}" target="_blank" class="rss-link">{escaped_title}</a>'
                else:
                    rss_html += escaped_title

                rss_html += """
                            </div>
                        </div>"""

            rss_html += """
                    </div>"""

        rss_html += """
                </div>"""
        return rss_html

    # 生成独立展示区内容
    def render_standalone_html(data: Optional[Dict]) -> str:
        """渲染独立展示区 HTML（复用热点词汇统计区样式）

        Args:
            data: 独立展示数据，格式：
                {
                    "platforms": [
                        {
                            "id": "zhihu",
                            "name": "知乎热榜",
                            "items": [
                                {
                                    "title": "标题",
                                    "url": "链接",
                                    "rank": 1,
                                    "ranks": [1, 2, 1],
                                    "first_time": "08:00",
                                    "last_time": "12:30",
                                    "count": 3,
                                }
                            ]
                        }
                    ],
                    "rss_feeds": [
                        {
                            "id": "hacker-news",
                            "name": "Hacker News",
                            "items": [
                                {
                                    "title": "标题",
                                    "url": "链接",
                                    "published_at": "2025-01-07T08:00:00",
                                    "author": "作者",
                                }
                            ]
                        }
                    ]
                }

        Returns:
            渲染后的 HTML 字符串
        """
        if not data:
            return ""

        platforms = data.get("platforms", [])
        rss_feeds = data.get("rss_feeds", [])

        if not platforms and not rss_feeds:
            return ""

        # 计算总条目数
        total_platform_items = sum(len(p.get("items", [])) for p in platforms)
        total_rss_items = sum(len(f.get("items", [])) for f in rss_feeds)
        total_count = total_platform_items + total_rss_items

        if total_count == 0:
            return ""

        standalone_html = f"""
                <div class="standalone-section">
                    <div class="standalone-section-header">
                        <div class="standalone-section-title">独立展示区</div>
                        <div class="standalone-section-count">{total_count} 条</div>
                    </div>"""

        # 渲染热榜平台（复用 word-group 结构）
        for platform in platforms:
            platform_name = platform.get("name", platform.get("id", ""))
            items = platform.get("items", [])
            if not items:
                continue

            standalone_html += f"""
                    <div class="standalone-group">
                        <div class="standalone-header">
                            <div class="standalone-name">{html_escape(platform_name)}</div>
                            <div class="standalone-count">{len(items)} 条</div>
                        </div>"""

            # 渲染每个条目（复用 news-item 结构）
            for j, item in enumerate(items, 1):
                title = item.get("title", "")
                url = item.get("url", "") or item.get("mobileUrl", "")
                rank = item.get("rank", 0)
                ranks = item.get("ranks", [])
                first_time = item.get("first_time", "")
                last_time = item.get("last_time", "")
                count = item.get("count", 1)

                standalone_html += f"""
                        <div class="news-item">
                            <div class="news-number">{j}</div>
                            <div class="news-content">
                                <div class="news-header">"""

                # 排名显示（复用 rank-num 样式，无 # 前缀）
                if ranks:
                    min_rank = min(ranks)
                    max_rank = max(ranks)

                    # 确定排名等级
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= 10:
                        rank_class = "high"
                    else:
                        rank_class = ""

                    if min_rank == max_rank:
                        rank_text = str(min_rank)
                    else:
                        rank_text = f"{min_rank}-{max_rank}"

                    standalone_html += f'<span class="rank-num {rank_class}">{rank_text}</span>'
                elif rank > 0:
                    if rank <= 3:
                        rank_class = "top"
                    elif rank <= 10:
                        rank_class = "high"
                    else:
                        rank_class = ""
                    standalone_html += f'<span class="rank-num {rank_class}">{rank}</span>'

                # 时间显示（复用 time-info 样式，将 HH-MM 转换为 HH:MM）
                if first_time and last_time and first_time != last_time:
                    first_time_display = convert_time_for_display(first_time)
                    last_time_display = convert_time_for_display(last_time)
                    standalone_html += f'<span class="time-info">{html_escape(first_time_display)}~{html_escape(last_time_display)}</span>'
                elif first_time:
                    first_time_display = convert_time_for_display(first_time)
                    standalone_html += f'<span class="time-info">{html_escape(first_time_display)}</span>'

                # 出现次数（复用 count-info 样式）
                if count > 1:
                    standalone_html += f'<span class="count-info">{count}次</span>'

                standalone_html += """
                                </div>
                                <div class="news-title">"""

                # 标题和链接（复用 news-link 样式）
                escaped_title = html_escape(title)
                if url:
                    escaped_url = html_escape(url)
                    standalone_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    standalone_html += escaped_title

                standalone_html += """
                                </div>
                            </div>
                        </div>"""

            standalone_html += """
                    </div>"""

        # 渲染 RSS 源（复用相同结构）
        for feed in rss_feeds:
            feed_name = feed.get("name", feed.get("id", ""))
            items = feed.get("items", [])
            if not items:
                continue

            standalone_html += f"""
                    <div class="standalone-group">
                        <div class="standalone-header">
                            <div class="standalone-name">{html_escape(feed_name)}</div>
                            <div class="standalone-count">{len(items)} 条</div>
                        </div>"""

            for j, item in enumerate(items, 1):
                title = item.get("title", "")
                url = item.get("url", "")
                published_at = item.get("published_at", "")
                author = item.get("author", "")

                standalone_html += f"""
                        <div class="news-item">
                            <div class="news-number">{j}</div>
                            <div class="news-content">
                                <div class="news-header">"""

                # 时间显示（格式化 ISO 时间）
                if published_at:
                    try:
                        from datetime import datetime as dt
                        if "T" in published_at:
                            dt_obj = dt.fromisoformat(published_at.replace("Z", "+00:00"))
                            time_display = dt_obj.strftime("%m-%d %H:%M")
                        else:
                            time_display = published_at
                    except:
                        time_display = published_at

                    standalone_html += f'<span class="time-info">{html_escape(time_display)}</span>'

                # 作者显示
                if author:
                    standalone_html += f'<span class="source-name">{html_escape(author)}</span>'

                standalone_html += """
                                </div>
                                <div class="news-title">"""

                escaped_title = html_escape(title)
                if url:
                    escaped_url = html_escape(url)
                    standalone_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    standalone_html += escaped_title

                standalone_html += """
                                </div>
                            </div>
                        </div>"""

            standalone_html += """
                    </div>"""

        standalone_html += """
                </div>"""
        return standalone_html

    # 生成 RSS 统计和新增 HTML
    rss_stats_html = render_rss_stats_html(rss_items, "RSS 订阅更新") if rss_items else ""
    rss_new_html = render_rss_stats_html(rss_new_items, "RSS 新增更新") if rss_new_items else ""

    # 生成独立展示区 HTML
    standalone_html = render_standalone_html(standalone_data)

    # 生成 AI 分析 HTML
    ai_html = render_ai_analysis_html_rich(ai_analysis) if ai_analysis else ""

    # 准备各区域内容映射
    region_contents = {
        "hotlist": stats_html,
        "rss": rss_stats_html,
        "new_items": (new_titles_html, rss_new_html),  # 元组，分别处理
        "standalone": standalone_html,
        "ai_analysis": ai_html,
    }

    def add_section_divider(content: str) -> str:
        """为内容的外层 div 添加 section-divider 类"""
        if not content or 'class="' not in content:
            return content
        first_class_pos = content.find('class="')
        if first_class_pos != -1:
            insert_pos = first_class_pos + len('class="')
            return content[:insert_pos] + "section-divider " + content[insert_pos:]
        return content

    # 按 region_order 顺序组装内容，动态添加分割线
    has_previous_content = False
    for region in region_order:
        content = region_contents.get(region, "")
        if region == "new_items":
            # 特殊处理 new_items 区域（包含热榜新增和 RSS 新增两部分）
            new_html, rss_new = content
            if new_html:
                if has_previous_content:
                    new_html = add_section_divider(new_html)
                html += new_html
                has_previous_content = True
            if rss_new:
                if has_previous_content:
                    rss_new = add_section_divider(rss_new)
                html += rss_new
                has_previous_content = True
        elif content:
            if has_previous_content:
                content = add_section_divider(content)
            html += content
            has_previous_content = True

    html += """
            </div>

            <div class="footer">
                <div class="footer-content">
                    由 <span class="project-name">TrendRadar</span> 生成 ·
                    <a href="https://github.com/sansan0/TrendRadar" target="_blank" class="footer-link">
                        GitHub 开源项目
                    </a>"""

    if update_info:
        html += f"""
                    <br>
                    <span style="color: #ea580c; font-weight: 500;">
                        发现新版本 {update_info['remote_version']}，当前版本 {update_info['current_version']}
                    </span>"""

    html += """
                </div>
            </div>
            <button class="back-to-top" id="backToTop" title="返回顶部" onclick="scrollToTop()">↑</button>
        </div>

        <script>
            async function saveAsImage() {
                const button = event.target;
                const originalText = button.textContent;

                try {
                    button.textContent = '生成中...';
                    button.disabled = true;
                    window.scrollTo(0, 0);

                    // 等待页面稳定
                    await new Promise(resolve => setTimeout(resolve, 200));

                    // 截图前隐藏按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 再次等待确保按钮完全隐藏
                    await new Promise(resolve => setTimeout(resolve, 100));

                    const container = document.querySelector('.container');

                    const canvas = await html2canvas(container, {
                        backgroundColor: '#ffffff',
                        scale: 1.5,
                        useCORS: true,
                        allowTaint: false,
                        imageTimeout: 10000,
                        removeContainer: false,
                        foreignObjectRendering: false,
                        logging: false,
                        width: container.offsetWidth,
                        height: container.offsetHeight,
                        x: 0,
                        y: 0,
                        scrollX: 0,
                        scrollY: 0,
                        windowWidth: window.innerWidth,
                        windowHeight: window.innerHeight
                    });

                    buttons.style.visibility = 'visible';

                    const link = document.createElement('a');
                    const now = new Date();
                    const filename = `TrendRadar_热点新闻分析_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}.png`;

                    link.download = filename;
                    link.href = canvas.toDataURL('image/png', 1.0);

                    // 触发下载
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    button.textContent = '保存成功!';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            }

            async function saveAsMultipleImages() {
                const button = event.target;
                const originalText = button.textContent;
                const container = document.querySelector('.container');
                const scale = 1.5;
                const maxHeight = 5000 / scale;

                try {
                    button.textContent = '分析中...';
                    button.disabled = true;

                    // 获取所有可能的分割元素
                    const newsItems = Array.from(container.querySelectorAll('.news-item'));
                    const wordGroups = Array.from(container.querySelectorAll('.word-group'));
                    const newSection = container.querySelector('.new-section');
                    const errorSection = container.querySelector('.error-section');
                    const header = container.querySelector('.header');
                    const footer = container.querySelector('.footer');

                    // 计算元素位置和高度
                    const containerRect = container.getBoundingClientRect();
                    const elements = [];

                    // 添加header作为必须包含的元素
                    elements.push({
                        type: 'header',
                        element: header,
                        top: 0,
                        bottom: header.offsetHeight,
                        height: header.offsetHeight
                    });

                    // 添加错误信息（如果存在）
                    if (errorSection) {
                        const rect = errorSection.getBoundingClientRect();
                        elements.push({
                            type: 'error',
                            element: errorSection,
                            top: rect.top - containerRect.top,
                            bottom: rect.bottom - containerRect.top,
                            height: rect.height
                        });
                    }

                    // 按word-group分组处理news-item
                    wordGroups.forEach(group => {
                        const groupRect = group.getBoundingClientRect();
                        const groupNewsItems = group.querySelectorAll('.news-item');

                        // 添加word-group的header部分
                        const wordHeader = group.querySelector('.word-header');
                        if (wordHeader) {
                            const headerRect = wordHeader.getBoundingClientRect();
                            elements.push({
                                type: 'word-header',
                                element: wordHeader,
                                parent: group,
                                top: groupRect.top - containerRect.top,
                                bottom: headerRect.bottom - containerRect.top,
                                height: headerRect.height
                            });
                        }

                        // 添加每个news-item
                        groupNewsItems.forEach(item => {
                            const rect = item.getBoundingClientRect();
                            elements.push({
                                type: 'news-item',
                                element: item,
                                parent: group,
                                top: rect.top - containerRect.top,
                                bottom: rect.bottom - containerRect.top,
                                height: rect.height
                            });
                        });
                    });

                    // 添加新增新闻部分
                    if (newSection) {
                        const rect = newSection.getBoundingClientRect();
                        elements.push({
                            type: 'new-section',
                            element: newSection,
                            top: rect.top - containerRect.top,
                            bottom: rect.bottom - containerRect.top,
                            height: rect.height
                        });
                    }

                    // 添加footer
                    const footerRect = footer.getBoundingClientRect();
                    elements.push({
                        type: 'footer',
                        element: footer,
                        top: footerRect.top - containerRect.top,
                        bottom: footerRect.bottom - containerRect.top,
                        height: footer.offsetHeight
                    });

                    // 计算分割点
                    const segments = [];
                    let currentSegment = { start: 0, end: 0, height: 0, includeHeader: true };
                    let headerHeight = header.offsetHeight;
                    currentSegment.height = headerHeight;

                    for (let i = 1; i < elements.length; i++) {
                        const element = elements[i];
                        const potentialHeight = element.bottom - currentSegment.start;

                        // 检查是否需要创建新分段
                        if (potentialHeight > maxHeight && currentSegment.height > headerHeight) {
                            // 在前一个元素结束处分割
                            currentSegment.end = elements[i - 1].bottom;
                            segments.push(currentSegment);

                            // 开始新分段
                            currentSegment = {
                                start: currentSegment.end,
                                end: 0,
                                height: element.bottom - currentSegment.end,
                                includeHeader: false
                            };
                        } else {
                            currentSegment.height = potentialHeight;
                            currentSegment.end = element.bottom;
                        }
                    }

                    // 添加最后一个分段
                    if (currentSegment.height > 0) {
                        currentSegment.end = container.offsetHeight;
                        segments.push(currentSegment);
                    }

                    button.textContent = `生成中 (0/${segments.length})...`;

                    // 隐藏保存按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 为每个分段生成图片
                    const images = [];
                    for (let i = 0; i < segments.length; i++) {
                        const segment = segments[i];
                        button.textContent = `生成中 (${i + 1}/${segments.length})...`;

                        // 创建临时容器用于截图
                        const tempContainer = document.createElement('div');
                        tempContainer.style.cssText = `
                            position: absolute;
                            left: -9999px;
                            top: 0;
                            width: ${container.offsetWidth}px;
                            background: white;
                        `;
                        tempContainer.className = 'container';

                        // 克隆容器内容
                        const clonedContainer = container.cloneNode(true);

                        // 移除克隆内容中的保存按钮
                        const clonedButtons = clonedContainer.querySelector('.save-buttons');
                        if (clonedButtons) {
                            clonedButtons.style.display = 'none';
                        }

                        tempContainer.appendChild(clonedContainer);
                        document.body.appendChild(tempContainer);

                        // 等待DOM更新
                        await new Promise(resolve => setTimeout(resolve, 100));

                        // 使用html2canvas截取特定区域
                        const canvas = await html2canvas(clonedContainer, {
                            backgroundColor: '#ffffff',
                            scale: scale,
                            useCORS: true,
                            allowTaint: false,
                            imageTimeout: 10000,
                            logging: false,
                            width: container.offsetWidth,
                            height: segment.end - segment.start,
                            x: 0,
                            y: segment.start,
                            windowWidth: window.innerWidth,
                            windowHeight: window.innerHeight
                        });

                        images.push(canvas.toDataURL('image/png', 1.0));

                        // 清理临时容器
                        document.body.removeChild(tempContainer);
                    }

                    // 恢复按钮显示
                    buttons.style.visibility = 'visible';

                    // 下载所有图片
                    const now = new Date();
                    const baseFilename = `TrendRadar_热点新闻分析_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;

                    for (let i = 0; i < images.length; i++) {
                        const link = document.createElement('a');
                        link.download = `${baseFilename}_part${i + 1}.png`;
                        link.href = images[i];
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        // 延迟一下避免浏览器阻止多个下载
                        await new Promise(resolve => setTimeout(resolve, 100));
                    }

                    button.textContent = `已保存 ${segments.length} 张图片!`;
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    console.error('分段保存失败:', error);
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            }

            function scrollToTop() {
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }

            document.addEventListener('DOMContentLoaded', function() {
                window.scrollTo(0, 0);

                var backToTop = document.getElementById('backToTop');
                if (backToTop) {
                    var ticking = false;
                    window.addEventListener('scroll', function() {
                        if (!ticking) {
                            requestAnimationFrame(function() {
                                if (window.scrollY > 400) {
                                    backToTop.classList.add('visible');
                                } else {
                                    backToTop.classList.remove('visible');
                                }
                                ticking = false;
                            });
                            ticking = true;
                        }
                    }, { passive: true });
                }
            });
        </script>
    </body>
    </html>
    """

    return html
