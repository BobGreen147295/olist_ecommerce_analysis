"""HTTP boundary for the RevenueOps Agent.

The browser never receives database URLs or model-provider credentials. This
service is intentionally separate from the static Cloudflare Pages frontend.
"""

from __future__ import annotations

import os
import re
import hashlib
import hmac
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import requests
from flask import Flask, jsonify, redirect, request


MAX_MESSAGE_LENGTH = 1_500
DEFAULT_ORIGINS = "https://olist-revenueops.pages.dev,http://localhost:3000"
SHOPIFY_SCOPES = ("read_orders", "read_customers", "read_products", "read_inventory")
SHOPIFY_API_VERSION = "2026-07"
SHOPIFY_SUMMARY_QUERY = """
query RevenueOpsInitialSummary {
  shop { currencyCode }
  ordersCount { count }
  customersCount { count }
  productsCount { count }
  inventoryItems(first: 250) {
    nodes { id }
    pageInfo { hasNextPage }
  }
}
"""
SHOPIFY_TREND_PAGE_SIZE = 250
SHOPIFY_TREND_MAX_ORDERS = 1_000
SHOPIFY_ORDER_TREND_QUERY = """
query RevenueOpsOrderTrend($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes {
      createdAt
      totalPriceSet { shopMoney { amount currencyCode } }
      currentTotalPriceSet { shopMoney { amount currencyCode } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def _money_amount(value: Any) -> Decimal:
    """解析 Shopify 金额；无效值按零处理，且不保存原始订单。"""
    try:
        return Decimal(str((((value or {}).get("shopMoney") or {}).get("amount") or "0")))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _shopify_order_trend(nodes: list[dict[str, Any]], window_days: int, truncated: bool) -> dict[str, Any]:
    """将瞬时订单节点压缩为按原订单日期汇总，不保留订单或客户标识。"""
    daily: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"orders": 0, "gross_sales": Decimal("0"), "net_sales": Decimal("0"), "refunds": Decimal("0")}
    )
    for node in nodes:
        created_at = node.get("createdAt") if isinstance(node, dict) else None
        if not isinstance(created_at, str) or len(created_at) < 10:
            continue
        bucket = daily[created_at[:10]]
        bucket["orders"] = int(bucket["orders"]) + 1
        gross = _money_amount(node.get("totalPriceSet"))
        net = _money_amount(node.get("currentTotalPriceSet"))
        bucket["gross_sales"] = Decimal(bucket["gross_sales"]) + gross
        bucket["net_sales"] = Decimal(bucket["net_sales"]) + net
        # Shopify 的 currentTotalPriceSet 已扣除退款、退货和订单编辑。
        # 因此这里是“退款/订单调整额”，不会伪装成纯退款金额。
        bucket["refunds"] = Decimal(bucket["refunds"]) + max(gross - net, Decimal("0"))

    days = [
        {"date": date, "orders": values["orders"], "gross_sales": float(values["gross_sales"]), "net_sales": float(values["net_sales"]), "refunds": float(values["refunds"])}
        for date, values in sorted(daily.items())
    ]
    return {
        "window_days": window_days,
        "orders_scanned": sum(day["orders"] for day in days),
        "truncated": truncated,
        "days": days,
        "totals": {"orders": sum(day["orders"] for day in days), "gross_sales": round(sum(day["gross_sales"] for day in days), 2), "net_sales": round(sum(day["net_sales"] for day in days), 2), "refunds": round(sum(day["refunds"] for day in days), 2)},
        "refund_attribution": "退款及订单调整额按原订单日期归集",
    }


def _shopify_rest_order_trend(connection: dict[str, Any], since: str, currency_code: str | None) -> tuple[list[dict[str, Any]], bool]:
    """GraphQL 趋势不可用时，以 REST 最小订单字段生成瞬时节点并立即聚合。"""
    url = f"https://{connection['shop_domain']}/admin/api/{SHOPIFY_API_VERSION}/orders.json"
    headers = {"X-Shopify-Access-Token": connection["access_token"]}
    nodes: list[dict[str, Any]] = []
    truncated = False
    params: dict[str, Any] | None = {
        "status": "any", "created_at_min": f"{since}T00:00:00Z", "limit": min(SHOPIFY_TREND_PAGE_SIZE, SHOPIFY_TREND_MAX_ORDERS),
        "fields": "created_at,total_price,current_total_price,currency",
    }
    while url and len(nodes) < SHOPIFY_TREND_MAX_ORDERS:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        orders = payload.get("orders") if isinstance(payload, dict) else None
        if not isinstance(orders, list):
            raise ValueError("Shopify 未返回可用的订单趋势数据")
        for order in orders:
            if not isinstance(order, dict) or not isinstance(order.get("created_at"), str):
                continue
            order_currency = order.get("currency") if isinstance(order.get("currency"), str) else (currency_code or "USD")
            nodes.append({
                "createdAt": order["created_at"],
                "totalPriceSet": {"shopMoney": {"amount": order.get("total_price") or "0", "currencyCode": order_currency}},
                "currentTotalPriceSet": {"shopMoney": {"amount": order.get("current_total_price") or "0", "currencyCode": order_currency}},
            })
            if len(nodes) >= SHOPIFY_TREND_MAX_ORDERS:
                truncated = True
                break
        url = response.links.get("next", {}).get("url")
        params = None
        if url and len(nodes) >= SHOPIFY_TREND_MAX_ORDERS:
            truncated = True
    return nodes, truncated


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

    @app.route("/v1/integrations/shopify/status", methods=["GET", "OPTIONS"])
    def shopify_status() -> Any:
        if request.method == "OPTIONS":
            return "", 204
        try:
            session = _require_session()
            from src.agent.merchant_connection_store import get_shopify_connection_status
            connection = get_shopify_connection_status(session["username"])
            # 旧版同步在保存趋势前失败时，已存在的安全汇总会一直显示，
            # 但没有机会自动补齐。仅当趋势缺失时，在仪表盘读取状态时做一次
            # 与手动“重新同步”完全相同的只读补齐；成功后立即重新读取状态。
            if connection and isinstance(connection.get("summary"), dict) and "order_trend" not in connection["summary"]:
                sync_shopify()
                connection = get_shopify_connection_status(session["username"])
            return jsonify({"connection": connection})
        except (ValueError, RuntimeError):
            return jsonify({"error": "登录已失效，请重新登录"}), 401

    @app.route("/v1/integrations/shopify/sync", methods=["POST", "OPTIONS"])
    def sync_shopify() -> Any:
        """同步计数与近 30 天订单日汇总，不保存订单、客户或设备级数据。"""
        if request.method == "OPTIONS":
            return "", 204
        try:
            session = _require_session()
            from src.agent.merchant_connection_store import get_shopify_connection_for_sync, save_shopify_sync_summary
            connection = get_shopify_connection_for_sync(session["username"])
            response = requests.post(
                f"https://{connection['shop_domain']}/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
                headers={"X-Shopify-Access-Token": connection["access_token"], "Content-Type": "application/json"},
                json={"query": SHOPIFY_SUMMARY_QUERY}, timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            errors = payload.get("errors") or payload.get("data", {}).get("errors")
            if errors or not isinstance(payload.get("data"), dict):
                raise ValueError("Shopify 未返回可用的汇总数据")
            data = payload["data"]
            shop = data.get("shop") or {}
            summary = {
                "orders": int((data.get("ordersCount") or {}).get("count", 0)),
                "customers": int((data.get("customersCount") or {}).get("count", 0)),
                "products": int((data.get("productsCount") or {}).get("count", 0)),
                # Shopify Admin GraphQL 没有 inventoryItemsCount。只读取最多 250 个
                # 非业务 ID 来计数，随后立即丢弃，避免写入任何库存项级数据。
                "inventory_items": len((data.get("inventoryItems") or {}).get("nodes") or []),
                "currency_code": shop.get("currencyCode") if isinstance(shop.get("currencyCode"), str) else None,
            }
            since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
            trend_nodes: list[dict[str, Any]] = []
            cursor: str | None = None
            has_next_page = True
            while has_next_page and len(trend_nodes) < SHOPIFY_TREND_MAX_ORDERS:
                trend_response = requests.post(
                    f"https://{connection['shop_domain']}/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
                    headers={"X-Shopify-Access-Token": connection["access_token"], "Content-Type": "application/json"},
                    json={"query": SHOPIFY_ORDER_TREND_QUERY, "variables": {
                        "first": min(SHOPIFY_TREND_PAGE_SIZE, SHOPIFY_TREND_MAX_ORDERS - len(trend_nodes)),
                        "after": cursor,
                        "query": f"created_at:>={since}",
                    }},
                    timeout=20,
                )
                trend_response.raise_for_status()
                trend_payload = trend_response.json()
                trend_errors = trend_payload.get("errors") or trend_payload.get("data", {}).get("errors")
                trend_orders = (trend_payload.get("data") or {}).get("orders")
                if trend_errors or not isinstance(trend_orders, dict):
                    # 个别店铺/API 版本可能拒绝 GraphQL 的趋势字段；改用同一
                    # read_orders 权限下的 REST 最小字段，不阻断已授权的汇总同步。
                    trend_nodes, rest_truncated = _shopify_rest_order_trend(connection, since, summary["currency_code"])
                    has_next_page = rest_truncated
                    break
                nodes = trend_orders.get("nodes") or []
                trend_nodes.extend(node for node in nodes if isinstance(node, dict))
                page_info = trend_orders.get("pageInfo") or {}
                has_next_page = bool(page_info.get("hasNextPage"))
                cursor = page_info.get("endCursor") if isinstance(page_info.get("endCursor"), str) else None
                if has_next_page and not cursor:
                    raise ValueError("Shopify 订单趋势分页信息无效")
            summary["order_trend"] = _shopify_order_trend(
                trend_nodes, 30, has_next_page or len(trend_nodes) >= SHOPIFY_TREND_MAX_ORDERS,
            )
            result = save_shopify_sync_summary(connection["workspace_id"], connection["shop_domain"], summary)
            return jsonify({"connection": {"provider": "shopify", "shop_domain": connection["shop_domain"], **result}})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except requests.RequestException:
            app.logger.exception("Shopify aggregate sync request failed")
            return jsonify({"error": "无法从 Shopify 同步汇总数据，请稍后重试"}), 502
        except RuntimeError:
            app.logger.exception("Shopify aggregate sync failed")
            return jsonify({"error": "同步服务暂不可用，请重新授权后重试"}), 503

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
