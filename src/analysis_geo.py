"""
地理分析模块 - 地区分布、人口密度、人均销售额

结合爬虫的人口数据 + 销售数据，进行地区市场分析，
并给出可执行的市场拓展建议（如东北部物流补贴）
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
class GeoAnalysisResult:
    state_revenue: pd.DataFrame
    city_revenue: pd.DataFrame
    region_per_capita: Optional[pd.DataFrame]  # 结合人口数据
    recommendations: list[dict]


def _load_population(pop_path: Optional[Path] = None) -> Optional[pd.DataFrame]:
    pop_path = pop_path or (DATA_DIR / "brazil_population.csv")
    if not pop_path.exists():
        logger.info("人口数据不存在，跳过地理经济分析")
        return None
    return pd.read_csv(pop_path)


def compute_state_revenue(
    fact_orders: pd.DataFrame,
) -> pd.DataFrame:
    """计算各州销售额、订单数、客单价"""
    state = (
        fact_orders.groupby("customer_state")
        .agg(
            total_revenue=("payment_value", "sum"),
            order_count=("order_id", "nunique"),
            customer_count=("customer_id", "nunique"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
    )
    state["aov"] = (state["total_revenue"] / state["order_count"]).round(2)
    state["revenue_share"] = (
        state["total_revenue"] / state["total_revenue"].sum()
    ).round(4)
    return state


def compute_city_revenue(
    fact_orders: pd.DataFrame, top_n: int = 30,
) -> pd.DataFrame:
    city = (
        fact_orders.dropna(subset=["customer_city"])
        .groupby(["customer_state", "customer_city"])
        .agg(
            total_revenue=("payment_value", "sum"),
            order_count=("order_id", "nunique"),
            customer_count=("customer_id", "nunique"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
        .head(top_n)
    )
    city["aov"] = (city["total_revenue"] / city["order_count"]).round(2)
    return city


def compute_per_capita(
    state_revenue: pd.DataFrame, population: pd.DataFrame,
) -> pd.DataFrame:
    """结合人口数据，计算人均销售额（市场饱和度/拓展潜力）"""
    merged = state_revenue.merge(population, left_on="customer_state", right_on="state", how="left")
    if "population" not in merged.columns:
        logger.warning("人口数据缺少 population 字段，无法计算人均销售额")
        return state_revenue.assign(population=None, sales_per_million=None)

    merged["sales_per_million"] = (
        merged["total_revenue"] / merged["population"] * 1_000_000
    ).round(2)
    # Agent / 看板约定列名（与历史 processed CSV 一致：sales_per_capita = 每百万人销售额）
    merged["state"] = merged["customer_state"]
    merged["sales"] = merged["total_revenue"]
    merged["sales_per_capita"] = merged["sales_per_million"]
    return merged


def _to_agent_region_table(per_capita: pd.DataFrame) -> pd.DataFrame:
    """写出 tools.py / dashboard 可读的地区表，同时保留分析用扩展列。"""
    df = per_capita.copy()
    if "state" not in df.columns and "customer_state" in df.columns:
        df["state"] = df["customer_state"]
    if "sales" not in df.columns and "total_revenue" in df.columns:
        df["sales"] = df["total_revenue"]
    if "sales_per_capita" not in df.columns and "sales_per_million" in df.columns:
        df["sales_per_capita"] = df["sales_per_million"]
    preferred = [
        "state",
        "sales",
        "population",
        "sales_per_capita",
        "order_count",
        "customer_count",
        "aov",
        "revenue_share",
        "sales_per_million",
        "customer_state",
        "total_revenue",
    ]
    cols = [c for c in preferred if c in df.columns]
    return df.loc[:, cols].drop_duplicates(subset=["state"], keep="first")


def generate_geo_recommendations(
    state_revenue: pd.DataFrame,
    per_capita: Optional[pd.DataFrame] = None,
    top_n_states: int = 5,
) -> list[dict]:
    """生成地理拓展建议

    关键策略:
    1. 头部市场集中度过高 → 分散风险 + 强化护城河
    2. 人口大州但市场渗透率低 → 物流补贴/促销拓展
    3. 长尾州但客单价高 → 小而美市场深耕
    """
    recs: list[dict] = []

    # 1. 头部集中度分析
    top_states = state_revenue.head(top_n_states)
    top_share = top_states["revenue_share"].sum()
    top_state = top_states.iloc[0]

    if top_share > 0.6:
        # 高集中度风险
        recs.append({
            "type": "concentration_risk",
            "title": f"头部{top_n_states}州销售额集中度 {top_share:.1%}，存在市场风险",
            "goal": "降低单一市场依赖，分散到新兴市场",
            "evidence": f"{top_state['customer_state']} 占比 {top_state['revenue_share']:.1%}，远超第二大市场",
            "actions": [
                f"对 NE（东北部）人口大州推出「首单免邮 + 当地物流合作」试点",
                "针对 SP/RJ 之外的 10 个潜力州做「定向优惠券」活动",
                "加强与巴西邮政 Correios 在中南部以外的合作，降低物流成本",
            ],
            "expected": {
                "top_share_reduction": f"-{round(top_share*5, 1)} 个百分点（6个月）",
                "new_market_growth": "15-20%",
            },
            "priority": "P1",
        })

    # 2. 人口大州低渗透率（需要人口数据）
    if per_capita is not None and "sales_per_million" in per_capita.columns:
        median_per_capita = per_capita["sales_per_million"].median()
        # 人口多但人均销售额低于中位数的州
        underpenetrated = (
            per_capita[
                (per_capita["population"] > 5_000_000)
                & (per_capita["sales_per_million"] < median_per_capita)
            ]
            .sort_values("population", ascending=False)
            .head(3)
        )
        for _, row in underpenetrated.iterrows():
            recs.append({
                "type": "market_expansion",
                "title": f"{row['customer_state']} 州：人口 {row['population']/1e6:.1f}M 但市场渗透低",
                "goal": "通过物流补贴提高该州订单数",
                "evidence": (
                    f"人口 {row['population']:,} / 人均销售额 "
                    f"R${row['sales_per_million']:,.0f}/M "
                    f"（仅为全国中位数的 {row['sales_per_million']/max(median_per_capita,1):.1%}）"
                ),
                "actions": [
                    f"在 {row['customer_state']} 推出「满 R$59 免邮」物流补贴",
                    f"与当地第三方物流（如 Jadlog）合作缩短配送时间",
                    "投放本地化 Facebook/Instagram 广告（葡语）",
                ],
                "expected": {
                    "state_growth": "25-35%",
                    "roi": "≈ 1:5（物流补贴成本 vs 新增 GMV）",
                },
                "priority": "P1",
            })

    # 3. 高 AOV 长尾州（小而美）
    tail_high_aov = (
        state_revenue[state_revenue["order_count"] < state_revenue["order_count"].median()]
        .sort_values("aov", ascending=False)
        .head(3)
    )
    if len(tail_high_aov) > 0:
        states = "、".join(tail_high_aov["customer_state"].to_list())
        recs.append({
            "type": "high_aov_tail",
            "title": f"{states} 等州客单价高但订单量小",
            "goal": "挖掘高净值客户，提升订单数",
            "evidence": (
                "平均客单价 R$"
                f"{tail_high_aov['aov'].mean():,.0f}（整体 {state_revenue['aov'].mean():,.0f}）"
            ),
            "actions": [
                "上架高端产品线（电子/家电）到这些州的推荐位",
                "推出「分期付款 0 利息」优惠，促进大额消费",
                "针对这些州的已购客户推送 VIP 升级权益",
            ],
            "expected": {
                "order_count_growth": "10-15%",
                "high_value_customer_gain": "+1000 名",
            },
            "priority": "P2",
        })

    logger.info(f"已生成 {len(recs)} 条地理运营建议")
    return recs


def run(
    fact_orders: pd.DataFrame,
    population: Optional[pd.DataFrame] = None,
    save_dir: Optional[Path] = None,
) -> GeoAnalysisResult:
    save_dir = save_dir or DATA_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    state_rev = compute_state_revenue(fact_orders)
    city_rev = compute_city_revenue(fact_orders)
    per_capita = None
    if population is None:
        population = _load_population()
    if population is not None:
        per_capita = compute_per_capita(state_rev, population)
        _to_agent_region_table(per_capita).to_csv(save_dir / "region_analysis.csv", index=False)
        logger.info(f"地区经济分析已保存: {save_dir / 'region_analysis.csv'}")

    recs = generate_geo_recommendations(state_rev, per_capita)
    return GeoAnalysisResult(
        state_revenue=state_rev,
        city_revenue=city_rev,
        region_per_capita=per_capita,
        recommendations=recs,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 50)
    print("  地理分析模块")
    print("=" * 50)

    from data_cleaning import build_fact_table, load_raw_data, clean_orders, clean_payments
    customers, orders, payments, order_items = load_raw_data()
    orders = clean_orders(orders)
    payments = clean_payments(payments)
    fact = build_fact_table(customers, orders, payments, order_items)

    result = run(fact_orders=fact)

    print("\nTOP5 销售州:")
    print(result.state_revenue.head(5).to_string())

    if result.region_per_capita is not None:
        print("\nTOP5 人均销售额州:")
        show = result.region_per_capita.sort_values("sales_per_million", ascending=False).head(5)
        print(show[["customer_state", "population", "sales_per_million"]].to_string())

    print("\n地理运营建议:")
    for r in result.recommendations:
        print(f"\n[{r['priority']}] {r['title']}")
        print(f"  目标: {r['goal']}")
        if "evidence" in r:
            print(f"  数据: {r['evidence']}")
        for a in r["actions"]:
            print(f"    • {a}")
        print(f"  预期: {r['expected']}")


if __name__ == "__main__":
    main()
