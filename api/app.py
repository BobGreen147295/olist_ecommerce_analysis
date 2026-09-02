"""HTTP boundary for the RevenueOps Agent.

The browser never receives database URLs or model-provider credentials. This
service is intentionally separate from the static Cloudflare Pages frontend.
"""

from __future__ import annotations

import os
import re
from typing import Any

from flask import Flask, jsonify, request


MAX_MESSAGE_LENGTH = 1_500
DEFAULT_ORIGINS = "https://olist-revenueops.pages.dev,http://localhost:3000"


def _allowed_origins() -> set[str]:
    values = os.environ.get("ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    return {value.strip().rstrip("/") for value in values.split(",") if value.strip()}


def _cors(response: Any) -> Any:
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin in _allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


def _safe_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, str]] = []
    for item in value[-8:]:
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            history.append({"role": role, "content": content[:1_500]})
    return history


def _brief(value: Any, limit: int = 180) -> str:
    """将 Agent 字段收束为面向商家的自然语言短句。"""
    text = re.sub(r"[*#`]+", "", str(value or ""))
    text = " ".join(text.split())
    return text[:limit].rstrip("，；、 ")


def _format_agent_answer(result: dict[str, Any]) -> str:
    """把 Agent 的结构化工作底稿转成聊天答复，不暴露工具名或 Markdown。"""
    diagnosis = result.get("diagnosis") if isinstance(result.get("diagnosis"), dict) else {}
    findings = diagnosis.get("findings") if isinstance(diagnosis.get("findings"), list) else []
    action_drafts = result.get("action_drafts") if isinstance(result.get("action_drafts"), list) else []

    draft = next((item for item in action_drafts if isinstance(item, dict)), {})
    title = _brief(draft.get("title"))
    if not title or title == "基于当前诊断制定小规模验证任务":
        opening = "我建议先做一轮小规模验证，而不是马上扩大动作。"
    else:
        opening = f"我建议你优先做“{title}”。"

    evidence: list[str] = []
    for finding in findings[:2]:
        if not isinstance(finding, dict):
            continue
        items = finding.get("evidence", [])
        if not isinstance(items, list):
            items = [items]
        item = _brief(items[0] if items else finding.get("title"))
        if item and "query_" not in item.lower():
            evidence.append(item)
    basis = f"目前的数据依据是：{'；'.join(evidence)}。" if evidence else "目前的数据还不足以支持更激进的判断。"

    actions = draft.get("actions") if isinstance(draft.get("actions"), list) else []
    next_steps = [_brief(item, 90) for item in actions[:2] if _brief(item, 90)]
    if next_steps:
        action_text = f"下一步先{'，再'.join(next_steps)}。"
    else:
        action_text = "下一步先确认目标人群和衡量指标，再决定是否启动实验。"

    return f"{opening}\n\n{basis}\n\n{action_text} 这是一项需要人工确认的建议，效果应通过小范围 A/B 测试验证。"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    @app.after_request
    def add_cors(response: Any) -> Any:
        return _cors(response)

    @app.route("/health", methods=["GET", "OPTIONS"])
    def health() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        provider = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
        return jsonify({"status": "ok", "service": "olist-revenueops-api", "llm_provider": provider})

    @app.route("/v1/chat", methods=["POST", "OPTIONS"])
    def chat() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        payload = request.get_json(silent=True) or {}
        message = payload.get("message", "")
        if not isinstance(message, str) or not message.strip():
            return jsonify({"error": "message 是必填字符串"}), 400
        if len(message) > MAX_MESSAGE_LENGTH:
            return jsonify({"error": f"message 最多 {MAX_MESSAGE_LENGTH} 个字符"}), 400
        try:
            from src.agent.agent_graph import run_with_history

            result = run_with_history(message.strip(), _safe_history(payload.get("history")))
            return jsonify({
                "answer": _format_agent_answer(result),
                "evidence": [
                    {"tool": item.get("tool"), "summary": item.get("summary"), "success": bool(item.get("success"))}
                    for item in result.get("tool_results", [])
                ],
                "action_drafts": result.get("action_drafts", []),
                "diagnosis": result.get("diagnosis", {}),
                "error": result.get("error"),
                "mode": "agent",
            })
        except Exception as exc:  # Detailed exception stays server-side.
            app.logger.exception("Agent chat failed")
            return jsonify({"error": "Agent 当前不可用，请稍后重试", "mode": "unavailable"}), 503

    @app.route("/v1/data-health", methods=["GET", "OPTIONS"])
    def data_health() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        try:
            from src.agent.commerce_store import get_connected_data_health
            from src.agent.task_store import storage_mode

            return jsonify({"storage_mode": storage_mode(), "connected_source": get_connected_data_health()})
        except Exception:
            app.logger.exception("Data health lookup failed")
            return jsonify({"storage_mode": "unavailable", "connected_source": None}), 503

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
