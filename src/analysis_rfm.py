"""
RFM 客户价值分析模块

R = Recency (最近购买时间)
F = Frequency (购买频次)
M = Monetary (购买金额)

输出:
- RFM 评分结果与客户分层
- 各群体业务特征分析
- 可执行商业建议
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "processed"

import sys

if str(PROJECT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "src"))

logger = logging.getLogger(__name__)


@dataclass
class RFMResult:
    rfm_data: pd.DataFrame
    segment_counts: dict
    segment_analysis: pd.DataFrame

    def to_csv(self, save_path: Path) -> None:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        self.rfm_data.to_csv(save_path, index=False)
        logger.info(f"RFM 结果已保存: {save_path}")


def _build_base_table(
    fact_orders: Optional[pd.DataFrame] = None,
    customers: Optional[pd.DataFrame] = None,
    orders: Optional[pd.DataFrame] = None,
    payments: Optional[pd.DataFrame] = None,
    order_items: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """构建 RFM 基础表：customer_id + 最近购买日期 + 次数 + 金额"""
    if fact_orders is None:
        if not all([orders is not None, payments is not None, customers is not None, order_items is not None]):
            raise ValueError("需要 fact_orders 或 (orders + payments + customers + order_items)")
        from data_cleaning import build_fact_table
        fact_orders = build_fact_table(customers, orders, payments, order_items)
    return fact_orders


def compute_rfm(
    fact_orders: Optional[pd.DataFrame] = None,
    customers: Optional[pd.DataFrame] = None,
    orders: Optional[pd.DataFrame] = None,
    payments: Optional[pd.DataFrame] = None,
    order_items: Optional[pd.DataFrame] = None,
    analysis_date: Optional[str] = None,
) -> RFMResult:
    """计算 RFM 指标并进行客户分层

    Args:
        fact_orders: 事实表（推荐）
        customers/orders/payments/order_items: 原始清洗后数据
        analysis_date: 分析基准日期，默认 2018-12-31

    Returns:
        RFMResult
    """
    fact = _build_base_table(fact_orders, customers, orders, payments, order_items)

    if analysis_date is None:
        # 取最后一个订单日期 + 1 天，保证 Recency 合理
        last_date = fact["order_date"].max()
        analysis_date = str(pd.Timestamp(last_date).date())
    analysis_dt = pd.to_datetime(analysis_date)

    # 按客户聚合
    rfm_raw = (
        fact.dropna(subset=["customer_id", "order_date", "payment_value"])
        .groupby("customer_id")
        .agg(
            last_purchase_date=("order_date", "max"),
            frequency=("order_id", "nunique"),
            monetary=("payment_value", "sum"),
        )
        .reset_index()
    )
    rfm_raw["last_purchase_date"] = pd.to_datetime(rfm_raw["last_purchase_date"])
    rfm_raw["recency"] = (analysis_dt - rfm_raw["last_purchase_date"]).dt.days
    rfm_raw = rfm_raw.fillna(0)

    # ---- RFM 评分 (1-5分) ----
    recency_max = max(float(rfm_raw["recency"].max()), 181.0)
    # 最近购买 → 高 R 分。必须保留 cut 的 labels，不能再用 cat.codes（会把 5,4,3,2,1 打成 1,2,3,4,5）
    rfm_raw["r_score"] = (
        pd.cut(
            rfm_raw["recency"],
            bins=[-1, 30, 60, 90, 180, recency_max + 1],
            labels=[5, 4, 3, 2, 1],
            include_lowest=True,
        )
        .astype("float")
        .fillna(1)
        .astype(int)
    )

    freq_max = max(float(rfm_raw["frequency"].max()), 6.0)
    rfm_raw["f_score"] = (
        pd.cut(
            rfm_raw["frequency"],
            bins=[-1, 1, 2, 3, 5, freq_max + 1],
            labels=[1, 2, 3, 4, 5],
            include_lowest=True,
        )
        .astype("float")
        .fillna(1)
        .astype(int)
    )

    monetary_max = max(float(rfm_raw["monetary"].max()), 1001.0)
    rfm_raw["m_score"] = (
        pd.cut(
            rfm_raw["monetary"],
            bins=[-1, 50, 100, 250, 500, 1000, monetary_max + 1],
            labels=[1, 2, 3, 4, 5, 6],
            include_lowest=True,
        )
        .astype("float")
        .fillna(1)
        .astype(int)
        .clip(upper=5)
    )

    rfm_raw["rfm_score"] = rfm_raw["r_score"] + rfm_raw["f_score"] + rfm_raw["m_score"]

    # ---- 客户分层 ----
    def _segment(row: pd.Series) -> str:
        score = row["rfm_score"]
        if score >= 12:
            return "高价值客户"
        elif score >= 9:
            return "潜在高价值客户"
        elif score >= 6:
            return "一般价值客户"
        else:
            return "低价值客户"

    rfm_raw["customer_segment"] = rfm_raw.apply(_segment, axis=1)

    # ---- 分层统计 ----
    segment_analysis = (
        rfm_raw.groupby("customer_segment")
        .agg(
            avg_recency=("recency", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_monetary=("monetary", "mean"),
            total_revenue=("monetary", "sum"),
            customer_count=("customer_id", "count"),
        )
        .round(2)
    )
    segment_analysis["revenue_share"] = (
        segment_analysis["total_revenue"] / segment_analysis["total_revenue"].sum()
    ).round(4)

    counts = rfm_raw["customer_segment"].value_counts().to_dict()

    result = RFMResult(
        rfm_data=rfm_raw,
        segment_counts=counts,
        segment_analysis=segment_analysis,
    )
    logger.info(f"RFM 计算完成: {len(rfm_raw)} 名客户，共 {len(counts)} 个分层")
    return result


def generate_segment_recommendations(rfm_result: RFMResult) -> list[dict]:
    """基于 RFM 分层生成可执行的商业建议

    每条建议包含：目标、行动、预期效果、关键指标、优先级
    """
    segment_counts = rfm_result.segment_counts
    total = sum(segment_counts.values())
    seg_meta = rfm_result.segment_analysis
    recs = []

    # ---- 高价值客户 ----
    if "高价值客户" in segment_counts:
        n_high = segment_counts["高价值客户"]
        share = n_high / max(total, 1)
        revenue_share = seg_meta.loc["高价值客户", "revenue_share"] if "高价值客户" in seg_meta.index else 0
        recs.append({
            "segment": "高价值客户",
            "count": n_high,
            "customer_share": round(share, 4),
            "revenue_share": round(float(revenue_share), 4),
            "title": "高价值客户 VIP 运营",
            "goal": "降低流失 + 提升复购率",
            "actions": [
                "建立 VIP 专属客服通道（响应时间 < 2 小时）",
                "每月自动推送个性化推荐 + 专属优惠券（满减+免邮）",
                "设计 3 级会员体系：消费达门槛自动升级（权益：积分倍率）",
                "提前邀请参与新品预售和折扣日",
            ],
            "expected": {
                "repurchase_rate_increase": "15-25%",
                "gmv_impact": f"≈ +{round(revenue_share * 20, 1)}% 核心营收增长",
            },
            "priority": "P0",
        })

    # ---- 潜在高价值客户 ----
    if "潜在高价值客户" in segment_counts:
        n_potential = segment_counts["潜在高价值客户"]
        recs.append({
            "segment": "潜在高价值客户",
            "count": n_potential,
            "customer_share": round(n_potential / max(total, 1), 4),
            "revenue_share": round(
                float(seg_meta.loc["潜在高价值客户", "revenue_share"]) if "潜在高价值客户" in seg_meta.index else 0, 4
            ),
            "title": "潜在高价值客户升级计划",
            "goal": "提升客单价 + 向高价值分层转化",
            "actions": [
                "推送关联商品组合推荐（搭配优惠 5-10%）",
                "限时 满2件8折 活动提升客单价",
                "大额优惠券（满 200 减 30）刺激二次购买",
                "设置升级礼：达到高价值分层送礼品或免邮1个月",
            ],
            "expected": {
                "conversion_to_high": "10-15%",
                "avg_order_value_increase": "8-12%",
            },
            "priority": "P1",
        })

    # ---- 一般/低价值客户 ----
    low_combined = segment_counts.get("一般价值客户", 0) + segment_counts.get("低价值客户", 0)
    if low_combined > 0:
        recs.append({
            "segment": "一般/低价值客户",
            "count": low_combined,
            "customer_share": round(low_combined / max(total, 1), 4),
            "title": "低价人群唤醒 + 成本控制",
            "goal": "以低成本方式提升活跃度，控制补贴投入",
            "actions": [
                "通过 WhatsApp/EDM 每周推送一次促销活动（低成本渠道）",
                "推送 9.9 包邮等低价引流品，唤醒沉睡客户",
                "推荐入门级热销商品降低首次购买门槛",
                "引入社交裂变活动（邀请好友获得折扣）",
            ],
            "expected": {
                "awakening_rate": "3-5%",
                "low_cost_roi": "≈ 1:4（渠道成本）",
            },
            "priority": "P2",
        })

    logger.info(f"已生成 {len(recs)} 条分层运营建议")
    return recs


def run_and_save(
    fact_orders: Optional[pd.DataFrame] = None,
    save_path: Optional[Path] = None,
) -> tuple[RFMResult, list[dict]]:
    """运行 RFM 并保存结果

    Returns:
        (RFMResult, 运营建议列表)
    """
    save_path = save_path or (DATA_DIR / "rfm_analysis.csv")
    rfm = compute_rfm(fact_orders=fact_orders)
    rfm.to_csv(save_path)
    recommendations = generate_segment_recommendations(rfm)
    return rfm, recommendations


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 50)
    print("  RFM 客户价值分析模块")
    print("=" * 50)

    # 加载清洗数据
    from data_cleaning import build_fact_table, load_raw_data, clean_orders, clean_payments, clean_customers, clean_order_items
    customers, orders, payments, order_items = load_raw_data()
    orders = clean_orders(orders)
    payments = clean_payments(payments)
    fact = build_fact_table(clean_customers(customers), orders, payments, clean_order_items(order_items))

    rfm_result, recs = run_and_save(fact_orders=fact)

    print("\n客户分层统计:")
    print(rfm_result.segment_analysis.to_string())

    print("\n分层运营建议:")
    for r in recs:
        print(f"\n[{r['priority']}] {r['title']}")
        print(f"  目标人群: {r['count']:,} 人 (占比 {r['customer_share']:.1%})")
        for a in r["actions"]:
            print(f"    • {a}")
        print(f"  预期效果: {r['expected']}")


if __name__ == "__main__":
    main()
