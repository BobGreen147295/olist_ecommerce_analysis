"""One-time, non-destructive migration between two PostgreSQL databases.

Run this only inside the Render API service.  It reads the current
``DATABASE_URL`` as the source and ``MIGRATION_TARGET_DATABASE_URL`` as the
destination.  It never prints connection strings or row contents.
"""

from __future__ import annotations

import os
import sys
import argparse
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import (
    account_store,
    auth_session_store,
    commerce_store,
    feedback_store,
    merchant_connection_store,
    pilot_application_store,
    chat_usage_store,
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
    "pilot_applications",
    "chat_usage",
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
    managed = os.environ.get("USE_MANAGED_POSTGRES")
    os.environ["DATABASE_URL"] = url
    os.environ["USE_MANAGED_POSTGRES"] = "0"
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original
        if managed is None:
            os.environ.pop("USE_MANAGED_POSTGRES", None)
        else:
            os.environ["USE_MANAGED_POSTGRES"] = managed


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
        pilot_application_store._initialize_schema()
        chat_usage_store._ensure_schema()


def _exists(cursor, table: str) -> bool:
    cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
    return cursor.fetchone()[0] is not None


def _verify_rows(source_rows, target_cursor, table: str, columns: list[str]) -> None:
    column_sql = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
    target_cursor.execute(f'SELECT {column_sql} FROM "{table}"')
    target_rows = target_cursor.fetchall()

    def fingerprints(rows):
        # ponytail: in-memory fingerprints for pilot-scale data; stream for large migrations.
        return sorted(hashlib.sha256(json.dumps(row, default=str, ensure_ascii=False).encode()).digest() for row in rows)

    if len(source_rows) != len(target_rows) or fingerprints(source_rows) != fingerprints(target_rows):
        raise RuntimeError(f"迁移内容验证失败：{table}")


def migrate(*, verify_only: bool = False) -> dict[str, int]:
    source_url = _postgres_url(os.environ.get("DATABASE_URL", ""))
    target_url = _postgres_url(os.environ.get("MIGRATION_TARGET_DATABASE_URL", ""))
    if source_url == target_url:
        raise RuntimeError("迁移源和目标不能相同")

    if not verify_only:
        _initialize_target(target_url)
    copied: dict[str, int] = {}
    with psycopg2.connect(source_url) as source, psycopg2.connect(target_url) as target:
        source.set_session(readonly=True, isolation_level="REPEATABLE READ")
        target.set_session(readonly=verify_only, isolation_level="REPEATABLE READ")
        with source.cursor() as source_cursor, target.cursor() as target_cursor:
            for table in TABLES:
                if not _exists(source_cursor, table):
                    continue
                if not _exists(target_cursor, table):
                    raise RuntimeError(f"目标缺少应用表：{table}")
                target_cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                if not verify_only and target_cursor.fetchone()[0]:
                    raise RuntimeError(f"目标表不是空表，拒绝覆盖：{table}")

            # Check every target before copying; one transaction rolls back all inserts on failure.
            for table in TABLES:
                if not _exists(source_cursor, table):
                    continue
                source_cursor.execute(f'SELECT * FROM "{table}"')
                rows = source_cursor.fetchall()
                columns = [column.name for column in source_cursor.description]
                column_sql = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
                placeholders = ", ".join("%s" for _ in columns)
                if rows and not verify_only:
                    target_cursor.executemany(
                        f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})', rows,
                    )
                _verify_rows(rows, target_cursor, table, columns)
                copied[table] = len(rows)
    return copied


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="只读核对源与目标，不建表或写入")
    arguments = parser.parse_args()
    summary = migrate(verify_only=arguments.verify_only)
    print(("验证完成：" if arguments.verify_only else "迁移完成并验证：") + ", ".join(f"{table}={count}" for table, count in summary.items()))
