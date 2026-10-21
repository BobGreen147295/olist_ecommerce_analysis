"""运营任务持久化层。

默认使用本地 JSON，适合开发和离线演示；配置 DATABASE_URL 后自动使用
PostgreSQL，适合 Streamlit Cloud 等多用户部署。页面和 Agent 不直接操作存储细节。
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
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
    if os.environ.get("USE_MANAGED_POSTGRES", "").strip() == "1":
        managed_url = os.environ.get("MIGRATION_TARGET_DATABASE_URL", "").strip()
        if managed_url:
            return managed_url
    value = os.environ.get("DATABASE_URL", "").strip()
    if value:
        return value
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
        url = _database_url()
        if url.startswith(("postgres://", "postgresql://")):
            import psycopg2
            conn = psycopg2.connect(url, connect_timeout=5, options="-c statement_timeout=5000")
        elif url.startswith("sqlite:///"):
            db_path = Path(url[len("sqlite:///"):]).resolve()
            conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5)
        else:
            return False, "不支持的数据库类型"
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            valid = cursor.fetchone() == (1,)
            cursor.close()
        finally:
            conn.close()
        return valid, "连接正常" if valid else "检查失败"
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


def _db_save_task(task: dict[str, Any], expected_payload: Optional[str] = None) -> None:
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        if expected_payload is not None:
            cursor.execute(f"SELECT payload FROM operation_tasks WHERE task_id = {placeholder}", (task["task_id"],))
            row = cursor.fetchone()
            # Legacy whitespace/key order/Unicode escaping are not state changes.
            # Compare decoded snapshots, then CAS the exact stored bytes so a
            # writer arriving between this SELECT and UPDATE still conflicts.
            canonical = lambda value: json.dumps(json.loads(value), ensure_ascii=False, sort_keys=True)
            if row is None or canonical(row[0]) != canonical(expected_payload):
                raise ValueError("任务已被其他操作更新，请刷新核对后再继续")
            cursor.execute(
                f"UPDATE operation_tasks SET status = {placeholder}, updated_at = {placeholder}, payload = {placeholder} "
                f"WHERE task_id = {placeholder} AND payload = {placeholder}",
                (task["status"], task["updated_at"], json.dumps(task, ensure_ascii=False), task["task_id"], row[0]),
            )
            if cursor.rowcount != 1:
                raise ValueError("任务已被其他操作更新，请刷新核对后再继续")
        elif placeholder == "%s":
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
        if task.get("execution", {}).get("mode") == "manual_handoff" and task["execution"].get("started_at"):
            raise ValueError("已启动的手工实验不能修改参数或状态")
        previous_payload = json.dumps(task, ensure_ascii=False)
        for field, value in updates.items():
            if field in EDITABLE_FIELDS:
                task[field] = value
        if "status" in updates and updates["status"] in VALID_STATUSES:
            task["status"] = updates["status"]
        task["updated_at"] = _now()
        if path is None and _use_database():
            _db_save_task(task, previous_payload)
        else:
            save_tasks(tasks, path)
        return task
    return None


def get_task(
    task_id: str,
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    return next(
        (task for task in load_tasks(path, owner=owner) if task.get("task_id") == task_id),
        None,
    )


def prepare_manual_execution(
    task_id: str,
    *,
    channel: str,
    budget: float,
    market: str,
    locale: str,
    attribution_window_days: int,
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Confirm a consented pilot task and prepare a contact-free handoff package."""
    channel = str(channel).strip().lower()
    market = str(market).strip().upper()
    locale = str(locale).strip()
    if channel not in {"email", "sms", "whatsapp", "manual"}:
        raise ValueError("执行渠道必须是 email、sms、whatsapp 或 manual")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
        raise ValueError("活动预算必须是有限的非负数字")
    if not market or len(market) > 16:
        raise ValueError("市场代码不能为空且最多 16 个字符")
    if not locale or len(locale) > 32:
        raise ValueError("语言代码不能为空且最多 32 个字符")
    if isinstance(attribution_window_days, bool) or not isinstance(attribution_window_days, int) or not 1 <= attribution_window_days <= 90:
        raise ValueError("归因窗口必须是 1 到 90 的整数天数")

    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id or (owner is not None and task.get("owner") != owner):
            continue
        if task.get("source_diagnosis", {}).get("source") != "consented_reactivation_aggregate":
            raise ValueError("只有已通过营销同意门禁的再激活机会可以生成执行包")
        if task.get("status") not in {"draft", "confirmed"}:
            raise ValueError("只有草案或已确认任务可以生成执行包")
        if task.get("execution", {}).get("started_at") or task.get("execution", {}).get("status") == "in_progress":
            raise ValueError("已启动的实验不能重新确认参数或重置观察窗口")
        previous_payload = json.dumps(task, ensure_ascii=False)
        now = _now()
        task.update({
            "status": "confirmed",
            "channel": channel,
            "budget": float(budget),
            "market": market,
            "locale": locale,
            "attribution_window_days": int(attribution_window_days),
            "updated_at": now,
            "execution": {
                "package_id": f"pkg_{uuid.uuid4().hex[:10]}",
                "mode": "manual_handoff",
                "status": "ready_for_export",
                "confirmed_at": now,
            },
        })
        if path is None and _use_database():
            _db_save_task(task, previous_payload)
        else:
            save_tasks(tasks, path)
        return task
    return None


