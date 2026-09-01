# Production deployment

This frontend is deployable as a standalone Next.js application. The recommended production path is Vercel + GitHub.

1. Push the repository to GitHub.
2. In Vercel, import `BobGreen147295/olist_ecommerce_analysis`.
3. Set **Root Directory** to `web`.
4. Leave the detected Next.js build settings unchanged, then deploy.
5. In Vercel Project Settings, add production environment variables from `.env.example` only when the Agent API is available.

Vercel will create a public HTTPS URL and automatically redeploy the `main` branch on every GitHub push. Validate the public deployment at `/api/health`.

## Security boundary

- Never add Supabase `DATABASE_URL`, OpenAI keys, or service-role keys as `NEXT_PUBLIC_*` variables.
- Add secrets in Vercel Project Settings, not in Git.
- The browser talks only to a server-side Agent API. The API owns authentication, tenant isolation, audit events, and database access.
