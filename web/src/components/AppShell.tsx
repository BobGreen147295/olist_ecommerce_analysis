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

const navigation = [
  { href: "/", label: "Overview", icon: SquaresFour },
  { href: "/opportunities", label: "Opportunities", icon: Target },
  { href: "/campaigns", label: "Campaigns", icon: MegaphoneSimple },
  { href: "/learning", label: "Learning", icon: ChartLineUp },
  { href: "/data", label: "Data", icon: Database },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);

  return <div className="app-shell">
    <button className={`nav-scrim ${navOpen ? "nav-scrim-visible" : ""}`} onClick={() => setNavOpen(false)} aria-label="关闭导航" />
    <aside className={`sidebar ${navOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-head">
        <Link className="brand" href="/" onClick={() => setNavOpen(false)}><span className="brand-mark">R</span><span>RevenueOps</span></Link>
        <button className="mobile-nav-close" onClick={() => setNavOpen(false)} aria-label="关闭导航"><X size={20} /></button>
      </div>
      <button className="workspace-switcher"><span className="workspace-dot" /><span><small>Workspace</small>Northstar Commerce</span><CaretDown className="workspace-chevron" size={14} /></button>
      <nav className="main-nav" aria-label="Main navigation">
        <p className="nav-label">Workspace</p>
        {navigation.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return <Link className={`nav-item ${active ? "nav-item-active" : ""}`} href={item.href} key={item.href} onClick={() => setNavOpen(false)}>
            <span className="nav-icon"><Icon size={18} weight={active ? "fill" : "regular"} /></span>{item.label}<span className="nav-active-mark" />
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
        <button className="mobile-nav-open" onClick={() => setNavOpen(true)} aria-label="打开导航"><List size={21} weight="bold" /></button>
        <div className="breadcrumb"><span>Northstar Commerce</span><span className="slash">/</span><span>Revenue workspace</span></div>
        <div className="topbar-actions"><span className="sync-status"><i /> Data up to date</span><button className="icon-button" onClick={() => setCopilotOpen(true)} aria-label="打开 AI 智能问答"><Sparkle size={20} weight="fill" /></button><Link href="/campaigns" className="primary-button">Create campaign <Plus size={17} weight="bold" /></Link></div>
      </header>
      <div className="app-frame">{children}</div>
    </main>
    <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} />
  </div>;
}
