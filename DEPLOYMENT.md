# 部署指南

商家经营复盘的双服务配置、账户作用域、模型边界和本机验收见 [整合说明](docs/commerce-research-integration.md)。GitHub 整合分支不会自动视为生产验收；发布前须配置独立服务密钥、HTTPS 与正式模型服务，并验证商家账户隔离。已有 Shopify 回调不因这次整合而更改。

当前生产架构由三个边界清晰的服务组成：

- **Cloudflare Pages**：部署 `web/` 中的 Next.js 前端；
- **Render**：通过 `Dockerfile.api` 部署 Flask API；
- **PostgreSQL**：保存账户、连接、任务和聚合数据。

线上地址中的 `olist` 是早期兼容标识。不要直接改仓库、Pages 项目或 Render 服务，否则必须同步修改 Shopify OAuth 回调和全部环境变量。

## 1. Render API

Render 服务使用仓库根目录与 `Dockerfile.api`。至少配置：

```text
DATABASE_URL=托管 PostgreSQL 连接串
ALLOWED_ORIGINS=https://olist-revenueops.pages.dev
APP_ADMIN_USERNAME=revenueops_admin
APP_ADMIN_PASSWORD=强随机密码
APP_REGISTRATION_CODE=受邀用户注册码
MERCHANT_TOKEN_ENCRYPTION_KEY=Fernet 密钥
SHOPIFY_CLIENT_ID=Shopify 应用 Client ID
SHOPIFY_CLIENT_SECRET=Shopify 应用 Client Secret
SHOPIFY_REDIRECT_URI=https://olist-revenueops-api.onrender.com/v1/integrations/shopify/callback
```

如启用 AI 对话，再配置模型提供商变量。所有密码、token 和连接串只能保存在 Render Environment，不能提交到 GitHub。

部署完成后验证：

```text
GET https://olist-revenueops-api.onrender.com/health
```

应返回 HTTP 200。免费实例休眠后的第一次请求可能较慢。

### 当前数据库切换状态（2026-09-15）

- Render 已配置 `MIGRATION_TARGET_DATABASE_URL`；
- `USE_MANAGED_POSTGRES=1`，应用运行时优先使用迁移后的托管 PostgreSQL；
- 旧 Supabase 项目的暂停提醒不代表当前生产数据库会暂停；
- 已实测生产 `/health` 返回 HTTP 200。
- 已完成登录后的只读回归：数据连接页可读取 Shopify 连接和匿名订单聚合，机会页可读取数据覆盖状态并正确执行营销同意安全门槛。

因此无需仅为旧 Supabase 的闲置暂停提醒付费，可让它暂停。删除旧项目或移除旧 `DATABASE_URL` 前，仍需完成一次最小写入回归验证，并保留可恢复备份。

最小写入回归在 2026-09-15 触发 Shopify 汇总重同步时返回 `summary:403`。现有连接和历史汇总仍可读取，数据库迁移未发现丢失；该错误发生在 Shopify API 的首个汇总请求，优先按授权令牌或已批准权限未刷新处理。下一动作是使用同一开发店重新执行只读 OAuth 授权，然后再次同步。

## 2. Cloudflare Pages

Pages 项目连接当前 GitHub 仓库，设置：

```text
Root directory: web
Build command: npx next build
Build output directory: /out
NEXT_PUBLIC_REVENUEOPS_API_URL=https://olist-revenueops-api.onrender.com
```

生产地址：`https://olist-revenueops.pages.dev/`。前端环境变量是公开值，绝不能放服务端密钥。

## 3. Shopify 应用

Shopify 应用使用只读 Admin API scopes。生产回调必须与 Render 中的 `SHOPIFY_REDIRECT_URI` 完全一致；修改域名或路径前，先同时更新 Shopify 应用版本和 Render 配置。

## 4. 发布验证

每次发布按顺序检查：

1. 后端测试通过，Render `/health` 返回 200；
2. 前端 `npm run build` 通过，Cloudflare Production Pages 部署成功；
3. 注册、登录、Shopify 连接、同步、断开与删除流程可用；
4. 未连接账户只看到明确标注的合成场景，不会读历史样本；
5. GitHub 中没有真实订单、客户文件或密钥。
