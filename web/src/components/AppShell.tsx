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
import { LeadInExperience } from "./LeadInExperience";

const navigation = [
  { href: "/", label: "总览", meta: "Overview", icon: SquaresFour },
  { href: "/opportunities", label: "机会", meta: "Opportunities", icon: Target },
  { href: "/campaigns", label: "活动", meta: "Campaigns", icon: MegaphoneSimple },
  { href: "/learning", label: "实验复盘", meta: "Learning", icon: ChartLineUp },
  { href: "/data", label: "数据连接", meta: "Data", icon: Database },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [introOpen, setIntroOpen] = useState(true);
  const currentPage = navigation.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href));
  const showIntro = pathname === "/" && introOpen;

  return <>{showIntro && <LeadInExperience onEnter={() => setIntroOpen(false)} />}<div className="app-shell" inert={showIntro} aria-hidden={showIntro || undefined}>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <button className={`nav-scrim ${navOpen ? "nav-scrim-visible" : ""}`} onClick={() => setNavOpen(false)} aria-label="关闭导航" />
    <aside className={`sidebar ${navOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-head">
        <Link className="brand" href="/" onClick={() => setNavOpen(false)}><span className="brand-mark"><ChartLineUp size={17} weight="bold" aria-hidden="true" /></span><span>RevenueOps</span></Link>
        <button className="mobile-nav-close" onClick={() => setNavOpen(false)} aria-label="关闭导航"><X size={20} /></button>
      </div>
      <button className="workspace-switcher"><span className="workspace-dot" /><span><small>Workspace</small>Northstar Commerce</span><CaretDown className="workspace-chevron" size={14} /></button>
      <nav className="main-nav" aria-label="Main navigation">
        <p className="nav-label">Workspace</p>
        {navigation.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return <Link className={`nav-item ${active ? "nav-item-active" : ""}`} href={item.href} key={item.href} onClick={() => setNavOpen(false)}>
            <span className="nav-icon"><Icon size={18} weight={active ? "fill" : "regular"} aria-hidden="true" /></span><span className="nav-copy"><strong>{item.label}</strong><small>{item.meta}</small></span><span className="nav-active-mark" />
          </Link>;
        })}
      </nav>
      <button className="agent-card" onClick={() => setCopilotOpen(true)}>
        <span className="agent-orb"><Sparkle size={18} weight="fill" /></span>
        <span className="agent-card-title">AI Co-pilot</span>
        <span className="agent-card-text">基于证据生成建议，执行始终由你确认。</span>
        <span className="agent-card-link">开始智能问答 <span aria-hidden>→</span></span>
      </button>
      <div className="user-card"><div className="avatar">NK</div><div><strong>Nora Kim</strong><span>Growth lead</span></div><button aria-label="账户选项"><DotsThree size={20} weight="bold" /></button></div>
    </aside>
    <main className="app-main">
      <header className="topbar">
        <button className="mobile-nav-open" onClick={() => setNavOpen(true)} aria-label="打开导航" aria-expanded={navOpen}><List size={21} weight="bold" aria-hidden="true" /></button>
        <div className="breadcrumb"><span>Northstar Commerce</span><span className="slash">/</span><span>{currentPage?.label ?? "Revenue workspace"}</span></div>
        <div className="topbar-actions"><span className="sync-status" role="status"><i /> 服务在线</span><button className="icon-button" onClick={() => setCopilotOpen(true)} aria-label="打开 AI 智能问答" aria-expanded={copilotOpen}><Sparkle size={20} weight="fill" aria-hidden="true" /></button><Link href="/campaigns" className="primary-button">新建活动 <Plus size={17} weight="bold" aria-hidden="true" /></Link></div>
      </header>
      <div className="app-frame" id="main-content">{children}</div>
    </main>
    <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} />
  </div></>;
}
