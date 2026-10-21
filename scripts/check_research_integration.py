"""Read-only release check. Never submits a review, AI task, sync or store action."""
import argparse
import json
import os
import re
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class CheckFailed(RuntimeError):
    pass


def check(base, token):
    parsed = urlsplit(base)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or not (parsed.scheme == "https"
                or (parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port))):
        raise CheckFailed("invalid_api_origin")
    if not token or not token.isascii() or any(c.isspace() for c in token):
        raise CheckFailed("missing_or_invalid_session")

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(path, authenticated=True):
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + token
        try:
            with opener.open(Request(base.rstrip("/") + path, headers=headers), timeout=20) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise CheckFailed("response_too_large")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise CheckFailed("invalid_response")
                return value
        except CheckFailed:
            raise
        except Exception as exc:
            # Status codes help identify auth/deployment gaps; bodies and credentials stay private.
            status = getattr(exc, "code", "transport_or_json")
            if isinstance(exc, HTTPError):
                exc.close()
            raise CheckFailed(f"request_failed:{path}:{status}") from None

    get("/health", authenticated=False)
    overview = get("/v1/commerce")
    if (overview.get("configured") is not True or not isinstance(overview.get("reviews"), list)
            or not isinstance(overview.get("aiEnabled"), bool)):
        raise CheckFailed("review_contract_not_ready")
    snapshot = get("/v1/commerce/report").get("snapshot")
    if not isinstance(snapshot, dict) or not re.fullmatch("[a-f0-9]{64}", str(snapshot.get("id", ""))):
        raise CheckFailed("snapshot_contract_not_ready")
    report = snapshot.get("report", {})
    if not isinstance(report, dict) or report.get("status") != "ready":
        raise CheckFailed("order_data_not_ready")
    return {"connection": "ready", "order_report": "ready", "ai_access": overview["aiEnabled"],
            "requests": 3, "mutations": 0, "model_submissions": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="HTTPS API origin, or 127.0.0.1 for local checks")
    args = parser.parse_args()
    try:
        result = check(args.base_url, os.environ.get("REVENUEOPS_CHECK_TOKEN", ""))
    except (CheckFailed, ValueError) as exc:
        code = str(exc) if isinstance(exc, CheckFailed) else "invalid_api_origin"
        print(json.dumps({"ok": False, "code": code}))
        return 1
    print(json.dumps({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
