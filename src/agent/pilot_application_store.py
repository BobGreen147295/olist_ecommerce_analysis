"""Minimal storage for merchant pilot applications."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .task_store import _connect_database, _use_database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _initialize_schema() -> None:
    if not _use_database():
        raise RuntimeError("试点申请需要配置 DATABASE_URL")
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pilot_applications (
                application_id VARCHAR(32) PRIMARY KEY,
                contact_email VARCHAR(254) NOT NULL,
                shop_domain VARCHAR(255) NOT NULL,
                monthly_orders VARCHAR(20) NOT NULL,
                challenge VARCHAR(32) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'new',
                consented_at VARCHAR(40) NOT NULL,
                created_at VARCHAR(40) NOT NULL
            )
            """
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def create_pilot_application(contact_email: str, shop_domain: str, monthly_orders: str, challenge: str) -> str:
    _initialize_schema()
    application_id = uuid.uuid4().hex[:16]
    now = _now()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO pilot_applications (application_id, contact_email, shop_domain, monthly_orders, challenge, status, consented_at, created_at) "
            f"VALUES ({', '.join([placeholder] * 8)})",
            (application_id, contact_email, shop_domain, monthly_orders, challenge, "new", now, now),
        )
        conn.commit()
        cursor.close()
        return application_id
    finally:
        conn.close()


def list_pilot_applications() -> list[dict[str, Any]]:
    _initialize_schema()
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT application_id, contact_email, shop_domain, monthly_orders, challenge, status, created_at "
            "FROM pilot_applications ORDER BY created_at DESC LIMIT 100"
        )
        rows = cursor.fetchall()
        cursor.close()
        fields = ["application_id", "contact_email", "shop_domain", "monthly_orders", "challenge", "status", "created_at"]
        return [dict(zip(fields, row)) for row in rows]
    finally:
        conn.close()
