import { Metric, PageHeading, StatusBadge } from "@/components/Ui";

export default function LearningPage() {
  return <main className="page-content"><PageHeading eyebrow="Measurement & learning" title="实验学习" description="区分已观测结果与模拟预估，避免把模型推演误当成真实收益。" />
    <section className="metrics-grid"><Metric label="已完成实验" value="1" detail="示例工作区" trend="具备对照组" /><Metric label="观测到的复购提升" value="+10.0pp" detail="实验组 20% / 对照组 10%" trend="样本仍有限" /><Metric label="归因净增收入" value="$6.8k" detail="示例归因结果" trend="需接入订单回执验证" /><Metric label="可靠性" value="中等" detail="样本量、周期影响结论" trend="不可直接规模化" /></section>
    <section className="content-grid learning-grid"><article className="card results-card"><div className="card-kicker"><StatusBadge tone="success">OBSERVED</StatusBadge><span>来自已结束实验的示例结果</span></div><h2>高流失风险客户召回 A/B 测试</h2><div className="results-bars"><div><span>实验组转化率</span><strong>20.0%</strong><i style={{width:"80%"}} /></div><div><span>对照组转化率</span><strong>10.0%</strong><i className="control" style={{width:"40%"}} /></div></div><p>归因逻辑：在相同观察窗内，计算实验组相对对照组的增量转化与对应订单收入，而不是直接用两组总收入相减。</p></article><article className="card caution-card"><p className="eyebrow">Guardrails</p><h3>结论使用边界</h3><ul><li>样本量不足时，不做扩量推荐。</li><li>未接入渠道回执时，不能声称“已触达”。</li><li>没有成本数据时，不展示真实 ROI。</li><li>跨市场、跨渠道结果不能直接迁移。</li></ul></article></section>
    <section className="card assumptions-card"><div><p className="eyebrow">SIMULATION</p><h2>下一轮预估只作为决策输入</h2></div><p>如果扩大到 1,000 人群，模型预估潜在增量收入为 $14.2k。该数字是基于当前样本转化率和历史客单价的推演，必须通过新的对照组实验验证。</p><button className="button button-ghost">查看预估假设</button></section>
  </main>;
}
