"""短时、可撤销的 API 登录会话。

会话令牌只在 TLS 请求的 Authorization 请求头中传输。数据库保存随机会话 ID
和到期时间，不保存原始 Bearer 令牌或密码。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from .task_store import _connect_database, _use_database


_TOKEN_TTL_MINUTES = 8 * 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _signing_key() -> bytes:
    value = os.environ.get("SESSION_SIGNING_KEY", "").strip()
    if len(value) < 32:
        raise RuntimeError("SESSION_SIGNING_KEY 至少需要 32 个随机字符")
    return value.encode("utf-8")


def _sign(value: str) -> str:
    return hmac.new(_signing_key(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _ensure_schema() -> None:
    if not _use_database():
        raise RuntimeError("登录会话需要配置 DATABASE_URL")
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_id VARCHAR(64) PRIMARY KEY,
                username VARCHAR(32) NOT NULL,
                role VARCHAR(20) NOT NULL,
                expires_at VARCHAR(40) NOT NULL,
                revoked_at VARCHAR(40),
                created_at VARCHAR(40) NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (username, expires_at)"
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def issue_session(username: str, role: str) -> str:
    _ensure_schema()
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_TTL_MINUTES)
    expiry_text = expires_at.isoformat(timespec="seconds")
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO auth_sessions (session_id, username, role, expires_at, revoked_at, created_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (session_id, username, role, expiry_text, None, _now()),
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()
    encoded_username = base64.urlsafe_b64encode(username.encode("utf-8")).decode("ascii").rstrip("=")
    payload = f"v1.{session_id}.{int(expires_at.timestamp())}.{encoded_username}"
    return f"{payload}.{_sign(payload)}"


def get_session(token: str) -> dict[str, str]:
    try:
        version, session_id, expiry, encoded_username, signature = token.split(".", 4)
        payload = f"{version}.{session_id}.{expiry}.{encoded_username}"
        username = base64.urlsafe_b64decode(encoded_username + "=" * (-len(encoded_username) % 4)).decode("utf-8")
        if version != "v1" or int(expiry) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
        if not hmac.compare_digest(_sign(payload), signature):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        raise ValueError("登录会话无效或已过期") from None

    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT username, role, expires_at, revoked_at FROM auth_sessions "
            f"WHERE session_id = {placeholder}", (session_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row or row[0] != username or row[3] or row[2] <= _now():
            raise ValueError("登录会话无效或已撤销")
        return {"session_id": session_id, "username": row[0], "role": row[1]}
    finally:
        conn.close()


def revoke_session(session_id: str) -> None:
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE auth_sessions SET revoked_at = {placeholder} WHERE session_id = {placeholder} "
            f"AND revoked_at IS NULL",
            (_now(), session_id),
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()
