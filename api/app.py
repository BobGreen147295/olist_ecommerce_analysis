"""HTTP boundary for the RevenueOps Agent.

The browser never receives database URLs or model-provider credentials. This
service is intentionally separate from the static Cloudflare Pages frontend.
"""

from __future__ import annotations

import os
import re
import hashlib
import hmac
from typing import Any
from urllib.parse import urlencode

import requests
from flask import Flask, jsonify, redirect, request


MAX_MESSAGE_LENGTH = 1_500
DEFAULT_ORIGINS = "https://olist-revenueops.pages.dev,http://localhost:3000"
SHOPIFY_SCOPES = ("read_orders", "read_customers", "read_products", "read_inventory")


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


def _shopify_readiness() -> dict[str, Any]:
    """只公开连接器的准备状态，绝不向浏览器返回 OAuth 密钥。"""
    missing = []
    if not os.environ.get("SHOPIFY_CLIENT_ID"):
        missing.append("SHOPIFY_CLIENT_ID")
    if not os.environ.get("SHOPIFY_CLIENT_SECRET"):
        missing.append("SHOPIFY_CLIENT_SECRET")
    if not os.environ.get("PUBLIC_API_BASE_URL"):
        missing.append("PUBLIC_API_BASE_URL")
    if not os.environ.get("PUBLIC_WEB_URL"):
        missing.append("PUBLIC_WEB_URL")
    if not os.environ.get("CONNECTION_TOKEN_ENCRYPTION_KEY"):
        missing.append("CONNECTION_TOKEN_ENCRYPTION_KEY")
    return {
        "provider": "shopify",
        "state": "ready_to_authorize" if not missing else "configuration_required",
        "required_scopes": list(SHOPIFY_SCOPES),
        "missing_configuration": missing,
        "message": "可由商家开始 OAuth 授权" if not missing else "尚未配置 Shopify 应用凭据，不能发起授权。",
    }


def _require_session() -> dict[str, str]:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise ValueError("请先登录后再连接店铺")
    from src.agent.auth_session_store import get_session
    return get_session(header.removeprefix("Bearer ").strip())


def _shopify_callback_url() -> str:
    return f"{os.environ.get('PUBLIC_API_BASE_URL', '').rstrip('/')}/v1/integrations/shopify/callback"


