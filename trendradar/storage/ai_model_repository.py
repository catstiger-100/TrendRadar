# coding=utf-8
"""
AI 模型配置仓库模块。

负责：
- 维护“快速模型 / 深度思考模型”双模型配置
- 提供常见供应商默认 BASE URL 与推荐模型名称
- 提供模型配置连通性测试能力
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

import psycopg2.extras

from trendradar.ai.client import AIClient
from trendradar.storage.news_repository import _get_conn, _put_conn

SCHEMA_LOCK_KEY = 551202605
_schema_ready = False
_schema_lock = threading.Lock()

PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    # 说明：
    # - base_url 优先选择 OpenAI 兼容或 LiteLLM 常用入口
    # - model_name 提供一个适合作为默认值的推荐模型，客户可自行覆盖
    "OpenAI": {
        "provider_code": "openai",
        "base_url": "https://api.openai.com/v1",
        "fast_model_name": "gpt-5.5-mini",
        "reasoning_model_name": "gpt-5.5",
    },
    "Anthropic": {
        "provider_code": "anthropic",
        "base_url": "https://api.anthropic.com",
        "fast_model_name": "claude-sonnet-4-5",
        "reasoning_model_name": "claude-opus-4-1",
    },
    "Google": {
        "provider_code": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "fast_model_name": "gemini-2.5-flash",
        "reasoning_model_name": "gemini-2.5-pro",
    },
    "阿里百炼": {
        "provider_code": "dashscope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "fast_model_name": "qwen3-30b-a3b-instruct-2507",
        "reasoning_model_name": "qwen-max",
    },
    "DeepSeek": {
        "provider_code": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "fast_model_name": "deepseek-chat",
        "reasoning_model_name": "deepseek-reasoner",
    },
    "智普": {
        "provider_code": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "fast_model_name": "glm-4.5-air",
        "reasoning_model_name": "glm-4.5",
    },
    "MinMax": {
        "provider_code": "openai",
        "base_url": "https://api.minimaxi.com/v1",
        "fast_model_name": "MiniMax-Text-01",
        "reasoning_model_name": "MiniMax-M1",
    },
    "Kimi": {
        "provider_code": "moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "fast_model_name": "moonshot-v1-8k",
        "reasoning_model_name": "kimi-thinking-preview",
    },
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ai_model_settings (
    id SMALLINT PRIMARY KEY DEFAULT 1,
    fast_model_name TEXT NOT NULL DEFAULT '',
    fast_provider TEXT NOT NULL DEFAULT '',
    fast_base_url TEXT NOT NULL DEFAULT '',
    fast_api_key TEXT NOT NULL DEFAULT '',
    reasoning_model_name TEXT NOT NULL DEFAULT '',
    reasoning_provider TEXT NOT NULL DEFAULT '',
    reasoning_base_url TEXT NOT NULL DEFAULT '',
    reasoning_api_key TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ai_model_settings_singleton CHECK (id = 1)
);
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
                cur.execute(
                    """
                    INSERT INTO ai_model_settings (id)
                    VALUES (1)
                    ON CONFLICT (id) DO NOTHING
                    """
                )
            conn.commit()
            _schema_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            _put_conn(conn)


def get_provider_presets() -> Dict[str, Dict[str, str]]:
    return PROVIDER_PRESETS


def get_settings() -> Dict[str, Any]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    fast_model_name,
                    fast_provider,
                    fast_base_url,
                    fast_api_key,
                    reasoning_model_name,
                    reasoning_provider,
                    reasoning_base_url,
                    reasoning_api_key,
                    created_at,
                    updated_at
                FROM ai_model_settings
                WHERE id = 1
                """
            )
            row = cur.fetchone()
        if not row:
            return _empty_settings()
        return _row_to_dict(row)
    finally:
        _put_conn(conn)


