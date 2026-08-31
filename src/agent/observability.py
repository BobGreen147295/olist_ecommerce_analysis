"""Agent 运行观测：记录可用于产品评估的脱敏运行摘要。"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = PROJECT_DIR / "data" / "processed" / "agent_runs.jsonl"


def build_run_meta(
    user_query: str,
    result: dict[str, Any],
    duration_ms: int,
) -> dict[str, Any]:
    """生成不保存原始问题文本的运行摘要，避免把潜在敏感信息写入日志。"""
    tool_results = result.get("tool_results", []) or []
    diagnosis = result.get("diagnosis", {}) or {}
    return {
        "run_id": uuid.uuid4().hex[:12],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_ms": duration_ms,
        "query_hash": hashlib.sha256(user_query.encode("utf-8")).hexdigest()[:16],
        "query_length": len(user_query),
        "tool_count": len(tool_results),
        "successful_tool_count": sum(bool(item.get("success")) for item in tool_results),
        "finding_count": len(diagnosis.get("findings", [])) if isinstance(diagnosis, dict) else 0,
        "action_count": len(result.get("action_drafts", []) or []),
        "structured_output": bool(isinstance(diagnosis, dict) and diagnosis.get("findings")),
        "error": result.get("error"),
    }


def append_run_log(run_meta: dict[str, Any]) -> None:
    """追加 JSONL 日志；写入失败不影响 Agent 主流程。"""
    log_path = Path(os.environ.get("AGENT_LOG_PATH", str(DEFAULT_LOG_PATH)))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(run_meta, ensure_ascii=False) + "\n")
    except OSError:
        return
