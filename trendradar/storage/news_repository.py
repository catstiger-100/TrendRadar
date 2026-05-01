# coding=utf-8
"""
资讯数据仓库模块

管理 PostgreSQL 中的新闻资讯数据，支持中文全文检索。
"""

import os
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

# PostgreSQL 连接配置（从环境变量读取）
PG_HOST = os.environ.get("PG_HOST", "postgres")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DB = os.environ.get("PG_DB", "trendradar")
PG_USER = os.environ.get("PG_USER", "trendradar")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "trendradar")

# 连接池（线程安全）
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DB,
            user=PG_USER,
            password=PG_PASSWORD,
        )
    return _pool


def _get_conn():
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SET timezone = 'Asia/Shanghai'")
    except Exception:
        conn.rollback()
    return conn


def _put_conn(conn):
    _get_pool().putconn(conn)


def _normalize_text(value: Any) -> str:
    """Convert values destined for TEXT columns into safe strings."""
    if value is None:
        return ""
    return str(value)


def _normalize_keywords(value: Any) -> List[str]:
    """Normalize keyword values for PostgreSQL TEXT[] insertion."""
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]

    keywords = []
    for item in values:
        text = _normalize_text(item).strip()
        if text and text not in keywords:
            keywords.append(text)
    return keywords


def save_articles(articles: List[Dict[str, Any]]) -> int:
    """
    批量保存新闻资讯（标题去重）。

    Args:
        articles: 资讯列表，每条包含:
            title, source_name, source_url, published_at,
            category_l1, category_l2, keywords, crawl_time

    Returns:
        实际新增的条数
    """
    if not articles:
        return 0

    conn = _get_conn()
    saved = 0
    try:
        # Clear any failed transaction state before reusing a pooled connection.
        conn.rollback()
        with conn.cursor() as cur:
            for article in articles:
                title = _normalize_text(article.get("title")).strip()
                if not title:
                    continue

                savepoint_created = False
                try:
                    cur.execute("SAVEPOINT save_article")
                    savepoint_created = True
                    crawl_count = int(article.get("crawl_count", 1) or 1)
                    cur.execute(
                        """
                        INSERT INTO news_articles (title, source_name, source_url, published_at,
                                                   category_l1, category_l2, keywords, crawl_time, crawl_count)
                        VALUES (%(title)s, %(source_name)s, %(source_url)s, %(published_at)s,
                                %(category_l1)s, %(category_l2)s, %(keywords)s, %(crawl_time)s, %(crawl_count)s)
                        ON CONFLICT (title) DO UPDATE SET
                            crawl_count = GREATEST(news_articles.crawl_count, EXCLUDED.crawl_count),
                            crawl_time = EXCLUDED.crawl_time
                        """,
                        {
                            "title": title,
                            "source_name": _normalize_text(article.get("source_name")),
                            "source_url": _normalize_text(article.get("source_url")),
                            "published_at": article.get("published_at"),
                            "category_l1": _normalize_text(article.get("category_l1")),
                            "category_l2": _normalize_text(article.get("category_l2")),
                            "keywords": _normalize_keywords(article.get("keywords")),
                            "crawl_time": article.get("crawl_time") or datetime.now(),
                            "crawl_count": crawl_count,
                        },
                    )
                    if cur.rowcount > 0:
                        saved += 1
                    cur.execute("RELEASE SAVEPOINT save_article")
                except Exception as e:
                    if savepoint_created:
                        cur.execute("ROLLBACK TO SAVEPOINT save_article")
                        cur.execute("RELEASE SAVEPOINT save_article")
                    else:
                        conn.rollback()
                    logger.warning(f"保存文章失败: {title[:50]}... - {e}")
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"批量保存失败: {e}")
        raise
    finally:
        _put_conn(conn)

    if saved > 0:
        logger.info(f"已保存 {saved} 条新资讯")
    return saved


def query_articles(
    keyword: Optional[str] = None,
    query_date: Optional[str] = None,
    source_name: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    分页查询资讯（按发布时间逆序）。

    Args:
        keyword: 关键词筛选（使用中文全文检索 + 关键词数组）
        query_date: 日期筛选（YYYY-MM-DD）
        source_name: 来源筛选
        page: 页码（从 1 开始）
        page_size: 每页条数

    Returns:
        (article_list, total_count)
    """
    conn = _get_conn()
    try:
        conditions = []
        params = {}

        if keyword and keyword.strip():
            kw = keyword.strip()
            conditions.append(
                """(
                    to_tsvector('chinese', title) @@ plainto_tsquery('chinese', %(keyword)s)
                    OR EXISTS (SELECT 1 FROM unnest(keywords) k WHERE k ILIKE %(keyword_like)s)
                )"""
            )
            params["keyword"] = kw
            params["keyword_like"] = f"%{kw}%"

        if query_date:
            try:
                d = date.fromisoformat(query_date)
                from datetime import timedelta
                next_day = d + timedelta(days=1)
                conditions.append(
                    "published_at >= %(date_start)s AND published_at < %(date_end)s"
                )
                params["date_start"] = d.isoformat()
                params["date_end"] = next_day.isoformat()
            except ValueError:
                pass

        if source_name and source_name.strip():
            conditions.append("source_name = %(source_name)s")
            params["source_name"] = source_name.strip()

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 查询总数
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM news_articles {where_clause}", params)
        total = cur.fetchone()[0]

        # 分页查询
        offset = (page - 1) * page_size
        params["limit"] = page_size
        params["offset"] = offset
        cur.execute(
            f"""
            SELECT id, title, source_name, source_url, published_at,
                   category_l1, category_l2, keywords, crawl_time, created_at, crawl_count
            FROM news_articles
            {where_clause}
            ORDER BY published_at DESC NULLS LAST, created_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )

        columns = [
            "id", "title", "source_name", "source_url", "published_at",
            "category_l1", "category_l2", "keywords", "crawl_time", "created_at", "crawl_count",
        ]
        rows = []
        for record in cur.fetchall():
            row = dict(zip(columns, record))
            # 格式化日期时间
            for dt_field in ("published_at", "crawl_time", "created_at"):
                if row.get(dt_field):
                    row[dt_field] = row[dt_field].isoformat()
            rows.append(row)
        cur.close()

        return rows, total
    except Exception as e:
        conn.rollback()
        logger.error(f"查询资讯失败: {e}")
        raise
    finally:
        _put_conn(conn)


def get_all_keywords() -> List[str]:
    """获取所有出现过的关键词（用于筛选下拉框）。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT unnest(keywords) AS kw
            FROM news_articles
            WHERE array_length(keywords, 1) > 0
            ORDER BY kw
            """
        )
        keywords = [row[0] for row in cur.fetchall()]
        cur.close()
        return keywords
    except Exception as e:
        conn.rollback()
        logger.error(f"获取关键词列表失败: {e}")
        return []
    finally:
        _put_conn(conn)


def get_all_source_names() -> List[str]:
    """获取所有出现过的来源名称（用于筛选下拉框）。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT source_name
            FROM news_articles
            WHERE source_name IS NOT NULL AND source_name != ''
            ORDER BY source_name
            """
        )
        names = [row[0] for row in cur.fetchall()]
        cur.close()
        return names
    except Exception as e:
        conn.rollback()
        logger.error(f"获取来源列表失败: {e}")
        return []
    finally:
        _put_conn(conn)


def table_exists() -> bool:
    """检查 news_articles 表是否存在。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'news_articles'
            )
            """
        )
        exists = cur.fetchone()[0]
        cur.close()
        return exists
    except Exception:
        conn.rollback()
        return False
    finally:
        _put_conn(conn)
