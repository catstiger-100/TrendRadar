# coding=utf-8
"""
资讯数据仓库模块

管理 PostgreSQL 中的新闻资讯数据，支持中文全文检索。
"""

import os
import logging
import hashlib
import json
from difflib import SequenceMatcher
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

AI_INTERPRET_STATUS_PENDING = "待解读"
AI_INTERPRET_STATUS_RUNNING = "解读中"
AI_INTERPRET_STATUS_DONE = "已解读"

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


def _build_title_md5(title: str) -> str:
    """基于规范化后的标题生成稳定 md5，用于精确去重。"""
    return hashlib.md5(title.encode("utf-8")).hexdigest()


def _normalize_similarity_text(value: Any) -> str:
    """为相似度比较准备统一文本，尽量忽略空白和常见标点差异。"""
    text = _normalize_text(value).strip().lower()
    if not text:
        return ""
    for char in (
        " ", "\t", "\r", "\n",
        "，", ",", "。", ".", "；", ";", "：", ":", "！", "!", "？", "?",
        "【", "】", "[", "]", "（", "）", "(", ")", "\"", "'", "“", "”",
    ):
        text = text.replace(char, "")
    return text


def _is_similar_to_title(title: str, candidate: Any, threshold: float = 0.8) -> bool:
    """判断摘要/正文是否与标题过于相似，避免把标题原样写入详情字段。"""
    normalized_title = _normalize_similarity_text(title)
    normalized_candidate = _normalize_similarity_text(candidate)
    if not normalized_title or not normalized_candidate:
        return False
    similarity = SequenceMatcher(None, normalized_title, normalized_candidate).ratio()
    return similarity >= threshold


def _sanitize_article_detail_fields(article: Dict[str, Any], title: str) -> None:
    """如果摘要/正文与标题过于相似，则在入库前清空这些字段。"""
    summary = _normalize_text(article.get("summary")).strip()
    content = _normalize_text(article.get("content")).strip()

    if summary and _is_similar_to_title(title, summary):
        summary = ""
    if content and _is_similar_to_title(title, content):
        content = ""

    article["summary"] = summary
    article["content"] = content


def save_articles(articles: List[Dict[str, Any]]) -> int:
    """
    批量保存新闻资讯（标题去重）。

    Args:
        articles: 资讯列表，每条包含:
            title, source_name, source_url, published_at,
            category_l1, category_l2, keywords, crawl_time,
            summary, content, source_id

    Returns:
        实际新增的条数
    """
    if not articles:
        return 0

    conn = _get_conn()
    saved = 0
    saved_article_ids: List[int] = []
    try:
        # Clear any failed transaction state before reusing a pooled connection.
        conn.rollback()
        with conn.cursor() as cur:
            for article in articles:
                title = _normalize_text(article.get("title")).strip()
                if not title:
                    continue
                _sanitize_article_detail_fields(article, title)

                savepoint_created = False
                try:
                    cur.execute("SAVEPOINT save_article")
                    savepoint_created = True
                    crawl_count = int(article.get("crawl_count", 1) or 1)
                    title_md5 = _build_title_md5(title)
                    cur.execute(
                        """
                        INSERT INTO news_articles (title, title_md5, source_name, source_url, source_id, published_at,
                                                   category_l1, category_l2, keywords, summary, content, crawl_time, crawl_count,
                                                   ai_interpret_status, ai_interpret_result, ai_one_line_summary)
                        VALUES (%(title)s, %(title_md5)s, %(source_name)s, %(source_url)s, %(source_id)s, %(published_at)s,
                                %(category_l1)s, %(category_l2)s, %(keywords)s,
                                %(summary)s, %(content)s, %(crawl_time)s, %(crawl_count)s,
                                %(ai_interpret_status)s, %(ai_interpret_result)s, %(ai_one_line_summary)s)
                        ON CONFLICT (title_md5) DO UPDATE SET
                            crawl_count = GREATEST(news_articles.crawl_count, EXCLUDED.crawl_count),
                            crawl_time = EXCLUDED.crawl_time,
                            source_id = COALESCE(NULLIF(EXCLUDED.source_id, ''), news_articles.source_id),
                            summary = COALESCE(NULLIF(EXCLUDED.summary, ''), news_articles.summary),
                            content = COALESCE(NULLIF(EXCLUDED.content, ''), news_articles.content),
                            ai_interpret_status = CASE
                                WHEN news_articles.ai_interpret_status = %(ai_interpret_done)s THEN news_articles.ai_interpret_status
                                ELSE %(ai_interpret_status)s
                            END
                        RETURNING id, ai_interpret_status
""",
                        {
                            "title": title,
                            "title_md5": title_md5,
                            "source_name": _normalize_text(article.get("source_name")),
                            "source_url": _normalize_text(article.get("source_url")),
                            "source_id": _normalize_text(article.get("source_id")),
                            "published_at": article.get("published_at"),
                            "category_l1": _normalize_text(article.get("category_l1")),
                            "category_l2": _normalize_text(article.get("category_l2")),
                            "keywords": _normalize_keywords(article.get("keywords")),
                            "summary": _normalize_text(article.get("summary")),
                            "content": _normalize_text(article.get("content")),
                            "crawl_time": article.get("crawl_time") or datetime.now(),
                            "crawl_count": crawl_count,
                            "ai_interpret_status": AI_INTERPRET_STATUS_PENDING,
                            "ai_interpret_done": AI_INTERPRET_STATUS_DONE,
                            "ai_interpret_result": "",
                            "ai_one_line_summary": "",
                        },
                    )
                    returned = cur.fetchone()
                    if returned:
                        saved_article_ids.append(int(returned[0]))
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

    if saved_article_ids:
        try:
            from trendradar.ai.news_interpreter import enqueue_article_interpretation
            enqueue_article_interpretation(saved_article_ids)
        except Exception as e:
            logger.warning(f"提交 AI 解读任务失败: {e}")

    if saved > 0:
        logger.info(f"已保存 {saved} 条新资讯")
    return saved


