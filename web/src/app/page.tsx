"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Metric, PageHeading, StatusBadge } from "@/components/Ui";
import { opportunities, workspace } from "@/lib/demo-data";

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
const SHOPIFY_SUMMARY_CACHE_KEY = "revenueops_shopify_summary_v1";
type ShopifySummary = { orders: number; customers: number; products: number; inventory_items: number; currency_code: string | null; is_development_store?: boolean };
type ShopifyDeltas = { orders: number; customers: number; products: number; inventory_items: number };
type ShopifyOrderTrend = { window_days: number; orders_scanned: number; truncated: boolean; days: { date: string; orders: number; gross_sales: number; net_sales: number; refunds: number }[]; totals: { orders: number; gross_sales: number; net_sales: number; refunds: number }; refund_attribution: string };
type ShopifySummaryWithTrend = ShopifySummary & { order_trend?: ShopifyOrderTrend };
type ShopifyConnection = { shop_domain: string; status: "connected" | "synced"; last_synced_at: string | null; summary: ShopifySummaryWithTrend | null; comparison?: { previous_synced_at: string; deltas: ShopifyDeltas } | null };

function deltaLabel(value: number | undefined, fallback: string) {
  if (value === undefined) return fallback;
  if (value === 0) return "较上次同步无变化";
  return `较上次同步 ${value > 0 ? "+" : ""}${value}`;
}

