"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useState } from "react";
import { CopilotPanel } from "./CopilotPanel";

const navigation = [
  { href: "/", label: "Overview", icon: "◈" },
  { href: "/opportunities", label: "Opportunities", icon: "◎" },
  { href: "/campaigns", label: "Campaigns", icon: "▣" },
  { href: "/learning", label: "Learning", icon: "↗" },
  { href: "/data", label: "Data", icon: "⌁" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [copilotOpen, setCopilotOpen] = useState(false);
  return <div className="app-shell"><aside className="sidebar">
    <Link className="brand" href="/"><span className="brand-mark">O</span><span>Olist<span className="brand-accent">/</span>RevenueOps</span></Link>
    <div className="workspace-switcher"><span className="workspace-dot" /><span>Northstar Commerce</span><span className="workspace-chevron">⌄</span></div>
    <nav className="main-nav" aria-label="Main navigation"><p className="nav-label">Workspace</p>{navigation.map((item) => {
      const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
      return <Link className={`nav-item ${active ? "nav-item-active" : ""}`} href={item.href} key={item.href}><span className="nav-icon">{item.icon}</span>{item.label}</Link>;
    })}</nav>
    <div className="agent-card"><div className="agent-orb">✦</div><p className="agent-card-title">AI Co-pilot</p><p className="agent-card-text">Evidence-backed help, always under your control.</p><button className="agent-card-link" onClick={() => setCopilotOpen(true)}>开始智能问答 →</button></div>
    <div className="user-card"><div className="avatar">NK</div><div><strong>Nora Kim</strong><span>Growth lead</span></div><button aria-label="Account options">•••</button></div>
  </aside><main className="app-main"><header className="topbar"><div className="breadcrumb"><span>Northstar Commerce</span><span className="slash">/</span><span>Revenue workspace</span></div><div className="topbar-actions"><span className="sync-status"><i /> Data up to date</span><button className="icon-button" onClick={() => setCopilotOpen(true)} aria-label="打开 AI 智能问答">✦</button><button className="primary-button">Create campaign <span>+</span></button></div></header><div className="app-frame">{children}</div></main><CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} /></div>;
}
