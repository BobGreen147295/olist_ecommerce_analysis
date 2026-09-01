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
QUALITY_EVALUATION_VERSION = "qa_v1"


def _is_actionable(value: Any) -> bool:
    """排除“待确认”等占位值，避免把空泛策略误判为可执行。"""
    text = str(value or "").strip()
    return bool(text) and text not in {"待确认", "暂无", "未知", "N/A"} and "待确认" not in text


def evaluate_response_quality(result: dict[str, Any]) -> dict[str, float | str]:
    """根据真实结构化输出计算确定性质量分，不调用 LLM 自评。"""
    diagnosis = result.get("diagnosis", {}) or {}
    findings = diagnosis.get("findings", []) if isinstance(diagnosis, dict) else []
    findings = findings if isinstance(findings, list) else []
    with_evidence = 0
    with_source = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        evidence = finding.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [evidence]
        if any(str(item or "").strip() for item in evidence):
            with_evidence += 1
        if str(finding.get("source", "")).strip():
            with_source += 1
    evidence_coverage = with_evidence / len(findings) if findings else 0.0
    source_citation_rate = with_source / len(findings) if findings else 0.0

    actions = result.get("action_drafts", []) or []
    actions = actions if isinstance(actions, list) else []
    action_scores: list[float] = []
    required_fields = ("title", "actions", "audience", "channel", "duration_days", "expected_metric")
    for action in actions:
        if not isinstance(action, dict):
            continue
        complete_fields = 0
        for field in required_fields:
            value = action.get(field)
            if field == "actions":
                valid = isinstance(value, list) and any(_is_actionable(item) for item in value)
            else:
                valid = _is_actionable(value)
            complete_fields += int(valid)
        action_scores.append(complete_fields / len(required_fields))
    action_completeness = sum(action_scores) / len(action_scores) if action_scores else 0.0
    quality_score = 0.45 * evidence_coverage + 0.25 * source_citation_rate + 0.30 * action_completeness
    return {
        "evaluation_version": QUALITY_EVALUATION_VERSION,
        "evidence_coverage": round(evidence_coverage, 4),
        "source_citation_rate": round(source_citation_rate, 4),
        "action_completeness": round(action_completeness, 4),
        "quality_score": round(quality_score, 4),
    }


def build_run_meta(
    user_query: str,
    result: dict[str, Any],
    duration_ms: int,
) -> dict[str, Any]:
    """生成不保存原始问题文本的运行摘要，避免把潜在敏感信息写入日志。"""
    tool_results = result.get("tool_results", []) or []
    diagnosis = result.get("diagnosis", {}) or {}
    quality = evaluate_response_quality(result)
    provider = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
    model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini") if provider in {"openai", "cloud"} else os.environ.get("OLLAMA_MODEL", "qwen3:8b")
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
        "model_provider": provider,
        "model_name": model_name,
        **quality,
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
