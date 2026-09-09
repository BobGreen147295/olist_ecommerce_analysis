"""One-time, non-destructive migration between two PostgreSQL databases.

Run this only inside the Render API service.  It reads the current
``DATABASE_URL`` as the source and ``MIGRATION_TARGET_DATABASE_URL`` as the
destination.  It never prints connection strings or row contents.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2

from src.agent import (
    account_store,
    auth_session_store,
    commerce_store,
    feedback_store,
    merchant_connection_store,
    task_store,
)


TABLES = (
    "operation_tasks",
    "app_users",
    "chat_conversations",
    "chat_messages",
    "auth_sessions",
    "commerce_data_sources",
    "commerce_orders",
    "agent_feedback",
    "agent_run_metrics",
    "merchant_workspaces",
    "oauth_authorization_states",
    "merchant_connections",
    "merchant_terms_acceptances",
    "merchant_sync_runs",
)


def _postgres_url(value: str) -> str:
    value = value.strip()
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        return value
    raise RuntimeError("迁移源和目标都必须是 PostgreSQL")


@contextmanager
def _target_database(url: str):
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original


def _initialize_target(url: str) -> None:
    """Create only the app-owned tables; no source records are changed."""
    with _target_database(url):
        conn, _ = task_store._connect_database()
        conn.close()
        account_store._initialize_schema()
        auth_session_store._ensure_schema()
        commerce_store._ensure_schema()
        feedback_store._initialize_schema()
        merchant_connection_store._ensure_schema()


def _exists(cursor, table: str) -> bool:
    cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
    return cursor.fetchone()[0] is not None


def migrate() -> dict[str, int]:
    source_url = _postgres_url(os.environ.get("DATABASE_URL", ""))
    target_url = _postgres_url(os.environ.get("MIGRATION_TARGET_DATABASE_URL", ""))
    if source_url == target_url:
        raise RuntimeError("迁移源和目标不能相同")

    _initialize_target(target_url)
    copied: dict[str, int] = {}
    with psycopg2.connect(source_url) as source, psycopg2.connect(target_url) as target:
        with source.cursor() as source_cursor, target.cursor() as target_cursor:
            for table in TABLES:
                if not _exists(source_cursor, table):
                    continue
                if not _exists(target_cursor, table):
                    raise RuntimeError(f"目标缺少应用表：{table}")
                target_cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                if target_cursor.fetchone()[0]:
                    raise RuntimeError(f"目标表不是空表，拒绝覆盖：{table}")

                source_cursor.execute(f'SELECT * FROM "{table}"')
                rows = source_cursor.fetchall()
                if not rows:
                    copied[table] = 0
                    continue
                columns = [column.name for column in source_cursor.description]
                column_sql = ", ".join(f'"{column}"' for column in columns)
                placeholders = ", ".join("%s" for _ in columns)
                target_cursor.executemany(
                    f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})',
                    rows,
                )
                copied[table] = len(rows)
    return copied


if __name__ == "__main__":
    summary = migrate()
    print("迁移完成：" + ", ".join(f"{table}={count}" for table, count in summary.items()))
