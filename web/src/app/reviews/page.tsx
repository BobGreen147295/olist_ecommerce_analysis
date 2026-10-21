"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { PageHeading } from "@/components/Ui";
import { OrderComparisonCard } from "@/components/OrderComparisonCard";
import { useI18n } from "@/components/I18n";
import { reviewMarkdown, type CommerceReview, type ReviewSnapshot, type ReviewTask, type ReviewAI } from "@/lib/commerce-review";
import "./reviews.css";

const api = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "") ?? "";
const sessionKey = "revenueops_access_token";
const nextWeek = () => new Date(Date.now() + 7 * 86400_000).toISOString().slice(0, 10);

export default function ReviewsPage() {
  const { locale } = useI18n(), english = locale === "en";
  const tx = (zh: string, en: string) => english ? en : zh;
  const [session, setSession] = useState<string | null | undefined>();
  useEffect(() => {
    const sync = () => setSession(sessionStorage.getItem(sessionKey));
    sync(); window.addEventListener("focus", sync); document.addEventListener("visibilitychange", sync);
    return () => { window.removeEventListener("focus", sync); document.removeEventListener("visibilitychange", sync); };
  }, []);
  return <main className="page-content review-workspace">
    <PageHeading eyebrow="Evidence to review" title={tx("经营复盘", "Operating reviews")} description={tx("核对自己的订单证据，参考行业资料，选择一项检查并回看结果。", "Check your order evidence, consult research, choose one check and review the outcome.")}/>
    {session === undefined ? <p role="status">{tx("正在核对登录…", "Checking sign-in…")}</p> : !session ? <section className="card"><h2>{tx("使用商家账户进入复盘", "Sign in to review your business")}</h2><p>{tx("复盘仅对当前账户可见。请在数据连接页登录。", "Reviews are private to your account. Sign in on Data connections.")}</p><Link className="button button-primary" href="/data">{tx("前往登录", "Sign in")}</Link></section>
      : <ReviewWorkspace key={session} session={session} onSessionChange={setSession}/>}
  </main>;
}

