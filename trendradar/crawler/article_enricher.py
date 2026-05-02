# coding=utf-8
"""
新闻详情增强模块

为部分来源补充摘要和正文内容，避免把来源特化逻辑散落到主流程中。
当前支持：
- 金十数据
- 金十期货
- 新浪财经 7x24
- 财联社热门
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class ArticleContentEnricher:
    """按来源补充新闻摘要和正文内容。"""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    SUPPORTED_SOURCE_IDS = {
        "jin10": "_enrich_jin10_article",
        "jin10-futures": "_enrich_jin10_futures_article",
        "sina-finance-7x24": "_enrich_sina_finance_article",
        "cls-hot": "_enrich_cls_article",
    }

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        timeout: int = 10,
        request_interval: float = 0.15,
    ):
        self.proxy_url = proxy_url
        self.timeout = timeout
        self.request_interval = request_interval
        self._session = requests.Session()
        self._cache: Dict[str, Dict[str, str]] = {}

    def enrich_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        为文章列表补充摘要/正文。

        说明：
        - 仅处理支持的来源；
        - 已有 summary/content 的文章不会重复抓取；
        - 单条抓取失败不影响整体流程。
        """
        enriched_articles: List[Dict[str, Any]] = []
        for article in articles:
            source_id = str(article.get("source_id", "") or "").strip()
            if not source_id or source_id not in self.SUPPORTED_SOURCE_IDS:
                enriched_articles.append(article)
                continue

            if article.get("summary") and article.get("content"):
                enriched_articles.append(article)
                continue

            try:
                content_data = self._enrich_article(article)
                if content_data:
                    article.update(content_data)
            except Exception as exc:
                logger.warning("增强新闻详情失败: source_id=%s error=%s", source_id, exc)

            enriched_articles.append(article)
            if self.request_interval > 0:
                time.sleep(self.request_interval)

        return enriched_articles

    def _enrich_article(self, article: Dict[str, Any]) -> Dict[str, str]:
        source_id = str(article.get("source_id", "") or "").strip()
        handler_name = self.SUPPORTED_SOURCE_IDS.get(source_id)
        if not handler_name:
            return {}

        handler: Callable[[Dict[str, Any]], Dict[str, str]] = getattr(self, handler_name)
        cache_key = self._build_cache_key(article)
        if cache_key in self._cache:
            return dict(self._cache[cache_key])

        data = handler(article)
        normalized = self._normalize_content_payload(data)
        self._cache[cache_key] = normalized
        return dict(normalized)

    def _build_cache_key(self, article: Dict[str, Any]) -> str:
        source_id = str(article.get("source_id", "") or "").strip()
        url = str(article.get("source_url", "") or "").strip()
        title = str(article.get("title", "") or "").strip()
        return f"{source_id}|{url}|{title}"

    def _build_proxies(self) -> Optional[Dict[str, str]]:
        if not self.proxy_url:
            return None
        return {"http": self.proxy_url, "https": self.proxy_url}

    def _request_text(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        response = self._session.get(
            url,
            headers=headers or self.DEFAULT_HEADERS,
            proxies=self._build_proxies(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text

    def _request_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        response = self._session.get(
            url,
            headers=headers or self.DEFAULT_HEADERS,
            proxies=self._build_proxies(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_json_from_jsonp(payload: str) -> str:
        payload = payload.strip()
        match = re.search(
            r"(?:try\s*\{\s*)?[^(]+\((\{.*\})\)\s*(?:\}\s*catch\s*\([^)]*\)\s*\{\s*\}\s*;?)?$",
            payload,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()

        start = payload.find('{"result"')
        if start == -1:
            start = payload.find("{")
        if start == -1:
            raise ValueError("无法从 JSONP 中提取 JSON")

        brace_depth = 0
        end = -1
        for index in range(start, len(payload)):
            char = payload[index]
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    end = index
                    break

        if end == -1:
            raise ValueError("无法从 JSONP 中提取 JSON")
        return payload[start:end + 1].strip()

    @staticmethod
    def _strip_html_tags(text: str) -> str:
        cleaned = html.unescape(text or "")
        cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</p\s*>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        cleaned = cleaned.replace("\xa0", " ")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        return cleaned.strip()

    @classmethod
    def _normalize_content_payload(cls, payload: Dict[str, Any]) -> Dict[str, str]:
        summary = cls._strip_html_tags(str(payload.get("summary", "") or ""))
        content = cls._strip_html_tags(str(payload.get("content", "") or ""))
        if not summary and content:
            summary = cls._build_summary_from_content(content)
        if summary and not content:
            content = summary
        return {
            "summary": summary,
            "content": content,
        }

    @staticmethod
    def _build_summary_from_content(content: str, limit: int = 180) -> str:
        if not content:
            return ""
        if len(content) <= limit:
            return content
        return content[:limit].rstrip() + "..."

    @staticmethod
    def _extract_detail_id(url: str) -> str:
        match = re.search(r"/detail/(\d+)", url or "")
        return match.group(1) if match else ""

    @staticmethod
    def _extract_query_param(url: str, name: str) -> str:
        match = re.search(rf"[?&]{re.escape(name)}=([^&#]+)", url or "")
        return match.group(1) if match else ""

    def _enrich_jin10_article(self, article: Dict[str, Any]) -> Dict[str, str]:
        detail_id = self._extract_detail_id(str(article.get("source_url", "") or ""))
        url = f"https://www.jin10.com/flash_newest.js?t={int(time.time() * 1000)}"
        payload = self._request_text(url)
        json_text = payload.replace("var newest = ", "").rstrip(";\n ")
        data = json.loads(json_text)

        for item in data:
            if detail_id and str(item.get("id", "")) != detail_id:
                continue

            content = str(item.get("data", {}).get("content", "") or "")
            title = str(article.get("title", "") or "")
            if detail_id or self._title_matches_content(title, content):
                return {
                    "summary": self._build_summary_from_content(
                        self._strip_html_tags(content)
                    ),
                    "content": content,
                }
        return {}

    def _enrich_jin10_futures_article(self, article: Dict[str, Any]) -> Dict[str, str]:
        detail_id = self._extract_detail_id(str(article.get("source_url", "") or ""))
        headers = dict(self.DEFAULT_HEADERS)
        headers.update(
            {
                "Origin": "https://qihuo.jin10.com",
                "Referer": "https://qihuo.jin10.com/",
                "x-app-id": "KxBcVoDHStE6CUkQ",
                "x-version": "1.0.0",
            }
        )
        data = self._request_json(
            "https://qh-flash-api.jin10.com/get_flash_list?channel=-1",
            headers=headers,
        )
        for item in data.get("data", []):
            if detail_id and str(item.get("id", "")) != detail_id:
                continue

            content = str(item.get("data", {}).get("content", "") or "")
            title = str(article.get("title", "") or "")
            if detail_id or self._title_matches_content(title, content):
                return {
                    "summary": self._build_summary_from_content(
                        self._strip_html_tags(content)
                    ),
                    "content": content,
                }
        return {}

    def _enrich_sina_finance_article(self, article: Dict[str, Any]) -> Dict[str, str]:
        detail_id = self._extract_query_param(
            str(article.get("source_url", "") or ""),
            "id",
        )
        callback = f"jQuery{int(time.time() * 1000)}"
        url = (
            "https://zhibo.sina.com.cn/api/zhibo/feed"
            f"?callback={callback}&page=1&page_size=20&zhibo_id=152"
            "&tag_id=0&dire=f&dpc=1&pagesize=20"
        )
        payload = self._request_text(url)
        json_text = self._extract_json_from_jsonp(payload)
        data = json.loads(json_text)
        feed_list = data.get("result", {}).get("data", {}).get("feed", {}).get("list", [])

        for item in feed_list:
            if detail_id and str(item.get("id", "")) != detail_id:
                continue

            content = str(item.get("rich_text", "") or "")
            title = str(article.get("title", "") or "")
            if detail_id or self._title_matches_content(title, content):
                plain_content = self._strip_html_tags(content)
                return {
                    "summary": self._build_summary_from_content(plain_content),
                    "content": plain_content,
                }
        return {}

    def _enrich_cls_article(self, article: Dict[str, Any]) -> Dict[str, str]:
        detail_id = self._extract_detail_id(str(article.get("source_url", "") or ""))
        if not detail_id:
            return {}

        url = (
            "https://www.cls.cn/nodeapi/updateTelegraphList"
            "?app=CailianpressWeb&category=&hasFirstVipArticle=1"
            "&lastTime=0&os=web&rn=100&subscribedColumnIds="
        )
        data = self._request_json(url)
        roll_data = data.get("data", {}).get("roll_data", [])

        for item in roll_data:
            if str(item.get("id", "")) != detail_id:
                continue

            summary = str(item.get("brief", "") or "")
            content = str(item.get("content", "") or "")
            return {
                "summary": summary,
                "content": content,
            }
        return {}

    @staticmethod
    def _title_matches_content(title: str, content: str) -> bool:
        normalized_title = re.sub(r"\s+", "", title or "")
        normalized_content = re.sub(r"\s+", "", content or "")
        if not normalized_title or not normalized_content:
            return False
        return normalized_title in normalized_content or normalized_content.startswith(
            normalized_title[:20]
        )
