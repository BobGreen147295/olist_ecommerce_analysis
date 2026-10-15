"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
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
  const sessionToken = useRef<string | null>(null);
  useEffect(() => {
    const token = sessionStorage.getItem("revenueops_access_token");
    if (token !== sessionToken.current) {
      sessionToken.current = token;
      setMessages([]);
    }
  }, [open]);
  const [agentMode, setAgentMode] = useState<"demo" | "agent" | "knowledge" | "unavailable">(API_BASE_URL ? "agent" : "demo");
  async function send(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || isLoading) return;
    const token = sessionStorage.getItem("revenueops_access_token");
    const sameSession = token === sessionToken.current;
    const history = sameSession ? messages.slice(-8).map(({ role, content }) => ({ role, content })) : [];
    sessionToken.current = token;
    setMessages((current) => [...(sameSession ? current : []), { role: "user", content: question }]);
    setDraft("");
    if (!API_BASE_URL) {
      setMessages((current) => [...current, { role: "assistant", content: replyFor(question, english) }]);
      return;
    }
    if (!token) {
      setMessages((current) => [...current, { role: "assistant", content: tx("请先在数据连接页登录，再使用真实数据问答。", "Sign in on the Data page before asking about real data.") }]);
      return;
    }
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/v1/chat`, { method: "POST", signal: AbortSignal.timeout(120000), headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ message: question, history }) });
      const payload = await response.json();
      if (sessionStorage.getItem("revenueops_access_token") !== token) return;
      if (response.status === 401 || response.status === 429) {
        if (response.status === 401) {
          sessionStorage.removeItem("revenueops_access_token");
          sessionToken.current = null;
        }
        setMessages((current) => [...(response.status === 401 ? [] : current), { role: "assistant", content: response.status === 401
          ? tx("登录已失效，请在数据连接页重新登录。", "Your session expired. Sign in again on the Data page.")
          : tx("AI 调用已达上限，请稍后再试；本次未调用模型。", "AI call limit reached. Try again later; no model call was made.") }]);
        return;
      }
      if (!response.ok || !payload.answer) throw new Error(payload.error || "Agent 请求失败");
      setAgentMode(payload.error || payload.mode === "unavailable" ? "unavailable" : payload.mode === "knowledge" ? "knowledge" : "agent");
      setMessages((current) => [...current, { role: "assistant", content: payload.answer }]);
    } catch {
      if (sessionStorage.getItem("revenueops_access_token") !== token) return;
      setAgentMode("unavailable");
      setMessages((current) => [...current, { role: "assistant", content: tx("实时 Agent 服务暂不可用，请稍后重试。本次没有生成经营结论。", "The live Agent is unavailable. Try again later; no business conclusion was generated.") }]);
    } finally {
      setIsLoading(false);
    }
  }
  const visibleMessages = messages.length ? messages : [{ role: "assistant" as const, content: tx("我是 RevenueOps AI Co-pilot。我可以解释当前机会、活动实验和数据缺口；所有建议均需人工确认，不会自动触达客户。", "I am the RevenueOps AI Co-pilot. I can explain current opportunities, experiments, and data gaps. Every recommendation requires human approval; no customer is contacted automatically.") }];
  return <><button className={`copilot-scrim ${open ? "copilot-visible" : ""}`} onClick={onClose} aria-label={tx("关闭 AI 对话", "Close AI chat")} /><aside className={`copilot-panel ${open ? "copilot-open" : ""}`} aria-label="AI Co-pilot">
    <header className="copilot-header"><div><p className="eyebrow">AI Co-pilot</p><h2>{tx("运营智能问答", "Operations intelligence")}</h2><span><i /> {agentMode === "agent" ? tx("服务端 Agent · 人工可控", "Live Agent · Human controlled") : agentMode === "knowledge" ? tx("方法说明 · 非店铺分析", "Method guidance · Not store analysis") : agentMode === "demo" ? tx("示例推理 · 人工可控", "Demo reasoning · Human controlled") : tx("本次分析未完成 · 未自动执行", "Analysis incomplete · No automatic action")}</span></div><button onClick={onClose} aria-label={tx("关闭", "Close")}><X size={18} aria-hidden /></button></header>
    <div className="copilot-context">{API_BASE_URL ? tx("仅查询当前登录账户已授权的数据；未登录时不会读取经营数据。", "Only the signed-in account's authorized data is queried; no business data is read when signed out.") : tx("当前为合成演示，不读取真实店铺数据。", "Synthetic demo only. No real store data is read.")}<br />{tx("可用范围以服务端实际返回为准；缺少数据时不补造经营结论。", "Available scope depends on server results. Missing data is not replaced with invented conclusions.")}</div>
    <div className="copilot-messages">{visibleMessages.map((message, index) => <div key={`${message.role}-${index}`} className={`copilot-message ${message.role}`}><span>{message.role === "assistant" ? "AI" : tx("你", "You")}</span><p>{message.content}</p></div>)}</div>
    <div className="copilot-prompts"><button onClick={() => setDraft(tx("为什么要先做流失客户召回？", "Why prioritize churn reactivation?"))}>{tx("为什么先做流失召回？", "Why start with churn?")}</button><button onClick={() => setDraft(tx("当前 ROI 可以相信吗？", "Can I trust the current ROI?"))}>{tx("当前 ROI 可以相信吗？", "Can I trust this ROI?")}</button><button onClick={() => setDraft(tx("还缺哪些数据连接？", "Which data connections are missing?"))}>{tx("还缺哪些数据？", "What data is missing?")}</button></div>
    <form className="copilot-compose" onSubmit={send}><textarea aria-label={tx("运营问题", "Operations question")} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={tx("问一个运营问题…", "Ask an operations question…")} rows={2} /><button type="submit" disabled={isLoading}>{isLoading ? tx("分析中…", "Analyzing…") : <><span>{tx("发送", "Send")}</span><ArrowUp size={16} aria-hidden /></>}</button></form>
    <p className="copilot-disclaimer">{agentMode === "agent" ? tx("回答由服务端 Agent 生成，仍需人工复核后执行。", "Answers come from the live Agent and still require human review before action.") : agentMode === "knowledge" ? tx("这是审核过的方法说明，未调用模型，也未核实店铺经营数据。", "Reviewed method guidance. No model call or store-data verification was performed.") : agentMode === "unavailable" ? tx("本次分析未完成，没有自动执行；方法资料不代表店铺结论。", "Analysis was not completed; no automatic action was taken. Method references are not store conclusions.") : tx("回答基于示例数据，不构成真实经营结论或自动执行指令。", "Answers use demo data and are not real business conclusions or automatic instructions.")}</p>
  </aside></>;
}
