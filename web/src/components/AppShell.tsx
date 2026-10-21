"use client";

import {
  ChartLineUp,
  Database,
  List,
  MegaphoneSimple,
  Plus,
  Sparkle,
  SquaresFour,
  Target,
  Notebook,
  BookOpen,
  X,
} from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useState } from "react";
import { CopilotPanel } from "./CopilotPanel";
import { I18nProvider, useI18n, type MessageKey } from "./I18n";
import { LeadInExperience } from "./LeadInExperience";

const navigation = [
  { href: "/", label: "overview", meta: "overviewMeta", icon: SquaresFour },
  { href: "/reviews", label: "reviews", meta: "reviewsMeta", icon: Notebook },
  { href: "/opportunities", label: "opportunities", meta: "opportunitiesMeta", icon: Target },
  { href: "/campaigns", label: "campaigns", meta: "campaignsMeta", icon: MegaphoneSimple },
  { href: "/learning", label: "learning", meta: "learningMeta", icon: ChartLineUp },
  { href: "/data", label: "data", meta: "dataMeta", icon: Database },
];

export function AppShell({ children }: { children: ReactNode }) {
  return <I18nProvider><AppShellContent>{children}</AppShellContent></I18nProvider>;
}

function AppShellContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [introOpen, setIntroOpen] = useState(true);
  const currentPage = navigation.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href));
  const showIntro = pathname === "/" && introOpen;
  const researchUrl = (() => {
    try { const value = new URL(process.env.NEXT_PUBLIC_RESEARCH_SITE_URL || "");
      return !value.username && !value.password && (value.protocol === "https:" || (value.protocol === "http:" && ["localhost", "127.0.0.1"].includes(value.hostname))) ? value.href : null;
    } catch { return null; }
  })();

  if (pathname === "/pilot" || pathname === "/pilot/sample-report" || pathname === "/privacy") {
    return <div className="public-pilot-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <header className="public-pilot-header">
        <Link className="public-pilot-brand" href="/">RevenueOps</Link>
        <nav aria-label="试点导航"><Link href="/pilot/sample-report">查看示例</Link><Link className="button button-primary" href="/pilot#apply">申请连店</Link></nav>
      </header>
      <div id="main-content">{children}</div>
    </div>;
  }

  return <>{showIntro && <LeadInExperience onEnter={() => setIntroOpen(false)} />}<div className="app-shell" inert={showIntro} aria-hidden={showIntro || undefined}>
    <a className="skip-link" href="#main-content">{t("skip")}</a>
    <button className={`nav-scrim ${navOpen ? "nav-scrim-visible" : ""}`} onClick={() => setNavOpen(false)} aria-label={t("closeNav")} />
    <aside className={`sidebar ${navOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-head">
        <Link className="brand" href="/" onClick={() => setNavOpen(false)}><span className="brand-mark"><ChartLineUp size={17} weight="bold" aria-hidden="true" /></span><span>RevenueOps</span></Link>
        <button className="mobile-nav-close" onClick={() => setNavOpen(false)} aria-label={t("closeNav")}><X size={20} /></button>
      </div>
      <Link className="workspace-switcher" href="/data"><span><small>RevenueOps</small>{t("workspaceIdentity")}</span></Link>
      <nav className="main-nav" aria-label="Main navigation">
        <p className="nav-label">{t("workspace")}</p>
        {navigation.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return <Link className={`nav-item ${active ? "nav-item-active" : ""}`} href={item.href} key={item.href} onClick={() => setNavOpen(false)}>
            <span className="nav-icon"><Icon size={18} weight={active ? "fill" : "regular"} aria-hidden="true" /></span><span className="nav-copy"><strong>{t(item.label as MessageKey)}</strong><small>{t(item.meta as MessageKey)}</small></span><span className="nav-active-mark" />
          </Link>;
        })}
        {researchUrl && <a className="nav-item" href={researchUrl}><span className="nav-icon"><BookOpen size={18} aria-hidden="true" /></span><span className="nav-copy"><strong>{locale === "en" ? "Research" : "研究资讯"}</strong><small>{locale === "en" ? "Cross-border AI Observer" : "跨境 AI 观察"}</small></span></a>}
      </nav>
      <button className="agent-card" onClick={() => { setNavOpen(false); setCopilotOpen(true); }}>
        <span className="agent-orb"><Sparkle size={18} weight="fill" /></span>
        <span className="agent-card-title">{t("copilotTitle")}</span>
        <span className="agent-card-text">{t("copilotBody")}</span>
        <span className="agent-card-link">{t("copilotCta")} <span aria-hidden>→</span></span>
      </button>
      <div className="user-card"><div className="avatar">RO</div><div><strong>{t("accountIdentity")}</strong><Link href="/data">{t("manageConnection")}</Link></div></div>
    </aside>
    <main className="app-main">
      <header className="topbar">
        <button className="mobile-nav-open" onClick={() => setNavOpen(true)} aria-label={t("openNav")} aria-expanded={navOpen}><List size={21} weight="bold" aria-hidden="true" /></button>
        <div className="breadcrumb"><span>RevenueOps</span><span className="slash">/</span><span>{currentPage ? t(currentPage.label as MessageKey) : t("workspaceIdentity")}</span></div>
        <div className="topbar-actions"><div className="language-switch" role="group" aria-label={t("language")}><button className={locale === "zh-CN" ? "active" : ""} onClick={() => setLocale("zh-CN")} aria-pressed={locale === "zh-CN"}>{t("chinese")}</button><button className={locale === "en" ? "active" : ""} onClick={() => setLocale("en")} aria-pressed={locale === "en"}>{t("english")}</button></div><Link className="sync-status" href="/data">{t("manageConnection")}</Link><button className="icon-button" onClick={() => setCopilotOpen(true)} aria-label={t("openCopilot")} aria-expanded={copilotOpen}><Sparkle size={20} weight="fill" aria-hidden="true" /></button><Link href="/campaigns" className="primary-button">{t("createCampaign")} <Plus size={17} weight="bold" aria-hidden="true" /></Link></div>
      </header>
      <div className="app-frame" id="main-content">{children}</div>
    </main>
    <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} />
  </div></>;
}
