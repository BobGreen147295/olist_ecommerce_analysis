"""商家工作区与外部平台连接的安全持久化层。

本模块不提供 HTTP 路由。只有完成登录会话与工作区归属校验后，OAuth
回调才可以调用这里的函数。访问令牌只以 Fernet 密文形式写入数据库，读取
令牌的函数也不会向 API 或前端返回原始值。
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .task_store import _connect_database, _use_database


_SHOP_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")
_STATE_TTL_MINUTES = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cipher() -> Fernet:
    """返回密钥保管器；缺少或无效密钥时拒绝写入，而不是降级为明文。"""
    key = os.environ.get("CONNECTION_TOKEN_ENCRYPTION_KEY", "").strip().encode("utf-8")
    if not key:
        raise RuntimeError("缺少 CONNECTION_TOKEN_ENCRYPTION_KEY，不能保存商家连接")
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("CONNECTION_TOKEN_ENCRYPTION_KEY 不是有效的 Fernet 密钥") from exc


def _ensure_schema() -> None:
    if not _use_database():
        raise RuntimeError("商家连接需要配置 DATABASE_URL")
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS merchant_workspaces (
                workspace_id VARCHAR(32) PRIMARY KEY,
                owner_username VARCHAR(32) NOT NULL UNIQUE,
                display_name VARCHAR(120) NOT NULL,
                created_at VARCHAR(40) NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_authorization_states (
                state_id VARCHAR(32) PRIMARY KEY,
                state_digest VARCHAR(64) NOT NULL UNIQUE,
                workspace_id VARCHAR(32) NOT NULL,
                owner_username VARCHAR(32) NOT NULL,
                provider VARCHAR(24) NOT NULL,
                shop_domain VARCHAR(255) NOT NULL,
                expires_at VARCHAR(40) NOT NULL,
                consumed_at VARCHAR(40),
                created_at VARCHAR(40) NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS merchant_connections (
                connection_id VARCHAR(32) PRIMARY KEY,
                workspace_id VARCHAR(32) NOT NULL,
                provider VARCHAR(24) NOT NULL,
                shop_domain VARCHAR(255) NOT NULL,
                encrypted_access_token TEXT NOT NULL,
                granted_scopes TEXT NOT NULL,
                status VARCHAR(24) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                updated_at VARCHAR(40) NOT NULL,
                UNIQUE (workspace_id, provider, shop_domain)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_merchant_connections_workspace "
            "ON merchant_connections (workspace_id, provider, status)"
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def get_or_create_workspace(owner_username: str, display_name: str | None = None) -> dict[str, str]:
    """每个已认证用户获得一个独立的默认工作区。"""
    if not owner_username:
        raise ValueError("需要已认证的商家身份")
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT workspace_id, owner_username, display_name FROM merchant_workspaces "
            f"WHERE owner_username = {placeholder}",
            (owner_username,),
        )
        row = cursor.fetchone()
        if row:
            cursor.close()
            return {"workspace_id": row[0], "owner_username": row[1], "display_name": row[2]}
        workspace = {
            "workspace_id": uuid.uuid4().hex[:24],
            "owner_username": owner_username,
            "display_name": (display_name or "我的商家工作区")[:120],
        }
        cursor.execute(
            f"INSERT INTO merchant_workspaces (workspace_id, owner_username, display_name, created_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (workspace["workspace_id"], workspace["owner_username"], workspace["display_name"], _now()),
        )
        conn.commit()
        cursor.close()
        return workspace
    finally:
        conn.close()


def issue_authorization_state(owner_username: str, shop_domain: str) -> str:
    """创建只可使用一次的 OAuth state；数据库从不保存原始 state。"""
    normalized_shop = shop_domain.strip().lower()
    if not _SHOP_DOMAIN.fullmatch(normalized_shop):
        raise ValueError("店铺域名必须是 xxx.myshopify.com")
    workspace = get_or_create_workspace(owner_username)
    raw_state = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=_STATE_TTL_MINUTES)).isoformat(timespec="seconds")
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO oauth_authorization_states "
            f"(state_id, state_digest, workspace_id, owner_username, provider, shop_domain, expires_at, consumed_at, created_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (uuid.uuid4().hex[:24], _state_digest(raw_state), workspace["workspace_id"], owner_username,
             "shopify", normalized_shop, expires_at, None, _now()),
        )
        conn.commit()
        cursor.close()
        return raw_state
    finally:
        conn.close()


def consume_authorization_state(owner_username: str, raw_state: str) -> dict[str, str]:
    """验证并消耗 state，确保授权回调不能被重放或跨工作区使用。"""
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT state_id, workspace_id, provider, shop_domain, expires_at, consumed_at "
            f"FROM oauth_authorization_states WHERE state_digest = {placeholder} AND owner_username = {placeholder}",
            (_state_digest(raw_state), owner_username),
        )
        row = cursor.fetchone()
        if not row or row[5] or row[4] <= _now():
            raise ValueError("授权状态无效、已使用或已过期")
        cursor.execute(
            f"UPDATE oauth_authorization_states SET consumed_at = {placeholder} WHERE state_id = {placeholder} "
            f"AND consumed_at IS NULL",
            (_now(), row[0]),
        )
        if cursor.rowcount != 1:
            raise ValueError("授权状态已被使用")
        conn.commit()
        cursor.close()
        return {"workspace_id": row[1], "provider": row[2], "shop_domain": row[3]}
    finally:
        conn.close()


def save_shopify_connection(workspace_id: str, shop_domain: str, access_token: str, granted_scopes: list[str]) -> None:
    """保存商家授权后的令牌密文；调用方不得记录 access_token。"""
    normalized_shop = shop_domain.strip().lower()
    if not _SHOP_DOMAIN.fullmatch(normalized_shop) or not access_token:
        raise ValueError("Shopify 连接参数无效")
    encrypted_token = _cipher().encrypt(access_token.encode("utf-8")).decode("ascii")
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        now = _now()
        cursor.execute(
            f"INSERT INTO merchant_connections "
            f"(connection_id, workspace_id, provider, shop_domain, encrypted_access_token, granted_scopes, status, created_at, updated_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) "
            f"ON CONFLICT (workspace_id, provider, shop_domain) DO UPDATE SET "
            f"encrypted_access_token = EXCLUDED.encrypted_access_token, granted_scopes = EXCLUDED.granted_scopes, "
            f"status = EXCLUDED.status, updated_at = EXCLUDED.updated_at",
            (uuid.uuid4().hex[:24], workspace_id, "shopify", normalized_shop, encrypted_token,
             ",".join(sorted(set(granted_scopes))), "connected", now, now),
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def list_connection_summaries(owner_username: str) -> list[dict[str, Any]]:
    """仅返回连接元数据，不返回令牌或可逆密文。"""
    workspace = get_or_create_workspace(owner_username)
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT provider, shop_domain, granted_scopes, status, created_at, updated_at "
            f"FROM merchant_connections WHERE workspace_id = {placeholder} ORDER BY updated_at DESC",
            (workspace["workspace_id"],),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {"provider": row[0], "shop_domain": row[1], "granted_scopes": row[2].split(",") if row[2] else [],
             "status": row[3], "created_at": row[4], "updated_at": row[5]}
            for row in rows
        ]
    finally:
        conn.close()
