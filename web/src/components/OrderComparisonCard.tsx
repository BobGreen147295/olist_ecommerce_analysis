type Period = { period: string; total_orders: number; total_amount: number; start: string; end_exclusive: string };
type Report = {
  status: "ready" | "unavailable"; model_called: false; source: string | null; currency: string | null;
  generated_at: string; issues: { code: string; message: string }[];
  comparison: null | { previous: Period; current: Period; amount_delta: number; change_pct: number | null; orders_delta: number };
  provenance: null | { imported_at: string | null; coverage_start: string | null; coverage_end: string | null };
};

// Treat network data as untrusted. A malformed card falls back to the server's text.
function isReport(value: unknown): value is Report {
  if (!value || typeof value !== "object") return false;
  const r = value as Report;
  if (r.model_called !== false || !["ready", "unavailable"].includes(r.status)
      || typeof r.generated_at !== "string" || !Array.isArray(r.issues)
      || !r.issues.every(i => i && typeof i.code === "string" && typeof i.message === "string")) return false;
  if (r.provenance !== null && (!r.provenance || ![r.provenance.imported_at, r.provenance.coverage_start, r.provenance.coverage_end].every(v => v === null || typeof v === "string"))) return false;
  if (r.status === "unavailable") return r.comparison === null;
  if (typeof r.source !== "string" || typeof r.currency !== "string" || !/^[A-Z]{3}$/.test(r.currency)) return false;
  const c = r.comparison;
  return c === null || Boolean(c && [c.previous, c.current].every(p => p && typeof p.period === "string"
    && typeof p.start === "string" && typeof p.end_exclusive === "string" && Number.isFinite(p.total_amount)
    && Number.isInteger(p.total_orders)) && Number.isFinite(c.amount_delta)
    && (c.change_pct === null || Number.isFinite(c.change_pct)) && Number.isInteger(c.orders_delta));
}

export function OrderComparisonCard({ report, fallback, english }: { report: unknown; fallback: string; english: boolean }) {
  if (!isReport(report)) return <p>{fallback}</p>;
  const tx = (zh: string, en: string) => english ? en : zh;
  const comparison = report.comparison;
  const amount = (value: number, signed = false) => `${signed && value > 0 ? "+" : ""}${value.toLocaleString(english ? "en-US" : "zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return <section className="order-comparison" aria-label={tx("两期订单金额核对", "Two-period order amount check")}>
    <header><strong>{report.status === "unavailable" ? tx("数据核对未完成", "Data check incomplete") : tx("两期订单金额核对", "Two-period order amounts")}</strong><small>{tx("固定计算 · 未调用 AI", "Fixed calculation · No AI call")}</small></header>
    {report.status === "ready" && <>
      <div className="order-comparison-source">{tx("来源", "Source")}: {report.source}<br />{tx("币种", "Currency")}: {report.currency} · UTC</div>
      {comparison && <>
        <div className="order-comparison-delta"><span>{tx("金额差额", "Amount difference")}</span><strong>{report.currency} {amount(comparison.amount_delta, true)}</strong>
          <span>{tx("变化率", "Change")}: {comparison.change_pct === null ? tx("不可计算：基期为零", "Undefined: zero baseline") : `${comparison.change_pct > 0 ? "+" : ""}${comparison.change_pct.toFixed(2)}%`}</span></div>
        <table><caption>{tx("最近两个有订单月份（不保证完整）", "Last two observed months (not necessarily complete)")}</caption><thead><tr><th scope="col">{tx("期间", "Period")}</th><th scope="col">{tx("订单金额", "Order amount")}</th><th scope="col">{tx("笔数", "Orders")}</th></tr></thead><tbody>
          {[comparison.previous, comparison.current].map(p => <tr key={p.period}><th scope="row">{p.period}</th><td>{amount(p.total_amount)}</td><td>{p.total_orders}</td></tr>)}
        </tbody></table>
      </>}
    </>}
    {!!report.issues.length && <ul className="order-comparison-issues" aria-label={tx("数据限制与异常", "Data limitations and issues")}>{report.issues.map(i => <li key={i.code}>{i.message}</li>)}</ul>}
    {report.status === "ready" && <p className="order-comparison-boundary">{tx("这是订单金额差异，不是净收入或利润；未扣退款、未排除取消订单。不能解释变化原因、广告效果或复购。", "This is an order amount difference, not net revenue or profit. Refunds are not deducted and cancelled orders are included. Causes, ad effects and repeat purchases are not explained.")}</p>}
    <details><summary>{tx("查看日期、来源与计算证据", "Inspect dates, source and calculation")}</summary>
      {comparison && <dl>{[comparison.previous, comparison.current].map(p => <div key={p.period}><dt>{p.period} (UTC)</dt><dd>{p.start} ≤ {tx("订单日期", "order date")} &lt; {p.end_exclusive}</dd></div>)}
        <div><dt>{tx("差额公式", "Difference formula")}</dt><dd>{amount(comparison.current.total_amount)} − {amount(comparison.previous.total_amount)} = {amount(comparison.amount_delta)}</dd></div>
        <div><dt>{tx("变化率公式", "Percentage formula")}</dt><dd>{tx("（本期 − 上期）÷ 上期 × 100%；上期为零时不计算。", "(Current − previous) ÷ previous × 100%; undefined when the previous amount is zero.")}</dd></div></dl>}
      <dl><div><dt>{tx("来源覆盖（首末订单日期，不代表完整）", "Source coverage (first/last orders, not completeness)")}</dt><dd>{report.provenance?.coverage_start || tx("未知", "Unknown")} → {report.provenance?.coverage_end || tx("未知", "Unknown")}</dd></div>
        <div><dt>{tx("导入时间（不是实时同步）", "Imported at (not live sync)")}</dt><dd>{report.provenance?.imported_at || tx("未知", "Unknown")}</dd></div>
        <div><dt>{tx("查询时间", "Queried at")}</dt><dd>{report.generated_at}</dd></div></dl>
      <p>{tx("按去重订单 ID、导入金额 total_amount 汇总，不合并币种。缺月不补零；数据仅限当前账户的当前来源。", "Aggregates deduplicated order IDs and imported total_amount, without merging currencies or zero-filling missing months. Only this account's active source is included.")}</p>
    </details>
    {report.status === "unavailable" && <a href="/data">{tx("前往数据页检查来源", "Check the source on Data")}</a>}
  </section>;
}
