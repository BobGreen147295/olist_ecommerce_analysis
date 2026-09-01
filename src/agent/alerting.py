"""主动经营预警：基于确定性数据规则生成可核验的运营待办。"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _month_label(year: int, month: int) -> str:
    return f"{int(year)}-{int(month):02d}"


def generate_operational_alerts(
    sales_trends: pd.DataFrame,
    rfm_analysis: pd.DataFrame,
    region_analysis: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[str]]:
    """返回预警与数据质量说明，不依赖 LLM，也不自动执行运营动作。"""
    alerts: list[dict[str, Any]] = []
    data_notes: list[str] = []

    if not sales_trends.empty and {"year", "month", "order_count", "total_sales"}.issubset(sales_trends.columns):
        monthly = (
            sales_trends.groupby(["year", "month"], as_index=False)
            .agg(order_count=("order_count", "sum"), total_sales=("total_sales", "sum"))
            .sort_values(["year", "month"])
            .reset_index(drop=True)
        )
        while len(monthly) >= 4:
            latest = monthly.iloc[-1]
            baseline_orders = monthly.iloc[-4:-1]["order_count"].median()
            if baseline_orders and latest["order_count"] < baseline_orders * 0.5:
                data_notes.append(
                    f"已排除 {_month_label(latest['year'], latest['month'])}：订单量 {int(latest['order_count']):,}，"
                    f"不足前 3 个完整月中位数的 50%，疑似未完成数据。"
                )
                monthly = monthly.iloc[:-1].reset_index(drop=True)
            else:
                break
        if len(monthly) >= 2:
            current, previous = monthly.iloc[-1], monthly.iloc[-2]
            sales_change = (current["total_sales"] / previous["total_sales"] - 1) if previous["total_sales"] else 0.0
            order_change = (current["order_count"] / previous["order_count"] - 1) if previous["order_count"] else 0.0
            if sales_change <= -0.08:
                severity = "high" if sales_change <= -0.15 else "medium"
                current_label = _month_label(current["year"], current["month"])
                previous_label = _month_label(previous["year"], previous["month"])
                alerts.append({
                    "id": "sales_decline", "severity": severity, "category": "销售异常",
                    "title": f"{current_label} 销售额环比下降 {abs(sales_change):.1%}",
                    "evidence": (
                        f"销售额从 {previous_label} 的 R$ {previous['total_sales']:,.0f} 降至 "
                        f"R$ {current['total_sales']:,.0f}；订单量环比 {order_change:+.1%}。"
                    ),
                    "impact": f"最近完整月订单 {int(current['order_count']):,} 笔，需定位地区、支付或客群变化。",
                    "suggested_action": "先拆解地区与支付方式，再对高价值沉睡客户做小规模召回验证。",
                    "source": "sales_trends.csv（按州月度数据聚合）",
                    "agent_question": f"请深度诊断 {current_label} 销售额环比下降的原因，重点拆解地区、支付方式和客户价值分层。",
                })

    if not rfm_analysis.empty and {"recency", "rfm_score", "monetary"}.issubset(rfm_analysis.columns):
        frame = rfm_analysis.copy()
        recency = pd.to_numeric(frame["recency"], errors="coerce")
        score = pd.to_numeric(frame["rfm_score"], errors="coerce")
        value_threshold = score.quantile(0.75)
        dormant = frame[(recency >= 180) & (score >= value_threshold)]
        dormant_share = len(dormant) / len(frame) if len(frame) else 0.0
        if len(dormant) and dormant_share >= 0.05:
            potential_value = pd.to_numeric(dormant["monetary"], errors="coerce").fillna(0).sum()
            alerts.append({
                "id": "high_value_dormant_customers", "severity": "medium", "category": "客户召回",
                "title": f"发现 {len(dormant):,} 位高价值沉睡客户",
                "evidence": (
                    f"RFM 评分位于前 25%，且距上次购买至少 180 天，占客户 {dormant_share:.1%}；"
                    f"历史累计消费 R$ {potential_value:,.0f}。"
                ),
                "impact": "该人群具备较高历史价值，但存在长期未复购风险。",
                "suggested_action": "以小样本邮件优惠券建立 A/B 测试，观察 7 天复购提升和 ROI。",
                "source": "rfm_analysis.csv（RFM 评分、消费金额与最近购买间隔）",
                "agent_question": "请分析高价值沉睡客户的规模与召回优先级，并生成一个可验证的 A/B 测试任务草稿。",
            })

    if not region_analysis.empty and {"state", "sales_per_capita"}.issubset(region_analysis.columns):
        frame = region_analysis.copy()
        frame["sales_per_capita"] = pd.to_numeric(frame["sales_per_capita"], errors="coerce")
        frame = frame.dropna(subset=["sales_per_capita"])
        if len(frame) >= 3:
            lowest = frame.nsmallest(1, "sales_per_capita").iloc[0]
            median_value = frame["sales_per_capita"].median()
            if median_value and lowest["sales_per_capita"] <= median_value * 0.7:
                state = str(lowest["state"])
                gap = 1 - lowest["sales_per_capita"] / median_value
                alerts.append({
                    "id": f"regional_efficiency_{state.lower()}", "severity": "low", "category": "地区机会",
                    "title": f"{state} 州人均销售效率低于样本中位数 {gap:.1%}",
                    "evidence": (
                        f"{state} 州每百万人销售额 R$ {lowest['sales_per_capita']:,.0f}，"
                        f"样本州中位数为 R$ {median_value:,.0f}。"
                    ),
                    "impact": "该州存在渠道覆盖、商品匹配或支付转化的提升空间。",
                    "suggested_action": "先用区域定向活动验证支付和品类策略，不直接扩大预算。",
                    "source": "region_analysis.csv（州级销售额与人口数据）",
                    "agent_question": f"请分析 {state} 州销售效率偏低的可能原因，并给出低风险验证策略。",
                })

    priority = {"high": 0, "medium": 1, "low": 2}
    return sorted(alerts, key=lambda item: priority[item["severity"]]), data_notes