def _shopify_hmac_is_valid(arguments: dict[str, str]) -> bool:
    received = arguments.get("hmac", "")
    secret = os.environ.get("SHOPIFY_CLIENT_SECRET", "").encode("utf-8")
    message = urlencode(sorted((key, value) for key, value in arguments.items() if key not in {"hmac", "signature"}))
    expected = hmac.new(secret, message.encode("utf-8"), hashlib.sha256).hexdigest()
    return bool(secret and received and hmac.compare_digest(received, expected))


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

    @app.route("/v1/integrations/shopify/readiness", methods=["GET", "OPTIONS"])
    def shopify_readiness() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        return jsonify(_shopify_readiness())

    @app.route("/v1/auth/login", methods=["POST", "OPTIONS"])
    def login() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        payload = request.get_json(silent=True) or {}
        username, password = payload.get("username", ""), payload.get("password", "")
        if not isinstance(username, str) or not isinstance(password, str):
            return jsonify({"error": "用户名或密码格式无效"}), 400
        try:
            from src.agent.account_store import authenticate_user
            from src.agent.auth_session_store import issue_session
            user = authenticate_user(username.strip(), password)
            if not user:
                return jsonify({"error": "用户名或密码不正确"}), 401
            return jsonify({"access_token": issue_session(user["username"], user["role"]), "expires_in": 1_800})
        except RuntimeError:
            app.logger.exception("Login service configuration failed")
            return jsonify({"error": "登录服务尚未配置完成"}), 503

    @app.route("/v1/auth/register", methods=["POST", "OPTIONS"])
    def register() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        payload = request.get_json(silent=True) or {}
        username = payload.get("username", "")
        password = payload.get("password", "")
        registration_code = payload.get("registration_code", "")
        if not all(isinstance(value, str) for value in (username, password, registration_code)):
            return jsonify({"error": "注册信息格式无效"}), 400
        try:
            from src.agent.account_store import create_user
            from src.agent.auth_session_store import issue_session
            user = create_user(username.strip(), password, registration_code, os.environ.get("REGISTRATION_CODE", ""))
            return jsonify({"access_token": issue_session(user["username"], user["role"]), "expires_in": 1_800}), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError:
            app.logger.exception("Registration service configuration failed")
            return jsonify({"error": "注册服务尚未配置完成"}), 503

    @app.route("/v1/auth/me", methods=["GET", "OPTIONS"])
    def current_user() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        try:
            session = _require_session()
            return jsonify({"username": session["username"], "role": session["role"]})
        except (ValueError, RuntimeError):
            return jsonify({"error": "登录已失效，请重新登录"}), 401

    @app.route("/v1/auth/logout", methods=["POST", "OPTIONS"])
    def logout() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        try:
            session = _require_session()
            from src.agent.auth_session_store import revoke_session
            revoke_session(session["session_id"])
            return "", 204
        except (ValueError, RuntimeError):
            return jsonify({"error": "登录已失效，请重新登录"}), 401

    @app.route("/v1/integrations/shopify/authorize", methods=["POST", "OPTIONS"])
    def authorize_shopify() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        readiness = _shopify_readiness()
        if readiness["state"] != "ready_to_authorize":
            return jsonify({"error": "Shopify 授权服务尚未配置完成"}), 503
        try:
            session = _require_session()
            payload = request.get_json(silent=True) or {}
            shop_domain = payload.get("shop_domain", "")
            if not isinstance(shop_domain, str):
                raise ValueError("店铺域名格式无效")
            from src.agent.merchant_connection_store import issue_authorization_state
            state = issue_authorization_state(session["username"], shop_domain)
            parameters = {
                "client_id": os.environ["SHOPIFY_CLIENT_ID"],
                "scope": ",".join(SHOPIFY_SCOPES),
                "redirect_uri": _shopify_callback_url(),
                "state": state,
            }
            return jsonify({"authorization_url": f"https://{shop_domain.strip().lower()}/admin/oauth/authorize?{urlencode(parameters)}"})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError:
            app.logger.exception("Shopify authorization initialization failed")
            return jsonify({"error": "授权服务暂不可用"}), 503

    @app.route("/v1/integrations/shopify/callback", methods=["GET"])
    def shopify_callback() -> Any:
        arguments = request.args.to_dict(flat=True)
        if not _shopify_hmac_is_valid(arguments):
            return "Shopify callback verification failed", 400
        try:
            from src.agent.merchant_connection_store import consume_authorization_state, save_shopify_connection
            context = consume_authorization_state(arguments.get("state", ""))
            if context["provider"] != "shopify" or context["shop_domain"] != arguments.get("shop", "").lower():
                raise ValueError("授权店铺与发起店铺不一致")
            response = requests.post(
                f"https://{context['shop_domain']}/admin/oauth/access_token",
                data={"client_id": os.environ["SHOPIFY_CLIENT_ID"], "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"], "code": arguments.get("code", "")},
                timeout=15,
            )
            response.raise_for_status()
            token_payload = response.json()
            access_token, scopes = token_payload.get("access_token"), token_payload.get("scope", "")
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("Shopify 未返回有效访问令牌")
            save_shopify_connection(context["workspace_id"], context["shop_domain"], access_token, scopes.split(","))
            return redirect(f"{os.environ['PUBLIC_WEB_URL'].rstrip('/')}/data?shopify=connected", code=302)
        except (ValueError, requests.RequestException, RuntimeError):
            app.logger.exception("Shopify authorization callback failed")
            return redirect(f"{os.environ.get('PUBLIC_WEB_URL', '').rstrip('/')}/data?shopify=failed", code=302)

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