export default function OverviewPage() {
  const top = opportunities[0];
  const [shopify, setShopify] = useState<ShopifyConnection | null>(null);
  useEffect(() => {
    try {
      const cached = JSON.parse(localStorage.getItem(SHOPIFY_SUMMARY_CACHE_KEY) ?? "null");
      if (cached?.connection?.summary && Date.now() - cached.cached_at < 86_400_000) setShopify(cached.connection);
    } catch { /* Ignore malformed browser-only cache. */ }
    const token = sessionStorage.getItem("revenueops_access_token");
    if (!token || !API_BASE_URL) return;
    fetch(`${API_BASE_URL}/v1/integrations/shopify/status`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => {
        if (response.status === 401) sessionStorage.removeItem("revenueops_access_token");
        return response.ok ? response.json() : null;
      })
      .then((data) => {
        const connection = data?.connection;
        if (connection?.summary) {
          setShopify(connection);
          localStorage.setItem(SHOPIFY_SUMMARY_CACHE_KEY, JSON.stringify({ connection, cached_at: Date.now() }));
        }
      })
      .catch(() => undefined);
  }, []);
  const summary = shopify?.summary;
  const deltas = shopify?.comparison?.deltas;
  const trend = summary?.order_trend;
  const isDevelopmentStore = Boolean(summary?.is_development_store);
  const realOpportunityReady = Boolean(!isDevelopmentStore && trend && trend.orders_scanned >= 20 && trend.days.length >= 3);
  const realOpportunityGate = isDevelopmentStore ? "当前连接的是 Shopify 开发店：数据仅用于验证同步，不能解锁真实机会建模或客户触达。" : !trend ? "尚未同步订单趋势，不能评估真实机会。" : realOpportunityReady ? "已满足基础数据门槛；确认分析口径后可进入真实机会建模。" : `当前仅 ${trend.orders_scanned} 笔订单、${trend.days.length} 个有订单的日期；达到 20 笔订单且覆盖 3 个日期后，才可进入真实机会建模。`;
  const currency = summary?.currency_code ?? "USD";
  const money = (amount: number) => new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(amount);
  return <main className="page-content">
    <PageHeading eyebrow="Revenue intelligence" title="今天先做哪件事？" description="把数据异常、可执行机会和实验结果放在一个可审计的运营工作台里。" action={<Link className="button button-primary" href="/campaigns">新建活动</Link>} />
    <section className="notice-bar"><span className="notice-dot" />{summary ? isDevelopmentStore ? `已接入 Shopify 开发店汇总数据：${shopify?.shop_domain}。仅用于同步验证，不会解锁真实机会或客户触达。` : `已接入 Shopify 授权汇总数据：${shopify?.shop_domain}。以下计数为真实数据；机会队列仍明确标为 Olist 样本，二者不会混用。` : `当前是${workspace.mode}：展示数据来自 ${workspace.dataSource}，不会向任何真实客户发送触达。`}</section>
    {summary ? <section className="metrics-grid"><Metric label="Shopify 订单" value={summary.orders.toLocaleString()} detail="授权店铺聚合数量" trend={deltaLabel(deltas?.orders, "首次同步基线")} /><Metric label="Shopify 客户" value={summary.customers.toLocaleString()} detail="授权店铺聚合数量" trend={deltaLabel(deltas?.customers, "不保存客户身份信息")} /><Metric label="Shopify 产品" value={summary.products.toLocaleString()} detail="授权店铺聚合数量" trend={deltaLabel(deltas?.products, "只读汇总同步")} /><Metric label="库存项" value={summary.inventory_items.toLocaleString()} detail="最多读取 250 个库存项" trend={deltaLabel(deltas?.inventory_items, summary.currency_code ? `店铺币种 ${summary.currency_code}` : "未返回币种")} /></section> : <section className="metrics-grid"><Metric label="可验证收入机会" value="$38.1k" detail="未来 30 天估算上限" trend="3 个待处理机会" /><Metric label="待人工审批" value="2" detail="Agent 已生成完整方案" trend="需确认人群与预算" /><Metric label="进行中的实验" value="1" detail="新客第二单激励" trend="第 4 / 14 天" /><Metric label="已验证净增收入" value="$6.8k" detail="最近 30 天（示例）" trend="基于对照组归因" /></section>}
    {trend && <section className="card api-card"><div><p className="eyebrow">SHOPIFY ORDER TREND</p><h2>近 {trend.window_days} 天订单汇总</h2><p>订单 {trend.totals.orders} 笔 · 销售额 {money(trend.totals.gross_sales)} · 退款/订单调整额 {money(trend.totals.refunds)} · 净销售额 {money(trend.totals.net_sales)}。仅保存按日汇总，{trend.refund_attribution}{trend.truncated ? "；已达到读取上限，结果可能不完整" : "。"}</p><details className="trend-day-details"><summary>查看按日汇总（{trend.days.length} 个有订单的日期）</summary><div className="trend-day-list">{trend.days.map((day) => <div className="trend-day-row" key={day.date}><time>{day.date}</time><span>订单 {day.orders} 笔</span><span>销售额 {money(day.gross_sales)}</span><span>净销售额 {money(day.net_sales)}</span></div>)}</div></details></div><span className="api-tag">{trend.orders_scanned} ORDERS AGGREGATED</span></section>}
    <section className="content-grid overview-grid"><article className="card opportunity-hero"><div className="card-kicker"><StatusBadge tone="warning">{top.priority} 优先级</StatusBadge><span>Olist 样本建议 · 需要你确认</span></div><h2>{top.title}</h2><p className="hero-copy">{top.evidence}。先用小预算测试，确认增量后再扩大人群与渠道。</p><div className="signal-row"><div><span>目标人群</span><strong>{top.segment}</strong></div><div><span>30 天机会</span><strong>{top.potential}</strong></div><div><span>综合分</span><strong>{top.score}/100</strong></div></div><div className="button-row"><Link className="button button-primary" href="/campaigns">查看样本活动草案</Link><Link className="button button-ghost" href="/opportunities">查看样本证据</Link></div></article><article className="card readiness-card"><div className="card-kicker"><span>DATA READINESS</span><StatusBadge tone={realOpportunityReady ? "success" : "warning"}>{realOpportunityReady ? "MODEL READY" : "DATA GATE"}</StatusBadge></div><h3>真实机会建模状态</h3><div className="readiness-score">{summary ? "74" : "68"}<span>/100</span></div><p>{realOpportunityGate}</p><Link href="/data" className="text-link">查看数据连接清单 →</Link></article></section>
    <section className="section-heading"><div><p className="eyebrow">Olist sample opportunity queue</p><h2>Olist 样本机会队列</h2></div><Link href="/opportunities" className="text-link">查看全部样本机会 →</Link></section>
    <section className="card table-card"><div className="table-head"><span>机会</span><span>负责人</span><span>预计机会</span><span>综合分</span><span>状态</span></div>{opportunities.map((item) => <div className="table-row" key={item.id}><div><strong>{item.title}</strong><small>{item.segment} · Olist 样本</small></div><span>{item.owner}</span><strong>{item.potential}</strong><strong>{item.score}</strong><StatusBadge tone={item.status === "待审批" ? "warning" : "neutral"}>{item.status}</StatusBadge></div>)}</section>
  </main>;
}
