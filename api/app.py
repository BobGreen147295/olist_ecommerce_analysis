"""HTTP boundary for the RevenueOps Agent.

The browser never receives database URLs or model-provider credentials. This
service is intentionally separate from the static Cloudflare Pages frontend.
"""

from __future__ import annotations

import os
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


def _format_agent_answer(result: dict[str, Any]) -> str:
    parts = [part.strip() for part in (result.get("analysis", ""), result.get("recommendation", "")) if part]
    if parts:
        return "\n\n".join(parts)
    return "当前未能生成结论。请检查数据连接或稍后重试。"


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
