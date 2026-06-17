from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class Insight:
    title: str
    level: str
    evidence: str
    action: str


class AIOperationInsightEngine:
    """Rule-based AI analyst for ecommerce operation decisions.

    The engine turns model/metric outputs into business-readable actions. It is
    intentionally local and deterministic so the demo can run without API keys.
    """

    def build_global_insights(
        self,
        *,
        total_revenue: float,
        top_regions: Iterable[tuple[str, float]],
        top_payment: tuple[str, int, float],
        high_value_customers: int,
        potential_customers: int,
        total_customers: int,
    ) -> list[Insight]:
        insights: list[Insight] = []
        top_regions = list(top_regions)

        if top_regions:
            regions = "、".join(region for region, _ in top_regions[:3])
            region_revenue = sum(value for _, value in top_regions[:3])
            share = region_revenue / total_revenue if total_revenue else 0
            insights.append(
                Insight(
                    title="重点地区集中度较高",
                    level="增长机会",
                    evidence=f"TOP3 地区 {regions} 贡献约 {share:.1%} 销售额。",
                    action="优先把广告预算、活动资源和仓配能力投向核心地区，同时用低成本活动测试长尾地区。",
                )
            )

        payment_name, payment_count, payment_share = top_payment
        insights.append(
            Insight(
                title="支付方式可作为转化优化入口",
                level="转化优化",
                evidence=f"{payment_name} 是主要支付方式，占比约 {payment_share:.1%}，共 {payment_count:,} 笔。",
                action="围绕主流支付方式设计支付优惠、分期免息或满减活动，并监控下单到支付的转化变化。",
            )
        )

        high_value_share = high_value_customers / total_customers if total_customers else 0
        potential_share = potential_customers / total_customers if total_customers else 0
        insights.append(
            Insight(
                title="客户分层可以直接指导运营预算",
                level="人群运营",
                evidence=(
                    f"高价值客户 {high_value_customers:,} 人，占比 {high_value_share:.1%}；"
                    f"潜在高价值客户 {potential_customers:,} 人，占比 {potential_share:.1%}。"
                ),
                action="高价值客户做会员权益和复购激励，潜在高价值客户做优惠券召回，低价值客户控制补贴成本。",
            )
        )

        return insights


def strategy_for_segment(segment: str) -> dict[str, str]:
    strategies = {
        "高价值": {
            "goal": "提升复购和客单价",
            "action": "会员权益、专属优惠券、新品优先购、生日礼遇。",
            "copy": "感谢你的持续支持，已为你准备专属会员权益和限时复购礼券。",
        },
        "潜在高价值": {
            "goal": "推动二次购买",
            "action": "满减券、关联推荐、加购提醒、限时活动。",
            "copy": "你可能会喜欢这些同类热卖商品，现在下单可使用专属优惠券。",
        },
        "一般价值": {
            "goal": "提高活跃和转化",
            "action": "场景化推荐、组合套装、轻量优惠。",
            "copy": "为你精选了近期热销搭配，组合购买更划算。",
        },
        "低价值": {
            "goal": "低成本唤醒",
            "action": "自动化内容触达、低成本券、减少高额补贴。",
            "copy": "近期热卖商品已更新，回店看看是否有你需要的商品。",
        },
    }
    return strategies.get(segment, strategies["一般价值"])
