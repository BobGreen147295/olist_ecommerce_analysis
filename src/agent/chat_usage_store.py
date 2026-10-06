"""Shared, transactional call limits; failed model requests also consume quota."""

from datetime import datetime, timedelta, timezone

from .task_store import _connect_database


class ChatLimitExceeded(ValueError):
    def __init__(self, retry_after: int):
        super().__init__("AI 调用额度已用完，请稍后再试")
        self.retry_after = retry_after


def _ensure_schema() -> None:
    conn, _ = _connect_database()
    try:
        conn.cursor().execute("""
            CREATE TABLE IF NOT EXISTS chat_usage (
                bucket VARCHAR(160) PRIMARY KEY,
                used INTEGER NOT NULL,
                expires_at VARCHAR(40) NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def reserve_chat_call(owner: str) -> None:
    if not owner:
        raise ValueError("必须指定已认证账户")
    _ensure_schema()
    now = datetime.now(timezone.utc)
    minute_end = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    day_end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    # Limits persist across restarts and are shared by all workers using this DB.
    limits = (
        ("global:" + now.strftime("%Y-%m-%d"), 100, day_end),
        ("day:" + owner + ":" + now.strftime("%Y-%m-%d"), 20, day_end),
        ("minute:" + owner + ":" + now.strftime("%Y-%m-%dT%H:%M"), 3, minute_end),
    )
    conn, p = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM chat_usage WHERE expires_at <= {p}", (now.isoformat(),))
        for bucket, limit, expiry in limits:
            cursor.execute(
                f"INSERT INTO chat_usage (bucket, used, expires_at) VALUES ({p}, 0, {p}) "
                "ON CONFLICT (bucket) DO NOTHING", (bucket, expiry.isoformat()),
            )
            cursor.execute(
                f"UPDATE chat_usage SET used = used + 1 WHERE bucket = {p} AND used < {p}",
                (bucket, limit),
            )
            if cursor.rowcount != 1:
                raise ChatLimitExceeded(max(1, int((expiry - now).total_seconds()) + 1))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
