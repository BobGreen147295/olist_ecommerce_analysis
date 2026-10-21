"""Merchant session facade. Only server-derived aggregate reports cross the bridge."""
from functools import wraps
from flask import Blueprint, jsonify, request
from src.agent.research_gateway import request_review, ResearchRejected, ResearchUnavailable


def commerce_reviews(require_session, authentication_error):
    bp = Blueprint("commerce_reviews", __name__)

    @bp.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    def guarded(fn):
        @wraps(fn)
        def run(**kwargs):
            if request.method == "OPTIONS":
                return "", 204
            try:
                owner = require_session()["username"]
            except authentication_error:
                return jsonify(error="请先登录或重新登录失效的会话"), 401
            except Exception:
                return jsonify(error="认证服务暂不可用"), 503
            try:
                if request.args:
                    raise ValueError("复盘接口不接受账户或查询参数")
                if request.content_length and request.content_length > 16 * 1024:
                    raise ValueError("提交内容超过限制")
                return fn(owner=owner, **kwargs)
            except ResearchRejected as exc:
                return jsonify(error=str(exc)), exc.status
            except (ResearchUnavailable, RuntimeError):
                return jsonify(error="经营复盘服务暂不可用；订单核对仍可在数据页使用"), 503
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
            except Exception:
                return jsonify(error="复盘未完成，请稍后重试"), 503
        return run

    def body(allowed):
        value = request.get_json(silent=True)
        if not isinstance(value, dict) or set(value) - set(allowed):
            raise ValueError("请使用指定复盘字段；账户与证据由服务器决定")
        return value

    def report(owner):
        from src.agent.order_trend_report import order_trend_report
        return order_trend_report(owner=owner)["report"]

    @bp.route("/v1/commerce", methods=["GET", "OPTIONS"])
    @guarded
    def overview(owner):
        return jsonify(request_review("GET", "", owner))

    @bp.route("/v1/commerce/report", methods=["GET", "OPTIONS"])
    @guarded
    def check(owner):
        return jsonify(request_review("POST", "/report", owner, {"report": report(owner)}))

    @bp.route("/v1/commerce/reviews", methods=["POST", "OPTIONS"])
    @guarded
    def save(owner):
        value = body(("requestId", "snapshotId", "decision", "note", "nextAction", "dueOn"))
        return jsonify(request_review("POST", "/reviews", owner, {"input": value, "report": report(owner)}))

    @bp.route("/v1/commerce/reviews/<uuid:review_id>", methods=["PATCH", "DELETE", "OPTIONS"])
    @guarded
    def update(owner, review_id):
        value = body(("outcome", "version")) if request.method == "PATCH" else None
        result = request_review(request.method, f"/reviews/{review_id}", owner, value)
        return ("", 204) if request.method == "DELETE" else jsonify(result)

    @bp.route("/v1/commerce/reviews/<uuid:review_id>/assistant", methods=["GET", "POST", "OPTIONS"])
    @guarded
    def assistant(owner, review_id):
        value = body(("requestId", "question", "platform")) if request.method == "POST" else None
        return jsonify(request_review(request.method, f"/reviews/{review_id}/assistant", owner, value))

    @bp.route("/v1/commerce/reviews/<uuid:review_id>/assistant/<uuid:task_id>/retry", methods=["POST", "OPTIONS"])
    @guarded
    def retry(owner, review_id, task_id):
        body(())
        return jsonify(request_review("POST", f"/reviews/{review_id}/assistant/{task_id}/retry", owner, {}))

    @bp.route("/v1/commerce/reviews/<uuid:review_id>/actions", methods=["POST", "OPTIONS"])
    @guarded
    def adopt(owner, review_id):
        value = body(("taskId", "actionIndex", "version", "dueOn"))
        return jsonify(request_review("POST", f"/reviews/{review_id}/actions", owner, value))

    return bp
