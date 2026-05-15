# coding=utf-8
"""
TrendRadar 管理 Web 服务。

服务 output 目录静态文件，同时提供关键词维护与 AI 分析 API。
"""

import io
import hashlib
import html
import json
import os
import re
import time
import shutil
import threading
import yaml
import zipfile
import traceback
from http import cookies
from datetime import datetime
from decimal import Decimal
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree

import requests

from trendradar.__main__ import NewsAnalyzer
from trendradar.ai.analyzer import AIAnalysisResult
from trendradar.ai.formatter import _format_list_content
from trendradar.core import load_config
from trendradar.core.frequency import (
    convert_keyword_markdown_to_frequency_text,
    parse_frequency_words_for_display,
)
from trendradar.storage import auth_repository
from trendradar.storage import ai_model_repository
from trendradar.storage import futures_symbol_repository
from trendradar.storage import news_favorite_repository
from trendradar.storage import news_share_repository
from trendradar.storage import user_keyword_repository
from trendradar.storage.news_repository import ensure_news_article_columns


OUTPUT_DIR = Path(os.environ.get("WEBSERVER_DIR", "/app/output"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))
CONSOLE_DIR = Path(os.environ.get("CONSOLE_DIST_DIR", "/app/console-dist"))
FREQUENCY_WORDS_PATH = Path(
    os.environ.get("FREQUENCY_WORDS_PATH", str(CONFIG_DIR / "frequency_words.txt"))
)
BACKUP_DIR = Path(os.environ.get("FREQUENCY_BACKUP_DIR", str(CONFIG_DIR / "backups")))
ADMIN_HTML_PATH = Path(__file__).resolve().parent / "static" / "admin.html"

# AI 态势解读全局互斥锁：禁止并发触发（包括定时轮询与手动刷新）
_SITUATION_REFRESH_LOCK = threading.Lock()
XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
AUTH_COOKIE_NAME = os.environ.get("AUTH_COOKIE_NAME", "trendradar_console_session")


ElementTree.register_namespace("", XLSX_MAIN_NS)
ElementTree.register_namespace("r", XLSX_REL_NS)


def _parse_hourly_cron_hours(schedule_expr):
    """解析形如 '0 9,13,15 * * *' 的整点小时列表。"""
    if not schedule_expr:
        return []
    parts = schedule_expr.split()
    if len(parts) != 5 or parts[0] != "0":
        return []
    try:
        return [int(h) for h in parts[1].split(",")]
    except ValueError:
        return []


def _strip_html(value):
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _truncate_to_bytes(text, max_bytes):
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    encoded = text.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore").rstrip() + "\n..."


def _split_message_batches(message, max_bytes):
    if len(message.encode("utf-8")) <= max_bytes:
        return [message]

    batches = []
    current = ""
    for paragraph in message.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate.encode("utf-8")) <= max_bytes:
            current = candidate
            continue

        if current:
            batches.append(current)
            current = ""

        if len(paragraph.encode("utf-8")) <= max_bytes:
            current = paragraph
        else:
            batches.append(_truncate_to_bytes(paragraph, max_bytes))

    if current:
        batches.append(current)
    return batches


def _load_screen_report_data():
    data_path = OUTPUT_DIR / "screen-data.json"
    if not data_path.exists():
        return None
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[通知调度] 读取 screen-data.json 失败: {exc}")
        return None


def _build_scheduled_notification_message(report_data):
    meta = report_data.get("meta", {}) or {}
    stats = report_data.get("stats", {}) or {}
    categories = report_data.get("categories", []) or []
    ai_panels = report_data.get("ai_panels", []) or []
    news = report_data.get("news", []) or []

    lines = [
        f"**TrendRadar 热点报告 - {meta.get('reportType', '当前榜单')}**",
        f"刷新时间：{meta.get('dateLabel', '')} {meta.get('refreshTime', '')}".strip(),
        f"当前榜单：{stats.get('newsTotal', 0)} 条；命中热点：{stats.get('hotNews', 0)} 条",
    ]

    if categories:
        lines.extend(["", "**关键词分布**"])
        for item in categories[:8]:
            lines.append(f"- {item.get('name', '')}: {item.get('count', 0)}")

    if ai_panels:
        lines.extend(["", "**AI 态势摘要**"])
        for panel in ai_panels[:3]:
            body = _strip_html(panel.get("html", ""))
            if not body:
                continue
            lines.append(f"**{panel.get('title', '')}**")
            lines.append(_truncate_to_bytes(body, 900))

    if news:
        lines.extend(["", "**热点 Top 25**"])
        for index, item in enumerate(news[:25], start=1):
            keywords = "、".join(item.get("matched_keywords") or [])
            source = item.get("source_name", "")
            time_display = item.get("time_display", "")
            title = item.get("title", "")
            url = item.get("url", "")
            line = f"{index}. {title}（{source} {time_display}；关键词：{keywords}）"
            if url:
                line += f"\n{url}"
            lines.append(line)

    lines.extend(["", "完整 HTML 报告已同步更新在 TrendRadar 控制台。"])
    return "\n".join(line for line in lines if line is not None)


def _strip_markdown_for_text(message):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", message)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 \2", text)
    return text


def _send_scheduled_channel(channel, webhook_url, message, msg_type="markdown"):
    webhook_urls = [url.strip() for url in str(webhook_url).split(";") if url.strip()]
    if not webhook_urls:
        return False

    if channel == "feishu":
        max_bytes = 28000
    elif channel == "dingtalk":
        max_bytes = 18000
    else:
        max_bytes = 3600

    batches = _split_message_batches(message, max_bytes)
    headers = {"Content-Type": "application/json"}
    all_ok = True

    for account_index, url in enumerate(webhook_urls, start=1):
        for batch_index, batch in enumerate(batches, start=1):
            prefix = ""
            if len(batches) > 1:
                prefix = f"【{batch_index}/{len(batches)}】\n"
            content = prefix + batch

            if channel == "feishu":
                payload = {"msg_type": "text", "content": {"text": _strip_markdown_for_text(content)}}
            elif channel == "dingtalk":
                payload = {
                    "msgtype": "markdown",
                    "markdown": {"title": "TrendRadar 热点报告", "text": content},
                }
            elif channel == "wework":
                if str(msg_type).lower() == "text":
                    payload = {"msgtype": "text", "text": {"content": _strip_markdown_for_text(content)}}
                else:
                    payload = {"msgtype": "markdown", "markdown": {"content": content}}
            else:
                return False

            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                try:
                    result = response.json()
                except Exception:
                    result = {}

                success_code = result.get("errcode", result.get("code", result.get("StatusCode")))
                ok = response.status_code == 200 and success_code in (0, "0")
                if ok:
                    print(f"[通知调度/{channel}] 账号{account_index} 第 {batch_index}/{len(batches)} 批发送成功")
                else:
                    print(
                        f"[通知调度/{channel}] 账号{account_index} 第 {batch_index}/{len(batches)} 批发送失败: "
                        f"status={response.status_code}, body={response.text[:300]}"
                    )
                    all_ok = False
                    break
            except Exception as exc:
                print(f"[通知调度/{channel}] 账号{account_index} 第 {batch_index}/{len(batches)} 批发送异常: {exc}")
                all_ok = False
                break

            if batch_index < len(batches):
                time.sleep(1)

    return all_ok


def _xlsx_column_name(cell_ref):
    return "".join(ch for ch in cell_ref if ch.isalpha())


def _xlsx_column_index(cell_ref):
    name = _xlsx_column_name(cell_ref)
    index = 0
    for char in name:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index - 1


