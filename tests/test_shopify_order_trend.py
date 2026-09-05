import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import api.app as app_module
from api.app import _shopify_order_trend, _shopify_rest_order_trend


def money(amount: str) -> dict:
    return {"shopMoney": {"amount": amount, "currencyCode": "USD"}}


def main() -> None:
    trend = _shopify_order_trend([
        {"createdAt": "2026-09-01T03:00:00Z", "totalPriceSet": money("20.00"), "currentTotalPriceSet": money("15.00")},
        {"createdAt": "2026-09-01T14:00:00Z", "totalPriceSet": money("10.00"), "currentTotalPriceSet": money("10.00")},
    ], 30, False)
    assert trend["totals"] == {"orders": 2, "gross_sales": 30.0, "net_sales": 25.0, "refunds": 5.0}
    assert trend["days"] == [{"date": "2026-09-01", "orders": 2, "gross_sales": 30.0, "net_sales": 25.0, "refunds": 5.0}]
    assert trend["refund_attribution"] == "退款及订单调整额按原订单日期归集"
    original_get = app_module.requests.get
    class RestResponse:
        links: dict = {}
        def raise_for_status(self) -> None: pass
        def json(self) -> dict:
            return {"orders": [{"created_at": "2026-09-02T10:00:00Z", "total_price": "24.95", "current_total_price": "24.95", "currency": "USD"}]}
    try:
        app_module.requests.get = lambda *args, **kwargs: RestResponse()
        rest_nodes, truncated = _shopify_rest_order_trend({"shop_domain": "demo.myshopify.com", "access_token": "test"}, "2026-08-01", "USD")
    finally:
        app_module.requests.get = original_get
    assert not truncated
    assert _shopify_order_trend(rest_nodes, 30, truncated)["totals"] == {"orders": 1, "gross_sales": 24.95, "net_sales": 24.95, "refunds": 0.0}
    print("Shopify order trend aggregation tests passed")


if __name__ == "__main__":
    main()
