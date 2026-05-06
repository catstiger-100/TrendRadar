# coding=utf-8
"""
RSS HTML 报告渲染模块

提供 RSS 订阅内容的 HTML 格式报告生成功能
"""

from datetime import datetime
from typing import Dict, List, Optional, Callable

from trendradar.report.helpers import html_escape


def render_rss_html_content(
    rss_items: List[Dict],
    total_count: int,
    feeds_info: Optional[Dict[str, str]] = None,
    *,
    get_time_func: Optional[Callable[[], datetime]] = None,
) -> str:
    """渲染 RSS HTML 内容

    Args:
        rss_items: RSS 条目列表，每个条目包含:
            - title: 标题
            - feed_id: RSS 源 ID
            - feed_name: RSS 源名称
            - url: 链接
            - published_at: 发布时间
            - summary: 摘要（可选）
            - author: 作者（可选）
        total_count: 条目总数
        feeds_info: RSS 源 ID 到名称的映射
        get_time_func: 获取当前时间的函数（可选，默认使用 datetime.now）

    Returns:
        渲染后的 HTML 字符串
    """
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RSS 订阅内容</title>
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
                --accent: #059669;
                --accent-deep: #047857;
                --accent-soft: #ecfdf5;
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
                    radial-gradient(ellipse at 15% 40%, rgba(5, 150, 105, 0.03) 0%, transparent 55%),
                    radial-gradient(ellipse at 85% 15%, rgba(16, 185, 129, 0.02) 0%, transparent 50%);
                color: var(--text);
                line-height: 1.6;
                -webkit-tap-highlight-color: rgba(5, 150, 105, 0.08);
                -webkit-text-size-adjust: 100%;
                -webkit-font-smoothing: antialiased;
                min-height: 100vh;
            }

            .container {
                max-width: 700px;
                width: 100%;
                margin: 0 auto;
                background: var(--surface);
                border-radius: var(--radius-lg);
                overflow: hidden;
                box-shadow: var(--shadow-lg);
            }

            /* ── Header ── */
            .header {
                background: linear-gradient(160deg, #022c22 0%, #064e3b 30%, #047857 60%, #059669 80%, #10b981 100%);
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
                    radial-gradient(ellipse at 75% 65%, rgba(167, 243, 208, 0.08) 0%, transparent 45%),
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
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent);
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
                grid-template-columns: repeat(2, 1fr);
                gap: 10px;
                max-width: 400px;
                margin: 0 auto;
            }

            .info-item {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: var(--radius);
                padding: 14px 8px;
                text-align: center;
                backdrop-filter: blur(4px);
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

            .feed-group {
                margin-bottom: 32px;
            }

            .feed-group:last-child { margin-bottom: 0; }

            .feed-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 16px;
                padding-left: 14px;
                border-left: 3px solid var(--accent);
            }

            .feed-name {
                font-size: 18px;
                font-weight: 700;
                color: var(--accent);
            }

            .feed-count {
                font-size: 12px;
                font-weight: 500;
                color: var(--text-muted);
            }

            .rss-item {
                margin-bottom: 8px;
                padding: 16px 18px;
                background: #f0fdf6;
                border: 1px solid #d1fae5;
                border-radius: var(--radius);
                border-left: 3px solid #10b981;
                transition: all 0.2s ease;
            }

            .rss-item:hover {
                background: #e6f9f0;
                border-color: #a7f3d0;
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.04);
            }

            .rss-item:last-child { margin-bottom: 0; }

            .rss-meta {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 8px;
                flex-wrap: wrap;
            }

            .rss-time {
                font-size: 12px;
                color: var(--text-muted);
                font-weight: 500;
            }

            .rss-author {
                font-size: 11px;
                font-weight: 600;
                color: var(--accent);
                background: #d1fae5;
                padding: 2px 8px;
                border-radius: 100px;
            }

            .rss-title {
                font-size: 15px;
                line-height: 1.55;
                color: var(--text);
                font-weight: 600;
                margin-bottom: 4px;
                overflow-wrap: break-word;
                word-break: break-word;
            }

            .rss-link {
                color: var(--text);
                text-decoration: none;
                transition: color 0.2s ease;
            }

            .rss-link:hover { color: var(--accent); }

            .rss-link:active { opacity: 0.7; }

            .rss-summary {
                font-size: 13px;
                color: var(--text-muted);
                line-height: 1.6;
                margin: 0;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
                overflow-wrap: break-word;
                word-break: break-word;
            }

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
                box-shadow: 0 4px 16px rgba(5, 150, 105, 0.35);
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
                background: #047857;
                transform: translateY(0) scale(0.93);
            }

            @media (min-width: 769px) {
                .back-to-top { right: calc(50% - 350px + 28px); }
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
                .info-value { font-size: 15px; }

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

                .feed-header { padding-left: 10px; border-left-width: 2px; }
                .feed-name { font-size: 16px; }
                .rss-item { padding: 14px; }
                .rss-title { font-size: 14px; }
                .rss-meta { gap: 8px; }

                .footer { padding: 18px 20px; }
                .back-to-top { bottom: 20px; right: 20px; width: 40px; height: 40px; font-size: 16px; }
            }

            @media (max-width: 360px) {
                body { padding: 4px; }
                .header { padding: 20px 14px 18px; }
                .header-title { font-size: 18px; }
                .header-info { grid-template-columns: 1fr; gap: 6px; }
                .content { padding: 16px 12px; }
                .rss-title { font-size: 13px; }
                .save-btn { padding: 10px 12px; font-size: 13px; min-height: 40px; }
                .info-value { font-size: 14px; }
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
                    --accent: #34d399;
                    --accent-deep: #10b981;
                    --accent-soft: #0f2620;
                    --shadow-sm: 0 1px 2px rgba(0,0,0,0.2);
                    --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 4px 12px rgba(0,0,0,0.25);
                    --shadow-lg: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.35), 0 20px 56px rgba(0,0,0,0.4);
                }

                body { background: var(--bg); background-image: none; }

                .header {
                    background: linear-gradient(160deg, #021a14 0%, #042f22 30%, #064e3b 60%, #065f46 80%, #047857 100%);
                }

                .info-item { background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.04); }

                .rss-item { background: #0f2620; border-color: #1a4035; }
                .rss-item:hover { background: #143528; border-color: #235a45; }
                .rss-author { background: #1a4035; }

                .footer { background: var(--surface-alt); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="save-buttons">
                    <button class="save-btn" onclick="saveAsImage()">保存为图片</button>
                </div>
                <div class="header-title">RSS 订阅内容</div>
                <div class="header-info">
                    <div class="info-item">
                        <span class="info-label">订阅条目</span>
                        <span class="info-value">"""

    html += f"{total_count} 条"

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

    # 按 feed_id 分组
    feeds_map: Dict[str, List[Dict]] = {}
    for item in rss_items:
        feed_id = item.get("feed_id", "unknown")
        if feed_id not in feeds_map:
            feeds_map[feed_id] = []
        feeds_map[feed_id].append(item)

    # 渲染每个 RSS 源的内容
    for feed_id, items in feeds_map.items():
        feed_name = items[0].get("feed_name", feed_id) if items else feed_id
        if feeds_info and feed_id in feeds_info:
            feed_name = feeds_info[feed_id]

        escaped_feed_name = html_escape(feed_name)

        html += f"""
                <div class="feed-group">
                    <div class="feed-header">
                        <div class="feed-name">{escaped_feed_name}</div>
                        <div class="feed-count">{len(items)} 条</div>
                    </div>"""

        for item in items:
            escaped_title = html_escape(item.get("title", ""))
            url = item.get("url", "")
            published_at = item.get("published_at", "")
            author = item.get("author", "")
            summary = item.get("summary", "")

            html += """
                    <div class="rss-item">
                        <div class="rss-meta">"""

            if published_at:
                html += f'<span class="rss-time">{html_escape(published_at)}</span>'

            if author:
                html += f'<span class="rss-author">by {html_escape(author)}</span>'

            html += """
                        </div>
                        <div class="rss-title">"""

            if url:
                escaped_url = html_escape(url)
                html += f'<a href="{escaped_url}" target="_blank" class="rss-link">{escaped_title}</a>'
            else:
                html += escaped_title

            html += """
                        </div>"""

            if summary:
                escaped_summary = html_escape(summary)
                html += f"""
                        <p class="rss-summary">{escaped_summary}</p>"""

            html += """
                    </div>"""

        html += """
                </div>"""

    html += """
            </div>

            <div class="footer">
                <div class="footer-content">
                    由 <span class="project-name">TrendRadar</span> 生成 ·
                    <a href="https://github.com/sansan0/TrendRadar" target="_blank" class="footer-link">
                        GitHub 开源项目
                    </a>
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

                    await new Promise(resolve => setTimeout(resolve, 200));

                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

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
                    const filename = `TrendRadar_RSS订阅_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}.png`;

                    link.download = filename;
                    link.href = canvas.toDataURL('image/png', 1.0);

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
