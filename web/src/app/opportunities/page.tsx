"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeading, StatusBadge } from "@/components/Ui";
import { opportunities } from "@/lib/demo-data";

const scoreFormula = "综合分 = 影响规模 35% + 增量潜力 30% + 置信度 20% + 可执行性 15%";
const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
const SHOPIFY_SUMMARY_CACHE_KEY = "revenueops_shopify_summary_v1";
const evidenceById = {
  "opp-001": { confidence: "中等 · 72%", freshness: "样本数据 · 2026-08-31", signals: ["近 90 天未复购", "历史贡献高于分位数 P80", "最近一次购买间隔拉长 18 天"], assumption: "按过去 30 天同类客户的平均复购贡献估算，不代表承诺收入。", guardrail: "先做 200 人 A/B 测试，控制优惠成本。" },
  "opp-002": { confidence: "中等 · 68%", freshness: "样本数据 · 2026-08-31", signals: ["美国首购客户", "首单后 14–30 天沉默", "第二单转化低于基线"], assumption: "假设邮件触达率和客单价接近历史均值。", guardrail: "不自动发送，需先确认邮件名单和优惠政策。" },
  "opp-003": { confidence: "偏低 · 55%", freshness: "样本数据 · 2026-08-31", signals: ["折扣高于 20%", "订单量上升", "净收入未完成归因"], assumption: "未接入广告成本、履约和退款数据，净利润判断不完整。", guardrail: "接入成本数据前，只作为待验证假设。" },
} as const;

export default function OpportunitiesPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [approved, setApproved] = useState<string | null>(null);
  const [shopifySynced, setShopifySynced] = useState(false);
  const [shopifyDevelopmentStore, setShopifyDevelopmentStore] = useState(false);
  useEffect(() => {
    try {
      const cached = JSON.parse(localStorage.getItem(SHOPIFY_SUMMARY_CACHE_KEY) ?? "null");
      setShopifySynced(Boolean(cached?.connection?.summary && Date.now() - cached.cached_at < 86_400_000));
      setShopifyDevelopmentStore(Boolean(cached?.connection?.summary?.is_development_store));
    } catch { /* Ignore malformed browser-only cache. */ }
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token || !API_BASE_URL) return;
    fetch(`${API_BASE_URL}/v1/integrations/shopify/status`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => {
        const connection = data?.connection;
        setShopifySynced(Boolean(connection?.summary));
        setShopifyDevelopmentStore(Boolean(connection?.summary?.is_development_store));
        if (connection?.summary) localStorage.setItem(SHOPIFY_SUMMARY_CACHE_KEY, JSON.stringify({ connection, cached_at: Date.now() }));
      })
      .catch(() => setShopifySynced(false));
  }, []);
  return <main className="page-content">
    <PageHeading eyebrow="Olist sample opportunity queue" title="Olist 样本机会" description="这些示例仅用于演示发现、量化和排序流程，不构成真实商家结论。" />
    {shopifySynced && <section className="notice-bar"><span className="notice-dot" />{shopifyDevelopmentStore ? "Shopify 开发店汇总数据已接入：仅用于验证同步，不能创建真实机会或客户触达。" : "Shopify 真实汇总数据已接入；本页下列机会仍是 Olist 样本，不能创建真实客户触达。"}</section>}
    <section className="formula-card"><div><span className="eyebrow">如何排序</span><strong>{scoreFormula}</strong></div><p>综合分用于排队，不等于收入承诺。上线前需要核对数据覆盖、目标人群和实验成本。</p></section>
    <section className="opportunity-list">{opportunities.map((item, index) => <article key={item.id} className="card opportunity-card"><div className="opportunity-rank">0{index + 1}</div><div className="opportunity-main"><div className="card-kicker"><StatusBadge tone={item.priority === "P0" ? "danger" : "warning"}>{item.priority}</StatusBadge><span>{item.owner} · {approved === item.id ? "已批准样本草案" : item.status}</span></div><h2>{item.title}</h2><p>{item.evidence}</p><div className="evidence-chips"><span>人群：{item.segment}</span><span>来源：客户分层 + 订单历史</span><span>置信度：{evidenceById[item.id as keyof typeof evidenceById].confidence}</span></div><button className="evidence-open" onClick={() => setSelected(item.id)}>{selected === item.id ? "收起样本证据链 ↑" : "查看样本证据链 →"}</button>{selected === item.id && <div className="evidence-panel"><div className="evidence-panel-head"><strong>为什么是这个样本机会？</strong><div><StatusBadge tone="accent">{evidenceById[item.id as keyof typeof evidenceById].freshness}</StatusBadge><StatusBadge tone="warning">估算值</StatusBadge></div></div><div className="signal-list">{evidenceById[item.id as keyof typeof evidenceById].signals.map((signal) => <span key={signal}>✓ {signal}</span>)}</div><div className="evidence-assumption"><strong>计算假设：</strong>{evidenceById[item.id as keyof typeof evidenceById].assumption}</div><div className="evidence-assumption evidence-guardrail"><strong>执行护栏：</strong>{evidenceById[item.id as keyof typeof evidenceById].guardrail}</div><div className="evidence-actions"><button className="button button-primary" onClick={() => setApproved(item.id)}>批准进入样本活动草案</button><button className="button button-ghost" onClick={() => setSelected(null)}>暂不处理</button></div></div>}</div><div className="opportunity-score"><span>综合分</span><strong>{item.score}</strong><small>30 天机会 {item.potential}</small><Link className="button button-ghost" href="/campaigns">创建样本草案</Link></div></article>)}</section>
  </main>;
}
