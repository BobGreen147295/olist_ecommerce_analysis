"""商家工作区与外部平台连接的安全持久化层。

本模块不提供 HTTP 路由。只有完成登录会话与工作区归属校验后，OAuth
回调才可以调用这里的函数。访问令牌只以 Fernet 密文形式写入数据库，读取
令牌的函数也不会向 API 或前端返回原始值。
"""

from __future__ import annotations

import hashlib
import json
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
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


_SUMMARY_COUNT_KEYS = ("orders", "customers", "products", "inventory_items")


def _summary_comparison(
    current: dict[str, Any], previous: dict[str, Any] | None, previous_synced_at: str | None,
) -> dict[str, Any] | None:
    """比较两次安全汇总；只返回聚合计数差值。"""
    if not previous or not previous_synced_at:
        return None
    return {
        "previous_synced_at": previous_synced_at,
        "deltas": {
            key: int(current.get(key, 0)) - int(previous.get(key, 0))
            for key in _SUMMARY_COUNT_KEYS
        },
    }


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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS merchant_sync_runs (
                sync_id VARCHAR(32) PRIMARY KEY,
                workspace_id VARCHAR(32) NOT NULL,
                provider VARCHAR(24) NOT NULL,
                shop_domain VARCHAR(255) NOT NULL,
                status VARCHAR(24) NOT NULL,
                summary_json TEXT NOT NULL,
                started_at VARCHAR(40) NOT NULL,
                completed_at VARCHAR(40)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_merchant_sync_runs_workspace "
            "ON merchant_sync_runs (workspace_id, provider, completed_at)"
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


def consume_authorization_state(raw_state: str) -> dict[str, str]:
    """验证并消耗 state，确保授权回调不能被重放或跨工作区使用。"""
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT state_id, workspace_id, provider, shop_domain, expires_at, consumed_at "
            f"FROM oauth_authorization_states WHERE state_digest = {placeholder}",
            (_state_digest(raw_state),),
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


def get_shopify_connection_for_sync(owner_username: str) -> dict[str, str]:
    """仅供服务端同步调用解密令牌；绝不能由 HTTP 响应返回这个字典。"""
    workspace = get_or_create_workspace(owner_username)
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT connection_id, shop_domain, encrypted_access_token FROM merchant_connections "
            f"WHERE workspace_id = {placeholder} AND provider = {placeholder} AND status IN ('connected', 'synced') "
            f"ORDER BY updated_at DESC LIMIT 1",
            (workspace["workspace_id"], "shopify"),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row:
            raise ValueError("尚未连接 Shopify 店铺")
        try:
            token = _cipher().decrypt(row[2].encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise RuntimeError("Shopify 授权令牌无法解密，请重新授权") from exc
        return {"workspace_id": workspace["workspace_id"], "connection_id": row[0], "shop_domain": row[1], "access_token": token}
    finally:
        conn.close()


def save_shopify_sync_summary(workspace_id: str, shop_domain: str, summary: dict[str, Any]) -> dict[str, Any]:
    """持久化只含聚合计数的同步结果，不存订单、客户或设备级原始数据。"""
    allowed = {"orders", "customers", "products", "inventory_items", "currency_code", "order_trend"}
    safe_summary = {key: summary[key] for key in allowed if key in summary}
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        now = _now()
        cursor.execute(
            f"SELECT summary_json, completed_at FROM merchant_sync_runs WHERE workspace_id = {placeholder} "
            f"AND provider = {placeholder} AND shop_domain = {placeholder} AND status = 'completed' "
            f"ORDER BY completed_at DESC LIMIT 1",
            (workspace_id, "shopify", shop_domain),
        )
        previous_row = cursor.fetchone()
        cursor.execute(
            f"INSERT INTO merchant_sync_runs "
            f"(sync_id, workspace_id, provider, shop_domain, status, summary_json, started_at, completed_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (uuid.uuid4().hex[:24], workspace_id, "shopify", shop_domain, "completed", json.dumps(safe_summary), now, now),
        )
        cursor.execute(
            f"UPDATE merchant_connections SET status = {placeholder}, updated_at = {placeholder} "
            f"WHERE workspace_id = {placeholder} AND provider = {placeholder} AND shop_domain = {placeholder}",
            ("synced", now, workspace_id, "shopify", shop_domain),
        )
        conn.commit()
        cursor.close()
        previous_summary = json.loads(previous_row[0]) if previous_row else None
        comparison = _summary_comparison(safe_summary, previous_summary, previous_row[1] if previous_row else None)
        return {"status": "synced", "last_synced_at": now, "summary": safe_summary, "comparison": comparison}
    finally:
        conn.close()


def get_shopify_connection_status(owner_username: str) -> dict[str, Any] | None:
    """返回给前端的安全连接状态；不含令牌、密文或任何原始商店数据。"""
    workspace = get_or_create_workspace(owner_username)
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT shop_domain, status FROM merchant_connections WHERE workspace_id = {placeholder} "
            f"AND provider = {placeholder} ORDER BY updated_at DESC LIMIT 1",
            (workspace["workspace_id"], "shopify"),
        )
        connection = cursor.fetchone()
        if not connection:
            cursor.close()
            return None
        cursor.execute(
            f"SELECT summary_json, completed_at FROM merchant_sync_runs WHERE workspace_id = {placeholder} "
            f"AND provider = {placeholder} AND shop_domain = {placeholder} AND status = 'completed' "
            f"ORDER BY completed_at DESC LIMIT 2",
            (workspace["workspace_id"], "shopify", connection[0]),
        )
        rows = cursor.fetchall()
        cursor.close()
        latest = rows[0] if rows else None
        previous = rows[1] if len(rows) > 1 else None
        latest_summary = json.loads(latest[0]) if latest else None
        previous_summary = json.loads(previous[0]) if previous else None
        return {
            "provider": "shopify", "shop_domain": connection[0], "status": connection[1],
            "last_synced_at": latest[1] if latest else None,
            "summary": latest_summary,
            "comparison": _summary_comparison(latest_summary, previous_summary, previous[1] if previous else None) if latest_summary else None,
        }
    finally:
        conn.close()
