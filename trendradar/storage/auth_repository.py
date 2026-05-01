# coding=utf-8
"""
用户、角色与登录认证仓库模块。

基于 PostgreSQL 提供：
- 用户/角色 CRUD
- 多角色关联
- PBKDF2 密码加密存储
- 会话令牌管理
"""

import base64
import hashlib
import hmac
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from trendradar.storage.news_repository import _get_conn, _put_conn


SESSION_TTL_DAYS = int(os.environ.get("AUTH_SESSION_TTL_DAYS", "7"))
PASSWORD_ITERATIONS = int(os.environ.get("AUTH_PASSWORD_ITERATIONS", "600000"))
DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "abc123456")
DEFAULT_ADMIN_ROLE = "ROLE_ADMIN"
SCHEMA_LOCK_KEY = 551202601
SESSION_CLEANUP_LOCK_KEY = 551202602
_schema_ready = False
_schema_lock = threading.Lock()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS auth_roles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    last_login_at TIMESTAMPTZ,
    last_login_ip TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_user_roles (
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES auth_roles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions (expires_at);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "pbkdf2_sha256${iterations}${salt}${digest}".format(
        iterations=PASSWORD_ITERATIONS,
        salt=base64.b64encode(salt).decode("ascii"),
        digest=base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(digest_b64.encode("ascii"))
        salt = base64.b64decode(salt_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def _cleanup_expired_sessions(cur, use_advisory_lock: bool = True) -> None:
    if use_advisory_lock:
        cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (SESSION_CLEANUP_LOCK_KEY,))
        row = cur.fetchone()
        locked = next(iter(row.values())) if isinstance(row, dict) else row[0]
        if not locked:
            return
    cur.execute("DELETE FROM auth_sessions WHERE expires_at <= NOW()")


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
            cur.execute(
                """
                INSERT INTO auth_roles (name, description)
                VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (DEFAULT_ADMIN_ROLE, "系统管理员"),
            )
            cur.execute(
                "SELECT id FROM auth_roles WHERE name = %s",
                (DEFAULT_ADMIN_ROLE,),
            )
            role_row = cur.fetchone()
            role_id = role_row[0]

            cur.execute(
                "SELECT id FROM auth_users WHERE username = %s",
                (DEFAULT_ADMIN_USERNAME,),
            )
            user_row = cur.fetchone()
            if user_row:
                user_id = user_row[0]
            else:
                cur.execute(
                    """
                    INSERT INTO auth_users (username, password_hash, full_name)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (
                        DEFAULT_ADMIN_USERNAME,
                        hash_password(DEFAULT_ADMIN_PASSWORD),
                        "系统管理员",
                    ),
                )
                user_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO auth_user_roles (user_id, role_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (user_id, role_id),
            )
            _cleanup_expired_sessions(cur, use_advisory_lock=False)
        conn.commit()
        _schema_ready = True
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def _serialize_dt(value: Optional[datetime]) -> str:
    return value.isoformat() if value else ""


def _role_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "created_at": _serialize_dt(row.get("created_at")),
        "updated_at": _serialize_dt(row.get("updated_at")),
    }


def _user_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    roles = row.get("roles") or []
    normalized_roles = [
        {"id": role["id"], "name": role["name"], "description": role.get("description", "")}
        for role in roles
        if role and role.get("id") is not None
    ]
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row.get("full_name") or "",
        "last_login_at": _serialize_dt(row.get("last_login_at")),
        "last_login_ip": row.get("last_login_ip") or "",
        "is_active": bool(row.get("is_active", True)),
        "created_at": _serialize_dt(row.get("created_at")),
        "updated_at": _serialize_dt(row.get("updated_at")),
        "roles": normalized_roles,
        "role_ids": [role["id"] for role in normalized_roles],
    }


