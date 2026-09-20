"use client";

import {
  ArrowRight,
  ChartLineUp,
  CheckCircle,
  Flask,
  ShieldCheck,
  Target,
} from "@phosphor-icons/react";
import { useEffect, useState, type PointerEvent } from "react";
import { useI18n } from "./I18n";

const stages = [
  {
    label: "发现机会",
    icon: Target,
    title: "高价值沉默客户",
    value: "$18,420",
    valueLabel: "30 天机会估算",
    detail: "识别复购间隔拉长且历史贡献较高的客户群体。",
    metrics: [["综合分", "86 / 100"], ["证据", "订单与复购趋势"], ["状态", "待人工审核"]],
  },
  {
    label: "设计实验",
    icon: Flask,
    title: "小样本召回实验",
    value: "14 天",
    valueLabel: "观察周期",
    detail: "先以对照组验证真实增量，再决定是否扩大预算。",
    metrics: [["实验组", "100 人"], ["对照组", "100 人"], ["停止条件", "ROI < 0"]],
  },
  {
    label: "验证增量",
    icon: ChartLineUp,
    title: "收入提升已归因",
    value: "$6,820",
    valueLabel: "演示净增收入",
    detail: "把结果与对照组比较，保留可审计的决策证据。",
    metrics: [["实验状态", "已完成"], ["归因方法", "对照组"], ["数据类型", "合成演示"]],
  },
] as const;

export function LeadInExperience({ onEnter }: { onEnter: () => void }) {
  const { locale, setLocale, t } = useI18n();
  const [activeStage, setActiveStage] = useState(0);
  const [exiting, setExiting] = useState(false);
  const stage = stages[activeStage];

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, []);

  function enterWorkspace() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      onEnter();
      return;
    }
    setExiting(true);
    window.setTimeout(onEnter, 360);
  }

  function moveSpotlight(event: PointerEvent<HTMLElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--pointer-x", `${event.clientX - bounds.left}px`);
    event.currentTarget.style.setProperty("--pointer-y", `${event.clientY - bounds.top}px`);
  }

  return <section className={`lead-in ${exiting ? "lead-in-exiting" : ""}`} aria-label="RevenueOps 产品介绍">
    <div className="lead-in-grid" aria-hidden="true" />
    <header className="lead-in-header">
      <div className="lead-in-brand"><span><ChartLineUp size={18} weight="bold" aria-hidden /></span>RevenueOps</div>
      <div className="lead-in-actions"><div className="language-switch" role="group" aria-label={t("language")}><button className={locale === "zh-CN" ? "active" : ""} onClick={() => setLocale("zh-CN")} aria-pressed={locale === "zh-CN"}>{t("chinese")}</button><button className={locale === "en" ? "active" : ""} onClick={() => setLocale("en")} aria-pressed={locale === "en"}>{t("english")}</button></div><div className="lead-in-status" role="status"><i /> {t("introStatus")}</div></div>
    </header>

    <div className="lead-in-layout">
      <div className="lead-in-copy">
        <p className="lead-in-kicker">{t("introKicker")}</p>
        <h1>{t("introTitle1")}<br />{t("introTitle2")}</h1>
        <p className="lead-in-summary">{t("introSummary")}</p>
        <button className="lead-in-cta" onClick={enterWorkspace}>{t("enterWorkspace")} <ArrowRight size={18} weight="bold" aria-hidden /></button>
        <div className="lead-in-trust">
          <span><ShieldCheck size={17} aria-hidden /> {t("humanApproval")}</span>
          <span><CheckCircle size={17} aria-hidden /> {t("separatedData")}</span>
        </div>
      </div>

      <article className="signal-console" onPointerMove={moveSpotlight}>
        <div className="signal-console-glow" aria-hidden="true" />
        <div className="signal-console-head">
          <div><span>决策链路</span><strong>从信号到结果</strong></div>
          <span className="signal-demo-label">合成演示</span>
        </div>
        <div className="signal-tabs" role="tablist" aria-label="决策链路阶段">
          {stages.map((item, index) => {
            const Icon = item.icon;
            return <button key={item.label} role="tab" aria-selected={index === activeStage} className={index === activeStage ? "signal-tab-active" : ""} onClick={() => setActiveStage(index)}>
              <Icon size={17} weight={index === activeStage ? "fill" : "regular"} aria-hidden />
              <span>{item.label}</span>
            </button>;
          })}
        </div>
        <div className="signal-stage" key={stage.label} role="tabpanel">
          <div className="signal-stage-main">
            <div><span>{stage.valueLabel}</span><strong>{stage.value}</strong></div>
            <div><h2>{stage.title}</h2><p>{stage.detail}</p></div>
          </div>
          <div className="signal-metrics">
            {stage.metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
          </div>
        </div>
        <div className="signal-progress" aria-hidden="true"><i style={{ width: `${((activeStage + 1) / stages.length) * 100}%` }} /></div>
      </article>
    </div>

    <footer className="lead-in-footer"><span>Revenue intelligence</span><span>Human controlled</span><span>Evidence tracked</span></footer>
  </section>;
}
