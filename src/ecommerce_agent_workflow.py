from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "processed"
REPORT_DIR = PROJECT_DIR / "reports"
DASHBOARD_DIR = PROJECT_DIR / "dashboard"


def money(value: float) -> str:
    return f"R${value:,.2f}"


def percent(value: float) -> str:
    return f"{value:.1%}"


@dataclass
class AgentFinding:
    agent: str
    priority: str
    title: str
    evidence: str
    recommendation: str
    next_action: str
    metric_snapshot: dict[str, Any]


class EcommerceDataMart:
    """Load processed Olist data and expose ecommerce operation metrics."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir

    def load(self) -> dict[str, pd.DataFrame]:
        customers = pd.read_csv(self.data_dir / "cleaned_customers.csv")
        orders = pd.read_csv(self.data_dir / "cleaned_orders.csv")
        payments = pd.read_csv(self.data_dir / "cleaned_payments.csv")
        order_items = pd.read_csv(self.data_dir / "cleaned_order_items.csv")
        rfm = pd.read_csv(self.data_dir / "rfm_analysis.csv")
        clusters = pd.read_csv(self.data_dir / "user_clusters.csv")
        sales_trends = pd.read_csv(self.data_dir / "sales_trends.csv")

        orders["order_purchase_timestamp"] = pd.to_datetime(
            orders["order_purchase_timestamp"], errors="coerce"
        )
        orders["month"] = orders["order_purchase_timestamp"].dt.to_period("M").astype(str)

        payment_by_order = (
            payments.groupby("order_id")
            .agg(
                payment_value=("payment_value", "sum"),
                payment_type=("payment_type", lambda s: s.mode().iat[0]),
                payment_installments=("payment_installments", "max"),
            )
            .reset_index()
        )
        item_by_order = (
            order_items.groupby("order_id")
            .agg(item_revenue=("price", "sum"), freight_value=("freight_value", "sum"))
            .reset_index()
        )
        fact_orders = (
            orders[["order_id", "customer_id", "order_status", "month"]]
            .merge(customers[["customer_id", "customer_state", "customer_city"]], on="customer_id", how="left")
            .merge(payment_by_order, on="order_id", how="left")
            .merge(item_by_order, on="order_id", how="left")
        )
        fact_orders[["payment_value", "item_revenue", "freight_value"]] = fact_orders[
            ["payment_value", "item_revenue", "freight_value"]
        ].fillna(0)

        return {
            "customers": customers,
            "orders": orders,
            "payments": payments,
            "order_items": order_items,
            "rfm": rfm,
            "clusters": clusters,
            "sales_trends": sales_trends,
            "fact_orders": fact_orders,
        }


class BusinessMonitorAgent:
    name = "经营监控智能体"

    def run(self, data: dict[str, pd.DataFrame]) -> AgentFinding:
        fact = data["fact_orders"]
        monthly = fact.groupby("month").agg(orders=("order_id", "nunique"), revenue=("payment_value", "sum"))
        median_orders = monthly["orders"].median()
        complete_monthly = monthly[monthly["orders"] >= median_orders * 0.25]
        if len(complete_monthly) < 2:
            complete_monthly = monthly
        latest = complete_monthly.tail(1).iloc[0]
        previous = complete_monthly.tail(2).head(1).iloc[0] if len(complete_monthly) > 1 else latest
        revenue_change = (latest["revenue"] - previous["revenue"]) / previous["revenue"] if previous["revenue"] else 0
        order_change = (latest["orders"] - previous["orders"]) / previous["orders"] if previous["orders"] else 0
        avg_order_value = fact["payment_value"].sum() / max(fact["order_id"].nunique(), 1)

        if revenue_change < -0.15:
            priority = "P0"
            title = "最近月份销售额明显下滑，需要优先排查"
            action = "对比上月流量、库存、价格、履约和活动节奏，先定位下滑来源。"
        elif revenue_change > 0.15:
            priority = "P1"
            title = "最近月份销售额明显增长，适合复盘放大"
            action = "复盘增长月份的地区、支付方式和客户分层，把有效策略复制到相似地区。"
        else:
            priority = "P2"
            title = "整体经营相对稳定，可从客群和地区寻找增量"
            action = "优先做高价值客户复购和重点地区转化优化。"

        return AgentFinding(
            agent=self.name,
            priority=priority,
            title=title,
            evidence=(
                f"最近月份销售额环比 {percent(revenue_change)}，订单数环比 {percent(order_change)}，"
                f"全局平均客单价 {money(avg_order_value)}。"
            ),
            recommendation="用月度经营指标先判断业务波动，再决定是排查异常还是放大增长策略。",
            next_action=action,
            metric_snapshot={
                "latest_month": monthly.index[-1],
                "analysis_month": complete_monthly.index[-1],
                "latest_revenue": round(float(latest["revenue"]), 2),
                "latest_orders": int(latest["orders"]),
                "revenue_change": round(float(revenue_change), 4),
                "order_change": round(float(order_change), 4),
                "avg_order_value": round(float(avg_order_value), 2),
            },
        )


class CustomerSegmentAgent:
    name = "客户分层智能体"

    def run(self, data: dict[str, pd.DataFrame]) -> AgentFinding:
        rfm = data["rfm"]
        counts = rfm["customer_segment"].value_counts()
        monetary = rfm.groupby("customer_segment")["monetary"].mean().sort_values(ascending=False)
        total_customers = len(rfm)
        high_value = int(counts.get("高价值", 0))
        potential = int(counts.get("潜在高价值", 0))
        high_value_share = high_value / total_customers if total_customers else 0
        potential_share = potential / total_customers if total_customers else 0

        return AgentFinding(
            agent=self.name,
            priority="P1",
            title="客户运营应优先围绕高价值和潜在高价值人群设计",
            evidence=(
                f"高价值客户 {high_value:,} 人，占比 {percent(high_value_share)}；"
                f"潜在高价值客户 {potential:,} 人，占比 {percent(potential_share)}。"
            ),
            recommendation=(
                "高价值客户做会员权益和复购激励；潜在高价值客户做优惠券召回、关联推荐和限时活动；"
                "低价值客户控制补贴成本。"
            ),
            next_action="建立三套触达策略：复购礼券、二次购买券、低成本内容唤醒，并分别跟踪转化率。",
            metric_snapshot={
                "segment_counts": {str(k): int(v) for k, v in counts.items()},
                "avg_monetary_by_segment": {str(k): round(float(v), 2) for k, v in monetary.items()},
            },
        )


class RegionalGrowthAgent:
    name = "地区增长智能体"

    def run(self, data: dict[str, pd.DataFrame]) -> AgentFinding:
        fact = data["fact_orders"]
        region_sales = fact.groupby("customer_state")["payment_value"].sum().sort_values(ascending=False)
        total = float(region_sales.sum())
        top3 = region_sales.head(3)
        top3_share = float(top3.sum() / total) if total else 0
        top_regions = "、".join(top3.index.tolist())

        if top3_share > 0.55:
            priority = "P1"
            title = "地区销售集中度高，核心地区值得继续深挖"
        else:
            priority = "P2"
            title = "地区分布相对分散，可做多地区投放测试"

        return AgentFinding(
            agent=self.name,
            priority=priority,
            title=title,
            evidence=f"TOP3 地区 {top_regions} 贡献 {percent(top3_share)} 销售额。",
            recommendation="核心地区优先做广告投放、爆品活动和仓配优化；长尾地区用小预算测试增量。",
            next_action=f"先为 {top_regions} 制定一轮地区专项活动，并对比活动前后客单价和订单数。",
            metric_snapshot={
                "top_regions": {str(k): round(float(v), 2) for k, v in top3.items()},
                "top3_share": round(top3_share, 4),
            },
        )


class PaymentConversionAgent:
    name = "支付转化智能体"

    def run(self, data: dict[str, pd.DataFrame]) -> AgentFinding:
        payments = data["payments"]
        payment_counts = payments["payment_type"].value_counts()
        payment_values = payments.groupby("payment_type")["payment_value"].sum().sort_values(ascending=False)
        top_payment = payment_counts.index[0]
        top_share = payment_counts.iloc[0] / payment_counts.sum()
        installment_avg = payments["payment_installments"].mean()

        return AgentFinding(
            agent=self.name,
            priority="P2",
            title="支付方式可以作为转化率和客单价优化入口",
            evidence=(
                f"{top_payment} 是主流支付方式，占比 {percent(float(top_share))}；"
                f"平均分期期数 {installment_avg:.2f}。"
            ),
            recommendation="围绕主流支付方式设计支付优惠、满减门槛或分期免息，观察支付结构和客单价变化。",
            next_action="做一次支付优惠 A/B 测试：核心地区展示支付优惠，对照组保持原价，比较支付转化和客单价。",
            metric_snapshot={
                "payment_counts": {str(k): int(v) for k, v in payment_counts.items()},
                "payment_values": {str(k): round(float(v), 2) for k, v in payment_values.items()},
                "avg_installments": round(float(installment_avg), 2),
            },
        )


class CampaignPlannerAgent:
    name = "活动策略智能体"

    def run(self, data: dict[str, pd.DataFrame], previous_findings: list[AgentFinding]) -> AgentFinding:
        rfm = data["rfm"]
        fact = data["fact_orders"]
        avg_order_value = fact["payment_value"].sum() / max(fact["order_id"].nunique(), 1)
        potential_count = int(rfm["customer_segment"].value_counts().get("潜在高价值", 0))
        assumed_conversion = 0.035
        expected_orders = round(potential_count * assumed_conversion)
        expected_revenue = expected_orders * avg_order_value

        return AgentFinding(
            agent=self.name,
            priority="P1",
            title="优先上线潜在高价值客户二次购买活动",
            evidence=(
                f"潜在高价值客户池约 {potential_count:,} 人；按 {percent(assumed_conversion)} 保守转化估算，"
                f"可带来约 {expected_orders:,} 单，预计销售额 {money(expected_revenue)}。"
            ),
            recommendation="用限时券、关联推荐和加购提醒促进二次购买，预算优先投向核心地区的潜在高价值客户。",
            next_action="活动方案：目标人群=潜在高价值客户；权益=满减券；周期=7 天；指标=领取率、核销率、复购率、客单价。",
            metric_snapshot={
                "target_segment": "潜在高价值",
                "target_customers": potential_count,
                "assumed_conversion": assumed_conversion,
                "expected_orders": expected_orders,
                "expected_revenue": round(float(expected_revenue), 2),
            },
        )


class ExecutiveSummaryAgent:
    name = "运营总监智能体"

    def run(self, findings: list[AgentFinding]) -> dict[str, Any]:
        priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        ordered = sorted(findings, key=lambda item: priority_rank.get(item.priority, 9))
        top_actions = [finding.next_action for finding in ordered[:3]]
        return {
            "agent": self.name,
            "summary": "系统已从经营、客户、地区、支付和活动五个角度完成诊断，建议优先做人群分层运营和核心地区增长实验。",
            "top_actions": top_actions,
            "ordered_findings": [asdict(finding) for finding in ordered],
        }


class EcommerceAgentWorkflow:
    def __init__(self) -> None:
        self.data_mart = EcommerceDataMart()
        self.monitor_agent = BusinessMonitorAgent()
        self.customer_agent = CustomerSegmentAgent()
        self.region_agent = RegionalGrowthAgent()
        self.payment_agent = PaymentConversionAgent()
        self.campaign_agent = CampaignPlannerAgent()
        self.summary_agent = ExecutiveSummaryAgent()

    def run(self) -> dict[str, Any]:
        data = self.data_mart.load()
        findings = [
            self.monitor_agent.run(data),
            self.customer_agent.run(data),
            self.region_agent.run(data),
            self.payment_agent.run(data),
        ]
        findings.append(self.campaign_agent.run(data, findings))
        summary = self.summary_agent.run(findings)
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "workflow": "AI 电商运营多智能体工作流",
            "summary": summary,
        }


def write_outputs(result: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    json_path = REPORT_DIR / "agent_workflow_result.json"
    md_path = REPORT_DIR / "agent_workflow_report.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    findings = result["summary"]["ordered_findings"]
    lines = [
        "# AI 电商运营多智能体工作流报告",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 总结",
        "",
        result["summary"]["summary"],
        "",
        "## 优先行动",
        "",
    ]
    for index, action in enumerate(result["summary"]["top_actions"], 1):
        lines.append(f"{index}. {action}")
    lines.extend(["", "## 智能体诊断详情", ""])
    for finding in findings:
        lines.extend(
            [
                f"### [{finding['priority']}] {finding['agent']}：{finding['title']}",
                "",
                f"- 证据：{finding['evidence']}",
                f"- 建议：{finding['recommendation']}",
                f"- 下一步：{finding['next_action']}",
                "",
            ]
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    workflow = EcommerceAgentWorkflow()
    result = workflow.run()
    write_outputs(result)
    print("Agent workflow finished.")
    print(REPORT_DIR / "agent_workflow_report.md")
    print(REPORT_DIR / "agent_workflow_result.json")


if __name__ == "__main__":
    main()
