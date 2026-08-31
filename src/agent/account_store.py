"""轻量账号与对话持久化层。

依赖 PostgreSQL（或本地 SQLite）保存账户哈希、会话和消息。密码只以 PBKDF2
哈希形式保存，原始密码不进入数据库、日志或页面状态。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .task_store import _connect_database, _use_database


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iteration_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.b64decode(salt_text),
            int(iteration_text),
        )
        return hmac.compare_digest(base64.b64encode(candidate).decode("ascii"), digest_text)
    except (ValueError, TypeError):
        return False


def _initialize_schema() -> None:
    if not _use_database():
        raise RuntimeError("账号与对话持久化需要配置 DATABASE_URL")
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_users (
                username VARCHAR(32) PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role VARCHAR(20) NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at VARCHAR(40) NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_conversations (
                conversation_id VARCHAR(32) PRIMARY KEY,
                username VARCHAR(32) NOT NULL,
                title VARCHAR(120) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                updated_at VARCHAR(40) NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id VARCHAR(32) PRIMARY KEY,
                conversation_id VARCHAR(32) NOT NULL,
                role VARCHAR(16) NOT NULL,
                content TEXT NOT NULL,
                created_at VARCHAR(40) NOT NULL
            )
            """
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def ensure_admin_account(username: str, password: str, reset_password: bool = False) -> None:
    """首次启动时创建管理员；仅在显式请求时重置已有管理员密码。"""
    if not username or not password:
        return
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT username FROM app_users WHERE username = {placeholder}", (username,)
        )
        if cursor.fetchone() is None:
            cursor.execute(
                f"INSERT INTO app_users (username, password_hash, role, enabled, created_at) "
                f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (username, _hash_password(password), "admin", True, _now()),
            )
            conn.commit()
        elif reset_password:
            cursor.execute(
                f"UPDATE app_users SET password_hash = {placeholder}, enabled = {placeholder} "
                f"WHERE username = {placeholder}",
                (_hash_password(password), True, username),
            )
            conn.commit()
        cursor.close()
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> Optional[dict[str, str]]:
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT username, password_hash, role, enabled FROM app_users WHERE username = {placeholder}",
            (username,),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row or not row[3] or not _verify_password(password, row[1]):
            return None
        return {"username": row[0], "role": row[2]}
    finally:
        conn.close()


def create_user(username: str, password: str, registration_code: str, expected_code: str) -> dict[str, str]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名需为 3-32 位英文、数字、下划线或连字符")
    if len(password) < 8:
        raise ValueError("密码至少需要 8 位")
    if not expected_code or not hmac.compare_digest(registration_code, expected_code):
        raise ValueError("邀请码不正确")

    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT username FROM app_users WHERE username = {placeholder}", (username,))
        if cursor.fetchone() is not None:
            raise ValueError("该用户名已被使用")
        cursor.execute(
            f"INSERT INTO app_users (username, password_hash, role, enabled, created_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (username, _hash_password(password), "operator", True, _now()),
        )
        conn.commit()
        cursor.close()
        return {"username": username, "role": "operator"}
    finally:
        conn.close()


def list_conversations(username: str) -> list[dict[str, Any]]:
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT conversation_id, title, created_at, updated_at FROM chat_conversations "
            f"WHERE username = {placeholder} ORDER BY updated_at DESC LIMIT 30",
            (username,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {"conversation_id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}
            for row in rows
        ]
    finally:
        conn.close()


def create_conversation(username: str, title: str = "新运营分析") -> dict[str, str]:
    _initialize_schema()
    conversation = {
        "conversation_id": uuid.uuid4().hex[:16],
        "username": username,
        "title": title[:120] or "新运营分析",
        "created_at": _now(),
        "updated_at": _now(),
    }
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO chat_conversations (conversation_id, username, title, created_at, updated_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            tuple(conversation.values()),
        )
        conn.commit()
        cursor.close()
        return conversation
    finally:
        conn.close()


def load_messages(conversation_id: str, username: str) -> list[dict[str, str]]:
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT m.message_id, m.role, m.content, m.created_at FROM chat_messages m "
            f"JOIN chat_conversations c ON c.conversation_id = m.conversation_id "
            f"WHERE m.conversation_id = {placeholder} AND c.username = {placeholder} "
            f"ORDER BY m.created_at ASC, m.message_id ASC",
            (conversation_id, username),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {"message_id": row[0], "role": row[1], "content": row[2], "created_at": row[3]}
            for row in rows
        ]
    finally:
        conn.close()


def append_message(conversation_id: str, username: str, role: str, content: str) -> str:
    if role not in {"user", "assistant"}:
        raise ValueError("消息角色不合法")
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        message_id = uuid.uuid4().hex[:16]
        cursor.execute(
            f"SELECT conversation_id FROM chat_conversations WHERE conversation_id = {placeholder} "
            f"AND username = {placeholder}",
            (conversation_id, username),
        )
        if cursor.fetchone() is None:
            raise ValueError("会话不存在或无权写入")
        now = _now()
        cursor.execute(
            f"INSERT INTO chat_messages (message_id, conversation_id, role, content, created_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (message_id, conversation_id, role, content, now),
        )
        cursor.execute(
            f"UPDATE chat_conversations SET updated_at = {placeholder} WHERE conversation_id = {placeholder}",
            (now, conversation_id),
        )
        conn.commit()
        cursor.close()
        return message_id
    finally:
        conn.close()