def list_roles() -> List[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, description, created_at, updated_at
                FROM auth_roles
                ORDER BY id
                """
            )
            return [_role_dict(row) for row in cur.fetchall()]
    finally:
        _put_conn(conn)


def create_role(name: str, description: str = "") -> Dict[str, Any]:
    ensure_schema()
    role_name = (name or "").strip()
    if not role_name:
        raise ValueError("角色名称不能为空")

    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO auth_roles (name, description)
                VALUES (%s, %s)
                RETURNING id, name, description, created_at, updated_at
                """,
                (role_name, (description or "").strip()),
            )
            row = cur.fetchone()
        conn.commit()
        return _role_dict(row)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise ValueError("角色名称已存在")
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def update_role(role_id: int, name: str, description: str = "") -> Dict[str, Any]:
    ensure_schema()
    role_name = (name or "").strip()
    if not role_name:
        raise ValueError("角色名称不能为空")

    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE auth_roles
                SET name = %s,
                    description = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, name, description, created_at, updated_at
                """,
                (role_name, (description or "").strip(), role_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("角色不存在")
        conn.commit()
        return _role_dict(row)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise ValueError("角色名称已存在")
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def delete_role(role_id: int) -> None:
    ensure_schema()
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM auth_user_roles WHERE role_id = %s",
                (role_id,),
            )
            if cur.fetchone()[0] > 0:
                raise ValueError("该角色已分配给用户，无法删除")
            cur.execute("DELETE FROM auth_roles WHERE id = %s", (role_id,))
            if cur.rowcount == 0:
                raise ValueError("角色不存在")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def _load_role_ids(cur, role_ids: List[int]) -> List[int]:
    if not role_ids:
        return []
    cur.execute(
        "SELECT id FROM auth_roles WHERE id = ANY(%s::int[]) ORDER BY id",
        (role_ids,),
    )
    existing_ids = [row[0] for row in cur.fetchall()]
    if len(existing_ids) != len(set(role_ids)):
        raise ValueError("部分角色不存在")
    return existing_ids


def list_users() -> List[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.full_name,
                    u.last_login_at,
                    u.last_login_ip,
                    u.is_active,
                    u.created_at,
                    u.updated_at,
                    COALESCE(
                        json_agg(
                            json_build_object(
                                'id', r.id,
                                'name', r.name,
                                'description', r.description
                            )
                            ORDER BY r.id
                        ) FILTER (WHERE r.id IS NOT NULL),
                        '[]'::json
                    ) AS roles
                FROM auth_users u
                LEFT JOIN auth_user_roles ur ON ur.user_id = u.id
                LEFT JOIN auth_roles r ON r.id = ur.role_id
                GROUP BY u.id
                ORDER BY u.id
                """
            )
            return [_user_dict(row) for row in cur.fetchall()]
    finally:
        _put_conn(conn)


