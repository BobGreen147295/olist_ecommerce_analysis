"use client";

import { ArrowUpRight, Broadcast, ShieldCheck } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

type Signal = {
  id: string;
  category: string;
  market: string;
  level: string;
  date: string;
  title: string;
  summary: string;
  action: string;
  source: string;
  href: string;
  update_mode?: "reviewed" | "official_feed";
};

const API_BASE_URL = process.env.NEXT_PUBLIC_REVENUEOPS_API_URL?.replace(/\/$/, "");
const fallbackSignals: Signal[] = [
  {
    id: "eu-low-value-duty",
    category: "合规",
    market: "欧盟",
    level: "高影响",
    date: "2026-07-20",
    title: "欧盟低价值进口商品已适用临时关税",
    summary: "自 2026 年 7 月 1 日起，价值不超过 150 欧元的进口商品按不同税则项目适用临时 3 欧元关税。",
    action: "复核欧盟订单的落地成本、税则分类与结账页费用说明，避免利润和到货体验偏差。",
    source: "欧盟委员会税务与关税联盟",
    href: "https://taxation-customs.ec.europa.eu/news/guidance-and-legal-text-temporary-flat-fee-low-value-imports-which-will-apply-until-1-july-2028-2026-06-08_en",
  },
  {
    id: "shopify-disclosures",
    category: "平台",
    market: "全球",
    level: "中影响",
    date: "2026-06-17",
    title: "Shopify 商品信息支持结构化披露字段",
    summary: "商家可在后台维护产品警示与自定义披露；支持的主题会在商品详情页展示这些信息。",
    action: "若销售受监管商品，抽查重点 SKU 的披露字段、主题呈现和自定义店面渲染是否一致。",
    source: "Shopify Changelog",
    href: "https://changelog.shopify.com/posts/product-listings-now-support-a-disclosures-field",
  },
  {
    id: "us-cargo-description",
    category: "物流",
    market: "美国",
    level: "中影响",
    date: "2025-02-24",
    title: "美国入境货物需要准确、可识别的商品描述",
    summary: "美国海关公开了可接受与不可接受的货物描述示例，强调描述应足以识别商品特征。",
    action: "检查承运商模板中的英文品名，避免只填品牌名、模糊简称或与实际商品不一致的描述。",
    source: "U.S. Customs and Border Protection",
    href: "https://www.cbp.gov/trade/basic-import-export/e-commerce/examples-unacceptable-vs-acceptable-cargo-descriptions",
  },
  {
    id: "ecb-reference-rates",
    category: "汇率",
    market: "欧盟",
    level: "观察",
    date: "2026-09-18",
    title: "欧洲央行工作日更新欧元参考汇率",
    summary: "欧洲央行通常在每个工作日约 16:00 CET 发布欧元对主要货币的参考汇率，仅供信息参考。",
    action: "把汇率变化作为毛利敏感度信号；实际定价、结算和对冲仍应使用支付渠道的成交数据。",
    source: "European Central Bank",
    href: "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
  },
];

const categories = ["全部", "合规", "平台", "物流", "汇率"] as const;
const markets = ["全部市场", "欧盟", "美国", "全球"] as const;

export function CrossBorderPulse() {
  const [category, setCategory] = useState<(typeof categories)[number]>("全部");
  const [market, setMarket] = useState<(typeof markets)[number]>("全部市场");
  const [signals, setSignals] = useState<Signal[]>(fallbackSignals);
  const [feedState, setFeedState] = useState<"loading" | "live" | "fallback">(API_BASE_URL ? "loading" : "fallback");
  const [selectedId, setSelectedId] = useState<string>(fallbackSignals[0].id);

  useEffect(() => {
    if (!API_BASE_URL) return;
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/v1/public-intelligence`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("public intelligence unavailable");
        return response.json();
      })
      .then((payload) => {
        const next = Array.isArray(payload?.signals) ? payload.signals.filter(isSignal) : [];
        if (!next.length) throw new Error("public intelligence payload invalid");
        setSignals(next);
        setFeedState(payload.feed_status === "live" ? "live" : "fallback");
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setFeedState("fallback");
      });
    return () => controller.abort();
  }, []);

  const filtered = signals.filter((signal) =>
    (category === "全部" || signal.category === category) &&
    (market === "全部市场" || signal.market === market || signal.market === "全球")
  );
  const selected = filtered.find((signal) => signal.id === selectedId) ?? filtered[0];

  return <section className="pulse-section" aria-labelledby="cross-border-pulse-title">
    <header className="pulse-heading">
      <div>
        <p className="eyebrow"><Broadcast size={14} aria-hidden /> Cross-border pulse</p>
        <h2 id="cross-border-pulse-title">跨境经营雷达</h2>
        <p>把平台、合规、物流与汇率变化，翻译成商家今天能执行的最小动作。</p>
      </div>
      <div className={`pulse-provenance pulse-provenance-${feedState}`}><ShieldCheck size={17} aria-hidden /><span>{feedState === "live" ? "官方汇率源已刷新" : feedState === "loading" ? "正在检查官方源" : "已使用审核回退"}<br />仅用公开信息，不读取客户数据</span></div>
    </header>

    <div className="pulse-controls" aria-label="跨境情报筛选">
      <div className="pulse-filters" aria-label="按类型筛选">
        {categories.map((item) => <button key={item} type="button" aria-pressed={category === item} onClick={() => setCategory(item)}>{item}</button>)}
      </div>
      <label className="pulse-market">市场
        <select value={market} onChange={(event) => setMarket(event.target.value as (typeof markets)[number])}>
          {markets.map((item) => <option key={item}>{item}</option>)}
        </select>
      </label>
    </div>

    {selected ? <div className="pulse-layout">
      <div className="pulse-list" aria-label="公开经营信号">
        {filtered.map((signal) => <button key={signal.id} type="button" className={signal.id === selected.id ? "pulse-item pulse-item-active" : "pulse-item"} onClick={() => setSelectedId(signal.id)}>
          <span className="pulse-item-meta"><span>{signal.market}</span><time dateTime={signal.date}>{signal.date}</time></span>
          <strong>{signal.title}</strong>
          <span className="pulse-item-footer"><span>{signal.category}</span><span>{signal.level}</span></span>
        </button>)}
      </div>
      <article className="pulse-brief" aria-live="polite">
        <div className="pulse-brief-meta"><span>{selected.level}</span><span>{selected.market} · {selected.category}</span></div>
        <h3>{selected.title}</h3>
        <p>{selected.summary}</p>
        <div className="pulse-action"><span>建议动作</span><strong>{selected.action}</strong></div>
        <a href={selected.href} target="_blank" rel="noreferrer">查看官方来源：{selected.source}<ArrowUpRight size={15} aria-hidden /></a>
      </article>
    </div> : <div className="pulse-empty">当前筛选下暂无信号，请切换市场或类型。</div>}

    <footer className="pulse-disclaimer">汇率由结构化官方源自动更新；其他信号经人工核验后发布 · 仅供经营判断，不构成法律、税务或投资建议。</footer>
  </section>;
}

function isSignal(value: unknown): value is Signal {
  if (!value || typeof value !== "object") return false;
  const signal = value as Record<string, unknown>;
  return ["id", "category", "market", "level", "date", "title", "summary", "action", "source", "href"]
    .every((key) => typeof signal[key] === "string" && signal[key] !== "");
}
