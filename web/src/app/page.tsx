"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Metric, StatusBadge } from "@/components/Ui";
import { CrossBorderPulse } from "@/components/CrossBorderPulse";
import { DailyOperatingBrief } from "@/components/DailyOperatingBrief";
import { opportunities, workspace } from "@/lib/demo-data";

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
const SHOPIFY_SUMMARY_CACHE_KEY = "revenueops_shopify_summary_v1";
type ShopifySummary = { orders: number; customers: number; products: number; inventory_items: number; currency_code: string | null; is_development_store?: boolean };
type ShopifyDeltas = { orders: number; customers: number; products: number; inventory_items: number };
type ShopifyOrderTrend = { window_days: number; orders_scanned: number; truncated: boolean; days: { date: string; orders: number; gross_sales: number; net_sales: number; refunds: number }[]; totals: { orders: number; gross_sales: number; net_sales: number; refunds: number }; refund_attribution: string };
type ShopifySummaryWithTrend = ShopifySummary & { order_trend?: ShopifyOrderTrend };
type ShopifyOpportunityReadiness = { state: "trend_required" | "development_store" | "insufficient_data" | "ready"; message: string };
type StoreOpportunity = { id: string; title: string; summary: string; evidence: Record<string, number> };
type ShopifyConnection = { shop_domain: string; status: "connected" | "synced"; last_synced_at: string | null; summary: ShopifySummaryWithTrend | null; comparison?: { previous_synced_at: string; deltas: ShopifyDeltas } | null; opportunity_readiness?: ShopifyOpportunityReadiness; store_opportunities?: StoreOpportunity[] };

function deltaLabel(value: number | undefined, fallback: string) {
  if (value === undefined) return fallback;
  if (value === 0) return "较上次同步无变化";
  return `较上次同步 ${value > 0 ? "+" : ""}${value}`;
}

export default function OverviewPage() {
  const [shopify, setShopify] = useState<ShopifyConnection | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const cached = JSON.parse(localStorage.getItem(SHOPIFY_SUMMARY_CACHE_KEY) ?? "null");
      return cached?.connection?.summary && Date.now() - cached.cached_at < 86_400_000 ? cached.connection : null;
    } catch { return null; }
  });
  useEffect(() => {
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
  const currency = summary?.currency_code ?? "USD";
  const money = (amount: number) => new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(amount);
  return <main className="page-content overview-page">
    <section className="command-hero">
      <div className="command-copy"><p className="eyebrow">Revenue intelligence</p><h1><span>今天，先做</span><span>这件事。</span></h1></div>
      <div className="command-brief"><p>从 Shopify 聚合数据中识别优先级，生成可审批的实验方案，并跟踪真实增量。</p><div className="command-actions"><Link className="button button-primary" href="/campaigns">新建活动 <span aria-hidden>↗</span></Link><span className="live-label"><i /> {summary ? "Shopify 已同步" : "等待真实数据"}</span></div></div>
    </section>
    <section className="notice-bar"><span className="notice-dot" />{summary ? isDevelopmentStore ? `已接入 Shopify 开发店汇总数据：${shopify?.shop_domain}。仅用于同步验证，不会解锁真实机会或客户触达。` : `已接入 Shopify 授权汇总数据：${shopify?.shop_domain}。以下计数为真实数据；机会队列仍明确标为合成演示场景，二者不会混用。` : `当前是${workspace.mode}：展示数据来自 ${workspace.dataSource}，不会向任何真实客户发送触达。`}</section>
    {summary ? <section className="metrics-grid"><Metric label="Shopify 订单" value={summary.orders.toLocaleString()} detail="授权店铺聚合数量" trend={deltaLabel(deltas?.orders, "首次同步基线")} /><Metric label="Shopify 客户" value={summary.customers.toLocaleString()} detail="授权店铺聚合数量" trend={deltaLabel(deltas?.customers, "不保存客户身份信息")} /><Metric label="Shopify 产品" value={summary.products.toLocaleString()} detail="授权店铺聚合数量" trend={deltaLabel(deltas?.products, "只读汇总同步")} /><Metric label="库存项" value={summary.inventory_items.toLocaleString()} detail="最多读取 250 个库存项" trend={deltaLabel(deltas?.inventory_items, summary.currency_code ? `店铺币种 ${summary.currency_code}` : "未返回币种")} /></section> : <section className="metrics-grid"><Metric label="Shopify 订单" value="—" detail="尚未读取授权汇总" trend="连接店铺后生成基线" tone="muted" /><Metric label="净销售额" value="—" detail="尚无可验证的真实数据" trend="不使用演示数据填充" tone="muted" /><Metric label="真实机会" value="0" detail="尚未达到建模门槛" trend="待完成数据连接" tone="muted" /><Metric label="已测量增量" value="—" detail="尚未运行真实实验" trend="不做收入承诺" tone="muted" /></section>}
    <DailyOperatingBrief hasSummary={Boolean(summary)} readiness={shopify?.opportunity_readiness} opportunities={shopify?.store_opportunities ?? []} lastSyncedAt={shopify?.last_synced_at} />
    {trend && <section className="card api-card"><div><p className="eyebrow">SHOPIFY ORDER TREND</p><h2>已同步订单历史汇总</h2><p>订单 {trend.totals.orders} 笔 · 销售额 {money(trend.totals.gross_sales)} · 退款/订单调整额 {money(trend.totals.refunds)} · 净销售额 {money(trend.totals.net_sales)}。仅保存按日汇总，{trend.refund_attribution}{trend.truncated ? "；已达到读取上限，结果可能不完整" : "。"}</p><details className="trend-day-details"><summary>查看按日汇总（{trend.days.length} 个有订单的日期）</summary><div className="trend-day-list">{trend.days.map((day) => <div className="trend-day-row" key={day.date}><time>{day.date}</time><span>订单 {day.orders} 笔</span><span>销售额 {money(day.gross_sales)}</span><span>净销售额 {money(day.net_sales)}</span></div>)}</div></details></div><span className="api-tag">{trend.orders_scanned} ORDERS AGGREGATED</span></section>}
    <CrossBorderPulse />
    <section className="section-heading"><div><p className="eyebrow">Synthetic opportunity queue</p><h2>合成演示机会队列</h2></div><Link href="/opportunities" className="text-link">查看全部演示机会 →</Link></section>
    <section className="card table-card"><div className="table-head"><span>机会</span><span>负责人</span><span>预计机会</span><span>综合分</span><span>状态</span></div>{opportunities.map((item) => <div className="table-row" key={item.id}><div><strong>{item.title}</strong><small>{item.segment} · 合成演示</small></div><span>{item.owner}</span><strong>{item.potential}</strong><strong>{item.score}</strong><StatusBadge tone={item.status === "待审批" ? "warning" : "neutral"}>{item.status}</StatusBadge></div>)}</section>
  </main>;
}
