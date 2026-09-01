import { PageHeading, StatusBadge } from "@/components/Ui";

const sources = [["订单与客户历史","已接入","Olist 历史样本","仅用于产品验证"],["活动执行回执","未接入","Klaviyo / Braze","接入后才可判断真实触达"],["广告消耗与转化","未接入","Meta / Google Ads","接入后才可计算渠道 ROI"],["履约与退款成本","未接入","Shopify / ERP","接入后才可计算净利润"]];

export default function DataPage() { return <main className="page-content"><PageHeading eyebrow="Data foundation" title="数据连接" description="跨境商家的真实价值来自可授权的数据连接，而不是替代商家保存或猜测业务数据。" action={<button className="button button-primary">申请连接器</button>} />
  <section className="notice-bar"><span className="notice-dot" />当前运行在示例工作区。连接真实店铺前，应由商家授权并明确数据范围、用途与保留周期。</section>
  <section className="data-layout"><article className="card"><div className="card-kicker"><span>CONNECTION STATUS</span><StatusBadge tone="neutral">DEMO WORKSPACE</StatusBadge></div><h2>数据域覆盖</h2><div className="data-table">{sources.map(([name, state, source, note]) => <div className="data-row" key={name}><div><strong>{name}</strong><small>{note}</small></div><StatusBadge tone={state === "已接入" ? "success" : "neutral"}>{state}</StatusBadge><span>{source}</span></div>)}</div></article><aside className="card data-contract"><p className="eyebrow">Principles</p><h3>连接原则</h3><ol><li>商家在自己的渠道平台授权。</li><li>最小化获取字段与访问范围。</li><li>明确数据更新频率和失效机制。</li><li>每一项 Agent 建议都可追溯数据来源。</li></ol></aside></section>
  <section className="card api-card"><div><p className="eyebrow">NEXT MILESTONE</p><h2>从样本到真实商家数据</h2><p>第一阶段优先接入 Shopify 订单、客户、退款与产品数据；第二阶段接入 Klaviyo 或 Braze 的事件回执；最后才接入广告成本做 ROI 归因。</p></div><span className="api-tag">API CONTRACT READY</span></section>
</main>; }
