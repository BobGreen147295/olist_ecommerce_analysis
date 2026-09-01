"""Agent 用户反馈与质量指标持久化层。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .task_store import _connect_database, _use_database


FEEDBACK_TYPES = {"content", "data", "experience"}
ISSUE_STATUSES = {"open", "resolved", "dismissed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _initialize_schema() -> None:
    if not _use_database():
        raise RuntimeError("反馈与质量指标需要配置 DATABASE_URL")
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_feedback (
                feedback_id VARCHAR(32) PRIMARY KEY,
                message_id VARCHAR(32) UNIQUE NOT NULL,
                conversation_id VARCHAR(32) NOT NULL,
                username VARCHAR(32) NOT NULL,
                rating INTEGER NOT NULL,
                reason TEXT,
                created_at VARCHAR(40) NOT NULL
            )
            """
        )
        if placeholder == "%s":
            cursor.execute("ALTER TABLE agent_feedback ADD COLUMN IF NOT EXISTS feedback_type VARCHAR(24) NOT NULL DEFAULT 'content'")
            cursor.execute("ALTER TABLE agent_feedback ADD COLUMN IF NOT EXISTS status VARCHAR(24) NOT NULL DEFAULT 'open'")
            cursor.execute("ALTER TABLE agent_feedback ADD COLUMN IF NOT EXISTS resolution TEXT")
            cursor.execute("ALTER TABLE agent_feedback ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(32)")
            cursor.execute("ALTER TABLE agent_feedback ADD COLUMN IF NOT EXISTS resolved_at VARCHAR(40)")
        else:
            cursor.execute("PRAGMA table_info(agent_feedback)")
            columns = {row[1] for row in cursor.fetchall()}
            additions = {
                "feedback_type": "TEXT NOT NULL DEFAULT 'content'",
                "status": "TEXT NOT NULL DEFAULT 'open'",
                "resolution": "TEXT",
                "resolved_by": "TEXT",
                "resolved_at": "TEXT",
            }
            for name, definition in additions.items():
                if name not in columns:
                    cursor.execute(f"ALTER TABLE agent_feedback ADD COLUMN {name} {definition}")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_run_metrics (
                run_id VARCHAR(32) PRIMARY KEY,
                conversation_id VARCHAR(32),
                username VARCHAR(32) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                duration_ms INTEGER NOT NULL,
                tool_count INTEGER NOT NULL,
                successful_tool_count INTEGER NOT NULL,
                finding_count INTEGER NOT NULL,
                action_count INTEGER NOT NULL,
                structured_output BOOLEAN NOT NULL,
                has_error BOOLEAN NOT NULL
            )
            """
        )
        metric_additions = {
            "evidence_coverage": "REAL",
            "source_citation_rate": "REAL",
            "action_completeness": "REAL",
            "quality_score": "REAL",
            "model_provider": "VARCHAR(24)",
            "model_name": "VARCHAR(80)",
            "evaluation_version": "VARCHAR(24)",
        }
        if placeholder == "%s":
            for name, definition in metric_additions.items():
                cursor.execute(f"ALTER TABLE agent_run_metrics ADD COLUMN IF NOT EXISTS {name} {definition}")
        else:
            cursor.execute("PRAGMA table_info(agent_run_metrics)")
            metric_columns = {row[1] for row in cursor.fetchall()}
            for name, definition in metric_additions.items():
                if name not in metric_columns:
                    cursor.execute(f"ALTER TABLE agent_run_metrics ADD COLUMN {name} {definition}")
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def save_feedback(
    message_id: str,
    conversation_id: str,
    username: str,
    rating: int,
    reason: str = "",
    feedback_type: str = "content",
) -> None:
    if rating not in {-1, 1}:
        raise ValueError("反馈评分只能为 -1 或 1")
    if feedback_type not in FEEDBACK_TYPES:
        raise ValueError("反馈类型不合法")
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT m.message_id FROM chat_messages m JOIN chat_conversations c "
            f"ON c.conversation_id = m.conversation_id WHERE m.message_id = {placeholder} "
            f"AND m.conversation_id = {placeholder} AND c.username = {placeholder}",
            (message_id, conversation_id, username),
        )
        if cursor.fetchone() is None:
            raise ValueError("消息不存在或无权反馈")
        if placeholder == "%s":
            cursor.execute(
                """
                INSERT INTO agent_feedback (feedback_id, message_id, conversation_id, username, rating, reason,
                    feedback_type, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO UPDATE SET rating = EXCLUDED.rating, reason = EXCLUDED.reason,
                    feedback_type = EXCLUDED.feedback_type, status = EXCLUDED.status, created_at = EXCLUDED.created_at,
                    resolution = NULL, resolved_by = NULL, resolved_at = NULL
                """,
                (uuid.uuid4().hex[:16], message_id, conversation_id, username, rating, reason.strip()[:500],
                 feedback_type, "open" if rating == -1 else "resolved", _now()),
            )
        else:
            cursor.execute(
                """
                INSERT INTO agent_feedback (feedback_id, message_id, conversation_id, username, rating, reason,
                    feedback_type, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET rating = excluded.rating, reason = excluded.reason,
                    feedback_type = excluded.feedback_type, status = excluded.status, created_at = excluded.created_at,
                    resolution = NULL, resolved_by = NULL, resolved_at = NULL
                """,
                (uuid.uuid4().hex[:16], message_id, conversation_id, username, rating, reason.strip()[:500],
                 feedback_type, "open" if rating == -1 else "resolved", _now()),
            )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def load_feedback(conversation_id: str, username: str) -> dict[str, dict[str, Any]]:
    if not conversation_id:
        return {}
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT feedback_id, message_id, rating, reason, feedback_type, status, resolution, created_at FROM agent_feedback "
            f"WHERE conversation_id = {placeholder} AND username = {placeholder}",
            (conversation_id, username),
        )
        rows = cursor.fetchall()
        cursor.close()
        return {
            row[1]: {
                "feedback_id": row[0], "rating": row[2], "reason": row[3] or "", "feedback_type": row[4],
                "status": row[5], "resolution": row[6] or "", "created_at": row[7],
            }
            for row in rows
        }
    finally:
        conn.close()


def record_run_metric(username: str, conversation_id: str | None, run_meta: dict[str, Any]) -> None:
    if not run_meta or not run_meta.get("run_id"):
        return
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        values = (
            run_meta["run_id"],
            conversation_id,
            username,
            run_meta.get("created_at", _now()),
            int(run_meta.get("duration_ms", 0) or 0),
            int(run_meta.get("tool_count", 0) or 0),
            int(run_meta.get("successful_tool_count", 0) or 0),
            int(run_meta.get("finding_count", 0) or 0),
            int(run_meta.get("action_count", 0) or 0),
            bool(run_meta.get("structured_output")),
            bool(run_meta.get("error")),
            run_meta.get("evidence_coverage"),
            run_meta.get("source_citation_rate"),
            run_meta.get("action_completeness"),
            run_meta.get("quality_score"),
            str(run_meta.get("model_provider", "unknown"))[:24],
            str(run_meta.get("model_name", "unknown"))[:80],
            str(run_meta.get("evaluation_version", ""))[:24],
        )
        if placeholder == "%s":
            cursor.execute(
                """
                INSERT INTO agent_run_metrics (run_id, conversation_id, username, created_at, duration_ms,
                    tool_count, successful_tool_count, finding_count, action_count, structured_output, has_error,
                    evidence_coverage, source_citation_rate, action_completeness, quality_score, model_provider,
                    model_name, evaluation_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO NOTHING
                """,
                values,
            )
        else:
            cursor.execute(
                """
                INSERT INTO agent_run_metrics (run_id, conversation_id, username, created_at, duration_ms,
                    tool_count, successful_tool_count, finding_count, action_count, structured_output, has_error,
                    evidence_coverage, source_citation_rate, action_completeness, quality_score, model_provider,
                    model_name, evaluation_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO NOTHING
                """,
                values,
            )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def get_quality_summary() -> dict[str, Any]:
    """返回管理员看板所需聚合，不返回原始问题内容。"""
    _initialize_schema()
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*), COALESCE(AVG(duration_ms), 0), COALESCE(SUM(tool_count), 0),
               COALESCE(SUM(successful_tool_count), 0), COALESCE(AVG(CASE WHEN structured_output THEN 1.0 ELSE 0.0 END), 0),
               COALESCE(AVG(CASE WHEN has_error THEN 1.0 ELSE 0.0 END), 0)
               FROM agent_run_metrics"""
        )
        run_row = cursor.fetchone()
        cursor.execute(
            """SELECT COUNT(*), COALESCE(SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END), 0)
               FROM agent_feedback"""
        )
        feedback_row = cursor.fetchone()
        cursor.close()
        total_runs, avg_duration, tool_count, success_count, structured_rate, error_rate = run_row
        feedback_count, helpful_count = feedback_row
        return {
            "total_runs": int(total_runs),
            "avg_duration_ms": round(float(avg_duration), 0),
            "tool_success_rate": (float(success_count) / float(tool_count)) if tool_count else None,
            "structured_output_rate": float(structured_rate),
            "error_rate": float(error_rate),
            "feedback_count": int(feedback_count),
            "helpful_rate": (float(helpful_count) / float(feedback_count)) if feedback_count else None,
        }
    finally:
        conn.close()


def get_answer_quality_summary() -> dict[str, Any]:
    """汇总真实回答的确定性质量指标，不返回用户问题或完整回答。"""
    _initialize_schema()
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*), COALESCE(AVG(quality_score), 0), COALESCE(AVG(evidence_coverage), 0),
               COALESCE(AVG(source_citation_rate), 0), COALESCE(AVG(action_completeness), 0)
               FROM agent_run_metrics WHERE evaluation_version IS NOT NULL AND evaluation_version <> ''"""
        )
        row = cursor.fetchone()
        cursor.execute(
            """SELECT model_provider, model_name, evaluation_version, COUNT(*), COALESCE(AVG(quality_score), 0),
               COALESCE(AVG(evidence_coverage), 0), COALESCE(AVG(source_citation_rate), 0),
               COALESCE(AVG(action_completeness), 0)
               FROM agent_run_metrics WHERE evaluation_version IS NOT NULL AND evaluation_version <> ''
               GROUP BY model_provider, model_name, evaluation_version ORDER BY COUNT(*) DESC"""
        )
        model_rows = cursor.fetchall()
        cursor.close()
        return {
            "evaluated_runs": int(row[0]),
            "quality_score": float(row[1]),
            "evidence_coverage": float(row[2]),
            "source_citation_rate": float(row[3]),
            "action_completeness": float(row[4]),
            "by_model": [
                {
                    "provider": item[0] or "unknown", "model": item[1] or "unknown", "version": item[2] or "unknown",
                    "runs": int(item[3]), "quality_score": float(item[4]), "evidence_coverage": float(item[5]),
                    "source_citation_rate": float(item[6]), "action_completeness": float(item[7]),
                }
                for item in model_rows
            ],
        }
    finally:
        conn.close()


def get_feedback_operations_summary() -> dict[str, Any]:
    """聚合负反馈闭环指标，供管理员评估产品迭代效率。"""
    _initialize_schema()
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT feedback_type, status, created_at, resolved_at FROM agent_feedback WHERE rating = -1"
        )
        rows = cursor.fetchall()
        cursor.close()
        by_type = {
            feedback_type: {"total": 0, "open": 0, "processed": 0}
            for feedback_type in sorted(FEEDBACK_TYPES)
        }
        closure_hours: list[float] = []
        processed_count = 0
        for feedback_type, status, created_at, resolved_at in rows:
            bucket = by_type.setdefault(feedback_type or "content", {"total": 0, "open": 0, "processed": 0})
            bucket["total"] += 1
            if status == "open":
                bucket["open"] += 1
                continue
            bucket["processed"] += 1
            processed_count += 1
            if not created_at or not resolved_at:
                continue
            try:
                created = datetime.fromisoformat(created_at)
                resolved = datetime.fromisoformat(resolved_at)
                closure_hours.append(max(0.0, (resolved - created).total_seconds() / 3600))
            except (TypeError, ValueError):
                continue
        total = len(rows)
        return {
            "negative_feedback_count": total,
            "open_count": sum(item["open"] for item in by_type.values()),
            "processed_count": processed_count,
            "processed_rate": (processed_count / total) if total else None,
            "avg_closure_hours": (sum(closure_hours) / len(closure_hours)) if closure_hours else None,
            "by_type": by_type,
        }
    finally:
        conn.close()


def list_feedback_issues(status: str | None = None) -> list[dict[str, Any]]:
    """返回负反馈待办，不读取原始业务提问或模型完整回复。"""
    _initialize_schema()
    if status is not None and status not in ISSUE_STATUSES:
        raise ValueError("处理状态不合法")
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        query = (
            "SELECT feedback_id, conversation_id, username, feedback_type, status, reason, resolution, "
            "resolved_by, created_at, resolved_at FROM agent_feedback WHERE rating = -1"
        )
        params: tuple = ()
        if status:
            query += f" AND status = {placeholder}"
            params = (status,)
        query += " ORDER BY created_at DESC LIMIT 100"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        fields = [
            "feedback_id", "conversation_id", "username", "feedback_type", "status", "reason",
            "resolution", "resolved_by", "created_at", "resolved_at",
        ]
        return [dict(zip(fields, row)) for row in rows]
    finally:
        conn.close()


def update_feedback_issue(feedback_id: str, status: str, resolution: str, resolved_by: str) -> None:
    if status not in ISSUE_STATUSES:
        raise ValueError("处理状态不合法")
    _initialize_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE agent_feedback SET status = {placeholder}, resolution = {placeholder}, "
            f"resolved_by = {placeholder}, resolved_at = {placeholder} WHERE feedback_id = {placeholder} "
            f"AND rating = -1",
            (status, resolution.strip()[:500], resolved_by, _now(), feedback_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("反馈待办不存在")
        conn.commit()
        cursor.close()
    finally:
        conn.close()
