"""Dedicated loopback entrypoint; never run this module on Render."""
from pathlib import Path
import argparse
import os
import secrets

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / '.env.personal-plus'
ORIGIN = 'http://127.0.0.1:63101'
OWNER = 'personal-owner'


def configure(path=ENV_FILE):
    if os.environ.get('RENDER'):
        raise RuntimeError('Personal Plus is local only')
    if not path.exists():
        runtime = ROOT / '.venv/personal-plus'
        runtime.mkdir(parents=True, exist_ok=True)
        values = {
            'PERSONAL_PLUS_LOCAL': '1', 'LLM_PROVIDER': 'personal_plus',
            'PLUS_PROBE_PORT': '63100',
            'PERSONAL_PLUS_BRIDGE_URL': 'http://127.0.0.1:63100',
            'PERSONAL_PLUS_BRIDGE_SECRET': secrets.token_urlsafe(32),
            'APP_ADMIN_USERNAME': OWNER, 'APP_ADMIN_PASSWORD': secrets.token_urlsafe(24),
            'SESSION_SIGNING_KEY': secrets.token_urlsafe(32),
            'DATABASE_URL': 'sqlite:///' + (runtime / 'personal.sqlite').as_posix(),
        }
        with path.open('x', encoding='utf-8') as output:
            output.write('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n')
    values = dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines() if line and not line.startswith('#'))
    if (values.get('APP_ADMIN_USERNAME') != OWNER or values.get('LLM_PROVIDER') != 'personal_plus'
            or values.get('PERSONAL_PLUS_BRIDGE_URL') != 'http://127.0.0.1:63100'
            or not values.get('DATABASE_URL', '').startswith('sqlite:///')
            or len(values.get('PERSONAL_PLUS_BRIDGE_SECRET', '')) < 32):
        raise RuntimeError('Invalid personal configuration')
    # Do not inherit production credentials, connections, notification or API-key fallbacks.
    for key in list(os.environ):
        if key.startswith(('OPENAI_', 'SHOPIFY_', 'PILOT_NOTIFICATION_', 'OLLAMA_', 'MIGRATION_TARGET_')):
            os.environ.pop(key, None)
    os.environ.update(values)
    os.environ.update(USE_MANAGED_POSTGRES='0', REGISTRATION_CODE='', ALLOWED_ORIGINS=ORIGIN,
                      AGENT_LOG_PATH=str(ROOT / '.venv/personal-plus/agent-runs.jsonl'))
    from src.agent.account_store import ensure_admin_account
    ensure_admin_account(OWNER, values['APP_ADMIN_PASSWORD'])


def create_personal_app(web_directory=None):
    from flask import abort, jsonify, redirect, request, send_from_directory
    from api.app import create_app
    from src.agent.auth_session_store import get_session

    app = create_app()
    web = Path(web_directory or ROOT / 'web/out')
    # Next's static segment URLs flatten slashes; Windows export can retain
    # nested segment directories. Map only existing exported files, not input paths.
    segments = {}
    for file in web.rglob('*.txt'):
        relative = file.relative_to(web).as_posix()
        if '/__next' in '/' + relative:
            prefix, suffix = relative.split('__next', 1)
            segments[prefix + '__next' + suffix.replace('/', '.')] = relative

    @app.before_request
    def personal_boundary():
        if request.host != '127.0.0.1:63101':
            abort(403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('Origin') != ORIGIN:
            abort(403)
        if request.path in ('/v1/auth/register', '/v1/pilot-applications') or (
                request.path.startswith('/v1/integrations/shopify/') and request.method not in ('GET', 'HEAD', 'OPTIONS')):
            return jsonify(error='个人本机版未开放商家注册、试点通知或店铺授权。'), 403
        bearer = request.headers.get('Authorization', '')
        if bearer.startswith('Bearer '):
            try:
                if get_session(bearer[7:])['username'] != OWNER:
                    abort(403)
            except (RuntimeError, ValueError):
                return jsonify(error='请登录本机个人账户。'), 401

    @app.after_request
    def private_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/')
    def home():
        return redirect('/data')

    @app.get('/<path:asset>')
    def exported_frontend(asset):
        # send_from_directory enforces traversal protection; never serve repository files.
        if asset.startswith(('v1/', '.')):
            abort(404)
        asset = segments.get(asset, asset)
        if (web / (asset + '.html')).is_file():
            asset += '.html'
        return send_from_directory(web, asset)

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    arguments = parser.parse_args()
    configure()
    if arguments.prepare:
        print('Personal configuration ready; credentials remain in the ignored local env file.')
    else:
        from werkzeug.serving import make_server
        # Fixed loopback binding is intentional; no LAN/public option.
        print('Personal RevenueOps: ' + ORIGIN + '/data', flush=True)
        make_server('127.0.0.1', 63101, create_personal_app(), threaded=True).serve_forever()
