"use client";

import { FormEvent, useState } from "react";
import { ArrowUp, X } from "@phosphor-icons/react";
import { useI18n } from "./I18n";

type Message = { role: "assistant" | "user"; content: string };

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");

function replyFor(question: string, english: boolean) {
  const normalized = question.toLowerCase();
  if (normalized.includes("流失") || normalized.includes("churn")) {
    return english ? "The current P0 opportunity is reactivating high-value customers at risk of churn. Evidence: no repeat purchase in 90 days and strong historical contribution. Validate uplift with a 200-person, 14-day email A/B test before scaling." : "当前 P0 机会是“挽回高价值流失风险客户”。证据是近 90 天未复购且历史贡献较高；建议先以 200 人、14 天观察窗的小规模 Email A/B 测试验证增量，而非直接全量触达。";
  }
  if (normalized.includes("roi") || normalized.includes("预算") || normalized.includes("收入")) {
    return english ? "The current $18.4k is a 30-day opportunity estimate, not realized revenue. Real ROI requires campaign cost, channel receipts, and control-group order revenue; demo values are not outcomes." : "当前的 $18.4k 是 30 天机会估算，不是已实现收入。真实 ROI 需要活动成本、渠道回执和对照组订单收入接入后才可计算；现阶段不能把模拟值当作结果。";
  }
  if (normalized.includes("数据") || normalized.includes("连接") || normalized.includes("shopify")) {
    return english ? "The demo workspace includes order and customer-history samples. Ad cost, channel receipts, refunds, and fulfillment cost are not connected. For a real merchant, connect Shopify orders, then CRM receipts, then ad cost." : "当前示例工作区已有订单与客户历史样本；广告成本、渠道回执、退款和履约成本还未接入。真实商家接入时，优先顺序是 Shopify 订单 → CRM 回执 → 广告成本。";
  }
  return english ? "Question noted. This version answers from the demo workspace: review evidence in Opportunities or turn an opportunity into a human-approved experiment draft in Campaigns. With the live Agent API, answers remain traceable to merchant-authorized data." : "我已记录你的问题。当前版本基于示例工作区回答：可以先查看 Opportunities 中的证据，或在 Campaigns 中把机会转为人工审批的实验草案。真实 Agent API 接入后，我会基于商家授权数据返回可追溯答案。";
}

export function CopilotPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { locale } = useI18n();
  const english = locale === "en";
  const tx = (zh: string, en: string) => english ? en : zh;
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [agentMode, setAgentMode] = useState<"demo" | "agent" | "unavailable">(API_BASE_URL ? "agent" : "demo");
  async function send(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || isLoading) return;
    setMessages((current) => [...current, { role: "user", content: question }]);
    setDraft("");
    if (!API_BASE_URL) {
      setMessages((current) => [...current, { role: "assistant", content: replyFor(question, english) }]);
      return;
    }
    setIsLoading(true);
    try {
      const history = messages.slice(-8).map(({ role, content }) => ({ role, content }));
      const response = await fetch(`${API_BASE_URL}/v1/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: question, history }) });
      const payload = await response.json();
      if (!response.ok || !payload.answer) throw new Error(payload.error || "Agent 请求失败");
      setAgentMode("agent");
      setMessages((current) => [...current, { role: "assistant", content: payload.answer }]);
    } catch {
      setAgentMode("unavailable");
      setMessages((current) => [...current, { role: "assistant", content: tx("实时 Agent 服务暂不可用。本次展示示例推理，不会把它当作真实商家结论。", "The live Agent service is unavailable. This response uses demo reasoning and is not treated as a real merchant conclusion.") + "\n\n" + replyFor(question, english) }]);
    } finally {
      setIsLoading(false);
    }
  }
  const visibleMessages = messages.length ? messages : [{ role: "assistant" as const, content: tx("我是 RevenueOps AI Co-pilot。我可以解释当前机会、活动实验和数据缺口；所有建议均需人工确认，不会自动触达客户。", "I am the RevenueOps AI Co-pilot. I can explain current opportunities, experiments, and data gaps. Every recommendation requires human approval; no customer is contacted automatically.") }];
  return <><button className={`copilot-scrim ${open ? "copilot-visible" : ""}`} onClick={onClose} aria-label={tx("关闭 AI 对话", "Close AI chat")} /><aside className={`copilot-panel ${open ? "copilot-open" : ""}`} aria-label="AI Co-pilot">
    <header className="copilot-header"><div><p className="eyebrow">AI Co-pilot</p><h2>{tx("运营智能问答", "Operations intelligence")}</h2><span><i /> {agentMode === "agent" ? tx("服务端 Agent · 人工可控", "Live Agent · Human controlled") : agentMode === "demo" ? tx("示例推理 · 人工可控", "Demo reasoning · Human controlled") : tx("服务暂不可用 · 已降级", "Service unavailable · Fallback active")}</span></div><button onClick={onClose} aria-label={tx("关闭", "Close")}><X size={18} aria-hidden /></button></header>
    <div className="copilot-context">{tx("当前上下文：Northstar Commerce · 示例工作区", "Context: Northstar Commerce · Demo workspace")}<br />{tx("数据范围：订单历史、客户分层、模拟实验结果", "Data scope: order history, customer segments, and simulated experiment results")}</div>
    <div className="copilot-messages">{visibleMessages.map((message, index) => <div key={`${message.role}-${index}`} className={`copilot-message ${message.role}`}><span>{message.role === "assistant" ? "AI" : tx("你", "You")}</span><p>{message.content}</p></div>)}</div>
    <div className="copilot-prompts"><button onClick={() => setDraft(tx("为什么要先做流失客户召回？", "Why prioritize churn reactivation?"))}>{tx("为什么先做流失召回？", "Why start with churn?")}</button><button onClick={() => setDraft(tx("当前 ROI 可以相信吗？", "Can I trust the current ROI?"))}>{tx("当前 ROI 可以相信吗？", "Can I trust this ROI?")}</button><button onClick={() => setDraft(tx("还缺哪些数据连接？", "Which data connections are missing?"))}>{tx("还缺哪些数据？", "What data is missing?")}</button></div>
    <form className="copilot-compose" onSubmit={send}><textarea aria-label={tx("运营问题", "Operations question")} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={tx("问一个运营问题…", "Ask an operations question…")} rows={2} /><button type="submit" disabled={isLoading}>{isLoading ? tx("分析中…", "Analyzing…") : <><span>{tx("发送", "Send")}</span><ArrowUp size={16} aria-hidden /></>}</button></form>
    <p className="copilot-disclaimer">{agentMode === "agent" ? tx("回答由服务端 Agent 生成，仍需人工复核后执行。", "Answers come from the live Agent and still require human review before action.") : tx("回答基于示例数据，不构成真实经营结论或自动执行指令。", "Answers use demo data and are not real business conclusions or automatic instructions.")}</p>
  </aside></>;
}
