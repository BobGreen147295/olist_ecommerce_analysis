"use client";

import { useState } from "react";
import { PageHeading, StatusBadge } from "@/components/Ui";

const sources = [["订单与客户历史","已接入","Olist 历史样本","仅用于产品验证"],["活动执行回执","未接入","Klaviyo / Braze","接入后才可判断真实触达"],["广告消耗与转化","未接入","Meta / Google Ads","接入后才可计算渠道 ROI"],["履约与退款成本","未接入","Shopify / ERP","接入后才可计算净利润"]];

const connectors = [
  { name: "Shopify", type: "订单、客户、产品、退款", detail: "优先接入 · 形成收入与复购基线", icon: "S" },
  { name: "Klaviyo", type: "邮件事件、订阅、触达回执", detail: "第二阶段 · 验证活动是否真的生效", icon: "K" },
  { name: "Meta Ads", type: "广告消耗、投放、转化", detail: "第三阶段 · 计算渠道级增量 ROI", icon: "M" },
];

export default function DataPage() {
  const [requested, setRequested] = useState<string | null>(null);
  return <main className="page-content"><PageHeading eyebrow="Data foundation" title="数据连接" description="跨境商家的真实价值来自可授权的数据连接，而不是替代商家保存或猜测业务数据。" action={<button className="button button-primary" onClick={() => document.getElementById("connectors")?.scrollIntoView({ behavior: "smooth" })}>申请连接器</button>} />
  <section className="notice-bar"><span className="notice-dot" />当前运行在示例工作区。连接真实店铺前，应由商家授权并明确数据范围、用途与保留周期。</section>
  <section className="data-layout"><article className="card"><div className="card-kicker"><span>CONNECTION STATUS</span><StatusBadge tone="neutral">DEMO WORKSPACE</StatusBadge></div><h2>数据域覆盖</h2><div className="data-table">{sources.map(([name, state, source, note]) => <div className="data-row" key={name}><div><strong>{name}</strong><small>{note}</small></div><StatusBadge tone={state === "已接入" ? "success" : "neutral"}>{state}</StatusBadge><span>{source}</span></div>)}</div></article><aside className="card data-contract"><p className="eyebrow">Principles</p><h3>连接原则</h3><ol><li>商家在自己的渠道平台授权。</li><li>最小化获取字段与访问范围。</li><li>明确数据更新频率和失效机制。</li><li>每一项 Agent 建议都可追溯数据来源。</li></ol></aside></section>
  <section className="card api-card"><div><p className="eyebrow">NEXT MILESTONE</p><h2>从样本到真实商家数据</h2><p>第一阶段优先接入 Shopify 订单、客户、退款与产品数据；第二阶段接入 Klaviyo 或 Braze 的事件回执；最后才接入广告成本做 ROI 归因。</p></div><span className="api-tag">API CONTRACT READY</span></section>
  <section className="card connector-card" id="connectors"><div className="card-heading"><div><p className="eyebrow">AUTHORIZED SOURCES</p><h2>选择一个真实数据源</h2><p>申请只记录你的意向，不会自动读取或发送任何数据。</p></div><StatusBadge tone="accent">商家可控</StatusBadge></div><div className="connector-grid">{connectors.map((connector) => { const isRequested = requested === connector.name; return <div className="connector-item" key={connector.name}><div className="connector-top"><span className="connector-logo">{connector.icon}</span><div><strong>{connector.name}</strong><small>{connector.type}</small></div></div><p>{connector.detail}</p><button className={`connector-button ${isRequested ? "connector-button-done" : ""}`} onClick={() => setRequested(isRequested ? null : connector.name)}>{isRequested ? "已记录申请 ✓" : "申请接入"}</button></div>; })}</div>{requested && <div className="connector-confirmation"><span>✓</span><div><strong>{requested} 接入意向已记录</strong><p>下一步应由商家完成 OAuth 授权，并确认字段范围、同步频率和数据保留期限。</p></div></div>}</section>
</main>; }