def get_manual_execution_package(
    task_id: str,
    *,
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    task = get_task(task_id, path=path, owner=owner)
    if task is None:
        return None
    execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
    if task.get("status") != "confirmed" or execution.get("mode") != "manual_handoff":
        raise ValueError("请先人工确认活动参数，再导出执行包")
    return {
        "package_id": execution["package_id"],
        "task_id": task["task_id"],
        "title": task.get("title", ""),
        "audience_definition": task.get("audience", ""),
        "channel": task.get("channel", ""),
        "budget": task.get("budget", 0),
        "market": task.get("market", "GLOBAL"),
        "locale": task.get("locale", "en"),
        "attribution_window_days": task.get("attribution_window_days", 7),
        "expected_metric": task.get("expected_metric", ""),
        "consent_basis": task.get("consent_basis", ""),
        "actions": " | ".join(str(item) for item in task.get("actions", [])),
        "execution_mode": "manual_handoff",
        "customer_contact_data": "not_included",
    }


def _observation_end(task: dict[str, Any]) -> datetime:
    """Derive the deadline from saved approval/start, never from submitted dates."""
    try:
        started = datetime.fromisoformat(task["execution"]["started_at"].replace("Z", "+00:00"))
        days = task["attribution_window_days"]
        if started.tzinfo is None or isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 90:
            raise ValueError()
        return started + timedelta(days=days)
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError):
        raise ValueError("启动记录或观察窗口无效，不能回传真实结果") from None


def mark_manual_execution_started(
    task_id: str,
    *,
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Record a merchant-confirmed manual start without calling an external channel."""
    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id or (owner is not None and task.get("owner") != owner):
            continue
        execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
        if task.get("status") != "confirmed" or execution.get("mode") != "manual_handoff":
            raise ValueError("请先人工确认活动参数并生成手工执行包")
        if execution.get("status") == "result_recorded":
            raise ValueError("该任务已经完成结果回传")
        if execution.get("status") == "in_progress":
            _observation_end(task)
            return task
        previous_payload = json.dumps(task, ensure_ascii=False)
        now = _now()
        execution["status"] = "in_progress"
        execution["started_at"] = now
        task["execution"] = execution
        execution["observation_ends_at"] = _observation_end(task).isoformat(timespec="seconds")
        task["updated_at"] = now
        if path is None and _use_database():
            _db_save_task(task, previous_payload)
        else:
            save_tasks(tasks, path)
        return task
    return None


def record_observed_result(
    task_id: str,
    *,
    treatment_users: int,
    treatment_orders: int,
    treatment_revenue: float,
    control_users: int,
    control_orders: int,
    control_revenue: float,
    cost: float,
    currency: str,
    revenue_net_of_refunds: bool,
    path: Optional[Path] = None,
    owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Store merchant-reported aggregate results for a confirmed manual handoff."""
    from src.agent.evaluation import evaluate_experiment

    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id or (owner is not None and task.get("owner") != owner):
            continue
        execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
        if task.get("status") != "confirmed" or execution.get("mode") != "manual_handoff":
            raise ValueError("只有已确认的手工执行包可以回传真实结果")
        if execution.get("status") != "in_progress" or not execution.get("started_at"):
            raise ValueError("请先记录商家确认的人工启动，再等待观察窗口结束")
        end = _observation_end(task)
        if datetime.fromisoformat(_now()) < end:
            raise ValueError(f"观察窗口尚未结束，请在 {end.isoformat(timespec='seconds')} 后回传")
        previous_payload = json.dumps(task, ensure_ascii=False)
        result = evaluate_experiment(
            treatment_users=treatment_users,
            treatment_orders=treatment_orders,
            treatment_revenue=treatment_revenue,
            control_users=control_users,
            control_orders=control_orders,
            control_revenue=control_revenue,
            cost=cost,
            currency=currency,
            attribution_window_days=int(task.get("attribution_window_days") or 7),
            measurement_mode="observed",
            revenue_net_of_refunds=revenue_net_of_refunds,
        )
        result.update({
            "source": "merchant_reported_aggregate",
            "verification": "self_reported",
            "observation_started_at": execution["started_at"],
            "observation_ends_at": end.isoformat(timespec="seconds"),
        })
        task["result"] = result
        task["status"] = "completed"
        task["updated_at"] = _now()
        execution["status"] = "result_recorded"
        execution["result_recorded_at"] = task["updated_at"]
        task["execution"] = execution
        if path is None and _use_database():
            _db_save_task(task, previous_payload)
        else:
            save_tasks(tasks, path)
        return task
    return None


def record_diagnostic_review(
    task_id: str, decision: str, *, path: Optional[Path] = None, owner: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Record structured feedback on store aggregates, not marketing execution."""
    choices = {"accepted": ("confirmed", "verify_business_cause"),
               "needs_information": ("draft", "clarify_definition"),
               "rejected": ("rejected", "stop_diagnosis")}
    if decision not in choices:
        raise ValueError("请选择认可、补充信息或停止诊断")
    tasks = load_tasks(path)
    for task in tasks:
        if task.get("task_id") != task_id or (owner is not None and task.get("owner") != owner):
            continue
        if task.get("source_diagnosis", {}).get("source") != "shopify_aggregate" or task.get("execution"):
            raise ValueError("只有店铺级汇总诊断可以记录此反馈，不会启动客户活动")
        previous_payload = json.dumps(task, ensure_ascii=False)
        status, action = choices[decision]
        review = {"decision": decision, "reviewed_at": _now(), "next_action": action}
        task["diagnostic_review"] = review
        task.setdefault("diagnostic_reviews", []).append(review)
        task["status"] = status
        task["updated_at"] = review["reviewed_at"]
        if path is None and _use_database():
            _db_save_task(task, previous_payload)
        else:
            save_tasks(tasks, path)
        return task
    return None


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
        if task.get("execution", {}).get("mode") == "manual_handoff":
            raise ValueError("手工实验必须通过观察期门禁回传结果")
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
