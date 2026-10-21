"""Personal loopback adapter. OAuth stays inside the independent local Node process."""
import os
from types import SimpleNamespace
from urllib.parse import urlsplit

import requests


class PersonalPlusError(RuntimeError):
    def __init__(self, code, status_code=503, cause=None):
        super().__init__(code)
        self.code, self.status_code = code, status_code
        self.cause = cause


class PersonalPlusLLM:
    def __init__(self):
        address = os.environ.get('PERSONAL_PLUS_BRIDGE_URL', '')
        parsed = urlsplit(address)
        self.secret = os.environ.get('PERSONAL_PLUS_BRIDGE_SECRET', '')
        if (os.environ.get('PERSONAL_PLUS_LOCAL') != '1' or os.environ.get('RENDER')
                or parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or not parsed.port or len(self.secret) < 32):
            raise PersonalPlusError('personal_local_only')
        self.url = address.rstrip('/') + '/personal/invoke'

    def invoke(self, prompt):
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 24_000:
            raise PersonalPlusError('personal_invalid_input', 400)
        # Never send the local bridge secret through an inherited HTTP proxy.
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.post(self.url, json={'prompt': prompt},
                                        headers={'Authorization': 'Bearer ' + self.secret},
                                        timeout=(3, 50), allow_redirects=False)
            if len(response.content) > 100_000:
                raise PersonalPlusError('personal_inference_failed')
            payload = response.json()
        except requests.Timeout:
            raise TimeoutError('personal_timeout') from None
        except (requests.RequestException, ValueError):
            raise ConnectionError('personal_bridge_unavailable') from None
        if response.status_code != 200:
            code = payload.get('error') if isinstance(payload, dict) else None
            if code not in {'personal_authorization_required', 'personal_usage_stopped', 'personal_busy', 'personal_model_unavailable', 'personal_output_limit'}:
                code = 'personal_inference_failed'
            cause = payload.get('cause') if isinstance(payload, dict) else None
            raise PersonalPlusError(code, response.status_code, cause)
        content = payload.get('content') if isinstance(payload, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise PersonalPlusError('personal_inference_failed')
        return SimpleNamespace(content=content)
