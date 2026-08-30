"""运营任务草稿的轻量持久化层。

V1 使用本地 JSON，接口设计保持数据库可替换：页面和 Agent 不直接操作文件。
"""

from __future__ import annotations

import json
import os
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
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_tasks(path: Optional[Path] = None) -> list[dict[str, Any]]:
    path = path or TASKS_PATH
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_tasks(tasks: list[dict[str, Any]], path: Optional[Path] = None) -> None:
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
) -> dict[str, Any]:
    now = _now()
    task = {
        "task_id": uuid.uuid4().hex[:12],
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "source_question": question,
        "source_diagnosis": source_diagnosis or {},
    }
    for field in EDITABLE_FIELDS:
        if field in draft:
            task[field] = draft[field]
    tasks = load_tasks(path)
    tasks.insert(0, task)
    save_tasks(tasks, path)
    return task


def update_task(
    task_id: str,
    updates: dict[str, Any],
    path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id:
            continue
        for field, value in updates.items():
            if field in EDITABLE_FIELDS:
                task[field] = value
        if "status" in updates and updates["status"] in VALID_STATUSES:
            task["status"] = updates["status"]
        task["updated_at"] = _now()
        save_tasks(tasks, path)
        return task
    return None


def get_task(task_id: str, path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    return next((task for task in load_tasks(path) if task.get("task_id") == task_id), None)


def complete_task(
    task_id: str,
    result: dict[str, Any],
    path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """写入实验结果并将任务置为 completed。"""
    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id:
            continue
        if task.get("status") != "confirmed":
            raise ValueError("只有 confirmed 状态的任务可以回填结果")
        task["result"] = result
        task["status"] = "completed"
        task["updated_at"] = _now()
        save_tasks(tasks, path)
        return task
    return None
