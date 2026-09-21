"use client";

import { ArrowRight, CheckCircle, Database, GlobeHemisphereWest, Warning } from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useI18n } from "./I18n";

type StoreOpportunity = { id: string; title: string; summary: string; evidence: Record<string, number> };
type Readiness = { state: "trend_required" | "development_store" | "insufficient_data" | "ready"; message: string };
type PublicSignal = { id: string; title: string; summary: string; action: string; source: string; href: string; date: string; update_mode?: string };
type BriefItem = {
  id: string;
  eyebrow: string;
  title: string;
  impact: string;
  evidence: string;
  action: string;
  href: string;
  kind: "signal" | "gate" | "watch" | "clear";
  external?: boolean;
};

const evidenceLabels: Record<string, string> = {
  recent_net_sales: "近 7 天净销售额",
  previous_net_sales: "前 7 天净销售额",
  gross_sales: "销售额",
  refunds: "退款与订单调整额",
  refund_rate: "退款率",
  order_count: "订单数",
};

const evidenceLabelsEn: Record<string, string> = {
  recent_net_sales: "Recent 7-day net sales", previous_net_sales: "Previous 7-day net sales", gross_sales: "Gross sales", refunds: "Refunds and adjustments", refund_rate: "Refund rate", order_count: "Orders",
};

function formatEvidence(evidence: Record<string, number>, english: boolean) {
  return Object.entries(evidence)
    .map(([key, value]) => `${(english ? evidenceLabelsEn : evidenceLabels)[key] ?? key.replaceAll("_", " ")} ${value}`)
    .join(" / ");
}

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");

