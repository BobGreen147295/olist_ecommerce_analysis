"""
支付分析 & 营销建议模块

输出:
- 支付方式分布
- 分期 vs 一次性的客单价差异
- 分期专属优惠的 ROI 估算
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)

import sys

if str(PROJECT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "src"))


def payment_distribution(fact_orders: pd.DataFrame) -> pd.DataFrame:
    """各支付方式的订单数、占比、平均分期数、客单价"""
    if "payment_type" not in fact_orders.columns:
        return pd.DataFrame()

    stats = (
        fact_orders.dropna(subset=["payment_type"])
        .groupby("payment_type")
        .agg(
            order_count=("order_id", "nunique"),
            total_revenue=("payment_value", "sum"),
            avg_installments=("payment_installments", "mean"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
    )
    stats["aov"] = (stats["total_revenue"] / stats["order_count"]).round(2)
    stats["order_share"] = (stats["order_count"] / stats["order_count"].sum()).round(4)
    stats["revenue_share"] = (stats["total_revenue"] / stats["total_revenue"].sum()).round(4)
    return stats


def installment_analysis(fact_orders: pd.DataFrame) -> pd.DataFrame:
    """分期行为分析：按分期数拆分 AOV"""
    if "payment_installments" not in fact_orders.columns:
        return pd.DataFrame()

    install = (
        fact_orders[
            (fact_orders["payment_type"] == "credit_card")
            & (fact_orders["payment_installments"] > 0)
        ]
        .groupby("payment_installments")
        .agg(
            order_count=("order_id", "nunique"),
            avg_value=("payment_value", "mean"),
            total_value=("payment_value", "sum"),
        )
        .reset_index()
        .sort_values("payment_installments")
    )
    return install


def generate_payment_recommendations(
    pay_stats: pd.DataFrame, install_stats: pd.DataFrame,
) -> list[dict]:
    """生成支付策略建议"""
    recs: list[dict] = []

    if pay_stats.empty:
        return recs

    credit_row = pay_stats[pay_stats["payment_type"] == "credit_card"]
    if len(credit_row) > 0:
        credit_share = float(credit_row.iloc[0]["revenue_share"])
        credit_aov = float(credit_row.iloc[0]["aov"])
        overall_aov = float(pay_stats["total_revenue"].sum() / pay_stats["order_count"].sum())

        if credit_share > 0.4 and credit_aov < overall_aov * 1.2:
            # 信用卡占比高但客单价不够高 → 分期优惠
            recs.append({
                "type": "installment_promotion",
                "title": "信用卡占比高但客单价偏低，推出「大额分期 0 利息」",
                "goal": "提升信用卡客单价 10%+",
                "evidence": (
                    f"信用卡营收占比 {credit_share:.1%}，"
                    f"客单价 R${credit_aov:,.2f}（整体 R${overall_aov:,.2f}）"
                ),
                "actions": [
                    "满 R$299 享 6 期免息，满 R$599 享 12 期免息",
                    "在 PDP（商品详情页）展示「x 期免息」标签，强化感知",
                    "与发卡行合作额外返现（如 Itaú/Bradesco 卡 5% off）",
                ],
                "expected": {
                    "aov_increase": "8-12%",
                    "big_ticket_product_boost": "电子/家居品类 +15-20%",
                },
                "priority": "P1",
            })

    boleto_row = pay_stats[pay_stats["payment_type"] == "boleto"]
    if len(boleto_row) > 0:
        share = float(boleto_row.iloc[0]["revenue_share"])
        if share > 0.1:
            # Boleto 占比高 → 过期率/弃单率高，用 Pix 替代
            recs.append({
                "type": "pix_promotion",
                "title": f"Boleto 占比 {share:.1%}，引导迁移 Pix 降低弃单",
                "goal": "Boleto → Pix 转化率提升 30%，降低支付弃单率",
                "evidence": f"Boleto 营收占比 {share:.1%}（平均弃单率 20-40%，Pix < 5%）",
                "actions": [
                    "Pix 支付额外 2% off 或赠送优惠券",
                    "Boleto 生成后 24h 自动推送 Pix 快捷支付链接（WhatsApp/邮件）",
                    "优化 Checkout：Pix 按钮放在信用卡下方第二优先级",
                ],
                "expected": {
                    "payment_abandonment_reduction": "5-8 个百分点",
                    "pix_share_increase": "+10 个百分点",
                },
                "priority": "P1",
            })

    # 分期层级分析
    if not install_stats.empty:
        large_installs = install_stats[install_stats["payment_installments"] >= 6]
        if len(large_installs) > 0:
            total_large_orders = int(large_installs["order_count"].sum())
            recs.append({
                "type": "high_installment_support",
                "title": f"{total_large_orders:,} 单使用 6+ 期分期，支持大额品类",
                "goal": "培育大额消费习惯",
                "evidence": f"6+ 期分期订单 {total_large_orders:,} 笔",
                "actions": [
                    "电子/家电品类推出 12 期 0 利息专属 banner",
                    "高价值品类上线「分期对比计算器」帮助决策",
                    "CRM 对分期大额用户推送家电/电子新品推荐",
                ],
                "expected": {
                    "big_ticket_growth": "10-15%",
                    "repurchase_of_high_value": "+5%",
                },
                "priority": "P2",
            })

    logger.info(f"已生成 {len(recs)} 条支付策略建议")
    return recs


def run(fact_orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    stats = payment_distribution(fact_orders)
    install = installment_analysis(fact_orders)
    recs = generate_payment_recommendations(stats, install)
    return stats, install, recs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 50)
    print("  支付分析 & 营销建议模块")
    print("=" * 50)

    from data_cleaning import build_fact_table, load_raw_data, clean_orders, clean_payments
    customers, orders, payments, order_items = load_raw_data()
    orders = clean_orders(orders)
    payments = clean_payments(payments)
    fact = build_fact_table(customers, orders, payments, order_items)

    pay_stats, install_stats, recs = run(fact)

    print("\n支付方式分布:")
    print(pay_stats.to_string())

    if not install_stats.empty:
        print("\n分期行为（前10档）:")
        print(install_stats.head(10).to_string())

    print("\n支付策略建议:")
    for r in recs:
        print(f"\n[{r['priority']}] {r['title']}")
        print(f"  目标: {r['goal']}")
        if "evidence" in r:
            print(f"  数据: {r['evidence']}")
        for a in r["actions"]:
            print(f"    • {a}")
        print(f"  预期: {r['expected']}")


if __name__ == "__main__":
    main()
