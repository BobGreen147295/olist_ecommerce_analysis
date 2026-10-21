import sys
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app import _shopify_opportunity_readiness
from scripts.evaluate_product import synthetic_summary


@patch("api.app._shopify_now", return_value=datetime(2026, 9, 15, 12, tzinfo=timezone.utc))
def main(_clock=None) -> None:
    assert _shopify_opportunity_readiness({})["state"] == "trend_required"
    assert _shopify_opportunity_readiness({"is_development_store": True, "order_trend": {"orders_scanned": 50, "days": [{}, {}, {}]}})["state"] == "development_store"
    assert _shopify_opportunity_readiness({"order_trend": {"orders_scanned": 19, "days": [{}, {}, {}]}})["state"] == "insufficient_data"
    assert _shopify_opportunity_readiness({"order_trend": {"orders_scanned": 20, "days": [{}, {}, {}]}})["state"] == "insufficient_data"
    assert _shopify_opportunity_readiness(synthetic_summary())["state"] == "ready"
    print("Shopify opportunity readiness tests passed")


if __name__ == "__main__":
    main()
