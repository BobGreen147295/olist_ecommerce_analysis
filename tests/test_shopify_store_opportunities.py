import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app import _shopify_signal_draft, _shopify_store_opportunities
from scripts.evaluate_product import synthetic_summary


def main() -> None:
    trend = synthetic_summary()["order_trend"]
    signals = _shopify_store_opportunities({"order_trend": trend})
    assert {signal["id"] for signal in signals} == {"net_sales_decline", "refund_pressure"}
    assert all(not {"customers", "orders", "email", "phone"} & set(signal) for signal in signals)
    assert _shopify_store_opportunities({"is_development_store": True, "order_trend": trend}) == []
    draft = _shopify_signal_draft({"order_trend": trend}, "refund_pressure")
    assert draft["audience"] == "不适用（店铺级汇总）"
    assert "客户触达" in draft["consent_basis"]
    print("Shopify store opportunity signal tests passed")


if __name__ == "__main__":
    main()