def query_articles(
    keyword: Optional[str] = None,
    query_date: Optional[str] = None,
    source_name: Optional[str] = None,
    favorite_only: bool = False,
    favorite_article_ids: Optional[List[int]] = None,
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

        if favorite_only:
            article_ids = [int(article_id) for article_id in (favorite_article_ids or [])]
            if not article_ids:
                return [], 0
            conditions.append("id = ANY(%(favorite_article_ids)s::int[])")
            params["favorite_article_ids"] = article_ids

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
            SELECT id, title, source_name, source_url, source_id, published_at,
                   category_l1, category_l2, keywords, summary, content, crawl_time, created_at, crawl_count,
                   ai_interpret_status, ai_interpret_result, ai_one_line_summary
            FROM news_articles
            {where_clause}
            ORDER BY published_at DESC NULLS LAST, created_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )

        columns = [
            "id", "title", "source_name", "source_url", "source_id", "published_at",
            "category_l1", "category_l2", "keywords", "summary", "content",
            "crawl_time", "created_at", "crawl_count",
            "ai_interpret_status", "ai_interpret_result", "ai_one_line_summary",
        ]
        article_ids = []
        rows = []
        for record in cur.fetchall():
            row = dict(zip(columns, record))
            # 格式化日期时间
            for dt_field in ("published_at", "crawl_time", "created_at"):
                if row.get(dt_field):
                    row[dt_field] = row[dt_field].isoformat()
            article_ids.append(row["id"])
            rows.append(row)
        cur.close()

        ai_symbol_map = get_article_ai_symbols_map(article_ids)
        for row in rows:
            row["ai_symbols"] = ai_symbol_map.get(row["id"], [])

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


