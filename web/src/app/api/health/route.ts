export function GET() {
  return Response.json({
    status: "ok",
    service: "olist-revenueops-web",
    version: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "local",
    timestamp: new Date().toISOString(),
  });
}
