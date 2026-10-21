"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeading, StatusBadge } from "@/components/Ui";
import { LifecycleTask, OpportunityLifecycle } from "@/components/OpportunityLifecycle";
import { useI18n } from "@/components/I18n";
import { opportunities } from "@/lib/demo-data";
import { TaskPicker } from "@/components/TaskPicker";
import { selectTask, taskHref } from "@/lib/task-workflow";

const scoreFormula = "综合分 = 影响规模 35% + 增量潜力 30% + 置信度 20% + 可执行性 15%";
const scoreFormulaEn = "Score = impact 35% + incremental potential 30% + confidence 20% + executability 15%";
const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
const SHOPIFY_SUMMARY_CACHE_KEY = "revenueops_shopify_summary_v1";
type StoreOpportunity = { id: "net_sales_decline" | "refund_pressure"; title: string; summary: string; evidence: Record<string, number> };
type ReactivationSignal = { state: "ready" | "not_ready"; message: string; eligible_customers?: number; eligible_historical_sales?: number; currency?: string; cutoff_date?: string; inactive_days?: number; coverage?: { imported_orders: number; identified_orders: number; consented_orders: number } };
const evidenceById = {
  "opp-001": { confidence: "中等 · 72%", freshness: "样本数据 · 2026-08-31", signals: ["近 90 天未复购", "历史贡献高于分位数 P80", "最近一次购买间隔拉长 18 天"], assumption: "按过去 30 天同类客户的平均复购贡献估算，不代表承诺收入。", guardrail: "先做 200 人 A/B 测试，控制优惠成本。" },
  "opp-002": { confidence: "中等 · 68%", freshness: "样本数据 · 2026-08-31", signals: ["美国首购客户", "首单后 14–30 天沉默", "第二单转化低于基线"], assumption: "假设邮件触达率和客单价接近历史均值。", guardrail: "不自动发送，需先确认邮件名单和优惠政策。" },
  "opp-003": { confidence: "偏低 · 55%", freshness: "样本数据 · 2026-08-31", signals: ["折扣高于 20%", "订单量上升", "净收入未完成归因"], assumption: "未接入广告成本、履约和退款数据，净利润判断不完整。", guardrail: "接入成本数据前，只作为待验证假设。" },
} as const;
const evidenceByIdEn = {
  "opp-001": { confidence: "Medium · 72%", freshness: "Sample data · 2026-08-31", signals: ["No repeat purchase in 90 days", "Historical contribution above P80", "Purchase interval increased by 18 days"], assumption: "Estimated from the average repeat contribution of similar customers over the past 30 days; not promised revenue.", guardrail: "Start with a 200-person A/B test and cap discount cost." },
  "opp-002": { confidence: "Medium · 68%", freshness: "Sample data · 2026-08-31", signals: ["First-time U.S. customers", "Inactive 14–30 days after first order", "Second-order conversion below baseline"], assumption: "Assumes email reach and order value remain close to historical averages.", guardrail: "Do not send automatically; confirm the audience and offer policy first." },
  "opp-003": { confidence: "Low · 55%", freshness: "Sample data · 2026-08-31", signals: ["Discount above 20%", "Order volume increased", "Net revenue attribution incomplete"], assumption: "Ad cost, fulfillment, and refund data are not connected, so the margin view is incomplete.", guardrail: "Treat as a hypothesis until cost data is connected." },
} as const;
const opportunityCopyEn: Record<string, { title: string; evidence: string; segment: string; status: string }> = {
  "opp-001": { title: "Reactivate high-value customers at risk of churn", evidence: "Repeat-purchase interval is increasing and the 30-day dormant share is above baseline.", segment: "No repeat purchase in 90 days · High historical value", status: "Awaiting approval" },
  "opp-002": { title: "Improve second purchase among new U.S. customers", evidence: "Second-order conversion among 14–30 day first-time buyers is below baseline.", segment: "First-time U.S. buyers · 14–30 days since first order", status: "Design needed" },
  "opp-003": { title: "Review margin erosion in high-discount orders", evidence: "Order volume increased while net-revenue attribution remains incomplete.", segment: "Repeat orders with discounts above 20%", status: "Needs validation" },
};

