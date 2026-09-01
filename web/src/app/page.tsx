import Link from "next/link";
import { Metric, PageHeading, StatusBadge } from "@/components/Ui";
import { opportunities, workspace } from "@/lib/demo-data";

export default function OverviewPage() {
  const top = opportunities[0];
  return (
    <main className="page-content">
      <PageHeading eyebrow="Revenue intelligence" title="今天先做哪件事？" description="把数据异常、可执行机会和实验结果放在一个可审计的运营工作台里。" action={<Link className="button button-primary" href="/campaigns">新建活动</Link>} />
      <section className="notice-bar"><span className="notice-dot" />当前是{workspace.mode}：展示数据来自 {workspace.dataSource}，不会向任何真实客户发送触达。</section>
      <section className="metrics-grid">
        <Metric label="可验证收入机会" value="$38.1k" detail="未来 30 天估算上限" trend="3 个待处理机会" />
        <Metric label="待人工审批" value="2" detail="Agent 已生成完整方案" trend="需确认人群与预算" />
        <Metric label="进行中的实验" value="1" detail="新客第二单激励" trend="第 4 / 14 天" />
        <Metric label="已验证净增收入" value="$6.8k" detail="最近 30 天（示例）" trend="基于对照组归因" />
      </section>
      <section className="content-grid overview-grid">
        <article className="card opportunity-hero">
          <div className="card-kicker"><StatusBadge tone="warning">{top.priority} 优先级</StatusBadge><span>Agent 建议 · 需要你确认</span></div>
          <h2>{top.title}</h2><p className="hero-copy">{top.evidence}。先用小预算测试，确认增量后再扩大人群与渠道。</p>
          <div className="signal-row"><div><span>目标人群</span><strong>{top.segment}</strong></div><div><span>30 天机会</span><strong>{top.potential}</strong></div><div><span>综合分</span><strong>{top.score}/100</strong></div></div>
          <div className="button-row"><Link className="button button-primary" href="/campaigns">查看活动草案</Link><Link className="button button-ghost" href="/opportunities">查看证据</Link></div>
        </article>
        <article className="card readiness-card"><div className="card-kicker"><span>DATA READINESS</span><StatusBadge tone="neutral">DEMO</StatusBadge></div><h3>数据接入准备度</h3><div className="readiness-score">68<span>/100</span></div><p>历史订单、客户分层已可用；广告消耗、履约成本和真实渠道回执仍待接入。</p><Link href="/data" className="text-link">查看数据连接清单 →</Link></article>
      </section>
      <section className="section-heading"><div><p className="eyebrow">Opportunity queue</p><h2>优先机会队列</h2></div><Link href="/opportunities" className="text-link">全部机会 →</Link></section>
      <section className="card table-card"><div className="table-head"><span>机会</span><span>负责人</span><span>预计机会</span><span>综合分</span><span>状态</span></div>{opportunities.map((item) => <div className="table-row" key={item.id}><div><strong>{item.title}</strong><small>{item.segment}</small></div><span>{item.owner}</span><strong>{item.potential}</strong><strong>{item.score}</strong><StatusBadge tone={item.status === "待审批" ? "warning" : "neutral"}>{item.status}</StatusBadge></div>)}</section>
    </main>
  );
}
