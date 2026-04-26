# coding=utf-8
"""
TrendRadar 管理 Web 服务。

服务 output 目录静态文件，同时提供关键词维护 API。
"""

import io
import json
import os
import shutil
import zipfile
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

from trendradar.core.frequency import (
    convert_keyword_markdown_to_frequency_text,
    parse_frequency_words_for_display,
)


OUTPUT_DIR = Path(os.environ.get("WEBSERVER_DIR", "/app/output"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))
FREQUENCY_WORDS_PATH = Path(
    os.environ.get("FREQUENCY_WORDS_PATH", str(CONFIG_DIR / "frequency_words.txt"))
)
BACKUP_DIR = Path(os.environ.get("FREQUENCY_BACKUP_DIR", str(CONFIG_DIR / "backups")))
ADMIN_HTML_PATH = Path(__file__).resolve().parent / "static" / "admin.html"
XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


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
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/admin.html":
            self._serve_admin_html()
            return
        if path == "/api/keywords":
            self._send_keywords()
            return
        if path == "/api/keywords/backups":
            self._send_backups()
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/keywords/upload":
            self._upload_keywords()
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

    def _send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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


def run(host="0.0.0.0", port=8080):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), AdminRequestHandler)
    print(f"TrendRadar 管理服务已启动: http://{host}:{port}")
    print(f"报告目录: {OUTPUT_DIR}")
    print(f"关键词文件: {FREQUENCY_WORDS_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    run(port=int(os.environ.get("WEBSERVER_PORT", "8080")))
