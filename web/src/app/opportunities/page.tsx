import Link from "next/link";
import { PageHeading, StatusBadge } from "@/components/Ui";
import { opportunities } from "@/lib/demo-data";

const scoreFormula = "综合分 = 影响规模 35% + 增量潜力 30% + 置信度 20% + 可执行性 15%";

export default function OpportunitiesPage() {
  return <main className="page-content">
    <PageHeading eyebrow="Opportunity queue" title="优先机会" description="Agent 只负责发现、量化和排序；是否执行仍由运营人员做决策。" />
    <section className="formula-card"><div><span className="eyebrow">如何排序</span><strong>{scoreFormula}</strong></div><p>综合分用于排队，不等于收入承诺。上线前需要核对数据覆盖、目标人群和实验成本。</p></section>
    <section className="opportunity-list">{opportunities.map((item, index) => <article key={item.id} className="card opportunity-card"><div className="opportunity-rank">0{index + 1}</div><div className="opportunity-main"><div className="card-kicker"><StatusBadge tone={item.priority === "P0" ? "danger" : "warning"}>{item.priority}</StatusBadge><span>{item.owner} · {item.status}</span></div><h2>{item.title}</h2><p>{item.evidence}</p><div className="evidence-chips"><span>人群：{item.segment}</span><span>来源：客户分层 + 订单历史</span><span>置信度：中等</span></div></div><div className="opportunity-score"><span>综合分</span><strong>{item.score}</strong><small>30 天机会 {item.potential}</small><Link className="button button-ghost" href="/campaigns">创建草案</Link></div></article>)}</section>
  </main>;
}