def update_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema()
    data = _normalize_payload(payload)
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE ai_model_settings
                SET
                    fast_model_name = %(fast_model_name)s,
                    fast_provider = %(fast_provider)s,
                    fast_base_url = %(fast_base_url)s,
                    fast_api_key = %(fast_api_key)s,
                    reasoning_model_name = %(reasoning_model_name)s,
                    reasoning_provider = %(reasoning_provider)s,
                    reasoning_base_url = %(reasoning_base_url)s,
                    reasoning_api_key = %(reasoning_api_key)s,
                    updated_at = NOW()
                WHERE id = 1
                RETURNING
                    id,
                    fast_model_name,
                    fast_provider,
                    fast_base_url,
                    fast_api_key,
                    reasoning_model_name,
                    reasoning_provider,
                    reasoning_base_url,
                    reasoning_api_key,
                    created_at,
                    updated_at
                """,
                data,
            )
            row = cur.fetchone()
        conn.commit()
        return _row_to_dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def build_runtime_ai_configs() -> Dict[str, Dict[str, Any]]:
    """
    构建运行期 AI 配置。

    返回：
    - shared: 兼容旧代码的默认配置，优先使用深度思考模型
    - fast: 快速模型配置，适合翻译/轻量任务
    - reasoning: 深度思考模型配置，适合分析任务
    """
    settings = get_settings()

    fast = _to_litellm_config(
        provider=settings.get("fast_provider", ""),
        model_name=settings.get("fast_model_name", ""),
        api_key=settings.get("fast_api_key", ""),
        base_url=settings.get("fast_base_url", ""),
    )
    reasoning = _to_litellm_config(
        provider=settings.get("reasoning_provider", ""),
        model_name=settings.get("reasoning_model_name", ""),
        api_key=settings.get("reasoning_api_key", ""),
        base_url=settings.get("reasoning_base_url", ""),
    )

    shared = reasoning if reasoning.get("MODEL") else fast
    return {
        "shared": shared,
        "fast": fast,
        "reasoning": reasoning,
    }


def test_model_connection(model_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if model_type not in ("fast", "reasoning"):
        raise ValueError("模型类型无效")

    settings = get_settings()
    data = _normalize_payload(payload or {})
    merged = {
        "fast_model_name": data.get("fast_model_name") or settings.get("fast_model_name", ""),
        "fast_provider": data.get("fast_provider") or settings.get("fast_provider", ""),
        "fast_base_url": data.get("fast_base_url") or settings.get("fast_base_url", ""),
        "fast_api_key": data.get("fast_api_key") or settings.get("fast_api_key", ""),
        "reasoning_model_name": data.get("reasoning_model_name") or settings.get("reasoning_model_name", ""),
        "reasoning_provider": data.get("reasoning_provider") or settings.get("reasoning_provider", ""),
        "reasoning_base_url": data.get("reasoning_base_url") or settings.get("reasoning_base_url", ""),
        "reasoning_api_key": data.get("reasoning_api_key") or settings.get("reasoning_api_key", ""),
    }

    prefix = "fast" if model_type == "fast" else "reasoning"
    config = _to_litellm_config(
        provider=merged.get(f"{prefix}_provider", ""),
        model_name=merged.get(f"{prefix}_model_name", ""),
        api_key=merged.get(f"{prefix}_api_key", ""),
        base_url=merged.get(f"{prefix}_base_url", ""),
    )

    client = AIClient(
        {
            **config,
            "TEMPERATURE": 0.1,
            "MAX_TOKENS": 32,
            "TIMEOUT": 25,
            "NUM_RETRIES": 0,
        }
    )
    valid, error = client.validate_config()
    if not valid:
        return {
            "success": False,
            "message": error,
            "model": config.get("MODEL", ""),
        }

    reply = client.chat(
        [
            {"role": "system", "content": "You are a concise connectivity test assistant."},
            {"role": "user", "content": "Reply with exactly: OK"},
        ],
        max_tokens=8,
        temperature=0,
    )
    normalized = (reply or "").strip()
    return {
        "success": True,
        "message": "连接测试成功",
        "model": config.get("MODEL", ""),
        "reply": normalized,
    }


def _to_litellm_config(provider: str, model_name: str, api_key: str, base_url: str) -> Dict[str, Any]:
    provider_name = (provider or "").strip()
    model = (model_name or "").strip()
    if provider_name and model and "/" not in model:
        provider_code = PROVIDER_PRESETS.get(provider_name, {}).get("provider_code") or provider_name.lower()
        model = f"{provider_code}/{model}"
    return {
        "MODEL": model,
        "API_KEY": (api_key or "").strip(),
        "API_BASE": (base_url or "").strip(),
    }


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    return {
        "fast_model_name": str(payload.get("fast_model_name", "") or "").strip(),
        "fast_provider": str(payload.get("fast_provider", "") or "").strip(),
        "fast_base_url": str(payload.get("fast_base_url", "") or "").strip(),
        "fast_api_key": str(payload.get("fast_api_key", "") or "").strip(),
        "reasoning_model_name": str(payload.get("reasoning_model_name", "") or "").strip(),
        "reasoning_provider": str(payload.get("reasoning_provider", "") or "").strip(),
        "reasoning_base_url": str(payload.get("reasoning_base_url", "") or "").strip(),
        "reasoning_api_key": str(payload.get("reasoning_api_key", "") or "").strip(),
    }


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "fast_model_name": row.get("fast_model_name", "") or "",
        "fast_provider": row.get("fast_provider", "") or "",
        "fast_base_url": row.get("fast_base_url", "") or "",
        "fast_api_key": row.get("fast_api_key", "") or "",
        "reasoning_model_name": row.get("reasoning_model_name", "") or "",
        "reasoning_provider": row.get("reasoning_provider", "") or "",
        "reasoning_base_url": row.get("reasoning_base_url", "") or "",
        "reasoning_api_key": row.get("reasoning_api_key", "") or "",
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
    }


def _empty_settings() -> Dict[str, Any]:
    return {
        "id": 1,
        "fast_model_name": "",
        "fast_provider": "",
        "fast_base_url": "",
        "fast_api_key": "",
        "reasoning_model_name": "",
        "reasoning_provider": "",
        "reasoning_base_url": "",
        "reasoning_api_key": "",
        "created_at": "",
        "updated_at": "",
    }