export function DailyOperatingBrief({
  hasSummary,
  readiness,
  opportunities,
  lastSyncedAt,
}: {
  hasSummary: boolean;
  readiness?: Readiness;
  opportunities: StoreOpportunity[];
  lastSyncedAt?: string | null;
}) {
  const { locale } = useI18n();
  const english = locale === "en";
  const tx = useCallback((zh: string, en: string) => english ? en : zh, [english]);
  const [publicSignal, setPublicSignal] = useState<PublicSignal | null>(null);
  const [publicFeedLive, setPublicFeedLive] = useState(false);

  useEffect(() => {
    if (!API_BASE_URL) return;
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/v1/public-intelligence`, { signal: controller.signal })
      .then(async (response) => response.ok ? response.json() : null)
      .then((payload) => {
        const signals = Array.isArray(payload?.signals) ? payload.signals as PublicSignal[] : [];
        const official = signals.find((signal) => signal.update_mode === "official_feed");
        if (official) setPublicSignal(official);
        setPublicFeedLive(payload?.feed_status === "live");
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const items = useMemo(() => {
    const next: BriefItem[] = opportunities.slice(0, 2).map((opportunity) => ({
      id: opportunity.id,
      eyebrow: tx("店铺级信号", "Store-level signal"),
      title: english && opportunity.id === "net_sales_decline" ? "Net sales decline needs review" : english && opportunity.id === "refund_pressure" ? "Refund pressure needs review" : opportunity.title,
      impact: english && opportunity.id === "net_sales_decline" ? "Recent net sales are below the previous comparison window." : english && opportunity.id === "refund_pressure" ? "Refunds and order adjustments have crossed the review threshold." : opportunity.summary,
      evidence: `${tx("来源", "Source")}: Shopify ${tx("按日汇总", "daily aggregates")} · ${tx("证据", "Evidence")}: ${formatEvidence(opportunity.evidence, english)}`,
      action: tx("核实业务原因并生成待审核草案", "Verify the business cause and create a review draft"),
      href: "/opportunities",
      kind: "signal" as const,
    }));

    if (!next.length) {
      if (!hasSummary) {
        next.push({ id: "connect-data", eyebrow: tx("数据准备", "Data readiness"), title: tx("连接真实 Shopify 店铺", "Connect a real Shopify store"), impact: tx("当前没有可用的授权店铺汇总，因此不会生成收入机会结论。", "No authorized store aggregate is available, so no revenue opportunity conclusion will be generated."), evidence: tx("数据状态：未获取到有效 Shopify 汇总", "Data status: no valid Shopify aggregate available"), action: tx("前往数据页完成只读授权与首次同步", "Complete read-only authorization and the initial sync"), href: "/data", kind: "gate" });
      } else if (readiness?.state !== "ready") {
        next.push({ id: "data-gate", eyebrow: tx("数据门槛", "Data threshold"), title: tx("真实机会建模尚未解锁", "Real opportunity modeling is still locked"), impact: english ? "Current coverage is insufficient for an actionable business conclusion." : (readiness?.message ?? "当前数据覆盖不足，不能形成可执行的经营结论。"), evidence: `${tx("同步状态", "Sync status")}: ${formatSyncTime(lastSyncedAt, locale)}`, action: tx("按数据页提示补齐真实订单趋势", "Complete the real order trend requested on the data page"), href: "/data", kind: "gate" });
      } else {
        next.push({ id: "no-alert", eyebrow: tx("店铺状态", "Store status"), title: tx("当前没有触发高优先级异常", "No high-priority anomaly is active"), impact: tx("最近同步的店铺级汇总未触发净销售下滑或退款压力规则。", "The latest store aggregate did not trigger net-sales decline or refund-pressure rules."), evidence: `${tx("同步状态", "Sync status")}: ${formatSyncTime(lastSyncedAt, locale)} · ${tx("未使用客户级数据", "No customer-level data used")}`, action: tx("保持监测，无需为了展示而制造任务", "Keep monitoring; do not manufacture work for display"), href: "/opportunities", kind: "clear" });
      }
    }

    if (publicSignal && next.length < 3) {
      next.push({ id: `public-${publicSignal.id}`, eyebrow: publicFeedLive ? tx("官方源已刷新", "Official feed refreshed") : tx("已审核公开信号", "Reviewed public signal"), title: publicSignal.title, impact: publicSignal.summary, evidence: `${tx("来源", "Source")}: ${publicSignal.source} · ${tx("数据日期", "Data date")}: ${publicSignal.date}`, action: publicSignal.action, href: "#cross-border-pulse", kind: "watch" });
    }
    return next.slice(0, 3);
  }, [english, hasSummary, lastSyncedAt, locale, opportunities, publicFeedLive, publicSignal, readiness, tx]);

  return <section className="daily-brief" aria-labelledby="daily-brief-title">
    <header className="daily-brief-heading">
      <div><p className="eyebrow">Daily operating brief</p><h2 id="daily-brief-title">{tx("今日经营简报", "Today's operating brief")}</h2><p>{tx("只展示最值得处理的事；没有可靠证据时，明确告诉你还缺什么。", "Only the highest-value work appears here. When evidence is weak, the missing input is made explicit.")}</p></div>
      <span className="daily-brief-count">{items.length.toString().padStart(2, "0")} {english ? "PRIORITIES" : "项优先事项"}</span>
    </header>
    <div className="daily-brief-list">
      {items.map((item, index) => <article className={`daily-brief-item daily-brief-${item.kind}`} key={item.id}>
        <div className="daily-brief-index">{String(index + 1).padStart(2, "0")}</div>
        <div className="daily-brief-main">
          <div className="daily-brief-kicker">{iconFor(item.kind)}<span>{item.eyebrow}</span></div>
          <h3>{item.title}</h3><p>{item.impact}</p>
          <details><summary>{tx("查看证据与判断边界", "View evidence and decision limits")}</summary><p>{item.evidence}</p></details>
        </div>
        <div className="daily-brief-action"><span>{tx("下一动作", "Next action")}</span><strong>{item.action}</strong>{item.external ? <a href={item.href} target="_blank" rel="noreferrer">{tx("打开来源", "Open source")} <ArrowRight size={14} /></a> : <Link href={item.href}>{tx("开始处理", "Start")} <ArrowRight size={14} /></Link>}</div>
      </article>)}
    </div>
  </section>;
}

function iconFor(kind: BriefItem["kind"]) {
  if (kind === "signal") return <Warning size={15} aria-hidden />;
  if (kind === "watch") return <GlobeHemisphereWest size={15} aria-hidden />;
  if (kind === "clear") return <CheckCircle size={15} aria-hidden />;
  return <Database size={15} aria-hidden />;
}

function formatSyncTime(value: string | null | undefined, locale: "zh-CN" | "en") {
  if (!value) return locale === "en" ? "No complete sync timestamp" : "尚无完整同步时间";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? (locale === "en" ? "Unknown sync time" : "同步时间未知") : date.toLocaleString(locale === "en" ? "en-US" : "zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
