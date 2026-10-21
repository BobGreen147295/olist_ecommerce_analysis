export type ReviewAction = { taskId: string; actionIndex: number; task: string; reason: string; measure: string; timing: string; dueOn: string; model: string; generatedAt: string };
export type ReviewSnapshot = { id: string; report: { status: "ready" | "unavailable"; source: string | null; currency: string | null; generated_at: string;
  rows: { period: string; total_orders: number; total_amount: number }[]; issues: { code: string; message: string }[] } };
export type CommerceReview = { id: string; version: number; input: { snapshotId: string; decision: "investigate" | "need_data" | "no_action"; note: string; nextAction: string; dueOn: string | null };
  snapshot: ReviewSnapshot; adoptedAction: ReviewAction | null; outcome: string | null; createdAt: string; completedAt: string | null };
export type ReviewTask = { id: string; status: "queued" | "running" | "failed" | "succeeded"; input: { question: string }; error: string | null;
  sourceChecks?: { id: number; state: "available" | "changed" | "unavailable" }[];
  output: null | { model: string; generatedAt: string; answer: { title: string; conclusion: string; findings: { title: string; detail: string; basis: "order_snapshot" | "public_source" | "hypothesis"; evidenceIds: number[] }[];
    actions: { priority: string; task: string; reason: string; measure: string; timing: string }[]; risks: string[]; missingData: string[] };
    sources: { id: number; itemId: string; title: string; url: string; source: string; publishedAt: string | null }[] } };
export type ReviewAI = { enabled: boolean; tasks: ReviewTask[] };
export function reviewMarkdown(review: CommerceReview) {
  const r = review.snapshot.report, a = review.adoptedAction;
  return ["# 经营复盘 / Operating review", `来源 / Source: ${r.source}; ${r.currency}; UTC`, `证据 / Snapshot: ${review.snapshot.id}`, `查询 / Queried: ${r.generated_at}`,
    "\n## 固定订单汇总 / Fixed order aggregates", ...r.rows.map(row => `- ${row.period}: ${row.total_orders} orders, ${row.total_amount} ${r.currency}`),
    "\n## 原始人工判断 / Original judgment", review.input.note, review.input.nextAction, review.input.dueOn ?? "",
    ...(a ? ["\n## 人工采纳的 AI 检查（待验证） / Adopted AI check (unverified)", a.task, a.reason, `验收与停止条件 / Acceptance & stop: ${a.measure}`, `复盘 / Review: ${a.dueOn}`, `${a.model}; ${a.generatedAt}; task ${a.taskId}`] : []),
    "\n## 人工观察 / Manual observation", review.outcome || "尚未回填 / Not recorded", "\n## 数据限制 / Limitations", ...r.issues.map(i => i.message),
    "订单金额未扣退款、未排除取消订单，不等于净收入或利润。人工观察与前后变化不能证明因果或增量效果。",
    "Order amounts include refunds/cancellations. They are not net revenue or profit. Observations and before/after changes do not establish causal uplift."].join("\n");
}