export default function OpportunitiesPage() {
  const { locale, t } = useI18n();
  const english = locale === "en";
  const tx = (zh: string, en: string) => english ? en : zh;
  const [selected, setSelected] = useState<string | null>(null);
  const [approved, setApproved] = useState<string | null>(null);
  const [shopifySynced, setShopifySynced] = useState(false);
  const [shopifyDevelopmentStore, setShopifyDevelopmentStore] = useState(false);
  const [storeOpportunities, setStoreOpportunities] = useState<StoreOpportunity[]>([]);
  const [reactivationSignal, setReactivationSignal] = useState<ReactivationSignal | null>(null);
  const [draftMessage, setDraftMessage] = useState("");
  const [lifecycleTasks, setLifecycleTasks] = useState<LifecycleTask[]>([]);
  const [reviewId, setReviewId] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewMessage, setReviewMessage] = useState("");
  const diagnosticTasks = lifecycleTasks.filter(task => task.source_diagnosis?.source === "shopify_aggregate");
  const diagnosticTask = selectTask(diagnosticTasks, reviewId);
  const reviewEvidence = Object.entries(diagnosticTask?.source_diagnosis?.evidence ?? {}).filter(([key,value]) => ["recent_net_sales","previous_net_sales","gross_sales","refunds"].includes(key) && Number.isFinite(value));
  const [lifecycleState, setLifecycleState] = useState<"loading" | "signed-out" | "empty" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [draftBusy, setDraftBusy] = useState(false);
  const [signalReadiness, setSignalReadiness] = useState<{ state: string; message: string } | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  useEffect(() => {
    try { localStorage.removeItem(SHOPIFY_SUMMARY_CACHE_KEY); } catch { /* No cache is read. */ }
    const token = sessionStorage.getItem("revenueops_access_token");
    let active = true;
    if (!token || !API_BASE_URL) { Promise.resolve().then(() => { if (active) setLifecycleState("signed-out"); }); return () => { active = false; }; }
    const currentSession = () => active && sessionStorage.getItem("revenueops_access_token") === token;
    const readAccount = async (path: string) => {
      const response = await fetch(`${API_BASE_URL}${path}`, { signal: AbortSignal.timeout(90000), headers: { Authorization: `Bearer ${token}` } });
      if (!currentSession()) return null;
      if (response.status === 401) {
        sessionStorage.removeItem("revenueops_access_token");
        setLifecycleTasks([]); setStoreOpportunities([]); setReactivationSignal(null);
        setSignalReadiness(null); setLastSyncedAt(null);
        setShopifySynced(false); setShopifyDevelopmentStore(false); setReviewId("");
        setLifecycleState("signed-out");
        setLoadError("expired");
        return null;
      }
      if (!response.ok) throw new Error("Request failed");
      return response.json();
    };
    readAccount("/v1/integrations/shopify/status")
      .then((data) => {
        if (!currentSession()) return;
        const connection = data?.connection;
        setShopifySynced(Boolean(connection?.summary));
        setShopifyDevelopmentStore(Boolean(connection?.summary?.is_development_store));
        setStoreOpportunities(Array.isArray(connection?.store_opportunities) ? connection.store_opportunities : []);
        setSignalReadiness(connection?.opportunity_readiness ?? null);
        setLastSyncedAt(connection?.last_synced_at ?? null);
      })
      .catch(() => { if (currentSession()) setLoadError("partial"); });
    readAccount("/v1/opportunities/reactivation")
      .then((data) => { if (currentSession()) setReactivationSignal(data?.signal ?? null); })
      .catch(() => { if (currentSession()) setLoadError("partial"); });
    readAccount("/v1/tasks")
      .then((data) => {
        if (!currentSession()) return;
        if (!Array.isArray(data?.tasks)) throw new Error("Invalid task response");
        const tasks = data.tasks as LifecycleTask[];
        setLifecycleTasks(tasks);
        setReviewId(new URLSearchParams(window.location.search).get("task") ?? "");
        setLifecycleState(tasks.length ? "ready" : "empty");
      })
      .catch(() => { if (currentSession()) setLifecycleState("error"); });
    return () => { active = false; };
  }, []);
  function clearExpiredSession(token: string) {
    if (sessionStorage.getItem("revenueops_access_token") !== token) return;
    sessionStorage.removeItem("revenueops_access_token");
    setLifecycleTasks([]); setStoreOpportunities([]); setReactivationSignal(null);
    setSignalReadiness(null); setLastSyncedAt(null);
    setShopifySynced(false); setShopifyDevelopmentStore(false); setReviewId("");
    setLifecycleState("signed-out"); setLoadError("expired");
  }
  async function createSignalDraft(signalId: StoreOpportunity["id"]) {
    if (draftBusy) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token || !API_BASE_URL) { setDraftMessage(tx("请先登录后再创建审核草案。", "Sign in before creating a review draft.")); return; }
    setDraftBusy(true); setDraftMessage("");
    try {
    const response = await fetch(`${API_BASE_URL}/v1/tasks/from-shopify-signal`, { method: "POST", signal: AbortSignal.timeout(90000), headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ signal_id: signalId }) });
    const data = await response.json().catch(() => ({}));
    if (sessionStorage.getItem("revenueops_access_token") !== token) return;
    if (response.status === 401) { clearExpiredSession(token); return; }
    if (response.ok && data.task) { setLifecycleTasks((current) => [data.task, ...current]); setLifecycleState("ready"); }
    setDraftMessage(response.ok && data.task ? tx("已创建待人工审核草案；不会创建活动或触达客户。", "A human-review draft was created. No campaign or customer contact was created.") : (english ? "Draft creation was not confirmed. Refresh to check before retrying." : (data.error ?? "草案创建未确认，请刷新核对后再试。")));
    } catch { if (sessionStorage.getItem("revenueops_access_token") === token) setDraftMessage(tx("网络异常，创建结果未确认。请先刷新核对，勿重复提交。", "Network error; creation is unconfirmed. Refresh to check before submitting again.")); }
    finally { setDraftBusy(false); }
  }
  async function createReactivationDraft() {
    if (draftBusy) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token || !API_BASE_URL) { setDraftMessage(tx("请先登录后再创建审核草案。", "Sign in before creating a review draft.")); return; }
    setDraftBusy(true); setDraftMessage("");
    try {
    const response = await fetch(`${API_BASE_URL}/v1/tasks/from-reactivation-signal`, { method: "POST", signal: AbortSignal.timeout(90000), headers: { Authorization: `Bearer ${token}` } });
    const data = await response.json().catch(() => ({}));
    if (sessionStorage.getItem("revenueops_access_token") !== token) return;
    if (response.status === 401) { clearExpiredSession(token); return; }
    if (response.ok && data.task) { setLifecycleTasks((current) => [data.task, ...current]); setLifecycleState("ready"); }
    setDraftMessage(response.ok && data.task ? tx("已创建再激活试点审核草案；未生成名单，未触达客户。", "A reactivation pilot review draft was created. No list was generated and no customer was contacted.") : (english ? "Draft creation was not confirmed. Refresh to check before retrying." : (data.error ?? "草案创建未确认，请刷新核对后再试。")));
    } catch { if (sessionStorage.getItem("revenueops_access_token") === token) setDraftMessage(tx("网络异常，创建结果未确认。请先刷新核对，勿重复提交。", "Network error; creation is unconfirmed. Refresh to check before submitting again.")); }
    finally { setDraftBusy(false); }
  }
  async function reviewDiagnosis(decision: "accepted" | "needs_information" | "rejected") {
    if (!diagnosticTask || !API_BASE_URL || reviewBusy) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token) { setReviewMessage(tx("请先登录。", "Sign in first.")); return; }
    setReviewBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/v1/tasks/${diagnosticTask.task_id}/diagnostic-review`, {method:"POST",headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`},body:JSON.stringify({decision})});
      const data = await response.json().catch(()=>({}));
      if (sessionStorage.getItem("revenueops_access_token") !== token) return;
      if (response.status === 401) { clearExpiredSession(token); return; }
      if (!response.ok || !data.task) { setReviewMessage(tx("反馈未能保存，请核对登录及任务后重试。", "Feedback was not saved. Check sign-in and task, then retry.")); return; }
      setLifecycleTasks(current=>current.map(task=>task.task_id===data.task.task_id?data.task:task));
      setReviewMessage(tx("已记录反馈；没有创建营销活动或触达客户。", "Feedback recorded. No marketing campaign or customer contact was created."));
    } catch { if(sessionStorage.getItem("revenueops_access_token")===token) setReviewMessage(tx("网络异常，保存未确认。请先刷新核对。", "Network error; saving was not confirmed. Refresh to check first.")); }
    finally { setReviewBusy(false); }
  }
  return <main className="page-content">
    <PageHeading eyebrow="Evidence to outcome" title={t("opportunitiesTitle")} description={t("opportunitiesDescription")} />
    <OpportunityLifecycle tasks={lifecycleTasks} state={lifecycleState} />
    {loadError && <div className="notice-bar" role="alert">{loadError === "expired" ? tx("登录已失效，请前往数据页重新登录。", "Session expired. Sign in on the data page.") : tx("部分数据读取失败，请刷新重试；这不代表没有机会。", "Some data could not be loaded. Refresh to retry; this does not mean there are no opportunities.")}<button className="button button-ghost" onClick={() => window.location.reload()}>{tx("刷新重试", "Refresh and retry")}</button></div>}
    {signalReadiness && signalReadiness.state !== "ready" && <section className="notice-bar" role="status"><span>{english ? "Store signals are not ready. Check coverage and manually resync on the data page. Snapshots older than 24 hours cannot create new signals; no automatic sync is performed." : signalReadiness.message}{lastSyncedAt && <> {tx("最近同步", "Last synced")}: <time dateTime={lastSyncedAt}>{lastSyncedAt}</time></>}</span><Link className="button button-ghost" href="/data">{tx("核对数据并手动同步", "Check data and sync manually")}</Link></section>}
    {draftBusy && <p role="status">{tx("正在创建审核草案，请勿重复提交…", "Creating a review draft. Please do not submit again…")}</p>}
    {diagnosticTasks.length > 0 && <section className="card real-campaign-card" aria-labelledby="diagnostic-review-title">
      <h2 id="diagnostic-review-title">{tx("店铺诊断审阅", "Store diagnosis review")}</h2>
      <p>{tx("这是店铺级信号审阅，不是营销活动审批；不需要客户名单。", "This reviews store-level signals, not marketing campaigns. No customer list is needed.")}</p>
      <TaskPicker tasks={diagnosticTasks} value={diagnosticTask?.task_id ?? ""} english={english} disabled={reviewBusy} onChange={id => { setReviewId(id); setReviewMessage(""); window.location.assign(id ? taskHref("/opportunities", id) : "/opportunities"); }} />
      {diagnosticTask && <>
        <h3>{diagnosticTask.title}</h3>
        <div className="execution-package-note">
          <strong>{tx("创建草案时保存的 Shopify 按日汇总证据", "Shopify daily aggregate evidence saved with this draft")}</strong>
          <span>{diagnosticTask.source_diagnosis?.provenance?.currency ?? tx("币种未记录", "Currency not recorded")} · {diagnosticTask.source_diagnosis?.provenance?.observed_start ?? "—"} / {diagnosticTask.source_diagnosis?.provenance?.observed_end ?? "—"}</span>
          {reviewEvidence.length ? reviewEvidence.map(([key,value]) => <span key={key}>{({recent_net_sales:tx("近7天订单当前总额", "Recent 7-day current order total"),previous_net_sales:tx("前7天订单当前总额", "Previous 7-day current order total"),gross_sales:tx("订单原始总额", "Original order total"),refunds:tx("退款/订单调整额", "Refunds/order adjustments")} as Record<string,string>)[key]}: {value}</span>) : <span>{tx("缺少数值证据，请补充口径；不会填入演示值。", "Numeric evidence is missing. Clarify definitions; demo values are not substituted.")}</span>}
          <span>{tx("金额不等于利润，信号不等于已核实原因。", "Amounts are not profit; a signal is not a verified cause.")}</span>
        </div>
        <div className="button-row">
          <button className="button button-primary" disabled={reviewBusy} onClick={() => reviewDiagnosis("accepted")}>{tx("认可信号，核实原因", "Accept signal; verify cause")}</button>
          <button className="button button-ghost" disabled={reviewBusy} onClick={() => reviewDiagnosis("needs_information")}>{tx("需要补充口径", "Clarify definitions")}</button>
          <button className="button button-ghost" disabled={reviewBusy} onClick={() => reviewDiagnosis("rejected")}>{tx("停止这项诊断", "Stop this diagnosis")}</button>
        </div>
        {diagnosticTask.diagnostic_review && <p role="status">{diagnosticTask.diagnostic_review.decision === "accepted" ? tx("已认可信号；下一步核实业务原因，不代表原因已经证实。", "Signal accepted; next verify the business cause. The cause is not proven.") : diagnosticTask.diagnostic_review.decision === "needs_information" ? tx("待补充信息；下一步核对分析口径。", "More information required; clarify metric definitions next.") : tx("已停止这项诊断，不生成执行包。", "Diagnosis stopped. No execution package is generated.")} {diagnosticTask.diagnostic_review.reviewed_at}</p>}
      </>}
      {reviewMessage && <p role="status">{reviewMessage}</p>}
    </section>}
    {shopifySynced && <section className="notice-bar"><span className="notice-dot" />{shopifyDevelopmentStore ? tx("Shopify 开发店汇总数据已接入：仅用于验证同步，不能创建真实机会或客户触达。", "Shopify development-store aggregates are connected for sync validation only; they cannot create real opportunities or customer outreach.") : tx("Shopify 真实汇总数据已接入；本页下列机会仍是合成演示场景，不能创建真实客户触达。", "Real Shopify aggregates are connected. The opportunities below remain synthetic demos and cannot create real customer outreach.")}</section>}
    {!shopifyDevelopmentStore && storeOpportunities.length > 0 && <section className="card aggregate-opportunity-card"><div><p className="eyebrow">SHOPIFY AGGREGATE SIGNALS</p><h2>{tx("店铺级待核实信号", "Store-level signals to verify")}</h2><p>{tx("仅基于已授权的按日订单汇总生成；不含客户、订单或联系方式，不能直接触达。", "Generated only from authorized daily order aggregates. No customers, orders, or contact details are included, and no outreach can be sent.")}</p></div><div className="aggregate-signal-list">{storeOpportunities.map((signal) => <article key={signal.id}><strong>{english && signal.id === "net_sales_decline" ? "Net sales decline" : english && signal.id === "refund_pressure" ? "Refund pressure" : signal.title}</strong><span>{english ? "Review the authorized store aggregate and verify the business cause before acting." : signal.summary}</span><small>{tx("需人工核实原因后再决定下一步。", "Verify the cause manually before choosing the next action.")}</small><button className="button button-ghost" disabled={draftBusy} onClick={() => createSignalDraft(signal.id)}>{tx("创建审核草案", "Create review draft")}</button></article>)}{draftMessage && <p className="aggregate-draft-message">{draftMessage}</p>}</div></section>}
    <section className="card aggregate-opportunity-card"><div><p className="eyebrow">CONSENTED REACTIVATION PILOT</p><h2>{tx("高价值沉默客户", "High-value dormant customers")}: {reactivationSignal?.state === "ready" ? tx("待审核机会", "Opportunity to review") : tx("数据尚未就绪", "Data not ready")}</h2><p>{english ? "Sign in and import an anonymized order CSV on the data page. This page never displays or stores a customer list." : (reactivationSignal?.message ?? "请登录并在数据页导入匿名订单 CSV 后计算。页面不会显示或保存客户名单。")}</p></div><div className="aggregate-signal-list"><article>{reactivationSignal?.state === "ready" ? <><strong>{reactivationSignal.eligible_customers?.toLocaleString() ?? 0} {tx("位待审核候选客户", "candidates for manual review")}</strong><span>{tx("历史消费额", "Historical spend")}: {reactivationSignal.currency} {reactivationSignal.eligible_historical_sales?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span><small>{tx(`规则：已同意营销、消费前 25%、以计算时 UTC 时间为基准沉默 ${reactivationSignal.inactive_days} 天；截止 ${reactivationSignal.cutoff_date}。默认阈值需按购买周期核对。`, `Rule: marketing consent, top 25% spend, inactive for ${reactivationSignal.inactive_days} days as of the UTC calculation time; cutoff ${reactivationSignal.cutoff_date}. Check the default threshold against the purchase cycle.`)}</small><button className="button button-ghost" disabled={draftBusy} onClick={createReactivationDraft}>{tx("创建审核草案", "Create review draft")}</button></> : <><strong>{tx("尚不能计算真实客户机会", "A real customer opportunity cannot be calculated yet")}</strong>{reactivationSignal?.coverage && <small>{tx(`已导入 ${reactivationSignal.coverage.imported_orders} 笔订单；含匿名客户 ID ${reactivationSignal.coverage.identified_orders} 笔；已授予营销同意 ${reactivationSignal.coverage.consented_orders} 笔。`, `${reactivationSignal.coverage.imported_orders} orders imported; ${reactivationSignal.coverage.identified_orders} have anonymous customer IDs; ${reactivationSignal.coverage.consented_orders} have marketing consent.`)}</small>}<small>{tx("下一步：导入带有明确营销同意状态的匿名历史订单；不会接受邮箱、电话或名单。", "Next: import anonymized order history with explicit marketing consent. Emails, phone numbers, and customer lists are not accepted.")}</small><Link className="button button-ghost" href="/data">{tx("前往数据连接", "Go to data connections")}</Link></>}</article>{draftMessage && <p className="aggregate-draft-message">{draftMessage}</p>}</div></section>
    <section className="section-heading"><div><p className="eyebrow">Synthetic opportunity queue</p><h2>{tx("合成演示机会", "Synthetic demo opportunities")}</h2></div><span>{tx("仅用于演示排序与证据链", "For ranking and evidence-chain demonstration only")}</span></section>
    <section className="formula-card"><div><span className="eyebrow">{tx("如何排序", "Ranking method")}</span><strong>{english ? scoreFormulaEn : scoreFormula}</strong></div><p>{tx("综合分用于排队，不等于收入承诺。上线前需要核对数据覆盖、目标人群和实验成本。", "The score prioritizes work; it is not a revenue promise. Verify data coverage, audience, and experiment cost before launch.")}</p></section>
    <section className="opportunity-list">{opportunities.map((item, index) => {
      const copy = english ? opportunityCopyEn[item.id] : null;
      const evidence = (english ? evidenceByIdEn : evidenceById)[item.id as keyof typeof evidenceById];
      return <article key={item.id} className="card opportunity-card"><div className="opportunity-rank">0{index + 1}</div><div className="opportunity-main"><div className="card-kicker"><StatusBadge tone={item.priority === "P0" ? "danger" : "warning"}>{item.priority}</StatusBadge><span>{item.owner} · {approved === item.id ? tx("已批准样本草案", "Sample draft approved") : (copy?.status ?? item.status)}</span></div><h2>{copy?.title ?? item.title}</h2><p>{copy?.evidence ?? item.evidence}</p><div className="evidence-chips"><span>{tx("人群", "Audience")}: {copy?.segment ?? item.segment}</span><span>{tx("来源：客户分层 + 订单历史", "Source: customer segments + order history")}</span><span>{tx("置信度", "Confidence")}: {evidence.confidence}</span></div><button className="evidence-open" onClick={() => setSelected(item.id)}>{selected === item.id ? tx("收起样本证据链 ↑", "Hide sample evidence ↑") : tx("查看样本证据链 →", "View sample evidence →")}</button>{selected === item.id && <div className="evidence-panel"><div className="evidence-panel-head"><strong>{tx("为什么是这个样本机会？", "Why this sample opportunity?")}</strong><div><StatusBadge tone="accent">{evidence.freshness}</StatusBadge><StatusBadge tone="warning">{tx("估算值", "Estimate")}</StatusBadge></div></div><div className="signal-list">{evidence.signals.map((signal) => <span key={signal}>✓ {signal}</span>)}</div><div className="evidence-assumption"><strong>{tx("计算假设", "Assumption")}:</strong>{evidence.assumption}</div><div className="evidence-assumption evidence-guardrail"><strong>{tx("执行护栏", "Guardrail")}:</strong>{evidence.guardrail}</div><div className="evidence-actions"><button className="button button-primary" onClick={() => setApproved(item.id)}>{tx("批准进入样本活动草案", "Approve sample campaign draft")}</button><button className="button button-ghost" onClick={() => setSelected(null)}>{tx("暂不处理", "Not now")}</button></div></div>}</div><div className="opportunity-score"><span>{tx("综合分", "Score")}</span><strong>{item.score}</strong><small>{tx("30 天机会", "30-day opportunity")} {item.potential}</small><Link className="button button-ghost" href="/campaigns">{tx("创建样本草案", "Create sample draft")}</Link></div></article>;
    })}</section>
  </main>;
}
