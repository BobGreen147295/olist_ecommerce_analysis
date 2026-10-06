# RevenueOps Agent API

Flask 服务把现有 LangGraph Agent 暴露为浏览器可调用的 HTTPS API。

## Endpoints

- `GET /health`：服务健康状态，不返回任何密钥。
- `GET /readyz`：只读 `SELECT 1` 检查数据库可达性，正常为 200，不可用为 503；不建表，不验证 Shopify 或模型服务。
- `POST /v1/chat`：必须携带登录返回的 Bearer 会话，数据账户由服务端会话决定；返回回答、工具证据、诊断和活动草案。
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

## AI 调用与迁移保护（2026-10-06）

- 问答不接受匿名调用，也不允许请求或模型选择另一个账户的数据。
- 默认固定窗口额度：每账户每分钟 3 次、每天 20 次；全服务每天 100 次。每日按 UTC 零点（中国时间 08:00）重置。额度存入 `chat_usage` 表，重新登录或重启不能清空额度。
- 超限返回 429 和 `Retry-After`；额度数据库异常返回 503，均不调用模型。通过额度后的模型失败仍计次，避免失败重试耗费失控。
- 云模型单次输出最多 1200 tokens、请求超时 30 秒、自动重试 0 次；一个问答最多经过三个模型节点。这是用量保护，不是人民币账单硬上限，也不取消 Render 数据库费用。
- 生产问答失败不再用示例经营建议替代；无后端配置的演示模式仍明确标注。
- `python scripts/migrate_postgres.py --verify-only` 只读核对源与目标已存在应用表的行数及内容指纹，不建表、不写入。应在暂停业务写入的维护窗口验证，以避免并发变化产生不一致。
- 正式迁移补齐 `pilot_applications`、`chat_usage`，拒绝覆盖非空目标，验证失败回滚本次插入；源库只读。初始化目标可能创建空表，不会因此修改源数据。
- 当前本地验收使用合成 SQLite 数据与 PostgreSQL 驱动替身；真实 PostgreSQL 迁移、备份恢复和线上登录仍须在发布前单独验收。不得因此直接删除或暂停旧数据库。
