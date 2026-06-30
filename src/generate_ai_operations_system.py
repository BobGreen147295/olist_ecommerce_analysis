from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ai_insight_engine import AIOperationInsightEngine, strategy_for_segment


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "processed"
OUTPUT_PATH = PROJECT_DIR / "dashboard" / "ai_operations_system.html"


def money(value: float) -> str:
    return f"R${value:,.2f}"


def load_data() -> dict:
    customers = pd.read_csv(DATA_DIR / "cleaned_customers.csv")
    orders = pd.read_csv(DATA_DIR / "cleaned_orders.csv")
    payments = pd.read_csv(DATA_DIR / "cleaned_payments.csv")
    order_items = pd.read_csv(DATA_DIR / "cleaned_order_items.csv")
    rfm = pd.read_csv(DATA_DIR / "rfm_analysis.csv")
    clusters = pd.read_csv(DATA_DIR / "user_clusters.csv")
    sales_trends = pd.read_csv(DATA_DIR / "sales_trends.csv")

    orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce")
    orders["month"] = orders["order_purchase_timestamp"].dt.to_period("M").astype(str)

    payment_by_order = (
        payments.groupby("order_id")
        .agg(payment_value=("payment_value", "sum"), payment_type=("payment_type", lambda s: s.mode().iat[0]))
        .reset_index()
    )
    price_by_order = order_items.groupby("order_id").agg(item_revenue=("price", "sum")).reset_index()

    fact = (
        orders[["order_id", "customer_id", "order_status", "month"]]
        .merge(customers[["customer_id", "customer_state", "customer_city"]], on="customer_id", how="left")
        .merge(payment_by_order, on="order_id", how="left")
        .merge(price_by_order, on="order_id", how="left")
    )
    fact["payment_value"] = fact["payment_value"].fillna(0)
    fact["item_revenue"] = fact["item_revenue"].fillna(0)

    monthly_state = (
        fact.groupby(["month", "customer_state", "payment_type", "order_status"], dropna=False)
        .agg(orders=("order_id", "nunique"), revenue=("payment_value", "sum"), item_revenue=("item_revenue", "sum"))
        .reset_index()
    )
    monthly_state = monthly_state.fillna("unknown")

    rfm_with_state = rfm.merge(customers[["customer_id", "customer_state"]], on="customer_id", how="left")
    rfm_summary = (
        rfm_with_state.groupby(["customer_segment", "customer_state"], dropna=False)
        .agg(
            customers=("customer_id", "nunique"),
            avg_recency=("recency", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_monetary=("monetary", "mean"),
            total_monetary=("monetary", "sum"),
        )
        .round(2)
        .reset_index()
    )

    clusters_with_state = clusters.merge(customers[["customer_id", "customer_state"]], on="customer_id", how="left")
    cluster_summary = (
        clusters_with_state.groupby(["cluster", "cluster_label", "customer_state"], dropna=False)
        .agg(customers=("customer_id", "nunique"), avg_spent=("total_spent", "mean"), avg_orders=("order_count", "mean"))
        .round(2)
        .reset_index()
    )

    total_revenue = float(fact["payment_value"].sum())
    region_sales = fact.groupby("customer_state")["payment_value"].sum().sort_values(ascending=False)
    payment_counts = payments["payment_type"].value_counts()
    top_payment_name = payment_counts.index[0]
    top_payment_count = int(payment_counts.iloc[0])
    top_payment_share = float(payment_counts.iloc[0] / payment_counts.sum())
    rfm_counts = rfm["customer_segment"].value_counts()

    engine = AIOperationInsightEngine()
    insights = engine.build_global_insights(
        total_revenue=total_revenue,
        top_regions=[(k, float(v)) for k, v in region_sales.head(5).items()],
        top_payment=(top_payment_name, top_payment_count, top_payment_share),
        high_value_customers=int(rfm_counts.get("高价值", 0)),
        potential_customers=int(rfm_counts.get("潜在高价值", 0)),
        total_customers=int(customers["customer_id"].nunique()),
    )

    return {
        "meta": {
            "totalOrders": int(fact["order_id"].nunique()),
            "totalRevenue": round(total_revenue, 2),
            "totalCustomers": int(customers["customer_id"].nunique()),
            "avgOrderValue": round(total_revenue / max(fact["order_id"].nunique(), 1), 2),
            "states": sorted(fact["customer_state"].dropna().unique().tolist()),
            "months": sorted(fact["month"].dropna().unique().tolist()),
            "segments": ["高价值", "潜在高价值", "一般价值", "低价值"],
            "strategies": {segment: strategy_for_segment(segment) for segment in ["高价值", "潜在高价值", "一般价值", "低价值"]},
        },
        "monthlyState": monthly_state.to_dict("records"),
        "rfm": rfm_summary.to_dict("records"),
        "clusters": cluster_summary.to_dict("records"),
        "salesTrends": sales_trends.to_dict("records"),
        "globalInsights": [insight.__dict__ for insight in insights],
    }


def build_html(payload: dict) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI 电商运营智能系统</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft YaHei", Arial, sans-serif; color: #172033; background: #f4f6f9; }}
    .app {{ display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }}
    aside {{ background: #101827; color: #eef2ff; padding: 22px; position: sticky; top: 0; height: 100vh; }}
    main {{ padding: 24px; }}
    h1 {{ font-size: 23px; margin: 0 0 8px; }}
    h2 {{ font-size: 18px; margin: 0 0 14px; }}
    h3 {{ font-size: 15px; margin: 0 0 8px; }}
    .sub {{ color: #9ca3af; line-height: 1.7; font-size: 13px; margin-bottom: 22px; }}
    label {{ display: block; margin: 16px 0 8px; color: #cbd5e1; font-size: 13px; }}
    select, input {{ width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: #fff; }}
    button {{ width: 100%; margin-top: 18px; padding: 11px; border: 0; border-radius: 6px; background: #2f6fed; color: white; font-weight: 700; cursor: pointer; }}
    .grid {{ display: grid; gap: 16px; }}
    .kpis {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 16px; }}
    .two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 16px; }}
    .three {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 17px; }}
    .kpi-label {{ color: #64748b; font-size: 12px; }}
    .kpi-value {{ font-size: 24px; font-weight: 800; margin-top: 8px; }}
    .kpi-note {{ color: #6b7280; font-size: 12px; margin-top: 7px; }}
    .chart {{ height: 340px; width: 100%; }}
    .insight {{ border-left: 4px solid #2f6fed; padding: 12px 14px; background: #f8fafc; border-radius: 6px; margin-bottom: 10px; }}
    .insight strong {{ display: inline-block; margin-right: 8px; color: #1d4ed8; }}
    .insight p {{ margin: 5px 0 0; color: #4b5563; line-height: 1.7; }}
    .pill {{ display: inline-flex; padding: 5px 8px; border-radius: 999px; background: #eaf2ff; color: #1d4ed8; font-size: 12px; }}
    .table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .table th, .table td {{ padding: 9px; border-bottom: 1px solid #e5e7eb; text-align: left; }}
    .table th {{ background: #f8fafc; color: #475569; }}
    .talk {{ line-height: 1.8; color: #374151; }}
    @media (max-width: 1000px) {{ .app {{ grid-template-columns: 1fr; }} aside {{ position: static; height: auto; }} .kpis, .two, .three {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<div class="app">
  <aside>
    <h1>AI 电商运营智能系统</h1>
    <div class="sub">动态筛选订单、地区和客群，实时生成经营指标、AI 诊断、运营策略和活动模拟结果。</div>
    <label>地区</label>
    <select id="stateFilter"></select>
    <label>客户分层</label>
    <select id="segmentFilter"></select>
    <label>开始月份</label>
    <select id="startMonth"></select>
    <label>结束月份</label>
    <select id="endMonth"></select>
    <label>活动预算（R$）</label>
    <input id="budgetInput" type="number" value="50000" min="0" step="1000">
    <button onclick="render()">生成 AI 运营诊断</button>
  </aside>
  <main>
    <section class="grid kpis">
      <div class="card"><div class="kpi-label">筛选订单数</div><div class="kpi-value" id="kpiOrders">-</div><div class="kpi-note">动态口径</div></div>
      <div class="card"><div class="kpi-label">筛选销售额</div><div class="kpi-value" id="kpiRevenue">-</div><div class="kpi-note">支付金额</div></div>
      <div class="card"><div class="kpi-label">平均客单价</div><div class="kpi-value" id="kpiAov">-</div><div class="kpi-note">销售额 / 订单数</div></div>
      <div class="card"><div class="kpi-label">AI 优先动作</div><div class="kpi-value" id="kpiAction">-</div><div class="kpi-note">按当前筛选自动判断</div></div>
    </section>

    <section class="grid two">
      <div class="card"><h2>动态销售趋势</h2><div id="trendChart" class="chart"></div></div>
      <div class="card"><h2>支付方式结构</h2><div id="paymentChart" class="chart"></div></div>
    </section>

    <section class="grid two">
      <div class="card"><h2>客户价值分层</h2><div id="segmentChart" class="chart"></div></div>
      <div class="card"><h2>AI 运营诊断</h2><div id="insights"></div></div>
    </section>

    <section class="grid two">
      <div class="card"><h2>活动模拟器</h2><div id="campaignSim" class="talk"></div></div>
      <div class="card"><h2>面试讲解提示</h2><div class="talk" id="talkTrack"></div></div>
    </section>

    <section class="card">
      <h2>用户聚类钻取</h2>
      <table class="table" id="clusterTable"></table>
    </section>
  </main>
</div>
<script>
const payload = {payload_json};
const fmtMoney = v => "R$" + Number(v || 0).toLocaleString(undefined, {{maximumFractionDigits: 2}});
const fmtNum = v => Number(v || 0).toLocaleString();

function initFilters() {{
  const state = document.getElementById("stateFilter");
  state.innerHTML = ["全部", ...payload.meta.states].map(v => `<option>${{v}}</option>`).join("");
  const segment = document.getElementById("segmentFilter");
  segment.innerHTML = ["全部", ...payload.meta.segments].map(v => `<option>${{v}}</option>`).join("");
  const start = document.getElementById("startMonth");
  const end = document.getElementById("endMonth");
  start.innerHTML = payload.meta.months.map(v => `<option>${{v}}</option>`).join("");
  end.innerHTML = payload.meta.months.map(v => `<option>${{v}}</option>`).join("");
  start.value = payload.meta.months[0];
  end.value = payload.meta.months[payload.meta.months.length - 1];
}}

function selected() {{
  return {{
    state: document.getElementById("stateFilter").value,
    segment: document.getElementById("segmentFilter").value,
    start: document.getElementById("startMonth").value,
    end: document.getElementById("endMonth").value,
    budget: Number(document.getElementById("budgetInput").value || 0)
  }};
}}

function filterMonthly(sel) {{
  return payload.monthlyState.filter(r =>
    (sel.state === "全部" || r.customer_state === sel.state) &&
    r.month >= sel.start && r.month <= sel.end
  );
}}

function filterRfm(sel) {{
  return payload.rfm.filter(r =>
    (sel.state === "全部" || r.customer_state === sel.state) &&
    (sel.segment === "全部" || r.customer_segment === sel.segment)
  );
}}

function sumBy(rows, key, valueKey) {{
  const out = {{}};
  rows.forEach(r => out[r[key]] = (out[r[key]] || 0) + Number(r[valueKey] || 0));
  return out;
}}

function topEntry(obj) {{
  return Object.entries(obj).sort((a,b) => b[1] - a[1])[0] || ["-", 0];
}}

function render() {{
  const sel = selected();
  const rows = filterMonthly(sel);
  const rfmRows = filterRfm(sel);
  const orders = rows.reduce((s,r) => s + Number(r.orders || 0), 0);
  const revenue = rows.reduce((s,r) => s + Number(r.revenue || 0), 0);
  const aov = revenue / Math.max(orders, 1);
  const payment = sumBy(rows, "payment_type", "orders");
  const monthly = sumBy(rows, "month", "revenue");
  const segmentCustomers = sumBy(rfmRows, "customer_segment", "customers");
  const topPay = topEntry(payment);
  const topSegment = topEntry(segmentCustomers);
  const action = sel.segment !== "全部" ? payload.meta.strategies[sel.segment].goal : "分层运营";

  document.getElementById("kpiOrders").textContent = fmtNum(orders);
  document.getElementById("kpiRevenue").textContent = fmtMoney(revenue);
  document.getElementById("kpiAov").textContent = fmtMoney(aov);
  document.getElementById("kpiAction").textContent = action;

  drawLine("trendChart", Object.keys(monthly).sort(), Object.keys(monthly).sort().map(m => monthly[m]));
  drawPie("paymentChart", payment);
  drawPie("segmentChart", segmentCustomers);
  renderInsights(sel, revenue, orders, aov, topPay, topSegment, rfmRows);
  renderCampaign(sel, revenue, rfmRows);
  renderClusters(sel);
  renderTalk(sel, revenue, orders, topSegment);
}}

function drawLine(id, x, y) {{
  const chart = echarts.init(document.getElementById(id));
  chart.setOption({{
    tooltip: {{ trigger: "axis", valueFormatter: fmtMoney }},
    grid: {{ left: 70, right: 20, top: 28, bottom: 58 }},
    xAxis: {{ type: "category", data: x, axisLabel: {{ rotate: 40 }} }},
    yAxis: {{ type: "value", axisLabel: {{ formatter: v => (v/1000000).toFixed(1) + "M" }} }},
    series: [{{ type: "line", smooth: true, areaStyle: {{}}, data: y, color: "#2f6fed" }}]
  }});
}}

function drawPie(id, obj) {{
  const chart = echarts.init(document.getElementById(id));
  chart.setOption({{
    tooltip: {{ trigger: "item" }},
    legend: {{ bottom: 0 }},
    series: [{{ type: "pie", radius: ["42%", "68%"], data: Object.entries(obj).map(([name,value]) => ({{name,value}})) }}]
  }});
}}

function renderInsights(sel, revenue, orders, aov, topPay, topSegment, rfmRows) {{
  const insights = [];
  const paymentShare = topPay[1] / Math.max(orders, 1);
  insights.push({{
    title: "当前筛选经营表现",
    level: revenue > 1000000 ? "高价值样本" : "需要继续放大样本",
    evidence: `当前口径销售额 ${{fmtMoney(revenue)}}，订单 ${{fmtNum(orders)}}，客单价 ${{fmtMoney(aov)}}。`,
    action: revenue > 1000000 ? "优先复盘高销售月份和核心地区，复制有效活动。" : "建议扩大时间范围或对比其他地区，避免样本过小误判。"
  }});
  insights.push({{
    title: "支付转化入口",
    level: "转化优化",
    evidence: `${{topPay[0]}} 是当前主支付方式，占订单约 ${{(paymentShare*100).toFixed(1)}}%。`,
    action: "可以设计支付优惠、满减门槛或分期免息，观察支付结构和客单价变化。"
  }});
  if (topSegment[0] !== "-") {{
    insights.push({{
      title: "重点运营客群",
      level: "人群运营",
      evidence: `当前最大客群是 ${{topSegment[0]}}，约 ${{fmtNum(topSegment[1])}} 人。`,
      action: payload.meta.strategies[topSegment[0]] ? payload.meta.strategies[topSegment[0]].action : "按 RFM 分层设计差异化触达。"
    }});
  }}
  document.getElementById("insights").innerHTML = insights.map(i => `
    <div class="insight"><h3><strong>${{i.level}}</strong>${{i.title}}</h3><p>${{i.evidence}}</p><p>${{i.action}}</p></div>
  `).join("");
}}

function renderCampaign(sel, revenue, rfmRows) {{
  const segment = sel.segment === "全部" ? "潜在高价值" : sel.segment;
  const strategy = payload.meta.strategies[segment] || payload.meta.strategies["一般价值"];
  const customers = rfmRows.reduce((s,r) => s + Number(r.customers || 0), 0) || 1;
  const conversion = segment === "高价值" ? 0.08 : segment === "潜在高价值" ? 0.06 : segment === "低价值" ? 0.015 : 0.035;
  const expectedOrders = Math.round(customers * conversion);
  const expectedRevenue = expectedOrders * (revenue / Math.max(1, filterMonthly(sel).reduce((s,r)=>s+Number(r.orders||0),0))) + sel.budget * 0.18;
  document.getElementById("campaignSim").innerHTML = `
    <p><span class="pill">模拟客群：${{segment}}</span></p>
    <p><strong>目标：</strong>${{strategy.goal}}</p>
    <p><strong>动作：</strong>${{strategy.action}}</p>
    <p><strong>预计新增订单：</strong>${{fmtNum(expectedOrders)}} 单</p>
    <p><strong>预计拉动销售额：</strong>${{fmtMoney(expectedRevenue)}}</p>
    <p><strong>可用触达话术：</strong>${{strategy.copy}}</p>
  `;
}}

function renderClusters(sel) {{
  const rows = payload.clusters.filter(r => sel.state === "全部" || r.customer_state === sel.state)
    .sort((a,b) => b.customers - a.customers)
    .slice(0, 8);
  document.getElementById("clusterTable").innerHTML = `
    <thead><tr><th>聚类</th><th>标签</th><th>地区</th><th>客户数</th><th>平均消费</th><th>平均订单</th><th>运营打法</th></tr></thead>
    <tbody>${{rows.map(r => `<tr><td>${{r.cluster}}</td><td>${{r.cluster_label}}</td><td>${{r.customer_state}}</td><td>${{fmtNum(r.customers)}}</td><td>${{fmtMoney(r.avg_spent)}}</td><td>${{Number(r.avg_orders).toFixed(2)}}</td><td>按消费能力和购买频次做差异化券包</td></tr>`).join("")}}</tbody>
  `;
}}

function renderTalk(sel, revenue, orders, topSegment) {{
  const scope = `${{sel.state === "全部" ? "全站" : sel.state + " 地区"}}，${{sel.segment === "全部" ? "全部客群" : sel.segment + "客群"}}`;
  document.getElementById("talkTrack").innerHTML = `
    <p>“这里不是静态报表，而是动态 AI 运营系统。我可以切换地区、客群和月份，系统会实时重算订单、销售额、客单价，并生成诊断建议。”</p>
    <p>“当前筛选口径是 <strong>${{scope}}</strong>，销售额为 <strong>${{fmtMoney(revenue)}}</strong>，订单数为 <strong>${{fmtNum(orders)}}</strong>。系统识别出的重点客群是 <strong>${{topSegment[0]}}</strong>。”</p>
    <p>“这些结果可以直接服务运营动作：预算投放、会员复购、优惠券召回、支付优惠和活动复盘。”</p>
  `;
}}

initFilters();
render();
</script>
</body>
</html>
"""


def main() -> None:
    payload = load_data()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_html(payload), encoding="utf-8")
    print(f"Generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
