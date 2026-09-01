# Production deployment

The RevenueOps web app is a static Next.js export hosted on Cloudflare Pages. This creates a public `*.pages.dev` HTTPS address that can be opened from any device without the developer's computer running.

## Deploy through GitHub

1. Sign in to [Cloudflare](https://dash.cloudflare.com/) with email verification.
2. Open **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**.
3. Authorize the GitHub account and choose `BobGreen147295/olist_ecommerce_analysis`.
4. Set project name to `olist-revenueops` and **Root directory** to `web`.
5. Use these build settings:

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Framework preset | `Next.js (Static HTML Export)` |
| Build command | `npx next build` |
| Build output directory | `out` |

6. Click **Save and Deploy**. Cloudflare will create `https://olist-revenueops.pages.dev` (or a close available name).

Every push to `main` will automatically redeploy the production site. Validate it at `/health.json`.

## Architecture boundary

The Web frontend is intentionally static. The Python Agent, PostgreSQL/Supabase access, authentication, and provider secrets belong in a separately deployed server-side API. The browser will call that API over HTTPS; it will never hold database connection strings or service keys.