def _xlsx_column_letter(index):
    index += 1
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _build_xlsx_workbook(sheet_name, rows, column_widths=None):
    worksheet = ElementTree.Element(f"{{{XLSX_MAIN_NS}}}worksheet")
    if rows and rows[0]:
        last_cell = f"{_xlsx_column_letter(len(rows[0]) - 1)}{len(rows)}"
        ElementTree.SubElement(worksheet, f"{{{XLSX_MAIN_NS}}}dimension", ref=f"A1:{last_cell}")

    if column_widths:
        cols = ElementTree.SubElement(worksheet, f"{{{XLSX_MAIN_NS}}}cols")
        for index, width in enumerate(column_widths, start=1):
            ElementTree.SubElement(
                cols,
                f"{{{XLSX_MAIN_NS}}}col",
                min=str(index),
                max=str(index),
                width=str(width),
                customWidth="1",
            )

    sheet_data = ElementTree.SubElement(worksheet, f"{{{XLSX_MAIN_NS}}}sheetData")
    for row_index, values in enumerate(rows, start=1):
        row_el = ElementTree.SubElement(sheet_data, f"{{{XLSX_MAIN_NS}}}row", r=str(row_index))
        for column_index, value in enumerate(values):
            cell_ref = f"{_xlsx_column_letter(column_index)}{row_index}"
            cell = ElementTree.SubElement(
                row_el,
                f"{{{XLSX_MAIN_NS}}}c",
                r=cell_ref,
                t="inlineStr",
            )
            inline = ElementTree.SubElement(cell, f"{{{XLSX_MAIN_NS}}}is")
            text = ElementTree.SubElement(inline, f"{{{XLSX_MAIN_NS}}}t")
            text.text = str(value)

    workbook = ElementTree.Element(f"{{{XLSX_MAIN_NS}}}workbook")
    sheets = ElementTree.SubElement(workbook, f"{{{XLSX_MAIN_NS}}}sheets")
    ElementTree.SubElement(
        sheets,
        f"{{{XLSX_MAIN_NS}}}sheet",
        name=sheet_name,
        sheetId="1",
        attrib={f"{{{XLSX_REL_NS}}}id": "rId1"},
    )

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    package_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/workbook.xml", ElementTree.tostring(workbook, encoding="utf-8", xml_declaration=True))
        archive.writestr("xl/worksheets/sheet1.xml", ElementTree.tostring(worksheet, encoding="utf-8", xml_declaration=True))
    return output.getvalue()


def _read_xlsx_shared_strings(archive):
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    values = []
    for item in root.findall("main:si", XLSX_NS):
        parts = [
            text.text or ""
            for text in item.findall(".//main:t", XLSX_NS)
        ]
        values.append("".join(parts))
    return values


def _xlsx_cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    value_el = cell.find("main:v", XLSX_NS)
    inline_el = cell.find("main:is/main:t", XLSX_NS)

    if cell_type == "inlineStr" and inline_el is not None:
        return inline_el.text or ""
    if value_el is None:
        return ""

    value = value_el.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return ""
    return value


def _xlsx_to_markdown(content):
    with zipfile.ZipFile(content) as archive:
        shared_strings = _read_xlsx_shared_strings(archive)
        sheet_name = "xl/worksheets/sheet1.xml"
        root = ElementTree.fromstring(archive.read(sheet_name))

    rows = []
    for row in root.findall(".//main:sheetData/main:row", XLSX_NS):
        values = []
        for cell in row.findall("main:c", XLSX_NS):
            index = _xlsx_column_index(cell.attrib.get("r", "A"))
            while len(values) <= index:
                values.append("")
            values[index] = _xlsx_cell_value(cell, shared_strings).strip()
        if any(values):
            rows.append(values)

    markdown_lines = []
    current_module = None
    current_category = None

    for values in rows:
        compact = [value for value in values if value]
        if not compact:
            continue

        first = compact[0]
        if first.startswith("#") or first.startswith(("-", "*", "+")):
            markdown_lines.append(first)
            continue

        if len(compact) >= 4:
            module, category, title, keywords = compact[:4]
            if module != current_module:
                markdown_lines.append(f"# {module}")
                current_module = module
                current_category = None
            if category != current_category:
                markdown_lines.append(f"## {category}")
                current_category = category
            markdown_lines.append(f"- {title}: {keywords}")

    return "\n".join(markdown_lines)


def _json_serialize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


_EMAIL_SCHEDULE_OPTIONS = [
    "",
    "0 9 * * *",
    "0 9,13,15 * * *",
    "0 9,12,18 * * *",
    "0 9,12,15,18 * * *",
    "0 8,12,18,22 * * *",
]

_EMAIL_SCHEDULE_LABELS = {
    "": "不启用",
    "0 9 * * *": "每天早晨 9:00",
    "0 9,13,15 * * *": "每天 9:00、13:00、15:00",
    "0 9,12,18 * * *": "每天 9:00、12:00、18:00",
    "0 9,12,15,18 * * *": "每天 9:00、12:00、15:00、18:00",
    "0 8,12,18,22 * * *": "每天 8:00、12:00、18:00、22:00",
}


def _apply_config_updates(content: str, updates: dict) -> str:
    """
    就地更新 config.yaml 中若干标量字段的值，保留注释/缩进。

    - crawl_interval_minutes 位于 advanced.crawler 下
    - opinion_page_size / opinion_max_load_count 位于 advanced.console 下，若块不存在则在文件末尾补齐
    - email.* 位于 notification.channels.email 下
    """
    # advanced.crawler.crawl_interval_minutes
    if "crawl_interval_minutes" in updates:
        interval = updates["crawl_interval_minutes"]
        if re.search(r"^\s*crawl_interval_minutes\s*:\s*\d+", content, flags=re.MULTILINE):
            content = re.sub(
                r"^(\s*crawl_interval_minutes\s*:\s*)\d+",
                lambda m: f"{m.group(1)}{interval}",
                content,
                flags=re.MULTILINE,
            )
        else:
            content = re.sub(
                r"(default_proxy:\s*\"[^\"]*\")\n",
                f"\\1\n    crawl_interval_minutes: {interval}\n",
                content,
                count=1,
            )

    # advanced.console.opinion_*
    console_keys = ("opinion_page_size", "opinion_max_load_count")
    if any(k in updates for k in console_keys):
        # 先尝试替换已有键
        for key in console_keys:
            if key not in updates:
                continue
            value = updates[key]
            pattern = rf"^(\s*{key}\s*:\s*)\d+"
            if re.search(pattern, content, flags=re.MULTILINE):
                content = re.sub(
                    pattern,
                    lambda m, v=value: f"{m.group(1)}{v}",
                    content,
                    flags=re.MULTILINE,
                )

        # 若 console 块不存在，则在 advanced 块末尾新增
        if not re.search(r"^\s*console\s*:", content, flags=re.MULTILINE):
            page_size = updates.get("opinion_page_size", 200)
            max_load = updates.get("opinion_max_load_count", 2000)
            block = (
                "\n  # 控制台资讯列表参数\n"
                "  console:\n"
                f"    opinion_page_size: {page_size}\n"
                f"    opinion_max_load_count: {max_load}\n"
            )
            # 在 advanced 块末尾（即文件末尾或下一个顶级键前）插入
            if not content.endswith("\n"):
                content += "\n"
            content += block
        else:
            # console 已有，但某个子键缺失则补齐
            for key in console_keys:
                if key not in updates:
                    continue
                if re.search(rf"^\s*{key}\s*:", content, flags=re.MULTILINE):
                    continue
                value = updates[key]
                content = re.sub(
                    r"(^\s*console\s*:[^\n]*\n)",
                    f"\\1    {key}: {value}\n",
                    content,
                    count=1,
                    flags=re.MULTILINE,
                )

    # notification.channels.email.* — 分段替换，先定位 email: 块再替换，避免误中顶层 schedule
    email_keys = ("email_from", "email_password", "email_to", "email_smtp_server", "email_smtp_port", "email_schedule")
    email_yaml_keys = {
        "email_from": "from",
        "email_password": "password",
        "email_to": "to",
        "email_smtp_server": "smtp_server",
        "email_smtp_port": "smtp_port",
        "email_schedule": "schedule",
    }
    email_block_match = re.search(r'^ {4}email\s*:\s*$', content, flags=re.MULTILINE)
    if email_block_match:
        email_seg_start = email_block_match.end()
        next_email_block = re.search(r'^ {4}\w', content[email_seg_start:], flags=re.MULTILINE)
        email_seg_end = email_seg_start + next_email_block.start() if next_email_block else len(content)
        email_segment = content[email_seg_start:email_seg_end]
        for update_key in email_keys:
            if update_key not in updates:
                continue
            yaml_key = email_yaml_keys[update_key]
            value = updates[update_key]
            quoted = f'"{value}"'
            pattern = rf'^(\s*{yaml_key}\s*:\s*)(".*?"|\'.*?\'|[^\s#][^\n]*|)'
            email_segment = re.sub(
                pattern,
                lambda m, q=quoted: f"{m.group(1)}{q}",
                email_segment,
                count=1,
                flags=re.MULTILINE,
            )
        content = content[:email_seg_start] + email_segment + content[email_seg_end:]

    # notification.channels.feishu/dingtalk/wework — 只有 webhook_url，schedule 已合并为顶层字段
    _channel_fields = {
        "feishu_webhook_url":   ("feishu",   "webhook_url"),
        "dingtalk_webhook_url": ("dingtalk", "webhook_url"),
        "wework_webhook_url":   ("wework",   "webhook_url"),
    }
    for update_key, (channel, yaml_key) in _channel_fields.items():
        if update_key not in updates:
            continue
        value = updates[update_key]
        quoted = f'"{value}"'
        channel_match = re.search(rf'^ {{4}}{channel}\s*:\s*$', content, flags=re.MULTILINE)
        if not channel_match:
            continue
        seg_start = channel_match.end()
        next_block = re.search(r'^ {4}\w', content[seg_start:], flags=re.MULTILINE)
        seg_end = seg_start + next_block.start() if next_block else len(content)
        segment = content[seg_start:seg_end]
        pattern = rf'^(\s*{yaml_key}\s*:\s*)(".*?"|\'.*?\'|[^\s#][^\n]*|)'
        new_segment = re.sub(
            pattern,
            lambda m, q=quoted: f"{m.group(1)}{q}",
            segment,
            count=1,
            flags=re.MULTILINE,
        )
        content = content[:seg_start] + new_segment + content[seg_end:]

    # notification.notification_schedule — 顶层字段，在 notification: 块内
    if "notification_schedule" in updates:
        value = updates["notification_schedule"]
        quoted = f'"{value}"'
        notif_match = re.search(r'^notification\s*:\s*$', content, flags=re.MULTILINE)
        if notif_match:
            ns_start = notif_match.end()
            # 找下一个顶层 key（无缩进）
            next_top = re.search(r'^\w', content[ns_start:], flags=re.MULTILINE)
            ns_end = ns_start + next_top.start() if next_top else len(content)
            ns_segment = content[ns_start:ns_end]
            pattern = r'^(\s*notification_schedule\s*:\s*)(".*?"|\'.*?\'|[^\s#][^\n]*|)'
            ns_segment = re.sub(
                pattern,
                lambda m, q=quoted: f"{m.group(1)}{q}",
                ns_segment,
                count=1,
                flags=re.MULTILINE,
            )
            content = content[:ns_start] + ns_segment + content[ns_end:]

    return content
