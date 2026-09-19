"use client";

import { ArrowRight, CheckCircle, Database, GlobeHemisphereWest, Warning } from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

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

function formatEvidence(evidence: Record<string, number>) {
  return Object.entries(evidence)
    .map(([key, value]) => `${evidenceLabels[key] ?? key.replaceAll("_", " ")} ${value}`)
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
      eyebrow: "店铺级信号",
      title: opportunity.title,
      impact: opportunity.summary,
      evidence: `来源：Shopify 按日汇总 · 证据：${formatEvidence(opportunity.evidence)}`,
      action: "核实业务原因并生成待审核草案",
      href: "/opportunities",
      kind: "signal" as const,
    }));

    if (!next.length) {
      if (!hasSummary) {
        next.push({ id: "connect-data", eyebrow: "数据准备", title: "连接真实 Shopify 店铺", impact: "当前没有可用的授权店铺汇总，因此不会生成收入机会结论。", evidence: "数据状态：未获取到有效 Shopify 汇总", action: "前往数据页完成只读授权与首次同步", href: "/data", kind: "gate" });
      } else if (readiness?.state !== "ready") {
        next.push({ id: "data-gate", eyebrow: "数据门槛", title: "真实机会建模尚未解锁", impact: readiness?.message ?? "当前数据覆盖不足，不能形成可执行的经营结论。", evidence: `同步状态：${formatSyncTime(lastSyncedAt)}`, action: "按数据页提示补齐真实订单趋势", href: "/data", kind: "gate" });
      } else {
        next.push({ id: "no-alert", eyebrow: "店铺状态", title: "当前没有触发高优先级异常", impact: "最近同步的店铺级汇总未触发净销售下滑或退款压力规则。", evidence: `同步状态：${formatSyncTime(lastSyncedAt)} · 未使用客户级数据`, action: "保持监测，无需为了展示而制造任务", href: "/opportunities", kind: "clear" });
      }
    }

    if (publicSignal && next.length < 3) {
      next.push({ id: `public-${publicSignal.id}`, eyebrow: publicFeedLive ? "官方源已刷新" : "已审核公开信号", title: publicSignal.title, impact: publicSignal.summary, evidence: `来源：${publicSignal.source} · 数据日期：${publicSignal.date}`, action: publicSignal.action, href: "#cross-border-pulse", kind: "watch" });
    }
    return next.slice(0, 3);
  }, [hasSummary, lastSyncedAt, opportunities, publicFeedLive, publicSignal, readiness]);

  return <section className="daily-brief" aria-labelledby="daily-brief-title">
    <header className="daily-brief-heading">
      <div><p className="eyebrow">Daily operating brief</p><h2 id="daily-brief-title">今日经营简报</h2><p>只展示最值得处理的事；没有可靠证据时，明确告诉你还缺什么。</p></div>
      <span className="daily-brief-count">{items.length.toString().padStart(2, "0")} PRIORITIES</span>
    </header>
    <div className="daily-brief-list">
      {items.map((item, index) => <article className={`daily-brief-item daily-brief-${item.kind}`} key={item.id}>
        <div className="daily-brief-index">{String(index + 1).padStart(2, "0")}</div>
        <div className="daily-brief-main">
          <div className="daily-brief-kicker">{iconFor(item.kind)}<span>{item.eyebrow}</span></div>
          <h3>{item.title}</h3><p>{item.impact}</p>
          <details><summary>查看证据与判断边界</summary><p>{item.evidence}</p></details>
        </div>
        <div className="daily-brief-action"><span>下一动作</span><strong>{item.action}</strong>{item.external ? <a href={item.href} target="_blank" rel="noreferrer">打开来源 <ArrowRight size={14} /></a> : <Link href={item.href}>开始处理 <ArrowRight size={14} /></Link>}</div>
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

function formatSyncTime(value?: string | null) {
  if (!value) return "尚无完整同步时间";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "同步时间未知" : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
