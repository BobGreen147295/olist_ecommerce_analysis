import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app import _shopify_opportunity_readiness


def main() -> None:
    assert _shopify_opportunity_readiness({})["state"] == "trend_required"
    assert _shopify_opportunity_readiness({"is_development_store": True, "order_trend": {"orders_scanned": 50, "days": [{}, {}, {}]}})["state"] == "development_store"
    assert _shopify_opportunity_readiness({"order_trend": {"orders_scanned": 19, "days": [{}, {}, {}]}})["state"] == "insufficient_data"
    assert _shopify_opportunity_readiness({"order_trend": {"orders_scanned": 20, "days": [{}, {}, {}]}})["state"] == "ready"
    print("Shopify opportunity readiness tests passed")


if __name__ == "__main__":
    main()
