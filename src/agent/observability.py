"""Agent 运行观测：记录可用于产品评估的脱敏运行摘要。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = PROJECT_DIR / "data" / "processed" / "agent_runs.jsonl"
QUALITY_EVALUATION_VERSION = "qa_v2"


def _matches_data_reference(evidence: Any, data: Any) -> bool:
    """Check a scalar against an explicit path in the current tool result."""
    if not isinstance(evidence, dict) or not isinstance(evidence.get("path"), str) or "value" not in evidence:
        return False
    value = data
    try:
        for key in evidence["path"].split("."):
            if isinstance(value, list) and not key.isdecimal():
                return False
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, IndexError, ValueError, TypeError):
        return False
    expected = evidence["value"]
    if isinstance(value, bool) or isinstance(expected, bool):
        return False
    if isinstance(value, (int, float)) and isinstance(expected, (int, float)):
        return math.isfinite(value) and math.isfinite(expected) and value == expected
    return isinstance(value, str) and isinstance(expected, str) and bool(value) and value == expected


def diagnosis_validation_errors(diagnosis: Any, tool_results: list[dict]) -> list[str]:
    """Check shape and exact current-tool references, not semantic truth of titles."""
    if not isinstance(diagnosis, dict) or type(diagnosis.get("data_sufficient")) is not bool:
        return ["诊断必须有布尔型 data_sufficient"]
    findings = diagnosis.get("findings")
    if not isinstance(findings, list) or not findings:
        return ["数据充分的诊断必须包含发现"]
    errors = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict) or not isinstance(finding.get("title"), str) or not finding["title"].strip():
            errors.append(f"发现 {index + 1} 缺少有效标题")
            continue
        evidence = finding.get("evidence")
        sources = [item for item in tool_results if item.get("success") is True
                   and item.get("data") is not None and finding.get("source")
                   and finding["source"] in (item.get("tool"), item.get("source"))]
        if not isinstance(evidence, list) or not evidence or not any(
            all(_matches_data_reference(reference, source["data"]) for reference in evidence)
            for source in sources
        ):
            errors.append(f"发现 {index + 1} 的来源、字段路径或值无法核验")
    return errors


def _is_actionable(value: Any) -> bool:
    """排除“待确认”等占位值，避免把空泛策略误判为可执行。"""
    text = str(value or "").strip()
    return bool(text) and text not in {"待确认", "暂无", "未知", "N/A"} and "待确认" not in text


def evaluate_response_quality(result: dict[str, Any]) -> dict[str, float | str]:
    """Score resolvable references and completeness, not semantic truth or causality."""
    diagnosis = result.get("diagnosis", {}) or {}
    findings = diagnosis.get("findings", []) if isinstance(diagnosis, dict) else []
    findings = findings if isinstance(findings, list) else []
    with_evidence = 0
    with_source = 0
    with_evidence_text = 0
    tool_results = result.get("tool_results", [])
    tool_results = tool_results if isinstance(tool_results, list) else []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        evidence = finding.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [evidence]
        if any(str(item or "").strip() for item in evidence):
            with_evidence_text += 1
        sources = [item for item in tool_results if isinstance(item, dict) and item.get("success") is True
                   and item.get("data") is not None and isinstance(finding.get("source"), str)
                   and finding["source"] in (item.get("tool"), item.get("source")) and finding["source"].strip()]
        if sources:
            with_source += 1
        if evidence and any(all(_matches_data_reference(item, source["data"]) for item in evidence) for source in sources):
            with_evidence += 1
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
        "score_kind": "reference_checks_and_completeness",
        "structural_evidence_coverage": round(with_evidence_text / len(findings), 4) if findings else 0.0,
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
        "verification_status": result.get("verification", {}).get("status", "not_checked"),
        "analysis_attempts": result.get("verification", {}).get("analysis_attempts", 0),
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