def create_user(
    username: str,
    password: str,
    full_name: str = "",
    role_ids: Optional[List[int]] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    ensure_schema()
    normalized_username = (username or "").strip()
    if not normalized_username:
        raise ValueError("用户名不能为空")
    if not password:
        raise ValueError("密码不能为空")

    role_ids = [int(role_id) for role_id in (role_ids or [])]
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            valid_role_ids = _load_role_ids(cur, role_ids)
            cur.execute(
                """
                INSERT INTO auth_users (username, password_hash, full_name, is_active)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    normalized_username,
                    hash_password(password),
                    (full_name or "").strip(),
                    bool(is_active),
                ),
            )
            user_id = cur.fetchone()["id"]
            for role_id in valid_role_ids:
                cur.execute(
                    """
                    INSERT INTO auth_user_roles (user_id, role_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (user_id, role_id),
                )
        conn.commit()
        return get_user_by_id(user_id)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise ValueError("用户名已存在")
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def update_user(
    user_id: int,
    username: str,
    full_name: str = "",
    role_ids: Optional[List[int]] = None,
    is_active: bool = True,
    password: str = "",
) -> Dict[str, Any]:
    ensure_schema()
    normalized_username = (username or "").strip()
    if not normalized_username:
        raise ValueError("用户名不能为空")

    role_ids = [int(role_id) for role_id in (role_ids or [])]
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            valid_role_ids = _load_role_ids(cur, role_ids)
            params = [
                normalized_username,
                (full_name or "").strip(),
                bool(is_active),
                user_id,
            ]
            if password:
                cur.execute(
                    """
                    UPDATE auth_users
                    SET username = %s,
                        full_name = %s,
                        is_active = %s,
                        password_hash = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        normalized_username,
                        (full_name or "").strip(),
                        bool(is_active),
                        hash_password(password),
                        user_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE auth_users
                    SET username = %s,
                        full_name = %s,
                        is_active = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    params,
                )
            row = cur.fetchone()
            if not row:
                raise ValueError("用户不存在")

            cur.execute("DELETE FROM auth_user_roles WHERE user_id = %s", (user_id,))
            for role_id in valid_role_ids:
                cur.execute(
                    """
                    INSERT INTO auth_user_roles (user_id, role_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (user_id, role_id),
                )
        conn.commit()
        return get_user_by_id(user_id)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise ValueError("用户名已存在")
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def delete_user(user_id: int) -> None:
    ensure_schema()
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_users WHERE id = %s", (user_id,))
            if cur.rowcount == 0:
                raise ValueError("用户不存在")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def get_user_by_id(user_id: int) -> Dict[str, Any]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.full_name,
                    u.last_login_at,
                    u.last_login_ip,
                    u.is_active,
                    u.created_at,
                    u.updated_at,
                    COALESCE(
                        json_agg(
                            json_build_object(
                                'id', r.id,
                                'name', r.name,
                                'description', r.description
                            )
                            ORDER BY r.id
                        ) FILTER (WHERE r.id IS NOT NULL),
                        '[]'::json
                    ) AS roles
                FROM auth_users u
                LEFT JOIN auth_user_roles ur ON ur.user_id = u.id
                LEFT JOIN auth_roles r ON r.id = ur.role_id
                WHERE u.id = %s
                GROUP BY u.id
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("用户不存在")
            return _user_dict(row)
    finally:
        _put_conn(conn)


def authenticate_user(username: str, password: str, login_ip: str, user_agent: str = "") -> Dict[str, Any]:
    ensure_schema()
    normalized_username = (username or "").strip()
    if not normalized_username or not password:
        raise ValueError("用户名或密码不能为空")

    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _cleanup_expired_sessions(cur)
            cur.execute(
                """
                SELECT id, username, password_hash, full_name, is_active
                FROM auth_users
                WHERE username = %s
                """,
                (normalized_username,),
            )
            row = cur.fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise ValueError("用户名或密码错误")
            if not row["is_active"]:
                raise ValueError("账号已禁用")

            token = secrets.token_urlsafe(32)
            expires_at = _utcnow() + timedelta(days=SESSION_TTL_DAYS)

            cur.execute(
                """
                UPDATE auth_users
                SET last_login_at = NOW(),
                    last_login_ip = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (login_ip or "", row["id"]),
            )
            cur.execute(
                """
                INSERT INTO auth_sessions (session_token, user_id, ip_address, user_agent, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (token, row["id"], login_ip or "", user_agent or "", expires_at),
            )
        conn.commit()
        user = get_user_by_id(row["id"])
        return {"session_token": token, "expires_at": expires_at.isoformat(), "user": user}
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def get_session_user(session_token: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    if not session_token:
        return None
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.id
                FROM auth_sessions s
                JOIN auth_users u ON u.id = s.user_id
                WHERE s.session_token = %s
                  AND s.expires_at > NOW()
                  AND u.is_active = TRUE
                """,
                (session_token,),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            cur.execute(
                """
                UPDATE auth_sessions
                SET last_seen_at = NOW(),
                    expires_at = %s
                WHERE session_token = %s
                """,
                (_utcnow() + timedelta(days=SESSION_TTL_DAYS), session_token),
            )
        conn.commit()
        return get_user_by_id(row["id"])
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def logout_session(session_token: str) -> None:
    if not session_token:
        return
    ensure_schema()
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_sessions WHERE session_token = %s", (session_token,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def change_password(user_id: int, old_password: str, new_password: str) -> None:
    ensure_schema()
    if not old_password or not new_password:
        raise ValueError("原密码和新密码不能为空")

    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT password_hash FROM auth_users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("用户不存在")
            if not verify_password(old_password, row["password_hash"]):
                raise ValueError("原密码不正确")
            cur.execute(
                """
                UPDATE auth_users
                SET password_hash = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (hash_password(new_password), user_id),
            )
            cur.execute("DELETE FROM auth_sessions WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)
