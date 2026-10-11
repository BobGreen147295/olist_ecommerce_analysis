"""Best-effort owner-only notification, after the application is committed."""
import hashlib
import hmac
import os
import re
import time
from urllib.parse import urlparse

import requests


def notification_configured() -> bool:
    url = os.environ.get("PILOT_NOTIFICATION_URL", "").strip()
    secret = os.environ.get("PILOT_NOTIFICATION_SECRET", "")
    return bool(re.fullmatch(r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec", url)
                and len(secret) >= 32)


def notify_owner(application_id: str) -> str:
    """Never forwards contact details, retries a send, or raises network failures."""
    if not notification_configured():
        return "not_configured"
    if not re.fullmatch(r"[a-f0-9]{16}", application_id):
        return "failed"
    timestamp = int(time.time())
    secret = os.environ["PILOT_NOTIFICATION_SECRET"].encode("utf-8")
    signature = hmac.new(secret, f"{application_id}.{timestamp}".encode("utf-8"), hashlib.sha256).hexdigest()
    try:
        response = requests.post(
            os.environ["PILOT_NOTIFICATION_URL"].strip(),
            json={"application_id": application_id, "timestamp": timestamp, "signature": signature},
            timeout=(3, 7), allow_redirects=False,
        )
        # ContentService redirects only the response body; do not re-POST the event.
        if response.status_code in (302, 303):
            location = response.headers.get("Location", "")
            parsed = urlparse(location)
            if parsed.scheme != "https" or parsed.netloc != "script.googleusercontent.com":
                return "failed"
            response = requests.get(location, timeout=(3, 7), allow_redirects=False)
        response.raise_for_status()
        data = response.json()
        return "accepted" if isinstance(data, dict) and data.get("ok") is True else "failed"
    except (requests.RequestException, ValueError):
        # No response body, URL or token in logs; timeout is not proof of non-delivery.
        return "failed"
