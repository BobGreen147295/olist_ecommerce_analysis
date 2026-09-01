"""运营任务持久化层。

默认使用本地 JSON，适合开发和离线演示；配置 DATABASE_URL 后自动使用
PostgreSQL，适合 Streamlit Cloud 等多用户部署。页面和 Agent 不直接操作存储细节。
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_DIR = Path(__file__).resolve().parents[2]
TASKS_PATH = Path(os.environ.get(
    "TASKS_PATH", str(PROJECT_DIR / "data" / "processed" / "operation_tasks.json")
))
VALID_STATUSES = {"draft", "confirmed", "rejected", "completed"}
EDITABLE_FIELDS = {
    "priority", "title", "actions", "audience", "channel", "budget",
    "duration_days", "expected_metric", "expected_effect",
    "market", "timezone", "locale", "attribution_window_days", "consent_basis",
}


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if value:
        return value
    # Streamlit Cloud 的 Secrets 不会自动注入 os.environ，需要在运行时读取。
    try:
        import streamlit as st
        return str(st.secrets.get("DATABASE_URL", "") or "").strip()
    except Exception:
        return ""


def _use_database() -> bool:
    return bool(_database_url())


def storage_mode() -> str:
    """返回当前任务存储模式，供页面展示且不暴露连接地址。"""
    url = _database_url()
    if url.startswith(("postgres://", "postgresql://")):
        return "PostgreSQL"
    if url.startswith("sqlite:///"):
        return "SQLite"
    return "本地 JSON"


def check_database_connection() -> tuple[bool, str]:
    """检查数据库连接，不返回账号、主机或连接串等敏感信息。"""
    if not _use_database():
        return False, "未配置 DATABASE_URL"
    try:
        conn, _ = _connect_database()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True, "连接正常"
    except Exception as exc:
        return False, f"连接失败：{type(exc).__name__}"


def _connect_database():
    """连接 PostgreSQL 或 SQLite URL，并在首次使用时建表。"""
    url = _database_url()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError("配置 DATABASE_URL 后需要安装 psycopg2-binary") from exc
        conn = psycopg2.connect(url)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_tasks (
                task_id VARCHAR(32) PRIMARY KEY,
                status VARCHAR(20) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                updated_at VARCHAR(40) NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.commit()
        cursor.close()
        return conn, "%s"
    if url.startswith("sqlite:///"):
        db_path = url[len("sqlite:///"):]
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.commit()
        return conn, "?"
    raise ValueError("DATABASE_URL 仅支持 postgresql:// 或 sqlite:/// 格式")


def _db_load_tasks() -> list[dict[str, Any]]:
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT payload FROM operation_tasks ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [json.loads(row[0]) for row in rows]
    finally:
        conn.close()


def _db_save_task(task: dict[str, Any]) -> None:
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        if placeholder == "%s":
            cursor.execute(
                """
                INSERT INTO operation_tasks (task_id, status, created_at, updated_at, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (task_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                (task["task_id"], task["status"], task["created_at"], task["updated_at"], json.dumps(task, ensure_ascii=False)),
            )
        else:
            cursor.execute(
                """
                INSERT INTO operation_tasks (task_id, status, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (task["task_id"], task["status"], task["created_at"], task["updated_at"], json.dumps(task, ensure_ascii=False)),
            )
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_tasks(path: Optional[Path] = None, owner: Optional[str] = None) -> list[dict[str, Any]]:
    if path is None and _use_database():
        tasks = _db_load_tasks()
        return tasks if owner is None else [task for task in tasks if task.get("owner") == owner]
    path = path or TASKS_PATH
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        tasks = value if isinstance(value, list) else []
        return tasks if owner is None else [task for task in tasks if task.get("owner") == owner]
    except (OSError, json.JSONDecodeError):
        return []


def save_tasks(tasks: list[dict[str, Any]], path: Optional[Path] = None) -> None:
    if path is None and _use_database():
        for task in tasks:
            _db_save_task(task)
        return
    path = path or TASKS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def create_task(
    draft: dict[str, Any],
    question: str = "",
    source_diagnosis: Optional[dict] = None,
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> dict[str, Any]:
    now = _now()
    task = {
        "task_id": uuid.uuid4().hex[:12],
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "source_question": question,
        "source_diagnosis": source_diagnosis or {},
        "owner": owner,
    }
    for field in EDITABLE_FIELDS:
        if field in draft:
            task[field] = draft[field]
    if path is None and _use_database():
        _db_save_task(task)
    else:
        tasks = load_tasks(path)
        tasks.insert(0, task)
        save_tasks(tasks, path)
    return task


def update_task(
    task_id: str,
    updates: dict[str, Any],
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id:
            continue
        if owner is not None and task.get("owner") != owner:
            continue
        for field, value in updates.items():
            if field in EDITABLE_FIELDS:
                task[field] = value
        if "status" in updates and updates["status"] in VALID_STATUSES:
            task["status"] = updates["status"]
        task["updated_at"] = _now()
        if path is None and _use_database():
            _db_save_task(task)
        else:
            save_tasks(tasks, path)
        return task
    return None


def get_task(task_id: str, path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    return next((task for task in load_tasks(path) if task.get("task_id") == task_id), None)


def complete_task(
    task_id: str,
    result: dict[str, Any],
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """写入实验结果并将任务置为 completed。"""
    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id:
            continue
        if owner is not None and task.get("owner") != owner:
            continue
        if task.get("status") != "confirmed":
            raise ValueError("只有 confirmed 状态的任务可以回填结果")
        task["result"] = result
        task["status"] = "completed"
        task["updated_at"] = _now()
        if path is None and _use_database():
            _db_save_task(task)
        else:
            save_tasks(tasks, path)
        return task
    return None


def launch_simulated_campaign(
    task_id: str,
    audience_size: int,
    market: str = "GLOBAL",
    timezone_name: str = "UTC",
    locale: str = "en",
    attribution_window_days: int = 7,
    consent_basis: str = "not_applicable_simulation",
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """创建可审计的模拟营销活动，不调用外部触达服务。"""
    if audience_size <= 0:
        raise ValueError("模拟触达人数必须大于 0")
    if not 1 <= int(attribution_window_days) <= 90:
        raise ValueError("归因窗口必须是 1 到 90 天")
    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id:
            continue
        if owner is not None and task.get("owner") != owner:
            continue
        if task.get("status") != "confirmed":
            raise ValueError("只有 confirmed 状态的任务可以创建模拟活动")
        if task.get("execution"):
            raise ValueError("该任务已经创建过模拟活动")
        now = _now()
        task["execution"] = {
            "campaign_id": f"sim_{uuid.uuid4().hex[:10]}",
            "mode": "simulation",
            "status": "launched",
            "launched_at": now,
            "audience_size": int(audience_size),
            "channel": task.get("channel", "待确认"),
            "budget": float(task.get("budget") or 0),
            "duration_days": int(task.get("duration_days") or 7),
            "market": str(market).upper().strip() or "GLOBAL",
            "timezone": str(timezone_name).strip() or "UTC",
            "locale": str(locale).strip() or "en",
            "attribution_window_days": int(attribution_window_days),
            "consent_basis": str(consent_basis).strip() or "not_applicable_simulation",
        }
        task["updated_at"] = now
        if path is None and _use_database():
            _db_save_task(task)
        else:
            save_tasks(tasks, path)
        return task
    return None
