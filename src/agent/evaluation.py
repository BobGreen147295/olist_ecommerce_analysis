"""运营任务实验结果计算。

只负责确定性指标计算，不让 LLM 参与 ROI、转化率或增量的计算。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def evaluate_experiment(
    treatment_users: int,
    treatment_orders: int,
    treatment_revenue: float,
    control_users: int,
    control_orders: int,
    control_revenue: float,
    cost: float,
) -> dict[str, Any]:
    values = {
        "treatment_users": treatment_users,
        "treatment_orders": treatment_orders,
        "treatment_revenue": treatment_revenue,
        "control_users": control_users,
        "control_orders": control_orders,
        "control_revenue": control_revenue,
        "cost": cost,
    }
    if any(value < 0 for value in values.values()):
        raise ValueError("实验人数、订单、收入和成本不能为负数")
    if treatment_users <= 0 or control_users <= 0:
        raise ValueError("实验组和对照组人数必须大于 0")
    if treatment_orders > treatment_users or control_orders > control_users:
        raise ValueError("订单数不能大于用户数")

    treatment_conversion = treatment_orders / treatment_users
    control_conversion = control_orders / control_users
    uplift = treatment_conversion - control_conversion
    relative_lift = uplift / control_conversion if control_conversion else None
    incremental_orders = treatment_users * uplift
    control_aov = control_revenue / control_orders if control_orders else 0
    incremental_revenue = incremental_orders * control_aov
    roi = (incremental_revenue - cost) / cost if cost > 0 else None

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "treatment_users": treatment_users,
        "treatment_orders": treatment_orders,
        "treatment_revenue": round(float(treatment_revenue), 2),
        "control_users": control_users,
        "control_orders": control_orders,
        "control_revenue": round(float(control_revenue), 2),
        "cost": round(float(cost), 2),
        "treatment_conversion": round(treatment_conversion, 6),
        "control_conversion": round(control_conversion, 6),
        "conversion_uplift_pp": round(uplift * 100, 4),
        "relative_lift": round(relative_lift, 6) if relative_lift is not None else None,
        "incremental_orders": round(incremental_orders, 2),
        "incremental_revenue": round(incremental_revenue, 2),
        "roi": round(roi, 6) if roi is not None else None,
    }