// Remount on session changes: old account evidence, drafts and pending UI state cannot carry over.
function ReviewWorkspace({ session, onSessionChange }: { session: string; onSessionChange: (value: string | null) => void }) {
  const { locale } = useI18n(), english = locale === "en";
  const tx = (zh: string, en: string) => english ? en : zh;
  const [reviews, setReviews] = useState<CommerceReview[]>([]), [selectedId, select] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<ReviewSnapshot | null>(null), [ai, setAI] = useState<ReviewAI | null>(null);
  const [taskId, selectTask] = useState<string | null>(null);
  const [notice, setNotice] = useState(""), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true);
  const [connection, setConnection] = useState<"checking" | "ready" | "unavailable">("checking"), [aiAccess, setAIAccess] = useState(false);
  const [connectionVersion, reconnect] = useState(0), historyLoaded = useRef(false);
  const [decision, setDecision] = useState<CommerceReview["input"]["decision"]>("investigate");
  const [note, setNote] = useState(""), [nextAction, setNextAction] = useState(""), [dueOn, setDueOn] = useState(nextWeek), [outcome, setOutcome] = useState("");
  const [platform, setPlatform] = useState("综合"), [question, setQuestion] = useState("请核对两期订单变化的解释边界，结合相关资料列出待验证假设与下一步检查。");
  const [actionDue, setActionDue] = useState(nextWeek), [refresh, setRefresh] = useState(0);
  const submission = useRef<{ key: string; id: string } | null>(null);
  const selected = reviews.find(r => r.id === selectedId), evidence = selected?.snapshot ?? snapshot;
  const tasks = ai?.tasks ?? [], task = tasks.find(t => t.id === taskId) ?? tasks[0];
  const generating = tasks.some(t => t.status === "queued" || t.status === "running");
  const changed = task?.sourceChecks?.some(s => s.state !== "available");

  const request = useCallback(async <T,>(path: string, method = "GET", payload?: unknown, signal?: AbortSignal): Promise<T> => {
    if (!session || !api) throw new Error("请先登录并确认复盘服务已配置 / Sign in and configure the review service");
    const current = () => sessionStorage.getItem(sessionKey) === session;
    if (!current()) { onSessionChange(sessionStorage.getItem(sessionKey)); throw new Error("账户已切换 / Account changed"); }
    let response: Response;
    const timeout = AbortSignal.timeout(method === "GET" ? 90_000 : 20_000);
    try { response = await fetch(api + "/v1/commerce" + path, { method, cache: "no-store", signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session}` }, ...(payload === undefined ? {} : { body: JSON.stringify(payload) }) }); }
    catch { throw new Error("连接未完成，请重试；已保存的复盘不会因此删除 / Connection failed. Retry; saved reviews are retained."); }
    const data = response.status === 204 ? {} : await response.json().catch(() => null);
    if (!current()) { onSessionChange(sessionStorage.getItem(sessionKey)); throw new Error("账户已切换 / Account changed"); }
    if (response.status === 401) { sessionStorage.removeItem(sessionKey); onSessionChange(null); throw new Error("登录已失效 / Session expired"); }
    if (!response.ok || !data) throw new Error(data?.error || "复盘服务暂不可用，请重试或前往数据页核对订单 / Review unavailable. Retry or check orders on Data connections.");
    return data as T;
  }, [session, onSessionChange]);
  useEffect(() => {
    if (!session || !api) return;
    const controller = new AbortController();
    request<{ configured: boolean; aiEnabled: boolean; reviews: CommerceReview[] }>("", "GET", undefined, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (!result.configured || !Array.isArray(result.reviews)) throw new Error("复盘服务尚未就绪 / Review service is not ready");
      setReviews(result.reviews); setConnection("ready"); setAIAccess(result.aiEnabled === true);
      if (!historyLoaded.current) { select(result.reviews[0]?.id ?? null); setOutcome(result.reviews[0]?.outcome ?? ""); historyLoaded.current = true; }
      setNotice("");
    }).catch(e => { if (!controller.signal.aborted) { setConnection("unavailable"); setNotice(String(e.message)); } }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request, session, connectionVersion]);
  useEffect(() => {
    if (!selectedId || !session) return;
    const controller = new AbortController(); let active = false;
    const load = async () => {
      if (document.hidden || active) return;
      active = true;
      try { const result = await request<ReviewAI>(`/reviews/${selectedId}/assistant`, "GET", undefined, controller.signal); if (!controller.signal.aborted) setAI(result); }
      catch (e) { if (!controller.signal.aborted) setNotice((e as Error).message); }
      finally { active = false; }
    };
    void load(); const timer = generating ? setInterval(() => void load(), 2500) : null;
    return () => { controller.abort(); if (timer) clearInterval(timer); };
  }, [selectedId, session, generating, request, refresh]);

  async function act(fn: () => Promise<void>) {
    if (busy) return; setBusy(true); setNotice("");
    try { await fn(); } catch (e) { setNotice((e as Error).message); } finally { setBusy(false); }
  }
  const update = (review: CommerceReview) => setReviews(items => [review, ...items.filter(r => r.id !== review.id)].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 30));
  const choose = (review: CommerceReview | null) => { select(review?.id ?? null); setOutcome(review?.outcome ?? ""); setAI(null); selectTask(null); };
  function requestId(input: unknown) {
    const key = JSON.stringify(input);
    if (submission.current?.key !== key) submission.current = { key, id: crypto.randomUUID() };
    return submission.current.id;
  }
  async function check() {
    choose(null); setSnapshot(null);
    const result = await request<{ snapshot: ReviewSnapshot }>("/report"); setSnapshot(result.snapshot);
    setNotice(tx("已核对当前账户汇总，未调用模型。", "Account aggregates checked without calling a model."));
  }
  async function save(e: FormEvent) {
    e.preventDefault(); if (!snapshot) return;
    const input = { snapshotId: snapshot.id, decision, note, nextAction: decision === "no_action" ? "" : nextAction, dueOn: decision === "no_action" ? null : dueOn };
    await act(async () => { const review = await request<CommerceReview>("/reviews", "POST", { ...input, requestId: requestId(input) }); update(review); choose(review); submission.current = null; });
  }
  async function generate(e: FormEvent) {
    e.preventDefault(); if (!selected) return;
    const input = { question, platform, reviewId: selected.id };
    await act(async () => { const result = await request<ReviewTask>(`/reviews/${selected.id}/assistant`, "POST", { question, platform, requestId: requestId(input) });
      setAI({ enabled: ai!.enabled, tasks: [result, ...tasks.filter(t => t.id !== result.id)].slice(0, 5) }); selectTask(result.id); submission.current = null; });
  }
  function download() {
    if (!selected) return;
    const url = URL.createObjectURL(new Blob([reviewMarkdown(selected)], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `commerce-review-${selected.id.slice(0, 8)}.md`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const output = task?.output;
  if (!api) return <p role="status">{tx("复盘服务尚未配置，请联系维护者。", "Review service is not configured. Contact support.")}</p>;
  return <>
      <section className="review-connection" aria-label={tx("复盘服务连接", "Review service connection")} aria-busy={loading}>
        <div><h2>{loading ? tx("正在检查复盘连接", "Checking review connection") : connection === "ready" ? tx("复盘连接已确认", "Review connection checked") : tx("复盘连接尚未就绪", "Review connection is not ready")}</h2>
          <p>{loading ? tx("首次连接可能稍慢，最多等待 90 秒。只读取连接与记录，不调用模型。", "The first connection can take longer. We wait up to 90 seconds, reading history without calling a model.") : connection === "ready" ? aiAccess ? tx("当前账户可保存复盘，AI 解读需主动生成。", "Your account can save reviews. AI runs only when requested.") : tx("当前账户可进行人工复盘，AI 解读尚未开放。", "Manual reviews are available. AI is not enabled for this account.") : tx("可能尚未配置或暂时断开。已保存记录不会因此删除，也不能据此判断没有历史复盘。", "The service may be unconfigured or temporarily unreachable. Saved reviews remain; this does not mean your history is empty.")}</p></div>
        <div className="review-buttons"><button className="button button-ghost" disabled={busy || loading} onClick={() => { setLoading(true); reconnect(n => n + 1); }}>{tx("重新检查连接", "Recheck connection")}</button><Link className="button button-ghost" href="/data">{tx("前往数据页核对订单", "Check orders on Data connections")}</Link></div>
      </section>
      <div className="review-toolbar"><p>{tx("核对和保存不消耗 AI 额度；不会同步店铺或执行营销。", "Checks and manual records use no AI quota and do not sync or change your store.")}</p><button className="button button-primary" disabled={busy || loading || connection !== "ready"} onClick={() => void act(check)}>{busy ? tx("处理中…", "Working…") : tx("核对订单数据", "Check order data")}</button></div>
      <p role="status" className="review-notice">{notice || (loading ? tx("正在读取复盘记录…", "Loading reviews…") : tx("先核对订单，或选择一条历史复盘。", "Check orders or select a saved review."))}</p>
      {(connection === "ready" || evidence) && <div className="review-layout"><section className="card review-evidence" aria-label={tx("订单证据", "Order evidence")}>
        {selected && <p className="review-help">{tx("已保存的证据快照，当前查看不会重新查询订单。", "Saved evidence snapshot; viewing does not re-query orders.")}</p>}
        {evidence ? <><OrderComparisonCard report={evidence.report} fallback={tx("报告结构异常，请重新核对。", "Invalid report; check again.")} english={english}/>{/synthetic|合成|演示/i.test(evidence.report.source ?? "") && <strong className="review-synthetic">{tx("合成数据 · 仅供流程验收", "Synthetic data · Workflow validation only")}</strong>}</> : <><h2>{tx("先取得一份可核对的报告", "Start with evidence you can check")}</h2><p>{tx("使用当前账户的已关联来源；覆盖不足和快照过期会明确提示。", "Uses your account's current source. Incomplete coverage and stale snapshots are identified.")}</p><Link href="/data">{tx("检查数据连接", "Check data connections")}</Link></>}
      </section><aside className="card review-record">
        {selected ? <><h2>{tx("判断与复盘", "Judgment and review")}</h2><p>{selected.input.note}</p><p>{tx("原始下一步", "Original next step")}: {selected.input.nextAction || tx("暂不行动", "No action")}</p><p>{selected.input.dueOn}</p>
          {selected.adoptedAction && <section className="review-adopted" aria-label={tx("已采纳检查", "Adopted check")}><h3>{tx("已采纳检查 · 待验证", "Adopted check · Unverified")}</h3><p>{selected.adoptedAction.task}</p><p>{selected.adoptedAction.measure}</p><p>{tx("计划复盘", "Review date")}: {selected.adoptedAction.dueOn}</p></section>}
          <form onSubmit={e => { e.preventDefault(); void act(async () => { update(await request<CommerceReview>(`/reviews/${selected.id}`, "PATCH", { outcome, version: selected.version })); setNotice(tx("人工观察已保存，不代表独立验证或因果效果。", "Manual observation saved; it does not establish causality.")); }); }}>
            <label>{tx("实际观察结果", "Actual observation")}<textarea required minLength={3} maxLength={2000} value={outcome} onChange={e => setOutcome(e.target.value)} rows={4}/></label><button className="button button-primary" disabled={busy}>{tx("保存复盘结果", "Save observation")}</button>
          </form><div className="review-buttons"><button className="button button-ghost" onClick={download}>{tx("导出复盘", "Export review")}</button><button className="button button-ghost" disabled={busy} onClick={() => { if (window.confirm(tx("删除复盘和关联解读？已发送模型请求与回执不会撤回，订单源数据不受影响。", "Delete review and linked AI tasks? Sent model requests and receipts remain; source orders stay intact."))) void act(async () => { await request(`/reviews/${selected.id}`, "DELETE"); setReviews(items => items.filter(r => r.id !== selected.id)); choose(null); }); }}>{tx("删除记录", "Delete record")}</button></div></>
          : <form onSubmit={e => void save(e)}><h2>{tx("记录下一步", "Record the next check")}</h2><label>{tx("本次决定", "Decision")}<select value={decision} onChange={e => setDecision(e.target.value as typeof decision)}><option value="investigate">{tx("进一步核实", "Investigate")}</option><option value="need_data">{tx("补充数据", "Get more data")}</option><option value="no_action">{tx("暂不行动", "No action")}</option></select></label>
            <label>{tx("你的判断或待核实问题", "Your judgment or question")}<textarea required minLength={3} maxLength={1200} rows={3} value={note} onChange={e => setNote(e.target.value)}/></label>
            {decision !== "no_action" && <><label>{tx("下一步检查", "Next check")}<textarea required minLength={3} maxLength={600} rows={3} value={nextAction} onChange={e => setNextAction(e.target.value)}/></label><label>{tx("计划复盘日期", "Review date")}<input required type="date" value={dueOn} onChange={e => setDueOn(e.target.value)}/></label></>}
            <button className="button button-primary" disabled={busy || connection !== "ready" || snapshot?.report.status !== "ready"}>{tx("保存复盘记录", "Save review")}</button><p className="review-help">{tx("仅填写汇总判断，不填客户身份或密钥。人工保存不会发送至模型。", "Use aggregate notes only. No customer identities or keys. Saving does not call a model.")}</p></form>}
      </aside></div>}
      {selected && <section className="card review-ai" aria-label={tx("AI 证据解读", "AI evidence interpretation")}><h2>{tx("把证据变成下一步检查", "Turn evidence into the next check")}</h2>
        <form onSubmit={e => void generate(e)}><label>{tx("行业资料范围", "Research scope")}<select value={platform} onChange={e => setPlatform(e.target.value)}>{["综合", "Shopify", "Amazon", "TikTok Shop", "eBay", "Walmart"].map(p => <option key={p}>{p}</option>)}</select></label><label>{tx("本次解读问题", "Question")}<textarea required minLength={3} maxLength={2000} rows={3} value={question} onChange={e => setQuestion(e.target.value)}/></label>
          <p className="review-help">{tx("主动生成会把汇总、原始判断和问题发送至已连接模型并消耗额度。完整解读保留七天，采纳行动随复盘保留至删除；回执可能含回答并长期保留。关键词检索的行业资料不证明本店变化原因，日期与市场适用性需核实。", "Generation sends aggregates, original judgment and your question to the connected model and uses quota. Full AI tasks are retained for seven days; adopted checks remain with the review until deleted. Receipts may retain answers longer. Keyword-matched research does not prove store-level causes; check dates and market applicability.")}</p>
          <button className="button button-primary" disabled={busy || generating || connection !== "ready" || !aiAccess || !ai?.enabled}>{generating ? tx("后台正在解读…", "Interpreting…") : tx("生成 AI 证据解读", "Generate AI interpretation")}</button><button type="button" className="button button-ghost" onClick={() => setRefresh(n => n + 1)}>{tx("刷新解读记录", "Refresh saved tasks")}</button>
          {ai && (!ai.enabled || !aiAccess) && <p>{tx("当前账户未开放 AI 解读，人工复盘仍可使用。", "AI is not enabled for this account. Manual reviews remain available.")}</p>}
        </form>
        {task && <div className="review-ai-result"><p className="review-help">{task.input.question}</p>{generating && <p role="status">{tx("任务已保存，刷新不会重复生成。", "Task saved; reload does not generate again.")}</p>}
          {task.status === "failed" && <div role="alert"><p>{task.error}</p>{!task.error?.includes("引用资料") && <button className="button button-ghost" disabled={busy || connection !== "ready" || !aiAccess || !ai?.enabled} onClick={() => void act(async () => { await request(`/reviews/${selected.id}/assistant/${task.id}/retry`, "POST", {}); setRefresh(n => n + 1); })}>{tx("重试本次解读", "Retry this task")}</button>}<p className="review-help">{tx("重试复用有效回执；无效回答或结果不明的恢复仍可能消耗额度。", "Valid receipts are reused; invalid or unknown outcomes can require another budgeted attempt.")}</p></div>}
          {output && <><h3>{output.answer.title}</h3><p className="review-conclusion">{output.answer.conclusion}</p><p className="review-help">{output.model} · {output.generatedAt} · {tx("模型解读，固定事实以订单报告为准。", "AI interpretation; use the fixed report to verify facts.")}</p>
            {changed && <p role="alert" className="review-warning">{tx("引用资料已变化或撤回，请重新解读再考虑采纳。", "Sources changed or were withdrawn. Generate and check again before adopting.")}</p>}
            {output.answer.findings.map((f, i) => <section className="review-finding" key={i}><span>{f.basis === "order_snapshot" ? tx("订单证据解读 · AI", "Order evidence interpretation · AI") : f.basis === "public_source" ? tx("行业资料解读 · AI", "Research interpretation · AI") : tx("待验证假设", "Unverified hypothesis")}</span><h4>{f.title}</h4><p>{f.detail}</p>{f.evidenceIds.map(id => <a key={id} href={`#review-source-${id}`}>{tx("资料", "Source")} {id}</a>)}</section>)}
            <details open={!selected.adoptedAction}><summary>{tx("待验证行动建议", "Suggested checks to validate")} · {output.answer.actions.length}</summary>
              {!selected.adoptedAction && <label>{tx("行动复盘日期", "Check review date")}<input type="date" required value={actionDue} onChange={e => setActionDue(e.target.value)}/></label>}
              {output.answer.actions.map((a, i) => <section className="review-action" key={i}><span>{a.priority} · {a.timing}</span><h4>{a.task}</h4><p>{a.reason}</p><p><strong>{tx("验收与停止条件", "Acceptance and stop conditions")}: </strong>{a.measure}</p><button className="button button-ghost" disabled={busy || !!selected.adoptedAction || !!changed || !actionDue} onClick={() => void act(async () => { update(await request<CommerceReview>(`/reviews/${selected.id}/actions`, "POST", { taskId: task.id, actionIndex: i, dueOn: actionDue, version: selected.version })); setNotice(tx("已采纳一项待验证检查，原始判断已保留。", "One unverified check adopted. Original judgment retained.")); })}>{selected.adoptedAction ? tx("本条复盘已有采纳行动", "A check is already adopted") : tx("采纳这项检查", "Adopt this check")}</button></section>)}
            </details><h3>{tx("还缺什么数据", "Missing evidence")}</h3><ul>{output.answer.missingData.map((s, i) => <li key={i}>{s}</li>)}</ul><details><summary>{tx("边界与风险", "Risks and boundaries")}</summary><ul>{output.answer.risks.map((s, i) => <li key={i}>{s}</li>)}</ul></details>
            <h3>{tx("行业资料", "Research sources")} · {output.sources.length}</h3>{!output.sources.length && <p>{tx("没有匹配的站内资料；不代表最新平台政策。", "No matching site sources; this is not a statement of current policy.")}</p>}{output.sources.map(s => <div className="review-source" id={`review-source-${s.id}`} key={s.id}><span>{s.id}. {s.source} · {s.publishedAt || tx("原文日期未知", "Publication date unknown")}</span>{task.sourceChecks?.some(c => c.id === s.id && c.state !== "available") ? <p>{s.title} — {tx("已变化或不可用", "Changed or unavailable")}</p> : <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a>}<p className="review-help">{tx("历史订单与行业消息的时间、适用范围需分别核对，相关不代表因果。", "Check source dates and applicability against order periods. Correlation does not establish causation.")}</p></div>)}</>}
        </div>}
        {tasks.length > 1 && <label>{tx("本条复盘的近期解读", "Recent interpretations")}<select value={task?.id || ""} onChange={e => selectTask(e.target.value)}>{tasks.map(t => <option key={t.id} value={t.id}>{t.status} · {t.input.question}</option>)}</select></label>}
      </section>}
      <section className="review-history"><h2>{tx("复盘记录", "Review history")}</h2><p className="review-help">{tx("仅当前账户可见，保留至删除；这里的检查不会创建或执行营销活动。", "Private to your account until deleted. These checks do not create or run campaigns.")}</p>{connection === "ready" && !reviews.length && <p>{tx("当前账户还没有复盘记录。先核对订单，再保存第一次判断。", "No saved reviews for this account. Check orders and record your first judgment.")}</p>}{reviews.map(r => <button className="card" key={r.id} aria-pressed={r.id === selectedId} disabled={busy} onClick={() => choose(r)}><span>{r.completedAt ? tx("已回填", "Observation saved") : tx("待复盘", "Awaiting review")}{r.adoptedAction?.dueOn || r.input.dueOn ? ` / ${r.adoptedAction?.dueOn || r.input.dueOn}` : ""}</span><strong>{r.input.note}</strong></button>)}</section>
    </>;
}