def ensure_news_article_columns() -> None:
    """兼容旧库：为 news_articles 补充详情字段。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        for column_name, ddl in [
            ("title_md5", "ALTER TABLE news_articles ADD COLUMN title_md5 TEXT NOT NULL DEFAULT ''"),
            ("source_id", "ALTER TABLE news_articles ADD COLUMN source_id TEXT NOT NULL DEFAULT ''"),
            ("summary", "ALTER TABLE news_articles ADD COLUMN summary TEXT NOT NULL DEFAULT ''"),
            ("content", "ALTER TABLE news_articles ADD COLUMN content TEXT NOT NULL DEFAULT ''"),
            ("ai_interpret_status", "ALTER TABLE news_articles ADD COLUMN ai_interpret_status TEXT NOT NULL DEFAULT '待解读'"),
            ("ai_interpret_result", "ALTER TABLE news_articles ADD COLUMN ai_interpret_result TEXT NOT NULL DEFAULT ''"),
            ("ai_one_line_summary", "ALTER TABLE news_articles ADD COLUMN ai_one_line_summary TEXT NOT NULL DEFAULT ''"),
        ]:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'news_articles'
                      AND column_name = %s
                )
                """,
                (column_name,),
            )
            exists = cur.fetchone()[0]
            if not exists:
                cur.execute(ddl)

        cur.execute("UPDATE news_articles SET title_md5 = md5(title) WHERE title_md5 = ''")
        cur.execute(
            """
            UPDATE news_articles
            SET ai_interpret_status = '待解读'
            WHERE ai_interpret_status = ''
            """
        )
        cur.execute("DROP INDEX IF EXISTS idx_news_articles_title_md5")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_news_articles_title_md5
            ON news_articles (title_md5)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS news_article_ai_symbols (
                id SERIAL PRIMARY KEY,
                article_id INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT '',
                symbol_name TEXT NOT NULL DEFAULT '',
                symbol_code TEXT NOT NULL DEFAULT '',
                direction TEXT NOT NULL DEFAULT '中性',
                strength INTEGER NOT NULL DEFAULT 3,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_article_ai_symbols_article_id
            ON news_article_ai_symbols (article_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_article_ai_symbols_strength
            ON news_article_ai_symbols (article_id, strength DESC)
            """
        )
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        logger.error(f"补充 news_articles 字段失败: {e}")
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


def get_article_for_ai_interpretation(article_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, summary, content, ai_interpret_status
            FROM news_articles
            WHERE id = %s
            """,
            (article_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return {
            "id": row[0],
            "title": row[1] or "",
            "summary": row[2] or "",
            "content": row[3] or "",
            "ai_interpret_status": row[4] or "",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def get_pending_ai_interpretation_article_ids(limit: int = 50) -> List[int]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id
            FROM news_articles
            WHERE ai_interpret_status IN (%s, %s)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (AI_INTERPRET_STATUS_PENDING, AI_INTERPRET_STATUS_RUNNING, int(limit)),
        )
        rows = [int(row[0]) for row in cur.fetchall()]
        cur.close()
        return rows
    except Exception:
        conn.rollback()
        return []
    finally:
        _put_conn(conn)


def mark_article_ai_interpret_status(article_id: int, status: str) -> None:
    conn = _get_conn()
    try:
        conn.rollback()
        cur = conn.cursor()
        cur.execute(
            "UPDATE news_articles SET ai_interpret_status = %s WHERE id = %s",
            (status, article_id),
        )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def save_article_ai_interpretation(
    article_id: int,
    one_line_summary: str,
    raw_result: str,
    symbol_matches: List[Dict[str, Any]],
) -> None:
    conn = _get_conn()
    try:
        conn.rollback()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE news_articles
            SET
                ai_interpret_status = %s,
                ai_interpret_result = %s,
                ai_one_line_summary = %s
            WHERE id = %s
            """,
            (
                AI_INTERPRET_STATUS_DONE,
                _normalize_text(raw_result),
                _normalize_text(one_line_summary),
                article_id,
            ),
        )
        cur.execute(
            "DELETE FROM news_article_ai_symbols WHERE article_id = %s",
            (article_id,),
        )
        if symbol_matches:
            cur.execute(
                "SELECT title FROM news_articles WHERE id = %s",
                (article_id,),
            )
            title_row = cur.fetchone()
            title = title_row[0] if title_row else ""
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO news_article_ai_symbols (
                    article_id, title, symbol_name, symbol_code, direction, strength, created_at
                )
                VALUES (%(article_id)s, %(title)s, %(symbol_name)s, %(symbol_code)s, %(direction)s, %(strength)s, NOW())
                """,
                [
                    {
                        "article_id": article_id,
                        "title": title,
                        "symbol_name": item.get("symbol_name", "") or "",
                        "symbol_code": item.get("symbol_code", "") or "",
                        "direction": item.get("direction", "中性") or "中性",
                        "strength": int(item.get("strength", 3) or 3),
                    }
                    for item in symbol_matches[:3]
                ],
            )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def get_article_ai_symbols(article_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT symbol_name, symbol_code, direction, strength
            FROM news_article_ai_symbols
            WHERE article_id = %s
            ORDER BY strength DESC, id ASC
            """,
            (article_id,),
        )
        rows = [
            {
                "symbol_name": row[0] or "",
                "symbol_code": row[1] or "",
                "direction": row[2] or "中性",
                "strength": int(row[3] or 3),
            }
            for row in cur.fetchall()
        ]
        cur.close()
        return rows
    except Exception:
        conn.rollback()
        return []
    finally:
        _put_conn(conn)


def get_article_ai_symbols_map(article_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    normalized_ids = [int(article_id) for article_id in (article_ids or []) if article_id]
    if not normalized_ids:
        return {}

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT article_id, symbol_name, symbol_code, direction, strength
            FROM news_article_ai_symbols
            WHERE article_id = ANY(%s::int[])
            ORDER BY article_id ASC, strength DESC, id ASC
            """,
            (normalized_ids,),
        )
        result: Dict[int, List[Dict[str, Any]]] = {}
        for row in cur.fetchall():
            result.setdefault(int(row[0]), []).append(
                {
                    "symbol_name": row[1] or "",
                    "symbol_code": row[2] or "",
                    "direction": row[3] or "中性",
                    "strength": int(row[4] or 3),
                }
            )
        cur.close()
        return result
    except Exception:
        conn.rollback()
        return {}
    finally:
        _put_conn(conn)
