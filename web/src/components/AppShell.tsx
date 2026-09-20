"use client";

import {
  CaretDown,
  ChartLineUp,
  Database,
  DotsThree,
  List,
  MegaphoneSimple,
  Plus,
  Sparkle,
  SquaresFour,
  Target,
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

  return <>{showIntro && <LeadInExperience onEnter={() => setIntroOpen(false)} />}<div className="app-shell" inert={showIntro} aria-hidden={showIntro || undefined}>
    <a className="skip-link" href="#main-content">{t("skip")}</a>
    <button className={`nav-scrim ${navOpen ? "nav-scrim-visible" : ""}`} onClick={() => setNavOpen(false)} aria-label={t("closeNav")} />
    <aside className={`sidebar ${navOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-head">
        <Link className="brand" href="/" onClick={() => setNavOpen(false)}><span className="brand-mark"><ChartLineUp size={17} weight="bold" aria-hidden="true" /></span><span>RevenueOps</span></Link>
        <button className="mobile-nav-close" onClick={() => setNavOpen(false)} aria-label={t("closeNav")}><X size={20} /></button>
      </div>
      <button className="workspace-switcher"><span className="workspace-dot" /><span><small>Workspace</small>Northstar Commerce</span><CaretDown className="workspace-chevron" size={14} /></button>
      <nav className="main-nav" aria-label="Main navigation">
        <p className="nav-label">{t("workspace")}</p>
        {navigation.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return <Link className={`nav-item ${active ? "nav-item-active" : ""}`} href={item.href} key={item.href} onClick={() => setNavOpen(false)}>
            <span className="nav-icon"><Icon size={18} weight={active ? "fill" : "regular"} aria-hidden="true" /></span><span className="nav-copy"><strong>{t(item.label as MessageKey)}</strong><small>{t(item.meta as MessageKey)}</small></span><span className="nav-active-mark" />
          </Link>;
        })}
      </nav>
      <button className="agent-card" onClick={() => setCopilotOpen(true)}>
        <span className="agent-orb"><Sparkle size={18} weight="fill" /></span>
        <span className="agent-card-title">{t("copilotTitle")}</span>
        <span className="agent-card-text">{t("copilotBody")}</span>
        <span className="agent-card-link">{t("copilotCta")} <span aria-hidden>→</span></span>
      </button>
      <div className="user-card"><div className="avatar">NK</div><div><strong>Nora Kim</strong><span>{t("growthLead")}</span></div><button aria-label={t("accountOptions")}><DotsThree size={20} weight="bold" /></button></div>
    </aside>
    <main className="app-main">
      <header className="topbar">
        <button className="mobile-nav-open" onClick={() => setNavOpen(true)} aria-label={t("openNav")} aria-expanded={navOpen}><List size={21} weight="bold" aria-hidden="true" /></button>
        <div className="breadcrumb"><span>Northstar Commerce</span><span className="slash">/</span><span>{currentPage ? t(currentPage.label as MessageKey) : "Revenue workspace"}</span></div>
        <div className="topbar-actions"><div className="language-switch" role="group" aria-label={t("language")}><button className={locale === "zh-CN" ? "active" : ""} onClick={() => setLocale("zh-CN")} aria-pressed={locale === "zh-CN"}>{t("chinese")}</button><button className={locale === "en" ? "active" : ""} onClick={() => setLocale("en")} aria-pressed={locale === "en"}>{t("english")}</button></div><span className="sync-status" role="status"><i /> {t("online")}</span><button className="icon-button" onClick={() => setCopilotOpen(true)} aria-label={t("openCopilot")} aria-expanded={copilotOpen}><Sparkle size={20} weight="fill" aria-hidden="true" /></button><Link href="/campaigns" className="primary-button">{t("createCampaign")} <Plus size={17} weight="bold" aria-hidden="true" /></Link></div>
      </header>
      <div className="app-frame" id="main-content">{children}</div>
    </main>
    <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} />
  </div></>;
}
