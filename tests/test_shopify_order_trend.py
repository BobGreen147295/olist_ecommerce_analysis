import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app import _shopify_order_trend


def money(amount: str) -> dict:
    return {"shopMoney": {"amount": amount, "currencyCode": "USD"}}


def main() -> None:
    trend = _shopify_order_trend([
        {"createdAt": "2026-09-01T03:00:00Z", "totalPriceSet": money("20.00"), "currentTotalPriceSet": money("15.00"), "totalRefundedSet": money("5.00")},
        {"createdAt": "2026-09-01T14:00:00Z", "totalPriceSet": money("10.00"), "currentTotalPriceSet": money("10.00"), "totalRefundedSet": money("0.00")},
    ], 30, False)
    assert trend["totals"] == {"orders": 2, "gross_sales": 30.0, "net_sales": 25.0, "refunds": 5.0}
    assert trend["days"] == [{"date": "2026-09-01", "orders": 2, "gross_sales": 30.0, "net_sales": 25.0, "refunds": 5.0}]
    assert trend["refund_attribution"] == "按原订单日期归集"
    print("Shopify order trend aggregation tests passed")


if __name__ == "__main__":
    main()
