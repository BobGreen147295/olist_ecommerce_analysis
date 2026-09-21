"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeading, StatusBadge } from "@/components/Ui";
import { useI18n } from "@/components/I18n";
import { campaigns } from "@/lib/demo-data";

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
type RealTask = {
  task_id: string;
  status: "draft" | "confirmed" | "rejected" | "completed";
  title?: string;
  audience?: string;
  channel?: string;
  budget?: number | null;
  market?: string;
  locale?: string;
  attribution_window_days?: number;
  expected_metric?: string;
  consent_basis?: string;
  source_diagnosis?: { source?: string };
  execution?: { status?: "ready_for_export" | "in_progress" | "result_recorded"; started_at?: string };
};

export default function CampaignsPage() {
  const { locale, t } = useI18n();
  const english = locale === "en";
  const tx = useCallback((zh: string, en: string) => english ? en : zh, [english]);
  const [stage, setStage] = useState<"draft" | "review" | "saved">("draft");
  const [showResults, setShowResults] = useState(false);
  const [realTask, setRealTask] = useState<RealTask | null>(null);
  const [realState, setRealState] = useState<"loading" | "signed-out" | "empty" | "ready">("loading");
  const [realMessage, setRealMessage] = useState("");
  const [form, setForm] = useState({ channel: "email", budget: "25", market: "US", locale: "en-US", attribution_window_days: "14" });

  useEffect(() => {
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token || !API_BASE_URL) { Promise.resolve().then(() => setRealState("signed-out")); return; }
    fetch(`${API_BASE_URL}/v1/tasks`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => response.ok ? response.json() : Promise.reject())
      .then((data) => {
        const task = (Array.isArray(data.tasks) ? data.tasks : []).find((item: RealTask) => item.source_diagnosis?.source === "consented_reactivation_aggregate") ?? null;
        setRealTask(task);
        setRealState(task ? "ready" : "empty");
        if (task) setForm({
          channel: task.channel && task.channel !== "待人工确认" ? task.channel : "email",
          budget: String(task.budget ?? 25), market: task.market ?? "US", locale: task.locale ?? "en-US",
          attribution_window_days: String(task.attribution_window_days ?? 14),
        });
      })
      .catch(() => { setRealState("empty"); setRealMessage(tx("暂时无法读取真实活动草案，请稍后重试。", "Unable to load the real campaign draft. Try again later.")); });
  }, [tx]);

  async function confirmRealTask() {
    if (!realTask || !API_BASE_URL) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token) { setRealState("signed-out"); return; }
    setRealMessage(tx("正在确认执行参数…", "Confirming execution parameters…"));
    const response = await fetch(`${API_BASE_URL}/v1/tasks/${realTask.task_id}/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ ...form, budget: Number(form.budget), attribution_window_days: Number(form.attribution_window_days) }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { setRealMessage(english ? "Unable to confirm campaign parameters. Try again later." : (data.error ?? "无法确认活动参数，请稍后重试。")); return; }
    setRealTask(data.task);
    setRealMessage(tx("已人工确认。执行包只包含活动规则，不包含客户邮箱、电话或名单。", "Human approval recorded. The execution package contains campaign rules only—no customer emails, phone numbers, or lists."));
  }

  async function downloadExecutionPackage() {
    if (!realTask || !API_BASE_URL) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token) { setRealState("signed-out"); return; }
    const response = await fetch(`${API_BASE_URL}/v1/tasks/${realTask.task_id}/execution-package.csv`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { const data = await response.json().catch(() => ({})); setRealMessage(english ? "Execution package export failed." : (data.error ?? "执行包导出失败。")); return; }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = `revenueops-${realTask.task_id}-execution-package.csv`; link.click();
    URL.revokeObjectURL(url);
    setRealMessage(tx("执行包已下载。请在商家自己的渠道平台完成最终受众选择与发送。", "Execution package downloaded. Complete final audience selection and sending in the merchant's own channel platform."));
  }

  async function startRealTask() {
    if (!realTask || !API_BASE_URL) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token) { setRealState("signed-out"); return; }
    setRealMessage(tx("正在记录人工启动…", "Recording the manual start…"));
    const response = await fetch(`${API_BASE_URL}/v1/tasks/${realTask.task_id}/start`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { setRealMessage(english ? "Unable to record the start. Try again later." : (data.error ?? "无法记录启动状态，请稍后重试。")); return; }
    setRealTask(data.task);
    setRealMessage(tx("已标记为实验中。这里只记录商家确认的启动时间，不会调用外部渠道或发送消息。", "Marked as running. This records the merchant-confirmed start time only; no external channel is called and no message is sent."));
  }

  return <main className="page-content">
    <PageHeading eyebrow="Campaign workspace" title={t("campaignsTitle")} description={t("campaignsDescription")} />

    <section className="card real-campaign-card" aria-labelledby="real-campaign-title">
      <div className="real-campaign-head"><div><p className="eyebrow">REAL PILOT WORKFLOW</p><h2 id="real-campaign-title">{tx("真实商家执行包", "Real merchant execution package")}</h2><p>{tx("只读取当前账号下通过营销同意门禁的再激活草案，不导出客户身份或联系方式。", "Only reactivation drafts that pass the marketing-consent gate are read. Customer identities and contact details are never exported.")}</p></div><StatusBadge tone={["confirmed", "completed"].includes(realTask?.status ?? "") ? "success" : "accent"}>{realTask?.status === "completed" ? tx("已完成", "Completed") : realTask?.execution?.status === "in_progress" ? tx("实验中", "Running") : realTask?.status === "confirmed" ? tx("已批准", "Approved") : tx("人工门禁", "Human gate")}</StatusBadge></div>
      {realState === "loading" && <div className="real-campaign-empty">{tx("正在读取真实活动草案…", "Loading the real campaign draft…")}</div>}
      {realState === "signed-out" && <div className="real-campaign-empty"><strong>{tx("需要登录当前试点账号", "Sign in to the current pilot account")}</strong><span>{tx("登录后才能读取该账号的真实机会草案。", "Sign in to read this account's real opportunity draft.")}</span><Link className="button button-ghost" href="/data">{tx("前往数据连接", "Go to data connections")}</Link></div>}
      {realState === "empty" && <div className="real-campaign-empty"><strong>{tx("还没有可执行的真实草案", "No executable real draft yet")}</strong><span>{realMessage || tx("先在机会页用已同意营销的匿名订单生成再激活草案。", "Create a reactivation draft from consented, anonymized orders on the opportunities page first.")}</span><Link className="button button-ghost" href="/opportunities">{tx("前往真实机会", "Go to real opportunities")}</Link></div>}
      {realState === "ready" && realTask && <>
        <div className="real-campaign-summary"><div><span>{tx("机会", "Opportunity")}</span><strong>{realTask.title}</strong></div><div><span>{tx("匿名受众定义", "Anonymous audience definition")}</span><strong>{realTask.audience}</strong></div><div><span>{tx("衡量指标", "Success metric")}</span><strong>{realTask.expected_metric}</strong></div></div>
        {realTask.status === "completed" ? <div className="real-campaign-empty"><strong>{tx("该执行包已完成结果回传", "Results have been submitted for this package")}</strong><span>{tx("真实归因结果已进入实验学习页。", "The real attribution result is available on the learning page.")}</span><Link className="button button-ghost" href="/learning">{tx("查看归因结果", "View attribution result")}</Link></div> : <>
        <div className="form-grid real-campaign-form">
          <label>{tx("执行渠道", "Execution channel")}<select value={form.channel} onChange={(event) => setForm({ ...form, channel: event.target.value })}><option value="email">Email</option><option value="sms">SMS</option><option value="whatsapp">WhatsApp</option><option value="manual">{tx("手工执行", "Manual execution")}</option></select></label>
          <label>{tx("试点预算", "Pilot budget")}<input type="number" min="0" step="1" value={form.budget} onChange={(event) => setForm({ ...form, budget: event.target.value })} /></label>
          <label>{tx("市场代码", "Market code")}<input maxLength={16} value={form.market} onChange={(event) => setForm({ ...form, market: event.target.value.toUpperCase() })} /></label>
          <label>{tx("语言代码", "Locale code")}<input maxLength={32} value={form.locale} onChange={(event) => setForm({ ...form, locale: event.target.value })} /></label>
          <label>{tx("归因窗口（天）", "Attribution window (days)")}<input type="number" min="1" max="90" value={form.attribution_window_days} onChange={(event) => setForm({ ...form, attribution_window_days: event.target.value })} /></label>
        </div>
        <div className="execution-package-note"><strong>{tx("安全边界", "Safety boundary")}</strong><span>{realTask.consent_basis}</span><span>{tx("确认只生成手工交接文件，不会调用外部渠道或自动发送。", "Confirmation generates a manual handoff file only; it does not call an external channel or send automatically.")}</span></div>
        <div className="button-row"><button className="button button-primary" onClick={confirmRealTask}>{realTask.status === "confirmed" ? tx("重新确认参数", "Reconfirm parameters") : tx("人工确认并生成执行包", "Approve and generate package")}</button>{realTask.status === "confirmed" && <button className="button button-ghost" onClick={downloadExecutionPackage}>{tx("下载安全执行包 CSV", "Download safe execution CSV")}</button>}{realTask.status === "confirmed" && realTask.execution?.status !== "in_progress" && <button className="button button-ghost" onClick={startRealTask}>{tx("标记试点已开始", "Mark pilot as started")}</button>}{realTask.execution?.status === "in_progress" && <Link className="button button-ghost" href="/learning">{tx("回传汇总结果", "Submit aggregate results")}</Link>}</div>
        {realMessage && <p className="inline-success" role="status">{realMessage}</p>}
        </>}
      </>}
    </section>

    <section className="section-heading"><div><p className="eyebrow">SYNTHETIC DEMO</p><h2>{tx("合成演示工作流", "Synthetic demo workflow")}</h2></div><button className="text-link" onClick={() => document.getElementById("campaign-builder")?.scrollIntoView({ behavior: "smooth" })}>{tx("查看演示草案 →", "View demo draft →")}</button></section>
    <section className="campaign-layout" id="campaign-builder"><article className="card campaign-builder"><div className="card-kicker"><StatusBadge tone={stage === "review" ? "accent" : "warning"}>{stage === "review" ? tx("审批中", "In review") : stage === "saved" ? tx("已保存草案", "Draft saved") : tx("待审批", "Awaiting approval")}</StatusBadge><span>{tx("来自合成机会 OPP-001", "From synthetic opportunity OPP-001")}</span></div><h2>{english ? "High-value customer reactivation test" : campaigns[0].name}</h2><p className="hero-copy">{english ? "Validate incremental repeat purchases with a controlled, human-approved experiment." : campaigns[0].objective}</p><div className="stepper"><div className="step active"><b>1</b><span>{tx("定义目标", "Define objective")}</span></div><div className="step active"><b>2</b><span>{tx("选择人群", "Select audience")}</span></div><div className="step active"><b>3</b><span>{tx("设置实验", "Configure test")}</span></div><div className={`step ${stage === "review" ? "active" : ""}`}><b>4</b><span>{tx("人工确认", "Human approval")}</span></div></div><div className="form-grid"><label>{tx("目标人群", "Target audience")}<div className="field-display">{english ? "High-value customers inactive for 90 days" : campaigns[0].audience}</div></label><label>{tx("触达渠道", "Channel")}<div className="field-display">{campaigns[0].channel}</div></label><label>{tx("活动预算", "Budget")}<div className="field-display">{campaigns[0].budget}</div></label><label>{tx("观察周期", "Observation window")}<div className="field-display">{tx("14 天", "14 days")}</div></label></div><div className="experiment-box"><div><strong>{tx("实验设计", "Experiment design")}</strong><span>{tx("建议随机分组，控制季节性干扰", "Randomize groups to limit seasonal bias")}</span></div><div className="experiment-grid"><div><small>{tx("实验组", "Treatment")}</small><b>{tx("100 人", "100 people")}</b></div><div><small>{tx("对照组", "Control")}</small><b>{tx("100 人", "100 people")}</b></div><div><small>{tx("停止条件", "Stop condition")}</small><b>ROI &lt; 0</b></div></div></div><div className="approval-note"><strong>{tx("审批前检查", "Pre-approval check")}</strong><span>{tx("确认人群规模、优惠成本、对照组与停止条件。审批仅生成执行清单，不代表系统已向客户发送内容。", "Confirm audience size, incentive cost, control group, and stop condition. Approval creates an execution checklist only; it does not send anything to customers.")}</span></div><div className="button-row"><button className="button button-primary" onClick={() => setStage("review")}>{stage === "review" ? tx("已提交审批 ✓", "Submitted ✓") : tx("提交人工审批", "Submit for human approval")}</button><button className="button button-ghost" onClick={() => setStage("saved")}>{stage === "saved" ? tx("已保存 ✓", "Saved ✓") : tx("保存为草案", "Save draft")}</button></div>{stage === "review" && <div className="inline-success">✓ {tx("已进入演示审批队列，不会触达客户。", "Added to the demo approval queue. No customer will be contacted.")}</div>}</article><aside className="card timeline-card"><p className="eyebrow">Approval trail</p><h3>{tx("操作留痕", "Audit trail")}</h3><ol className="timeline"><li><b>{tx("Agent 生成方案", "Agent creates proposal")}</b><span>{tx("包含人群证据、预算和预期指标", "Includes audience evidence, budget, and success metric")}</span></li><li><b>{tx("运营确认参数", "Operator confirms parameters")}</b><span>{stage === "review" ? tx("已提交 · 等待审批", "Submitted · Awaiting approval") : tx("待完成 · 需人工确认", "Pending · Human approval required")}</span></li><li><b>{tx("渠道平台执行", "Channel execution")}</b><span>{tx("未连接 · 不会自动发送", "Not connected · No automatic sending")}</span></li><li><b>{tx("归因与复盘", "Attribution and learning")}</b><span>{tx("对照组完成后计算", "Calculated after the control window closes")}</span></li></ol></aside></section>

    <section className="section-heading"><div><p className="eyebrow">DEMO CAMPAIGNS</p><h2>{tx("演示活动列表", "Demo campaign list")}</h2></div><button className="text-link" onClick={() => setShowResults(!showResults)}>{showResults ? tx("收起结果", "Hide results") : tx("查看演示结果", "View demo results")} →</button></section><section className="card table-card"><div className="table-head"><span>{tx("活动", "Campaign")}</span><span>{tx("渠道", "Channel")}</span><span>{tx("预算", "Budget")}</span><span>{tx("阶段", "Stage")}</span></div>{campaigns.map((item, index) => <div className="table-row campaign-row" key={item.id}><div><strong>{english ? `Demo campaign ${index + 1}` : item.name}</strong><small>{english ? "Synthetic workflow for product demonstration only" : item.objective}</small></div><span>{item.channel}</span><strong>{item.budget}</strong><StatusBadge tone={index === 0 && stage === "review" ? "accent" : item.state === "进行中" ? "success" : "warning"}>{index === 0 && stage === "review" ? tx("审批中", "In review") : english ? "Demo" : item.state}</StatusBadge></div>)}</section>{showResults && <section className="card results-preview"><div><p className="eyebrow">DEMO ATTRIBUTION</p><h2>{tx("结果回执预览", "Result preview")}</h2><p>{tx("以下为演示数据。正式版本需要接入渠道事件和订单回执后计算。", "These are demo values. Production attribution requires channel events and order receipts.")}</p></div><div className="result-metrics"><div><span>{tx("实验组转化", "Treatment conversion")}</span><strong>20.0%</strong></div><div><span>{tx("对照组转化", "Control conversion")}</span><strong>10.0%</strong></div><div><span>{tx("提升", "Uplift")}</span><strong className="metric-positive">+10.0pp</strong></div><div><span>ROI</span><strong>0.0%</strong></div></div></section>}
  </main>;
}
