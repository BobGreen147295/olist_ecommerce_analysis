# RevenueOps Agent API

Flask 服务把现有 LangGraph Agent 暴露为浏览器可调用的 HTTPS API。

## Endpoints

- `GET /health`：服务健康状态，不返回任何密钥。
- `POST /v1/chat`：运行 Agent，返回回答、工具证据、诊断和活动草案。
- `GET /v1/data-health`：返回连接状态与安全的数据覆盖摘要。

## Run locally

```bash
python -m flask --app api.app:app run --port 8000
```

Then configure the web app with `NEXT_PUBLIC_REVENUEOPS_API_URL=http://localhost:8000`.

## Deployment requirements

Set these as host-managed secrets, never in Git:

- `OPENAI_API_KEY` when `LLM_PROVIDER=openai`
- `DATABASE_URL` for PostgreSQL/Supabase
- `SESSION_SIGNING_KEY`: at least 32 random characters; signs the short-lived
  browser API session and must never be committed.
- `REGISTRATION_CODE`: a long one-time/private invitation code used only to
  create the initial connection account; rotate it after the initial account is created.
- `CONNECTION_TOKEN_ENCRYPTION_KEY`: a valid Fernet key used only to encrypt
  merchant platform access tokens at rest.
- `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `PUBLIC_API_BASE_URL`, and
  `PUBLIC_WEB_URL` before enabling Shopify OAuth. The client secret and access
  tokens remain server-side at all times.
- `ALLOWED_ORIGINS=https://olist-revenueops.pages.dev`

The included `Dockerfile.api` can be deployed on any container platform. The API should be deployed before setting `NEXT_PUBLIC_REVENUEOPS_API_URL` in Cloudflare Pages.
