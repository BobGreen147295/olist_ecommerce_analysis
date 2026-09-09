import Link from "next/link";

export default function PrivacyPage() {
  return <main className="page-content"><section className="card api-card"><p className="eyebrow">REVENUEOPS DATA TERMS · v1.0 · 2026-09-09</p><h1>商家数据处理条款</h1><p>本条款适用于商家使用 RevenueOps 连接 Shopify 并查看收入、复购、退款和库存汇总的场景。</p><h2>各方角色与用途</h2><p>商家是其店铺客户数据的控制者。RevenueOps 仅为向商家提供运营分析而处理最小必要数据，不出售、不用于广告定向，也不向第三方披露。</p><h2>最小化与安全</h2><p>RevenueOps 仅请求 Shopify 只读权限；OAuth 令牌以密文保存。订单导入会在浏览器删除邮箱、电话、姓名和地址，并使用匿名客户标识。</p><h2>保留与删除</h2><p>匿名订单和同步汇总自采集起最多保留 90 天。商家可在“数据连接 → 保留与删除”随时删除 RevenueOps 本地数据；该操作不会修改 Shopify 店铺数据。</p><h2>商家责任</h2><p>商家确认其有权授权数据访问，并负责处理其客户的同意、删除和不出售数据请求。若需要受保护客户字段或跨境合规承诺，双方应另行签署适用的数据处理协议。</p><p><Link href="/data">返回数据连接</Link></p></section></main>;
}
