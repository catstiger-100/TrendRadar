# coding=utf-8
"""
数据获取器模块

负责从 NewsNow API 抓取新闻数据，支持：
- 单个平台数据获取
- 批量平台数据爬取
- 自定义站点抓取
- 自动重试机制
- 代理支持
"""

import html
import json
import random
import re
import time
from typing import Callable, Dict, List, Tuple, Optional, Union

import requests


class DataFetcher:
    """数据获取器"""

    # 默认 API 地址
    DEFAULT_API_URL = "https://newsnow.busiyi.world/api/s"

    # 默认请求头
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }

    CUSTOM_SOURCE_HANDLERS = {
        "jin10-futures": "_fetch_jin10_futures_items",
        "sina-finance-7x24": "_fetch_sina_finance_7x24_items",
    }

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        api_url: Optional[str] = None,
    ):
        """
        初始化数据获取器

        Args:
            proxy_url: 代理服务器 URL（可选）
            api_url: API 基础 URL（可选，默认使用 DEFAULT_API_URL）
        """
        self.proxy_url = proxy_url
        self.api_url = api_url or self.DEFAULT_API_URL

    def _build_proxies(self) -> Optional[Dict[str, str]]:
        """构建 requests 代理配置"""
        if not self.proxy_url:
            return None
        return {"http": self.proxy_url, "https": self.proxy_url}

    @staticmethod
    def _normalize_title(raw_title: object) -> str:
        """清洗标题文本，兼容 HTML/空白字符"""
        if raw_title is None:
            return ""

        text = str(raw_title)
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _append_result_item(
        items: Dict[str, Dict[str, Union[List[int], str]]],
        title: str,
        rank: int,
        url: str = "",
        mobile_url: str = "",
    ) -> None:
        """向结果集中追加一条标准化新闻记录"""
        if title in items:
            items[title]["ranks"].append(rank)
            if not items[title].get("url") and url:
                items[title]["url"] = url
            if not items[title].get("mobileUrl") and mobile_url:
                items[title]["mobileUrl"] = mobile_url
            return

        items[title] = {
            "ranks": [rank],
            "url": url,
            "mobileUrl": mobile_url,
        }

    @staticmethod
    def _extract_json_from_jsonp(payload: str) -> str:
        """从 JSONP 响应中提取 JSON 主体"""
        payload = payload.strip()

        match = re.search(r"^[^(]+\((.*)\)\s*;?\s*$", payload, re.DOTALL)
        if match:
            return match.group(1).strip()

        start = payload.find('{"result"')
        if start == -1:
            start = payload.find("{")

        end_marker = ");"
        end = payload.rfind(end_marker)
        if end != -1 and end > start:
            return payload[start:end].strip()

        end = payload.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("无法从响应中提取 JSON 数据")

        return payload[start:end + 1].strip()

    def _retry_fetch(
        self,
        source_id: str,
        fetch_func: Callable[[], Dict[str, Dict[str, Union[List[int], str]]]],
        max_retries: int = 2,
        min_retry_wait: int = 3,
        max_retry_wait: int = 5,
    ) -> Optional[Dict[str, Dict[str, Union[List[int], str]]]]:
        """带重试的结构化数据抓取"""
        retries = 0
        while retries <= max_retries:
            try:
                items = fetch_func()
                print(f"获取 {source_id} 成功（自定义源）")
                return items
            except Exception as e:
                retries += 1
                if retries <= max_retries:
                    base_wait = random.uniform(min_retry_wait, max_retry_wait)
                    additional_wait = (retries - 1) * random.uniform(1, 2)
                    wait_time = base_wait + additional_wait
                    print(f"请求 {source_id} 失败: {e}. {wait_time:.2f}秒后重试...")
                    time.sleep(wait_time)
                else:
                    print(f"请求 {source_id} 失败: {e}")
                    return None

        return None

    def _fetch_custom_source(
        self,
        source_id: str,
        max_retries: int = 2,
        min_retry_wait: int = 3,
        max_retry_wait: int = 5,
    ) -> Optional[Dict[str, Dict[str, Union[List[int], str]]]]:
        """抓取自定义站点数据，返回统一格式结果"""
        handler_name = self.CUSTOM_SOURCE_HANDLERS.get(source_id)
        if not handler_name:
            raise ValueError(f"未知的自定义数据源: {source_id}")

        handler = getattr(self, handler_name)
        return self._retry_fetch(
            source_id,
            handler,
            max_retries=max_retries,
            min_retry_wait=min_retry_wait,
            max_retry_wait=max_retry_wait,
        )

    def _fetch_jin10_futures_items(self) -> Dict[str, Dict[str, Union[List[int], str]]]:
        """抓取金十期货快讯"""
        url = "https://qh-flash-api.jin10.com/get_flash_list?channel=-1"
        headers = {
            "User-Agent": self.DEFAULT_HEADERS["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://qihuo.jin10.com",
            "Referer": "https://qihuo.jin10.com/",
            "x-app-id": "KxBcVoDHStE6CUkQ",
            "x-version": "1.0.0",
        }
        response = requests.get(
            url,
            headers=headers,
            proxies=self._build_proxies(),
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        items = {}

        for index, item in enumerate(data.get("data", []), 1):
            title = self._normalize_title(item.get("data", {}).get("content", ""))
            if not title:
                continue

            detail_id = item.get("id")
            detail_url = (
                f"https://flash.jin10.com/detail/{detail_id}" if detail_id else ""
            )
            self._append_result_item(items, title, index, detail_url, detail_url)

        return items

    def _fetch_sina_finance_7x24_items(self) -> Dict[str, Dict[str, Union[List[int], str]]]:
        """抓取新浪财经 7x24 快讯"""
        callback = f"jQuery{int(time.time() * 1000)}"
        url = (
            "https://zhibo.sina.com.cn/api/zhibo/feed"
            f"?callback={callback}&page=1&page_size=20&zhibo_id=152"
            "&tag_id=0&dire=f&dpc=1&pagesize=20"
        )
        response = requests.get(
            url,
            headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]},
            proxies=self._build_proxies(),
            timeout=10,
        )
        response.raise_for_status()

        json_text = self._extract_json_from_jsonp(response.text)
        data = json.loads(json_text)
        feed_list = data.get("result", {}).get("data", {}).get("feed", {}).get("list", [])

        items = {}
        for index, item in enumerate(feed_list, 1):
            title = self._normalize_title(item.get("rich_text", ""))
            if not title:
                continue

            detail_id = item.get("id")
            detail_url = (
                f"https://finance.sina.com.cn/7x24/notification.shtml?id={detail_id}"
                if detail_id else ""
            )
            self._append_result_item(items, title, index, detail_url, detail_url)

        return items

    def fetch_data(
        self,
        id_info: Union[str, Tuple[str, str]],
        max_retries: int = 2,
        min_retry_wait: int = 3,
        max_retry_wait: int = 5,
    ) -> Tuple[Optional[str], str, str]:
        """
        获取指定ID数据，支持重试

        Args:
            id_info: 平台ID 或 (平台ID, 别名) 元组
            max_retries: 最大重试次数
            min_retry_wait: 最小重试等待时间（秒）
            max_retry_wait: 最大重试等待时间（秒）

        Returns:
            (响应文本, 平台ID, 别名) 元组，失败时响应文本为 None
        """
        if isinstance(id_info, tuple):
            id_value, alias = id_info
        else:
            id_value = id_info
            alias = id_value

        url = f"{self.api_url}?id={id_value}&latest"
        proxies = self._build_proxies()

        retries = 0
        while retries <= max_retries:
            try:
                response = requests.get(
                    url,
                    proxies=proxies,
                    headers=self.DEFAULT_HEADERS,
                    timeout=10,
                )
                response.raise_for_status()

                data_text = response.text
                data_json = json.loads(data_text)

                status = data_json.get("status", "未知")
                if status not in ["success", "cache"]:
                    raise ValueError(f"响应状态异常: {status}")

                status_info = "最新数据" if status == "success" else "缓存数据"
                print(f"获取 {id_value} 成功（{status_info}）")
                return data_text, id_value, alias

            except Exception as e:
                retries += 1
                if retries <= max_retries:
                    base_wait = random.uniform(min_retry_wait, max_retry_wait)
                    additional_wait = (retries - 1) * random.uniform(1, 2)
                    wait_time = base_wait + additional_wait
                    print(f"请求 {id_value} 失败: {e}. {wait_time:.2f}秒后重试...")
                    time.sleep(wait_time)
                else:
                    print(f"请求 {id_value} 失败: {e}")
                    return None, id_value, alias

        return None, id_value, alias

    def crawl_websites(
        self,
        ids_list: List[Union[str, Tuple[str, str]]],
        request_interval: int = 100,
    ) -> Tuple[Dict, Dict, List]:
        """
        爬取多个网站数据

        Args:
            ids_list: 平台ID列表，每个元素可以是字符串或 (平台ID, 别名) 元组
            request_interval: 请求间隔（毫秒）

        Returns:
            (结果字典, ID到名称的映射, 失败ID列表) 元组
        """
        results = {}
        id_to_name = {}
        failed_ids = []

        for i, id_info in enumerate(ids_list):
            if isinstance(id_info, tuple):
                id_value, name = id_info
            else:
                id_value = id_info
                name = id_value

            id_to_name[id_value] = name
            if id_value in self.CUSTOM_SOURCE_HANDLERS:
                source_items = self._fetch_custom_source(id_value)
                if source_items is not None:
                    results[id_value] = source_items
                else:
                    failed_ids.append(id_value)
            else:
                response, _, _ = self.fetch_data(id_info)

                if response:
                    try:
                        data = json.loads(response)
                        results[id_value] = {}

                        for index, item in enumerate(data.get("items", []), 1):
                            title = item.get("title")
                            title = self._normalize_title(title)
                            if not title:
                                continue

                            self._append_result_item(
                                results[id_value],
                                title,
                                index,
                                item.get("url", ""),
                                item.get("mobileUrl", ""),
                            )
                    except json.JSONDecodeError:
                        print(f"解析 {id_value} 响应失败")
                        failed_ids.append(id_value)
                    except Exception as e:
                        print(f"处理 {id_value} 数据出错: {e}")
                        failed_ids.append(id_value)
                else:
                    failed_ids.append(id_value)

            # 请求间隔（除了最后一个）
            if i < len(ids_list) - 1:
                actual_interval = request_interval + random.randint(-10, 20)
                actual_interval = max(50, actual_interval)
                time.sleep(actual_interval / 1000)

        print(f"成功: {list(results.keys())}, 失败: {failed_ids}")
        return results, id_to_name, failed_ids
