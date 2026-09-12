# 部署指南

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
