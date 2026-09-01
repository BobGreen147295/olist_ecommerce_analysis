"use client";

import { FormEvent, useState } from "react";

type Message = { role: "assistant" | "user"; content: string };

const welcome: Message = {
  role: "assistant",
  content: "我是 RevenueOps AI Co-pilot。我可以解释当前机会、活动实验和数据缺口；所有建议均需人工确认，不会自动触达客户。",
};

function replyFor(question: string) {
  const normalized = question.toLowerCase();
  if (normalized.includes("流失") || normalized.includes("churn")) {
    return "当前 P0 机会是“挽回高价值流失风险客户”。证据是近 90 天未复购且历史贡献较高；建议先以 200 人、14 天观察窗的小规模 Email A/B 测试验证增量，而非直接全量触达。";
  }
  if (normalized.includes("roi") || normalized.includes("预算") || normalized.includes("收入")) {
    return "当前的 $18.4k 是 30 天机会估算，不是已实现收入。真实 ROI 需要活动成本、渠道回执和对照组订单收入接入后才可计算；现阶段不能把模拟值当作结果。";
  }
  if (normalized.includes("数据") || normalized.includes("连接") || normalized.includes("shopify")) {
    return "当前示例工作区已有订单与客户历史样本；广告成本、渠道回执、退款和履约成本还未接入。真实商家接入时，优先顺序是 Shopify 订单 → CRM 回执 → 广告成本。";
  }
  return "我已记录你的问题。当前版本基于示例工作区回答：可以先查看 Opportunities 中的证据，或在 Campaigns 中把机会转为人工审批的实验草案。真实 Agent API 接入后，我会基于商家授权数据返回可追溯答案。";
}

export function CopilotPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([welcome]);
  const [draft, setDraft] = useState("");
  function send(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question) return;
    setMessages((current) => [...current, { role: "user", content: question }, { role: "assistant", content: replyFor(question) }]);
    setDraft("");
  }
  return <><button className={`copilot-scrim ${open ? "copilot-visible" : ""}`} onClick={onClose} aria-label="关闭 AI 对话" /><aside className={`copilot-panel ${open ? "copilot-open" : ""}`} aria-label="AI Co-pilot">
    <header className="copilot-header"><div><p className="eyebrow">AI Co-pilot</p><h2>运营智能问答</h2><span><i /> 示例推理 · 人工可控</span></div><button onClick={onClose} aria-label="关闭">×</button></header>
    <div className="copilot-context">当前上下文：Northstar Commerce · 示例工作区<br />数据范围：订单历史、客户分层、模拟实验结果</div>
    <div className="copilot-messages">{messages.map((message, index) => <div key={`${message.role}-${index}`} className={`copilot-message ${message.role}`}><span>{message.role === "assistant" ? "AI" : "你"}</span><p>{message.content}</p></div>)}</div>
    <div className="copilot-prompts"><button onClick={() => setDraft("为什么要先做流失客户召回？")}>为什么先做流失召回？</button><button onClick={() => setDraft("当前 ROI 可以相信吗？")}>当前 ROI 可以相信吗？</button><button onClick={() => setDraft("还缺哪些数据连接？")}>还缺哪些数据？</button></div>
    <form className="copilot-compose" onSubmit={send}><textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="问一个运营问题…" rows={2} /><button type="submit">发送 ↑</button></form>
    <p className="copilot-disclaimer">回答基于示例数据，不构成真实经营结论或自动执行指令。</p>
  </aside></>;
}
