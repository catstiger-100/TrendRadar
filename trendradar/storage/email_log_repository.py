# coding=utf-8
from __future__ import annotations

import logging
import threading

from trendradar.storage.news_repository import _get_conn, _put_conn

logger = logging.getLogger(__name__)

SCHEMA_LOCK_KEY = 551202605
_schema_ready = False
_schema_lock = threading.Lock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS email_send_logs (
    id         SERIAL PRIMARY KEY,
    sent_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    email_from TEXT        NOT NULL,
    email_to   TEXT        NOT NULL,
    content_md5 TEXT       NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_email_send_logs_content_md5
    ON email_send_logs (content_md5);
"""


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return

    with _schema_lock:
        if _schema_ready:
            return

        conn = _get_conn()
        try:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK_KEY,))
                cur.execute(SCHEMA_SQL)
            conn.commit()
            _schema_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            _put_conn(conn)


def has_been_sent(content_md5: str) -> bool:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM email_send_logs WHERE content_md5 = %s LIMIT 1",
                (content_md5,),
            )
            return cur.fetchone() is not None
    except Exception as e:
        conn.rollback()
        logger.error(f"查询邮件发送记录失败: {e}")
        raise
    finally:
        _put_conn(conn)


def record_send(email_from: str, email_to: str, content_md5: str) -> None:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_send_logs (email_from, email_to, content_md5)
                VALUES (%s, %s, %s)
                ON CONFLICT (content_md5) DO NOTHING
                """,
                (email_from, email_to, content_md5),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"记录邮件发送日志失败: {e}")
        raise
    finally:
        _put_conn(conn)
