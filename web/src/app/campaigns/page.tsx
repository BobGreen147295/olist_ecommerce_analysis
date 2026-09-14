"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeading, StatusBadge } from "@/components/Ui";
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
};

export default function CampaignsPage() {
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
      .catch(() => { setRealState("empty"); setRealMessage("暂时无法读取真实活动草案，请稍后重试。"); });
  }, []);

  async function confirmRealTask() {
    if (!realTask || !API_BASE_URL) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token) { setRealState("signed-out"); return; }
    setRealMessage("正在确认执行参数…");
    const response = await fetch(`${API_BASE_URL}/v1/tasks/${realTask.task_id}/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ ...form, budget: Number(form.budget), attribution_window_days: Number(form.attribution_window_days) }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { setRealMessage(data.error ?? "无法确认活动参数，请稍后重试。"); return; }
    setRealTask(data.task);
    setRealMessage("已人工确认。执行包只包含活动规则，不包含客户邮箱、电话或名单。");
  }

  async function downloadExecutionPackage() {
    if (!realTask || !API_BASE_URL) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token) { setRealState("signed-out"); return; }
    const response = await fetch(`${API_BASE_URL}/v1/tasks/${realTask.task_id}/execution-package.csv`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { const data = await response.json().catch(() => ({})); setRealMessage(data.error ?? "执行包导出失败。"); return; }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = `revenueops-${realTask.task_id}-execution-package.csv`; link.click();
    URL.revokeObjectURL(url);
    setRealMessage("执行包已下载。请在商家自己的渠道平台完成最终受众选择与发送。");
  }

  return <main className="page-content">
    <PageHeading eyebrow="Campaign workspace" title="活动工作台" description="将真实机会转换为可审核的执行包；任何客户触达仍由商家在自己的渠道平台最终确认。" />

    <section className="card real-campaign-card" aria-labelledby="real-campaign-title">
      <div className="real-campaign-head"><div><p className="eyebrow">REAL PILOT WORKFLOW</p><h2 id="real-campaign-title">真实商家执行包</h2><p>只读取当前账号下通过营销同意门禁的再激活草案，不导出客户身份或联系方式。</p></div><StatusBadge tone={realTask?.status === "confirmed" ? "success" : "accent"}>{realTask?.status === "confirmed" ? "已确认" : "人工门禁"}</StatusBadge></div>
      {realState === "loading" && <div className="real-campaign-empty">正在读取真实活动草案…</div>}
      {realState === "signed-out" && <div className="real-campaign-empty"><strong>需要登录当前试点账号</strong><span>登录后才能读取该账号的真实机会草案。</span><Link className="button button-ghost" href="/data">前往数据连接</Link></div>}
      {realState === "empty" && <div className="real-campaign-empty"><strong>还没有可执行的真实草案</strong><span>{realMessage || "先在机会页用已同意营销的匿名订单生成再激活草案。"}</span><Link className="button button-ghost" href="/opportunities">前往真实机会</Link></div>}
      {realState === "ready" && realTask && <>
        <div className="real-campaign-summary"><div><span>机会</span><strong>{realTask.title}</strong></div><div><span>匿名受众定义</span><strong>{realTask.audience}</strong></div><div><span>衡量指标</span><strong>{realTask.expected_metric}</strong></div></div>
        <div className="form-grid real-campaign-form">
          <label>执行渠道<select value={form.channel} onChange={(event) => setForm({ ...form, channel: event.target.value })}><option value="email">Email</option><option value="sms">SMS</option><option value="whatsapp">WhatsApp</option><option value="manual">手工执行</option></select></label>
          <label>试点预算<input type="number" min="0" step="1" value={form.budget} onChange={(event) => setForm({ ...form, budget: event.target.value })} /></label>
          <label>市场代码<input maxLength={16} value={form.market} onChange={(event) => setForm({ ...form, market: event.target.value.toUpperCase() })} /></label>
          <label>语言代码<input maxLength={32} value={form.locale} onChange={(event) => setForm({ ...form, locale: event.target.value })} /></label>
          <label>归因窗口（天）<input type="number" min="1" max="90" value={form.attribution_window_days} onChange={(event) => setForm({ ...form, attribution_window_days: event.target.value })} /></label>
        </div>
        <div className="execution-package-note"><strong>安全边界</strong><span>{realTask.consent_basis}</span><span>确认只生成手工交接文件，不会调用外部渠道或自动发送。</span></div>
        <div className="button-row"><button className="button button-primary" onClick={confirmRealTask}>{realTask.status === "confirmed" ? "重新确认参数" : "人工确认并生成执行包"}</button>{realTask.status === "confirmed" && <button className="button button-ghost" onClick={downloadExecutionPackage}>下载安全执行包 CSV</button>}</div>
        {realMessage && <p className="inline-success" role="status">{realMessage}</p>}
      </>}
    </section>

    <section className="section-heading"><div><p className="eyebrow">SYNTHETIC DEMO</p><h2>合成演示工作流</h2></div><button className="text-link" onClick={() => document.getElementById("campaign-builder")?.scrollIntoView({ behavior: "smooth" })}>查看演示草案 →</button></section>
    <section className="campaign-layout" id="campaign-builder"><article className="card campaign-builder"><div className="card-kicker"><StatusBadge tone={stage === "review" ? "accent" : "warning"}>{stage === "review" ? "审批中" : stage === "saved" ? "已保存草案" : "待审批"}</StatusBadge><span>来自合成机会 OPP-001</span></div><h2>{campaigns[0].name}</h2><p className="hero-copy">{campaigns[0].objective}</p><div className="stepper"><div className="step active"><b>1</b><span>定义目标</span></div><div className="step active"><b>2</b><span>选择人群</span></div><div className="step active"><b>3</b><span>设置实验</span></div><div className={`step ${stage === "review" ? "active" : ""}`}><b>4</b><span>人工确认</span></div></div><div className="form-grid"><label>目标人群<div className="field-display">{campaigns[0].audience}</div></label><label>触达渠道<div className="field-display">{campaigns[0].channel}</div></label><label>活动预算<div className="field-display">{campaigns[0].budget}</div></label><label>观察周期<div className="field-display">14 天</div></label></div><div className="experiment-box"><div><strong>实验设计</strong><span>建议随机分组，控制季节性干扰</span></div><div className="experiment-grid"><div><small>实验组</small><b>100 人</b></div><div><small>对照组</small><b>100 人</b></div><div><small>停止条件</small><b>ROI &lt; 0</b></div></div></div><div className="approval-note"><strong>审批前检查</strong><span>确认人群规模、优惠成本、对照组与停止条件。审批仅生成执行清单，不代表系统已向客户发送内容。</span></div><div className="button-row"><button className="button button-primary" onClick={() => setStage("review")}>{stage === "review" ? "已提交审批 ✓" : "提交人工审批"}</button><button className="button button-ghost" onClick={() => setStage("saved")}>{stage === "saved" ? "已保存 ✓" : "保存为草案"}</button></div>{stage === "review" && <div className="inline-success">✓ 已进入演示审批队列，不会触达客户。</div>}</article><aside className="card timeline-card"><p className="eyebrow">Approval trail</p><h3>操作留痕</h3><ol className="timeline"><li><b>Agent 生成方案</b><span>包含人群证据、预算和预期指标</span></li><li><b>运营确认参数</b><span>{stage === "review" ? "已提交 · 等待审批" : "待完成 · 需人工确认"}</span></li><li><b>渠道平台执行</b><span>未连接 · 不会自动发送</span></li><li><b>归因与复盘</b><span>对照组完成后计算</span></li></ol></aside></section>

    <section className="section-heading"><div><p className="eyebrow">DEMO CAMPAIGNS</p><h2>演示活动列表</h2></div><button className="text-link" onClick={() => setShowResults(!showResults)}>{showResults ? "收起结果" : "查看演示结果"} →</button></section><section className="card table-card"><div className="table-head"><span>活动</span><span>渠道</span><span>预算</span><span>阶段</span></div>{campaigns.map((item, index) => <div className="table-row campaign-row" key={item.id}><div><strong>{item.name}</strong><small>{item.objective}</small></div><span>{item.channel}</span><strong>{item.budget}</strong><StatusBadge tone={index === 0 && stage === "review" ? "accent" : item.state === "进行中" ? "success" : "warning"}>{index === 0 && stage === "review" ? "审批中" : item.state}</StatusBadge></div>)}</section>{showResults && <section className="card results-preview"><div><p className="eyebrow">DEMO ATTRIBUTION</p><h2>结果回执预览</h2><p>以下为演示数据。正式版本需要接入渠道事件和订单回执后计算。</p></div><div className="result-metrics"><div><span>实验组转化</span><strong>20.0%</strong></div><div><span>对照组转化</span><strong>10.0%</strong></div><div><span>提升</span><strong className="metric-positive">+10.0pp</strong></div><div><span>ROI</span><strong>0.0%</strong></div></div></section>}
  </main>;
}
