"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Metric, StatusBadge } from "@/components/Ui";
import { CrossBorderPulse } from "@/components/CrossBorderPulse";
import { DailyOperatingBrief } from "@/components/DailyOperatingBrief";
import { useI18n } from "@/components/I18n";
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

function deltaLabel(value: number | undefined, fallback: string, english: boolean) {
  if (value === undefined) return fallback;
  if (value === 0) return english ? "No change since last sync" : "较上次同步无变化";
  return english ? `${value > 0 ? "+" : ""}${value} since last sync` : `较上次同步 ${value > 0 ? "+" : ""}${value}`;
}

export default function OverviewPage() {
  const { locale, t } = useI18n();
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
  const english = locale === "en";
  const tx = (zh: string, en: string) => english ? en : zh;
  const demoOpportunityCopy: Record<string, { title: string; segment: string; status: string }> = {
    "opp-001": { title: "Reactivate high-value customers at risk of churn", segment: "No repeat purchase in 90 days · High historical value", status: "Awaiting approval" },
    "opp-002": { title: "Improve second purchase among new U.S. customers", segment: "First-time U.S. buyers · 14–30 days since first order", status: "Design needed" },
    "opp-003": { title: "Review margin erosion in high-discount orders", segment: "Repeat orders with discounts above 20%", status: "Needs validation" },
  };
  const money = (amount: number) => new Intl.NumberFormat(english ? "en-US" : "zh-CN", { style: "currency", currency, maximumFractionDigits: 2 }).format(amount);
  return <main className="page-content overview-page">
    <section className="command-hero">
      <div className="command-copy"><p className="eyebrow">{t("overviewKicker")}</p><h1><span>{t("overviewTitle1")}</span><span>{t("overviewTitle2")}</span></h1></div>
      <div className="command-brief"><p>{t("overviewSummary")}</p><div className="command-actions"><Link className="button button-primary" href="/campaigns">{t("createCampaign")} <span aria-hidden>↗</span></Link><span className="live-label"><i /> {summary ? t("shopifySynced") : t("waitingData")}</span></div></div>
    </section>
    <section className="notice-bar"><span className="notice-dot" />{summary ? isDevelopmentStore ? (english ? `Shopify development-store aggregates connected: ${shopify?.shop_domain}. Used only to validate sync; real opportunities and customer activation remain locked.` : `已接入 Shopify 开发店汇总数据：${shopify?.shop_domain}。仅用于同步验证，不会解锁真实机会或客户触达。`) : (english ? `Authorized Shopify aggregates connected: ${shopify?.shop_domain}. Counts below are real; the opportunity queue remains explicitly synthetic and is never mixed with them.` : `已接入 Shopify 授权汇总数据：${shopify?.shop_domain}。以下计数为真实数据；机会队列仍明确标为合成演示场景，二者不会混用。`) : (english ? "This demo workspace uses synthetic order scenarios and campaign results. No messages are sent to real customers." : `当前是${workspace.mode}：展示数据来自 ${workspace.dataSource}，不会向任何真实客户发送触达。`)}</section>
    {summary ? <section className="metrics-grid"><Metric label={t("shopifyOrders")} value={summary.orders.toLocaleString()} detail={t("authorizedCount")} trend={deltaLabel(deltas?.orders, t("firstBaseline"), english)} /><Metric label={t("shopifyCustomers")} value={summary.customers.toLocaleString()} detail={t("authorizedCount")} trend={deltaLabel(deltas?.customers, t("noIdentity"), english)} /><Metric label={t("shopifyProducts")} value={summary.products.toLocaleString()} detail={t("authorizedCount")} trend={deltaLabel(deltas?.products, t("readOnlySync"), english)} /><Metric label={t("inventoryItems")} value={summary.inventory_items.toLocaleString()} detail={t("inventoryLimit")} trend={deltaLabel(deltas?.inventory_items, summary.currency_code ? (english ? `Store currency ${summary.currency_code}` : `店铺币种 ${summary.currency_code}`) : (english ? "Currency unavailable" : "未返回币种"), english)} /></section> : <section className="metrics-grid"><Metric label={t("shopifyOrders")} value="—" detail={english ? "Authorized aggregate not read" : "尚未读取授权汇总"} trend={t("connectBaseline")} tone="muted" /><Metric label={t("netSales")} value="—" detail={t("noVerifiedData")} trend={t("noDemoFill")} tone="muted" /><Metric label={t("realOpportunities")} value="0" detail={t("modelingGate")} trend={t("connectData")} tone="muted" /><Metric label={t("measuredUplift")} value="—" detail={t("noRealExperiment")} trend={t("noRevenuePromise")} tone="muted" /></section>}
    <DailyOperatingBrief hasSummary={Boolean(summary)} readiness={shopify?.opportunity_readiness} opportunities={shopify?.store_opportunities ?? []} lastSyncedAt={shopify?.last_synced_at} />
    {trend && <section className="card api-card"><div><p className="eyebrow">SHOPIFY ORDER TREND</p><h2>{tx("已同步订单历史汇总", "Synced order-history aggregate")}</h2><p>{tx("订单", "Orders")} {trend.totals.orders} · {tx("销售额", "Gross sales")} {money(trend.totals.gross_sales)} · {tx("退款/订单调整额", "Refunds and adjustments")} {money(trend.totals.refunds)} · {tx("净销售额", "Net sales")} {money(trend.totals.net_sales)}. {tx("仅保存按日汇总。", "Only daily aggregates are stored.")}{trend.truncated ? tx("已达到读取上限，结果可能不完整。", "The read limit was reached; results may be incomplete.") : ""}</p><details className="trend-day-details"><summary>{tx(`查看按日汇总（${trend.days.length} 个有订单的日期）`, `View daily aggregates (${trend.days.length} active dates)`)}</summary><div className="trend-day-list">{trend.days.map((day) => <div className="trend-day-row" key={day.date}><time>{day.date}</time><span>{tx("订单", "Orders")} {day.orders}</span><span>{tx("销售额", "Gross")} {money(day.gross_sales)}</span><span>{tx("净销售额", "Net")} {money(day.net_sales)}</span></div>)}</div></details></div><span className="api-tag">{trend.orders_scanned} ORDERS AGGREGATED</span></section>}
    <CrossBorderPulse />
    <section className="section-heading"><div><p className="eyebrow">Synthetic opportunity queue</p><h2>{t("syntheticQueue")}</h2></div><Link href="/opportunities" className="text-link">{t("viewAllDemo")} →</Link></section>
    <section className="card table-card"><div className="table-head"><span>{t("opportunity")}</span><span>{t("owner")}</span><span>{t("estimatedOpportunity")}</span><span>{t("compositeScore")}</span><span>{t("status")}</span></div>{opportunities.map((item) => { const copy = english ? demoOpportunityCopy[item.id] : null; return <div className="table-row" key={item.id}><div><strong>{copy?.title ?? item.title}</strong><small>{copy?.segment ?? item.segment} · {t("demoLabel")}</small></div><span>{item.owner}</span><strong>{item.potential}</strong><strong>{item.score}</strong><StatusBadge tone={item.status === "待审批" ? "warning" : "neutral"}>{copy?.status ?? item.status}</StatusBadge></div>; })}</section>
  </main>;
}
