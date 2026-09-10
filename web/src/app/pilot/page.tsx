import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "RevenueOps 试点计划 | Shopify 收入诊断",
  description: "面向 Shopify 商家的 7 天只读收入诊断试点。",
};

export default function PilotPage() {
  return <main className="page-content pilot-page">
    <section className="pilot-hero">
      <p className="eyebrow">RevenueOps pilot · 首批 3 家商家</p>
      <h1>7 天找出一项值得验证的收入机会</h1>
      <p>面向已有订单、希望更清楚地判断复购、退款或折扣问题的 Shopify 商家。我们先做只读数据诊断，再由商家自行决定是否采取行动。</p>
      <div className="button-row"><Link className="button button-primary" href="/data">评估数据连接</Link><Link className="button button-ghost" href="/privacy">查看数据处理条款</Link></div>
    </section>

    <section className="pilot-grid">
      <article className="card">
        <p className="eyebrow">试点交付</p>
        <h2>一份可审阅的诊断结论</h2>
        <ul className="pilot-list">
          <li>订单、产品与库存的最小化汇总检查</li>
          <li>一个优先级明确的复购、退款或折扣假设</li>
          <li>一份由商家确认后才执行的行动建议</li>
        </ul>
      </article>
      <article className="card pilot-guardrails">
        <p className="eyebrow">数据边界</p>
        <h2>商家始终保有控制权</h2>
        <ul className="pilot-list">
          <li>仅请求 Shopify 只读权限</li>
          <li>不会自动发送营销信息或修改店铺内容</li>
          <li>可随时撤销授权并删除 RevenueOps 本地数据</li>
        </ul>
      </article>
    </section>

    <section className="card pilot-steps">
      <div><p className="eyebrow">如何进行</p><h2>三步完成试点</h2></div>
      <ol>
        <li><strong>确认范围</strong><span>商家确认试点目的、数据范围与保留方式。</span></li>
        <li><strong>只读同步</strong><span>连接 Shopify，读取必要的订单、产品和库存汇总。</span></li>
        <li><strong>审阅建议</strong><span>交付诊断结果；任何后续活动均须商家单独审批。</span></li>
      </ol>
    </section>

    <section className="pilot-fit">
      <article><h2>适合</h2><p>已有真实订单，且正想判断复购表现、退款变化或折扣效率的 Shopify 商家。</p></article>
      <article><h2>暂不适合</h2><p>尚无可用订单数据，或希望系统直接代替人工向客户群发营销内容的场景。</p></article>
    </section>

    <section className="pilot-summary card">
      <p className="eyebrow">试点说明</p>
      <p>RevenueOps 试点是一次有限范围的只读收入诊断，不承诺特定营收结果，不会在未经确认的情况下执行客户触达或店铺变更。</p>
    </section>
  </main>;
}