def _extract_system_keywords():
    """从 frequency_words.txt 中提取所有系统关键词（去重）。"""
    if not FREQUENCY_WORDS_PATH.exists():
        return []
    content = FREQUENCY_WORDS_PATH.read_text(encoding="utf-8")
    modules = parse_frequency_words_for_display(content)
    keywords = []
    for module in modules:
        for category in module.get("categories", []):
            for group in category.get("groups", []):
                for kw in group.get("keywords", []):
                    if kw and kw not in keywords:
                        keywords.append(kw)
    return keywords


class AdminRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self._extra_headers = []
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        for key, value in self._extra_headers:
            self.send_header(key, value)
        self._extra_headers = []
        super().end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/console" or path == "/console/":
            self._serve_console_index()
            return
        if path.startswith("/console/"):
            if self._serve_console_asset(path):
                return
        if path == "/admin.html":
            self._serve_admin_html()
            return
        if path == "/api/keywords":
            self._send_keywords()
            return
        if path == "/api/keywords/backups":
            self._send_backups()
            return
        if path == "/api/keywords/template/md":
            self._send_keyword_template_md()
            return
        if path == "/api/keywords/template/xlsx":
            self._send_keyword_template_xlsx()
            return
        if path == "/api/news":
            self._send_news()
            return
        if path == "/api/news/favorites":
            self._send_news_favorites()
            return
        if path == "/api/news/shares":
            self._send_news_shares()
            return
        if path.startswith("/api/public/shares/"):
            self._send_public_share(path)
            return
        if path == "/api/news/keywords-list":
            self._send_news_keywords_list()
            return
        if path == "/api/news/sources-list":
            self._send_news_sources_list()
            return
        if path == "/api/auth/me":
            self._send_auth_me()
            return
        if path == "/api/roles":
            self._send_roles()
            return
        if path == "/api/situation-overview":
            self._send_situation_overview()
            return
        if path == "/api/ai-models":
            self._send_ai_models()
            return
        if path == "/api/futures-symbols":
            self._send_futures_symbols()
            return
        if path == "/api/users":
            self._send_users()
            return
        if path == "/api/system-config":
            self._send_system_config()
            return
        super().do_GET()

    def translate_path(self, path):
        parsed_path = urlparse(path).path
        if parsed_path.startswith("/console/"):
            relative = parsed_path.removeprefix("/console/").strip("/")
            if relative:
                return str((CONSOLE_DIR / relative).resolve())
        return super().translate_path(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/keywords/upload":
            self._upload_keywords()
            return
        if path == "/api/keywords":
            self._save_keywords()
            return
        if path == "/api/ai-analysis/reanalyze":
            self._reanalyze_ai()
            return
        if path == "/api/situation-overview/refresh":
            self._refresh_situation_analysis()
            return
        if path == "/api/auth/login":
            self._login()
            return
        if path == "/api/auth/logout":
            self._logout()
            return
        if path == "/api/auth/change-password":
            self._change_password()
            return
        if path == "/api/news/interpret":
            self._interpret_article()
            return
        if path == "/api/news/favorites":
            self._create_news_favorite()
            return
        if path == "/api/news/shares":
            self._create_or_update_news_share()
            return
        if path == "/api/roles":
            self._create_role()
            return
        if path == "/api/ai-models":
            self._update_ai_models()
            return
        if path == "/api/ai-models/auto-interpret":
            self._update_auto_interpret()
            return
        if path == "/api/ai-models/test":
            self._test_ai_model()
            return
        if path == "/api/futures-symbols":
            self._create_futures_symbol()
            return
        if path == "/api/users":
            self._create_user()
            return
        if path == "/api/system-config":
            self._update_system_config()
            return
        self.send_error(404, "Not Found")

    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith("/api/roles/"):
            self._update_role(path)
            return
        if path.startswith("/api/futures-symbols/"):
            self._update_futures_symbol(path)
            return
        if path.startswith("/api/users/"):
            self._update_user(path)
            return
        self.send_error(404, "Not Found")

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/news/favorites/"):
            self._delete_news_favorite(path)
            return
        if path.startswith("/api/roles/"):
            self._delete_role(path)
            return
        if path.startswith("/api/futures-symbols/"):
            self._delete_futures_symbol(path)
            return
        if path.startswith("/api/users/"):
            self._delete_user(path)
            return
        self.send_error(404, "Not Found")

    def _serve_admin_html(self):
        if not ADMIN_HTML_PATH.exists():
            self.send_error(404, "admin.html not found")
            return
        data = ADMIN_HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_console_index(self):
        index_path = CONSOLE_DIR / "index.html"
        if not index_path.exists():
            self.send_error(404, "console index not found")
            return
        data = index_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_console_asset(self, path):
        relative = path.removeprefix("/console/").strip("/")
        if not relative:
            self._serve_console_index()
            return True

        asset_path = (CONSOLE_DIR / relative).resolve()
        console_root = CONSOLE_DIR.resolve()
        if console_root not in asset_path.parents and asset_path != console_root:
            self.send_error(403, "Forbidden")
            return True

        if asset_path.is_file():
            super().do_GET()
            return True

        # Support history routing under /console.
        self._serve_console_index()
        return True

    def _send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False, default=_json_serialize).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("请求体不是合法的 JSON") from exc

    def _client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else ""

    def _build_public_base_url(self):
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "").strip()
        forwarded_host = self.headers.get("X-Forwarded-Host", "").strip()
        host = forwarded_host or self.headers.get("Host", "").strip()
        proto = forwarded_proto or ("https" if self.server.server_port == 443 else "http")
        return f"{proto}://{host}".rstrip("/")

    def _get_session_token(self):
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return ""
        jar = cookies.SimpleCookie()
        jar.load(cookie_header)
        morsel = jar.get(AUTH_COOKIE_NAME)
        return morsel.value if morsel else ""

    def _set_session_cookie(self, token):
        cookie = cookies.SimpleCookie()
        cookie[AUTH_COOKIE_NAME] = token
        cookie[AUTH_COOKIE_NAME]["path"] = "/"
        cookie[AUTH_COOKIE_NAME]["httponly"] = True
        cookie[AUTH_COOKIE_NAME]["samesite"] = "Lax"
        if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
            cookie[AUTH_COOKIE_NAME]["secure"] = True
        self._extra_headers.append(("Set-Cookie", cookie.output(header="").strip()))

    def _clear_session_cookie(self):
        cookie = cookies.SimpleCookie()
        cookie[AUTH_COOKIE_NAME] = ""
        cookie[AUTH_COOKIE_NAME]["path"] = "/"
        cookie[AUTH_COOKIE_NAME]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        cookie[AUTH_COOKIE_NAME]["max-age"] = 0
        cookie[AUTH_COOKIE_NAME]["httponly"] = True
        cookie[AUTH_COOKIE_NAME]["samesite"] = "Lax"
        self._extra_headers.append(("Set-Cookie", cookie.output(header="").strip()))

    def _require_auth(self):
        token = self._get_session_token()
        user = auth_repository.get_session_user(token)
        if not user:
            self._clear_session_cookie()
            self._send_json(401, {"error": "未登录或登录已失效"})
            return None
        return user

    def _parse_id_from_path(self, path, prefix):
        value = path.removeprefix(prefix).strip("/")
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError("无效的 ID") from exc

    def _build_ai_panel_payload(self, result: AIAnalysisResult):
        if not result or not getattr(result, "success", False):
            message = getattr(result, "error", "") or "当前运行未生成 AI 热点分析。"
            return [
                {
                    "title": "核心热点态势",
                    "html": message,
                    "text": message,
                }
            ]

        panels = []

        def add_panel(title, text):
            if not text:
                return
            normalized = _format_list_content(text)
            panels.append(
                {
                    "title": title,
                    "text": normalized,
                    "html": normalized.replace("\n", "<br>"),
                }
            )

        add_panel("核心热点态势", result.core_trends)
        add_panel("舆论风向争议", result.sentiment_controversy)
        add_panel("异动与弱信号", result.signals)
        add_panel("RSS 深度洞察", result.rss_insights)
        add_panel("研判策略建议", result.outlook_strategy)

        if result.standalone_summaries:
            standalone_text = "\n\n".join(
                f"{name}\n{_format_list_content(summary)}"
                for name, summary in result.standalone_summaries.items()
                if summary
            )
            add_panel("独立源点速览", standalone_text)

        return panels or [
            {
                "title": "核心热点态势",
                "html": "当前运行未生成 AI 热点分析。",
                "text": "当前运行未生成 AI 热点分析。",
            }
        ]

    def _load_runtime_analysis_data(self):
        analyzer = NewsAnalyzer(load_config())

        analysis_data = analyzer._load_analysis_data(quiet=True)
        if not analysis_data:
            raise RuntimeError("未找到可用于 AI 分析的热榜数据")

        (
            all_results,
            id_to_name,
            title_info,
            new_titles,
            word_groups,
            filter_words,
            global_filters,
        ) = analysis_data

        mode = analyzer.report_mode
        stats, total_titles = analyzer.ctx.count_frequency(
            all_results,
            word_groups,
            filter_words,
            id_to_name,
            title_info,
            new_titles,
            mode=mode,
            global_filters=global_filters,
            quiet=True,
        )

        rss_items = None
        raw_rss_items = None
        if analyzer.ctx.rss_enabled:
            rss_items, _, raw_rss_items = analyzer._crawl_rss_data()

        standalone_data = analyzer._prepare_standalone_data(
            all_results,
            id_to_name,
            title_info,
            raw_rss_items,
        )

        mode_strategy = analyzer._get_mode_strategy()
        ai_result = analyzer._run_ai_analysis(
            stats=stats,
            rss_items=rss_items,
            mode=mode,
            report_type=mode_strategy["report_type"],
            id_to_name=id_to_name,
            current_results=all_results,
            schedule=analyzer.ctx.create_scheduler().resolve(),
            standalone_data=standalone_data,
        )

        if ai_result is None:
            raise RuntimeError("当前配置未启用 AI 分析或调度器禁止本时段分析")

        report_data = analyzer.ctx.prepare_report(
            stats,
            failed_ids=None,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
        )
        screen_payload = analyzer.ctx.build_screen_data(
            report_data=report_data,
            total_titles=total_titles,
            mode=mode,
            rss_items=rss_items,
            ai_analysis=ai_result,
        )
        return analyzer, ai_result, screen_payload

    def _reanalyze_ai(self):
        try:
            _, ai_result, screen_payload = self._load_runtime_analysis_data()
            panels = self._build_ai_panel_payload(ai_result)
            payload = {
                "success": bool(ai_result.success),
                "panels": panels,
                "screen_payload": screen_payload,
                "meta": {
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "model": getattr(ai_result, "ai_mode", "") or "",
                    "total_news": getattr(ai_result, "total_news", 0),
                    "analyzed_news": getattr(ai_result, "analyzed_news", 0),
                },
            }
            if not ai_result.success:
                payload["error"] = ai_result.error or "AI 分析失败"
                self._send_json(500, payload)
                return

            self._send_json(200, payload)
        except Exception as exc:
            traceback.print_exc()
            self._send_json(500, {"success": False, "error": str(exc)})

    def _send_keywords(self):
        try:
            content = FREQUENCY_WORDS_PATH.read_text(encoding="utf-8")
            self._send_json(
                200,
                {
                    "modules": parse_frequency_words_for_display(content),
                    "updated_at": datetime.fromtimestamp(
                        FREQUENCY_WORDS_PATH.stat().st_mtime
                    ).isoformat(timespec="seconds"),
                },
            )
        except FileNotFoundError:
            self._send_json(404, {"error": "frequency_words.txt 不存在"})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_backups(self):
        backups = []
        if BACKUP_DIR.exists():
            for path in sorted(BACKUP_DIR.glob("frequency_words.*.txt"), reverse=True):
                backups.append(
                    {
                        "name": path.name,
                        "size": path.stat().st_size,
                        "created_at": datetime.fromtimestamp(
                            path.stat().st_mtime
                        ).isoformat(timespec="seconds"),
                    }
                )
        self._send_json(200, {"backups": backups})

    def _send_keyword_template_md(self):
        content = """# 宏观与金融政策
## 经济数据
- 核心经济数据: CPI|PPI|GDP|PMI|非农|失业率
- 央行货币政策: 降息|加息|降准|准备金|利率调整

## 政策法规
- 行业监管政策: 监管|政策|法规|新规|合规

# 地缘政治与国际贸易
## 国际关系
- 中美关系: 中美|贸易战|关税|制裁
- 地缘冲突: 地缘|冲突|战争|军事|局势

## 贸易动态
- 进出口贸易: 出口|进口|贸易|订单

# 市场情绪与盘面特征
## 资金流向
- 资金动向: 资金|增持|减持|北向|主力

## 市场情绪
- 情绪指标: 恐慌|乐观|情绪|信心|预期
"""
        data = content.encode("utf-8")
        self._send_file_download("keyword_template.md", data, "text/markdown")

    def _send_keyword_template_xlsx(self):
        md_content = """# 宏观与金融政策
## 经济数据
- 核心经济数据: CPI|PPI|GDP|PMI|非农|失业率
- 央行货币政策: 降息|加息|降准|准备金|利率调整

## 政策法规
- 行业监管政策: 监管|政策|法规|新规|合规

# 地缘政治与国际贸易
## 国际关系
- 中美关系: 中美|贸易战|关税|制裁
- 地缘冲突: 地缘|冲突|战争|军事|局势

## 贸易动态
- 进出口贸易: 出口|进口|贸易|订单
"""
        # 将标记转换为 xlsx 所需的 rows
        rows = []
        current_module = ""
        current_category = ""
        for line in md_content.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("# "):
                current_module = line[2:]
            elif line.startswith("## "):
                current_category = line[3:]
            elif line.startswith("- "):
                parts = line[2:].split(":", 1)
                title = parts[0].strip()
                keywords = parts[1].strip() if len(parts) > 1 else ""
                rows.append([current_module, current_category, title, keywords])

        data = _build_xlsx_workbook(
            "关键词",
            [["模块", "分类", "标题", "关键词"], *rows],
            column_widths=[22, 16, 20, 36],
        )
        self._send_file_download("keyword_template.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def _send_file_download(self, filename, data, mime_type):
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_upload_file(self):
        content_type = self.headers.get("Content-Type")
        if not content_type:
            raise ValueError("缺少 Content-Type")

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
        )

        file_part = None
        for part in message.iter_parts():
            if part.get_param("name", header="content-disposition") == "file":
                file_part = part
                break

        if file_part is None or not file_part.get_filename():
            raise ValueError("请上传关键词 Markdown 或 XLSX 文件")

        filename = Path(file_part.get_filename()).name
        if not filename.lower().endswith((".md", ".markdown", ".xlsx")):
            raise ValueError("当前支持上传 .md、.markdown 或 .xlsx 文件")

        data = file_part.get_payload(decode=True) or b""
        if not data:
            raise ValueError("上传文件为空")
        if filename.lower().endswith(".xlsx"):
            return filename, _xlsx_to_markdown(io.BytesIO(data))
        return filename, data.decode("utf-8-sig")

    def _send_news_keywords_list(self):
        """返回关键词列表，用户常用关键词在前，系统关键词在后。"""
        user = self._require_auth()
        if not user:
            return
        try:
            user_keywords = user_keyword_repository.get_user_keywords(user["id"], limit=20)

            system_keywords = _extract_system_keywords()
            seen = {uk["keyword"] for uk in user_keywords}
            remaining = [kw for kw in system_keywords if kw not in seen]

            self._send_json(200, {
                "keywords": {
                    "user": user_keywords,
                    "system": remaining,
                },
            })
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_news(self):
        """分页查询资讯（支持关键词、日期和来源筛选）。"""
        user = self._require_auth()
        if not user:
            return
        try:
            from trendradar.storage.news_repository import query_articles

            query = parse_qs(urlparse(self.path).query)
            keyword = query.get("keyword", [None])[0]
            query_date = query.get("date", [None])[0]
            source = query.get("source", [None])[0]
            favorite_only = query.get("favorite_only", ["0"])[0] in ("1", "true", "True")
            page = int(query.get("page", ["1"])[0])
            page_size = int(query.get("page_size", ["200"])[0])
            if keyword and keyword.strip():
                try:
                    user_keyword_repository.record_usage(user["id"], keyword.strip())
                except Exception:
                    pass
            favorite_article_ids = None
            if favorite_only:
                favorite_article_ids = list(
                    news_favorite_repository.get_favorite_article_ids(user["id"])
                )

            rows, total = query_articles(
                keyword=keyword,
                query_date=query_date,
                source_name=source,
                favorite_only=favorite_only,
                favorite_article_ids=favorite_article_ids,
                page=page,
                page_size=page_size,
            )
            favorite_map = news_favorite_repository.get_favorite_map(
                user["id"],
                [row["id"] for row in rows],
            )
            share_map = self._get_share_map(user["id"], [row["id"] for row in rows])
            for row in rows:
                favorite = favorite_map.get(row["id"])
                row["is_favorite"] = bool(favorite)
                row["favorite"] = favorite or None
                share = share_map.get(row["id"])
                row["is_shared"] = bool(share)
                row["share"] = share or None
            self._send_json(200, {
                "items": rows,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": max(1, (total + page_size - 1) // page_size),
            })
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _get_share_map(self, user_id, article_ids):
        article_ids = [int(article_id) for article_id in article_ids if article_id is not None]
        if not article_ids:
            return {}
        share_map = {}
        for article_id in article_ids:
            share = news_share_repository.get_share_by_article_and_user(article_id, user_id)
            if share:
                share_map[article_id] = share
        return share_map

    def _send_news_favorites(self):
        user = self._require_auth()
        if not user:
            return
        try:
            query = parse_qs(urlparse(self.path).query)
            article_ids = [
                int(value)
                for value in query.get("article_id", [])
                if str(value).isdigit()
            ]
            favorites = news_favorite_repository.get_favorite_map(user["id"], article_ids)
            self._send_json(200, {"favorites": favorites})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_news_shares(self):
        user = self._require_auth()
        if not user:
            return
        try:
            query = parse_qs(urlparse(self.path).query)
            article_id = int(query.get("article_id", ["0"])[0])
            share = news_share_repository.get_share_by_article_and_user(article_id, user["id"])
            self._send_json(200, {"share": share})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _create_news_favorite(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            article_id = int(payload.get("article_id", 0))
            title = str(payload.get("title", "") or "").strip()
            thought = str(payload.get("thought", "") or "").strip()
            if article_id <= 0:
                raise ValueError("文章 ID 无效")
            favorite = news_favorite_repository.add_favorite(
                article_id=article_id,
                user_id=user["id"],
                thought=thought,
                title=title,
            )
            self._send_json(201, {"favorite": favorite})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _interpret_article(self):
        user = self._require_auth()
        if not user:
            return
        try:
            from trendradar.ai.news_interpreter import enqueue_article_interpretation_force
            from trendradar.storage import news_repository

            payload = self._read_json_body()
            article_id = int(payload.get("article_id", 0))
            if article_id <= 0:
                raise ValueError("文章 ID 无效")

            article = news_repository.get_article_for_ai_interpretation(article_id)
            if not article:
                self._send_json(404, {"success": False, "reason": "文章不存在"})
                return

            status = article.get("ai_interpret_status", "")
            if status == "已解读":
                symbols = news_repository.get_article_ai_symbols(article_id)
                self._send_json(200, {
                    "success": True,
                    "one_line_summary": article.get("ai_one_line_summary", ""),
                    "symbols": symbols,
                })
                return
            if status == "解读中":
                self._send_json(200, {"success": True, "queued": True})
                return

            enqueue_article_interpretation_force([article_id])
            self._send_json(200, {"success": True, "queued": True})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _create_or_update_news_share(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            article_id = int(payload.get("article_id", 0))
            title = str(payload.get("title", "") or "").strip()
            thought = str(payload.get("thought", "") or "").strip()
            if article_id <= 0:
                raise ValueError("文章 ID 无效")
            share = news_share_repository.upsert_share(
                article_id=article_id,
                user_id=user["id"],
                title=title,
                thought=thought,
                share_base_url=self._build_public_base_url(),
            )
            self._send_json(201, {"share": share})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _delete_news_favorite(self, path):
        user = self._require_auth()
        if not user:
            return
        try:
            article_id = self._parse_id_from_path(path, "/api/news/favorites/")
            deleted = news_favorite_repository.remove_favorite(article_id, user["id"])
            self._send_json(200, {"deleted": deleted})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_public_share(self, path):
        try:
            share_token = path.removeprefix("/api/public/shares/").strip("/")
            if not share_token:
                self.send_error(404, "Not Found")
                return
            share = news_share_repository.get_share_detail_by_token(share_token)
            if not share:
                self.send_error(404, "Not Found")
                return
            self._send_json(200, {"share": share})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_news_sources_list(self):
        """返回所有已存储的来源名称列表（用于筛选下拉框）。"""
        try:
            from trendradar.storage.news_repository import get_all_source_names
            sources = get_all_source_names()
            self._send_json(200, {"sources": sources})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _backup_frequency_file(self):
        if not FREQUENCY_WORDS_PATH.exists():
            return None
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = BACKUP_DIR / f"frequency_words.{timestamp}.txt"
        shutil.copy2(FREQUENCY_WORDS_PATH, backup_path)
        return backup_path

    def _save_keywords(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            content = str(payload.get("content", "") or "")
            if not content.strip():
                raise ValueError("关键词内容不能为空")

            FREQUENCY_WORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            backup_path = self._backup_frequency_file()
            FREQUENCY_WORDS_PATH.write_text(content, encoding="utf-8")

            modules = parse_frequency_words_for_display(content)
            self._send_json(
                200,
                {
                    "message": "关键词已保存",
                    "backup": backup_path.name if backup_path else None,
                    "modules": modules,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except PermissionError:
            self._send_json(
                500,
                {"error": "无法写入 frequency_words.txt，请确认 config 目录可写"},
            )
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _upload_keywords(self):
        try:
            filename, content = self._read_upload_file()
            new_frequency_text = convert_keyword_markdown_to_frequency_text(content)

            FREQUENCY_WORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            backup_path = self._backup_frequency_file()
            FREQUENCY_WORDS_PATH.write_text(new_frequency_text, encoding="utf-8")

            modules = parse_frequency_words_for_display(new_frequency_text)
            self._send_json(
                200,
                {
                    "message": "关键词已更新",
                    "filename": filename,
                    "backup": backup_path.name if backup_path else None,
                    "modules": modules,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except PermissionError:
            self._send_json(
                500,
                {"error": "无法写入 frequency_words.txt，请确认 config 目录可写"},
            )
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_auth_me(self):
        user = self._require_auth()
        if not user:
            return
        self._send_json(200, {"user": user})

    def _login(self):
        try:
            payload = self._read_json_body()
            result = auth_repository.authenticate_user(
                username=payload.get("username", ""),
                password=payload.get("password", ""),
                login_ip=self._client_ip(),
                user_agent=self.headers.get("User-Agent", ""),
            )
            self._set_session_cookie(result["session_token"])
            self._send_json(200, {"user": result["user"], "expires_at": result["expires_at"]})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _logout(self):
        try:
            token = self._get_session_token()
            auth_repository.logout_session(token)
            self._clear_session_cookie()
            self._send_json(200, {"message": "已退出登录"})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _change_password(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            auth_repository.change_password(
                user_id=user["id"],
                old_password=payload.get("old_password", ""),
                new_password=payload.get("new_password", ""),
            )
            self._clear_session_cookie()
            self._send_json(200, {"message": "密码修改成功，请重新登录"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_roles(self):
        user = self._require_auth()
        if not user:
            return
        try:
            self._send_json(200, {"items": auth_repository.list_roles()})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_situation_overview(self):
        user = self._require_auth()
        if not user:
            return
        try:
            from trendradar.storage.news_repository import (
                get_latest_articles,
                get_situation_stats,
                get_situation_symbol_stats,
            )
            from trendradar.ai.situation_analyzer import get_latest_analysis

            query = parse_qs(urlparse(self.path).query)
            try:
                top_limit = int((query.get("top_limit") or ["10"])[0])
            except (TypeError, ValueError):
                top_limit = 10
            if top_limit not in (10, 15, 20, 30):
                top_limit = 10

            stats = get_situation_stats()
            symbol_stats = get_situation_symbol_stats(top_limit=top_limit)
            articles = get_latest_articles(limit=40)
            analysis = get_latest_analysis()

            self._send_json(
                200,
                {
                    "stats": stats,
                    "symbol_stats": symbol_stats,
                    "articles": articles,
                    "analysis": analysis,
                    "top_limit": top_limit,
                },
            )
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _refresh_situation_analysis(self):
        user = self._require_auth()
        if not user:
            return

        username = user.get("username") if isinstance(user, dict) else str(user)

        # 互斥：同一时刻只允许一次解读执行，并发请求直接 409
        if not _SITUATION_REFRESH_LOCK.acquire(blocking=False):
            print(
                f"[situation-refresh] 用户 {username} 请求被拒绝：已有解读任务正在进行"
            )
            self._send_json(
                409,
                {
                    "success": False,
                    "error": "已有 AI 解读任务正在执行，请稍后重试",
                },
            )
            return

        started = datetime.now()
        print(f"[situation-refresh] 用户 {username} 触发 AI 态势解读，开始执行 ...")

        try:
            from trendradar.ai.situation_analyzer import (
                run_situation_analysis,
                get_latest_analysis,
            )

            result = run_situation_analysis()
            elapsed = (datetime.now() - started).total_seconds()

            if not result.get("success"):
                err = result.get("error", "AI 解读失败")
                print(
                    f"[situation-refresh] 用户 {username} 解读失败（耗时 {elapsed:.1f}s）："
                    f"{err}"
                )
                self._send_json(
                    500,
                    {"success": False, "error": err, "elapsed": elapsed},
                )
                return

            print(
                f"[situation-refresh] 用户 {username} 解读完成（耗时 {elapsed:.1f}s）"
            )
            self._send_json(
                200,
                {
                    "success": True,
                    "elapsed": elapsed,
                    "analysis": get_latest_analysis(),
                },
            )
        except Exception as exc:
            traceback.print_exc()
            print(f"[situation-refresh] 用户 {username} 解读异常：{exc}")
            self._send_json(500, {"success": False, "error": str(exc)})
        finally:
            _SITUATION_REFRESH_LOCK.release()

    def _send_ai_models(self):
        user = self._require_auth()
        if not user:
            return
        try:
            self._send_json(
                200,
                {
                    "settings": ai_model_repository.get_settings(),
                    "provider_presets": ai_model_repository.get_provider_presets(),
                },
            )
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_futures_symbols(self):
        user = self._require_auth()
        if not user:
            return
        try:
            self._send_json(200, {"items": futures_symbol_repository.list_symbols()})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _update_ai_models(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            settings = ai_model_repository.update_settings(payload)
            self._send_json(
                200,
                {
                    "settings": settings,
                    "message": "AI 模型配置已保存",
                },
            )
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _update_auto_interpret(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body() or {}
            if "auto_interpret_enabled" not in payload:
                self._send_json(400, {"error": "缺少 auto_interpret_enabled 字段"})
                return
            enabled = payload["auto_interpret_enabled"]
            settings = ai_model_repository.update_auto_interpret(enabled)
            username = user.get("username") if isinstance(user, dict) else str(user)
            state = "开启" if settings.get("auto_interpret_enabled") else "关闭"
            print(f"[ai-models] 用户 {username} {state} 自动解读")
            self._send_json(
                200,
                {
                    "settings": settings,
                    "message": f"自动解读已{state}",
                },
            )
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _test_ai_model(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            model_type = str(payload.get("model_type", "") or "").strip()
            result = ai_model_repository.test_model_connection(model_type, payload)
            self._send_json(200, result)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _create_role(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            item = auth_repository.create_role(
                name=payload.get("name", ""),
                description=payload.get("description", ""),
            )
            self._send_json(201, {"item": item})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _create_futures_symbol(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            item = futures_symbol_repository.create_symbol(
                name=payload.get("name", ""),
                code=payload.get("code", ""),
                sector=payload.get("sector", ""),
                exchange=payload.get("exchange", ""),
            )
            self._send_json(201, {"item": item})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _update_role(self, path):
        user = self._require_auth()
        if not user:
            return
        try:
            role_id = self._parse_id_from_path(path, "/api/roles/")
            payload = self._read_json_body()
            item = auth_repository.update_role(
                role_id=role_id,
                name=payload.get("name", ""),
                description=payload.get("description", ""),
            )
            self._send_json(200, {"item": item})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _update_futures_symbol(self, path):
        user = self._require_auth()
        if not user:
            return
        try:
            symbol_id = self._parse_id_from_path(path, "/api/futures-symbols/")
            payload = self._read_json_body()
            item = futures_symbol_repository.update_symbol(
                symbol_id=symbol_id,
                name=payload.get("name", ""),
                code=payload.get("code", ""),
                sector=payload.get("sector", ""),
                exchange=payload.get("exchange", ""),
            )
            self._send_json(200, {"item": item})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _delete_role(self, path):
        user = self._require_auth()
        if not user:
            return
        try:
            role_id = self._parse_id_from_path(path, "/api/roles/")
            auth_repository.delete_role(role_id)
            self._send_json(200, {"message": "角色已删除"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _delete_futures_symbol(self, path):
        user = self._require_auth()
        if not user:
            return
        try:
            symbol_id = self._parse_id_from_path(path, "/api/futures-symbols/")
            futures_symbol_repository.delete_symbol(symbol_id)
            self._send_json(200, {"message": "期货品种已删除"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_users(self):
        user = self._require_auth()
        if not user:
            return
        try:
            self._send_json(200, {"items": auth_repository.list_users()})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _create_user(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()
            item = auth_repository.create_user(
                username=payload.get("username", ""),
                password=payload.get("password", ""),
                full_name=payload.get("full_name", ""),
                role_ids=payload.get("role_ids", []),
                is_active=payload.get("is_active", True),
            )
            self._send_json(201, {"item": item})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _update_user(self, path):
        current_user = self._require_auth()
        if not current_user:
            return
        try:
            user_id = self._parse_id_from_path(path, "/api/users/")
            payload = self._read_json_body()
            item = auth_repository.update_user(
                user_id=user_id,
                username=payload.get("username", ""),
                full_name=payload.get("full_name", ""),
                role_ids=payload.get("role_ids", []),
                is_active=payload.get("is_active", True),
                password=payload.get("password", ""),
            )
            self._send_json(200, {"item": item})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _delete_user(self, path):
        current_user = self._require_auth()
        if not current_user:
            return
        try:
            user_id = self._parse_id_from_path(path, "/api/users/")
            if current_user["id"] == user_id:
                raise ValueError("不能删除当前登录用户")
            auth_repository.delete_user(user_id)
            self._send_json(200, {"message": "用户已删除"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})


    def _send_system_config(self):
        user = self._require_auth()
        if not user:
            return
        try:
            config_path = CONFIG_DIR / "config.yaml"
            interval = 0
            page_size = 200
            max_load_count = 2000
            email_from = ""
            email_password = ""
            email_to = ""
            email_smtp_server = ""
            email_smtp_port = ""
            email_schedule = ""
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                advanced = config.get("advanced", {}) or {}
                interval = (
                    advanced.get("crawler", {}).get("crawl_interval_minutes", 0)
                ) or 0
                console_cfg = advanced.get("console", {}) or {}
                page_size = int(console_cfg.get("opinion_page_size", page_size) or page_size)
                max_load_count = int(
                    console_cfg.get("opinion_max_load_count", max_load_count) or max_load_count
                )
                email_cfg = (
                    config.get("notification", {}) or {}
                ).get("channels", {}).get("email", {}) or {}
                email_from = email_cfg.get("from", "") or ""
                email_password = email_cfg.get("password", "") or ""
                email_to = email_cfg.get("to", "") or ""
                email_smtp_server = email_cfg.get("smtp_server", "") or ""
                email_smtp_port = str(email_cfg.get("smtp_port", "") or "")
                email_schedule = email_cfg.get("schedule", "") or ""
                notif_cfg = config.get("notification", {}) or {}
                channels_cfg = notif_cfg.get("channels", {}) or {}
                feishu_cfg = channels_cfg.get("feishu", {}) or {}
                dingtalk_cfg = channels_cfg.get("dingtalk", {}) or {}
                wework_cfg = channels_cfg.get("wework", {}) or {}
                notification_schedule = notif_cfg.get("notification_schedule", "") or ""
            self._send_json(
                200,
                {
                    "crawl_interval_minutes": int(interval),
                    "cron_schedule": os.environ.get("CRON_SCHEDULE", "*/30 * * * *"),
                    "available_intervals": [1, 3, 5, 10, 15, 30],
                    "opinion_page_size": page_size,
                    "opinion_max_load_count": max_load_count,
                    "email_from": email_from,
                    "email_password": email_password,
                    "email_to": email_to,
                    "email_smtp_server": email_smtp_server,
                    "email_smtp_port": email_smtp_port,
                    "email_schedule": email_schedule,
                    "email_schedule_options": [
                        {"label": _EMAIL_SCHEDULE_LABELS[v], "value": v}
                        for v in _EMAIL_SCHEDULE_OPTIONS
                    ],
                    "feishu_webhook_url": feishu_cfg.get("webhook_url", "") or "",
                    "dingtalk_webhook_url": dingtalk_cfg.get("webhook_url", "") or "",
                    "wework_webhook_url": wework_cfg.get("webhook_url", "") or "",
                    "notification_schedule": notification_schedule,
                    "notification_schedule_options": [
                        {"label": _EMAIL_SCHEDULE_LABELS[v], "value": v}
                        for v in _EMAIL_SCHEDULE_OPTIONS
                    ],
                },
            )
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _update_system_config(self):
        user = self._require_auth()
        if not user:
            return
        try:
            payload = self._read_json_body()

            updates = {}  # 字段名 -> 新值（int）
            messages = []

            if "crawl_interval_minutes" in payload:
                interval = int(payload.get("crawl_interval_minutes", 0))
                if interval not in (0, 1, 3, 5, 10, 15, 30):
                    raise ValueError("抓取频率必须是 0/1/3/5/10/15/30 之一")
                updates["crawl_interval_minutes"] = interval
                messages.append(
                    f"抓取频率已更新为 {interval} 分钟" if interval > 0 else "已切换为外部 cron 频率"
                )

            page_size_raw = payload.get("opinion_page_size")
            max_load_raw = payload.get("opinion_max_load_count")
            if page_size_raw is not None or max_load_raw is not None:
                page_size = int(page_size_raw) if page_size_raw is not None else 200
                max_load = int(max_load_raw) if max_load_raw is not None else 2000
                if not (10 <= page_size <= 500):
                    raise ValueError("单次加载条数必须在 10-500 之间")
                if not (10 <= max_load <= 10000):
                    raise ValueError("最多加载条数必须在 10-10000 之间")
                if max_load < page_size:
                    raise ValueError("最多加载条数不能小于单次加载条数")
                # 向上对齐到 page_size 的整数倍，避免最后一页越界
                if max_load % page_size != 0:
                    max_load = (max_load // page_size + 1) * page_size
                    max_load = min(max_load, 10000)
                updates["opinion_page_size"] = page_size
                updates["opinion_max_load_count"] = max_load
                messages.append(f"资讯列表加载已更新：每次 {page_size} 条，最多 {max_load} 条")

            # 邮件配置字段
            email_fields = ("email_from", "email_password", "email_to", "email_smtp_server", "email_smtp_port", "email_schedule")
            has_email_update = any(k in payload for k in email_fields)
            if has_email_update:
                if "email_from" in payload:
                    v = str(payload["email_from"]).strip()
                    if v and "@" not in v:
                        raise ValueError("发件人邮箱格式不正确")
                    updates["email_from"] = v
                if "email_password" in payload:
                    updates["email_password"] = str(payload["email_password"])
                if "email_to" in payload:
                    updates["email_to"] = str(payload["email_to"]).strip()
                if "email_smtp_server" in payload:
                    updates["email_smtp_server"] = str(payload["email_smtp_server"]).strip()
                if "email_smtp_port" in payload:
                    port_raw = payload["email_smtp_port"]
                    if port_raw == "" or port_raw is None:
                        updates["email_smtp_port"] = ""
                    else:
                        port = int(port_raw)
                        if not (1 <= port <= 65535):
                            raise ValueError("SMTP 端口必须在 1-65535 之间")
                        updates["email_smtp_port"] = str(port)
                if "email_schedule" in payload:
                    schedule_val = str(payload["email_schedule"]).strip()
                    if schedule_val not in _EMAIL_SCHEDULE_OPTIONS:
                        raise ValueError("发送时间选项无效")
                    updates["email_schedule"] = schedule_val
                messages.append("邮件配置已更新")

            # 飞书/钉钉/企业微信 webhook_url（共用 notification_schedule）
            _notif_channels = ("feishu", "dingtalk", "wework")
            _notif_names = {"feishu": "飞书", "dingtalk": "钉钉", "wework": "企业微信"}
            notif_changed = False
            for ch in _notif_channels:
                if f"{ch}_webhook_url" in payload:
                    updates[f"{ch}_webhook_url"] = str(payload[f"{ch}_webhook_url"]).strip()
                    notif_changed = True
            if "notification_schedule" in payload:
                sv = str(payload["notification_schedule"]).strip()
                if sv not in _EMAIL_SCHEDULE_OPTIONS:
                    raise ValueError("推送渠道发送时间选项无效")
                updates["notification_schedule"] = sv
                notif_changed = True
            if notif_changed:
                messages.append("推送渠道配置已更新")

            if not updates:
                raise ValueError("没有需要更新的字段")

            config_path = CONFIG_DIR / "config.yaml"
            if not config_path.exists():
                raise RuntimeError("config.yaml 不存在")

            content = config_path.read_text(encoding="utf-8")
            content = _apply_config_updates(content, updates)
            config_path.write_text(content, encoding="utf-8")

            response = {"message": "；".join(messages)}
            response.update(updates)
            self._send_json(200, response)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

def run(host="0.0.0.0", port=8080):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    auth_repository.ensure_schema()
    ai_model_repository.ensure_schema()
    futures_symbol_repository.ensure_schema()
    ensure_news_article_columns()
    news_favorite_repository.ensure_schema()
    news_share_repository.ensure_schema()
    user_keyword_repository.ensure_schema()
    try:
        from trendradar.ai.news_interpreter import enqueue_pending_interpretations
        pending = enqueue_pending_interpretations(limit=30)
        if pending:
            print(f"AI 新闻解读启动补跑任务: {pending} 条")
    except Exception as exc:
        print(f"AI 新闻解读补跑任务启动失败: {exc}")

    # 启动态势解读定时线程（每小时一次）
    def _situation_analysis_loop():
        import time as _time
        # 首次启动延迟 30 秒，等待服务就绪
        _time.sleep(30)
        while True:
            if not _SITUATION_REFRESH_LOCK.acquire(blocking=False):
                print("态势解读跳过本轮：已有解读任务正在执行")
            else:
                try:
                    from trendradar.ai.situation_analyzer import run_situation_analysis
                    result = run_situation_analysis()
                    if result.get("success"):
                        print(f"态势解读完成：{result.get('total_articles', 0)} 条新闻")
                    else:
                        print(f"态势解读跳过：{result.get('error', '未知错误')}")
                except Exception as exc:
                    print(f"态势解读执行失败: {exc}")
                finally:
                    _SITUATION_REFRESH_LOCK.release()
            _time.sleep(3600)

    sit_thread = threading.Thread(
        target=_situation_analysis_loop,
        name="situation-analyzer",
        daemon=True,
    )
    sit_thread.start()

    # 启动邮件定时发送线程
    def _email_schedule_loop():
        import time as _time
        last_sent_minute = None
        _time.sleep(60)  # 启动延迟，等待服务就绪
        while True:
            _time.sleep(30)
            try:
                config_path = CONFIG_DIR / "config.yaml"
                if not config_path.exists():
                    continue
                with open(config_path, "r", encoding="utf-8") as _f:
                    _cfg = yaml.safe_load(_f) or {}
                email_cfg = (
                    _cfg.get("notification", {}) or {}
                ).get("channels", {}).get("email", {}) or {}
                schedule_expr = email_cfg.get("schedule", "") or ""
                if not schedule_expr:
                    continue
                trigger_hours = _parse_hourly_cron_hours(schedule_expr)
                if not trigger_hours:
                    continue
                now = datetime.now()
                current_minute = now.replace(second=0, microsecond=0)
                if current_minute == last_sent_minute:
                    continue
                if now.hour in trigger_hours and now.minute == 0:
                    last_sent_minute = current_minute
                    html_path = OUTPUT_DIR / "index.html"
                    if not html_path.exists():
                        print(f"[邮件调度] index.html 不存在，跳过本次发送")
                        continue
                    from_email = email_cfg.get("from", "") or ""
                    password = email_cfg.get("password", "") or ""
                    to_email = email_cfg.get("to", "") or ""
                    smtp_server = email_cfg.get("smtp_server", "") or ""
                    smtp_port = email_cfg.get("smtp_port", "") or ""
                    if not from_email or not password or not to_email:
                        print(f"[邮件调度] 邮件配置不完整，跳过本次发送")
                        continue
                    print(f"[邮件调度] 触发定时发送 ({now.strftime('%H:%M')})")
                    try:
                        import hashlib as _hashlib
                        from trendradar.notification.senders import send_to_email
                        from trendradar.storage import email_log_repository as _email_log
                        html_content = html_path.read_bytes()
                        content_md5 = _hashlib.md5(html_content).hexdigest()
                        if _email_log.has_been_sent(content_md5):
                            print(f"[邮件调度] 内容未变化（md5={content_md5[:8]}…），跳过发送")
                            continue
                        ok = send_to_email(
                            from_email=from_email,
                            password=password,
                            to_email=to_email,
                            report_type="定时报告",
                            html_file_path=str(html_path),
                            custom_smtp_server=smtp_server or None,
                            custom_smtp_port=int(smtp_port) if smtp_port else None,
                        )
                        if ok:
                            _email_log.record_send(from_email, to_email, content_md5)
                        else:
                            print("[邮件调度] 发送器返回失败，未记录发送日志")
                    except Exception as _exc:
                        print(f"[邮件调度] 发送失败: {_exc}")
            except Exception as _exc:
                print(f"[邮件调度] 调度循环异常: {_exc}")

    email_thread = threading.Thread(
        target=_email_schedule_loop,
        name="email-scheduler",
        daemon=True,
    )
    email_thread.start()

    # 启动飞书/钉钉/企业微信定时推送线程
    def _notification_schedule_loop():
        import time as _time
        last_sent_minute: dict = {}  # channel -> last triggered datetime
        _time.sleep(60)
        while True:
            _time.sleep(30)
            try:
                config_path = CONFIG_DIR / "config.yaml"
                if not config_path.exists():
                    continue
                with open(config_path, "r", encoding="utf-8") as _f:
                    _cfg = yaml.safe_load(_f) or {}
                notif_cfg = _cfg.get("notification", {}) or {}
                channels_cfg = notif_cfg.get("channels", {}) or {}
                schedule_expr = notif_cfg.get("notification_schedule", "") or ""
                now = datetime.now()
                current_minute = now.replace(second=0, microsecond=0)

                trigger_hours = _parse_hourly_cron_hours(schedule_expr)
                if not trigger_hours:
                    continue
                if now.hour not in trigger_hours or now.minute != 0:
                    continue

                configured_channels = []
                for channel in ("feishu", "dingtalk", "wework"):
                    ch_cfg = channels_cfg.get(channel, {}) or {}
                    webhook_url = ch_cfg.get("webhook_url", "") or ""
                    if not webhook_url:
                        continue
                    if last_sent_minute.get(channel) == current_minute:
                        continue
                    configured_channels.append((channel, ch_cfg, webhook_url))

                if not configured_channels:
                    continue

                html_path = OUTPUT_DIR / "index.html"
                screen_data_path = OUTPUT_DIR / "screen-data.json"
                if not html_path.exists() or not screen_data_path.exists():
                    print("[通知调度] 报告文件不存在，先触发一次报告生成")
                    try:
                        analyzer = NewsAnalyzer(config=load_config())
                        analyzer.run()
                    except Exception as _exc:
                        print(f"[通知调度] 报告生成失败: {_exc}")
                        continue

                try:
                    latest_mtime = max(
                        html_path.stat().st_mtime if html_path.exists() else 0,
                        screen_data_path.stat().st_mtime if screen_data_path.exists() else 0,
                    )
                    if latest_mtime < current_minute.timestamp():
                        print(f"[通知调度] 触发报告刷新 ({now.strftime('%H:%M')})")
                        analyzer = NewsAnalyzer(config=load_config())
                        analyzer.run()
                except Exception as _exc:
                    print(f"[通知调度] 报告刷新失败: {_exc}")
                    continue

                report_data = _load_screen_report_data()
                if not report_data:
                    print("[通知调度] 无法读取最新报告数据，跳过本次渠道推送")
                    continue

                message = _build_scheduled_notification_message(report_data)
                content_md5 = hashlib.md5(message.encode("utf-8")).hexdigest()

                for channel, ch_cfg, webhook_url in configured_channels:
                    last_sent_minute[channel] = current_minute
                    try:
                        from trendradar.storage import notification_log_repository as _notif_log
                        if _notif_log.has_been_sent(channel, content_md5):
                            print(f"[通知调度/{channel}] 内容未变化（md5={content_md5[:8]}…），跳过")
                            continue
                        print(f"[通知调度/{channel}] 触发定时推送 ({now.strftime('%H:%M')})")
                        ok = _send_scheduled_channel(
                            channel,
                            webhook_url,
                            message,
                            msg_type=ch_cfg.get("msg_type", "markdown"),
                        )
                        if ok:
                            _notif_log.record_send(channel, webhook_url, content_md5)
                        else:
                            print(f"[通知调度/{channel}] 发送器返回失败，未记录发送日志")
                    except Exception as _exc:
                        print(f"[通知调度/{channel}] 推送失败: {_exc}")
            except Exception as _exc:
                print(f"[通知调度] 调度循环异常: {_exc}")

    notif_thread = threading.Thread(
        target=_notification_schedule_loop,
        name="notification-scheduler",
        daemon=True,
    )
    notif_thread.start()

    server = ThreadingHTTPServer((host, port), AdminRequestHandler)
    print(f"TrendRadar 管理服务已启动: http://{host}:{port}")
    print(f"报告目录: {OUTPUT_DIR}")
    print(f"关键词文件: {FREQUENCY_WORDS_PATH}")
    print(f"Console 目录: {CONSOLE_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    run(port=int(os.environ.get("WEBSERVER_PORT", "8080")))
