# coding=utf-8
"""
TrendRadar 管理 Web 服务。

服务 output 目录静态文件，同时提供关键词维护与 AI 分析 API。
"""

import io
import json
import os
import shutil
import zipfile
import traceback
from http import cookies
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree

from trendradar.__main__ import NewsAnalyzer
from trendradar.ai.analyzer import AIAnalysisResult
from trendradar.ai.formatter import _format_list_content
from trendradar.core import load_config
from trendradar.core.frequency import (
    convert_keyword_markdown_to_frequency_text,
    parse_frequency_words_for_display,
)
from trendradar.storage import auth_repository
from trendradar.storage import news_favorite_repository
from trendradar.storage import news_share_repository
from trendradar.storage.news_repository import ensure_news_article_columns


OUTPUT_DIR = Path(os.environ.get("WEBSERVER_DIR", "/app/output"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))
CONSOLE_DIR = Path(os.environ.get("CONSOLE_DIST_DIR", "/app/console-dist"))
FREQUENCY_WORDS_PATH = Path(
    os.environ.get("FREQUENCY_WORDS_PATH", str(CONFIG_DIR / "frequency_words.txt"))
)
BACKUP_DIR = Path(os.environ.get("FREQUENCY_BACKUP_DIR", str(CONFIG_DIR / "backups")))
ADMIN_HTML_PATH = Path(__file__).resolve().parent / "static" / "admin.html"
XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
AUTH_COOKIE_NAME = os.environ.get("AUTH_COOKIE_NAME", "trendradar_console_session")


def _xlsx_column_name(cell_ref):
    return "".join(ch for ch in cell_ref if ch.isalpha())


def _xlsx_column_index(cell_ref):
    name = _xlsx_column_name(cell_ref)
    index = 0
    for char in name:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index - 1


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
        if path == "/api/users":
            self._send_users()
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
        if path == "/api/ai-analysis/reanalyze":
            self._reanalyze_ai()
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
        if path == "/api/news/favorites":
            self._create_news_favorite()
            return
        if path == "/api/news/shares":
            self._create_or_update_news_share()
            return
        if path == "/api/roles":
            self._create_role()
            return
        if path == "/api/users":
            self._create_user()
            return
        self.send_error(404, "Not Found")

    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith("/api/roles/"):
            self._update_role(path)
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
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
        """返回所有已存储的关键词列表（用于筛选下拉框）。"""
        try:
            from trendradar.storage.news_repository import get_all_keywords
            keywords = get_all_keywords()
            self._send_json(200, {"keywords": keywords})
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


def run(host="0.0.0.0", port=8080):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    auth_repository.ensure_schema()
    ensure_news_article_columns()
    news_favorite_repository.ensure_schema()
    news_share_repository.ensure_schema()
    server = ThreadingHTTPServer((host, port), AdminRequestHandler)
    print(f"TrendRadar 管理服务已启动: http://{host}:{port}")
    print(f"报告目录: {OUTPUT_DIR}")
    print(f"关键词文件: {FREQUENCY_WORDS_PATH}")
    print(f"Console 目录: {CONSOLE_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    run(port=int(os.environ.get("WEBSERVER_PORT", "8080")))
