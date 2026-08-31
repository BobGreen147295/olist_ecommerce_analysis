"""Agent 用户反馈与质量指标持久化层。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .task_store import _connect_database, _use_database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _initialize_schema() -> None:
    if not _use_database():
        raise RuntimeError("反馈与质量指标需要配置 DATABASE_URL")
    conn, _ = _connect_database()
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
) -> None:
    if rating not in {-1, 1}:
        raise ValueError("反馈评分只能为 -1 或 1")
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
                INSERT INTO agent_feedback (feedback_id, message_id, conversation_id, username, rating, reason, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO UPDATE SET rating = EXCLUDED.rating, reason = EXCLUDED.reason,
                    created_at = EXCLUDED.created_at
                """,
                (uuid.uuid4().hex[:16], message_id, conversation_id, username, rating, reason.strip()[:500], _now()),
            )
        else:
            cursor.execute(
                """
                INSERT INTO agent_feedback (feedback_id, message_id, conversation_id, username, rating, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET rating = excluded.rating, reason = excluded.reason,
                    created_at = excluded.created_at
                """,
                (uuid.uuid4().hex[:16], message_id, conversation_id, username, rating, reason.strip()[:500], _now()),
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
            f"SELECT message_id, rating, reason, created_at FROM agent_feedback "
            f"WHERE conversation_id = {placeholder} AND username = {placeholder}",
            (conversation_id, username),
        )
        rows = cursor.fetchall()
        cursor.close()
        return {
            row[0]: {"rating": row[1], "reason": row[2] or "", "created_at": row[3]}
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
        )
        if placeholder == "%s":
            cursor.execute(
                """
                INSERT INTO agent_run_metrics (run_id, conversation_id, username, created_at, duration_ms,
                    tool_count, successful_tool_count, finding_count, action_count, structured_output, has_error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO NOTHING
                """,
                values,
            )
        else:
            cursor.execute(
                """
                INSERT INTO agent_run_metrics (run_id, conversation_id, username, created_at, duration_ms,
                    tool_count, successful_tool_count, finding_count, action_count, structured_output, has_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
