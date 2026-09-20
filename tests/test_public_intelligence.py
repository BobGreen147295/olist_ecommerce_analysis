import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.agent.public_intelligence as intelligence
from api.app import create_app
from src.agent.public_intelligence import _build_public_intelligence, _parse_ecb_rates, _parse_shopify_changelog


ECB_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube><Cube time="2026-09-18">
    <Cube currency="USD" rate="1.1780"/>
    <Cube currency="GBP" rate="0.86420"/>
    <Cube currency="CNY" rate="8.2711"/>
  </Cube></Cube>
</gesmes:Envelope>"""

SHOPIFY_SAMPLE = """
<div class="block post-block changelog-post" data-tag="international">
  <div class="post-block__date"><span class="heading--5">September 19</span></div>
  <div class="post-block__content">
    <h3><a class="post-block__link" href="/posts/new-market-update">New market update</a></h3>
    <div class="post__content"><p>Merchants can now use a new cross-border option.</p></div>
  </div>
</div>
"""


def test_structured_ecb_feed_updates_only_exchange_rate_signal() -> None:
    date, rates = _parse_ecb_rates(ECB_SAMPLE)
    assert date == "2026-09-18"
    assert rates["USD"] == "1.1780"

    payload = _build_public_intelligence(
        fetch_ecb=lambda: (date, rates),
        fetch_shopify=lambda: _parse_shopify_changelog(
            SHOPIFY_SAMPLE, datetime(2026, 9, 20, tzinfo=timezone.utc),
        ),
        now=datetime(2026, 9, 18, 16, 0, tzinfo=timezone.utc),
    )
    assert payload["feed_status"] == "live"
    assert payload["privacy"] == "public_sources_only"
    assert len(payload["signals"]) == 4
    assert payload["signals"][0]["title"] == "New market update"
    exchange = next(item for item in payload["signals"] if item["id"] == "ecb-reference-rates")
    assert "1.1780 USD" in exchange["summary"]
    assert exchange["update_mode"] == "official_feed"


def test_source_failure_keeps_reviewed_fallback() -> None:
    def unavailable() -> tuple[str, dict[str, str]]:
        raise ValueError("offline")

    def shopify_unavailable() -> dict[str, str]:
        raise ValueError("offline")

    payload = _build_public_intelligence(fetch_ecb=unavailable, fetch_shopify=shopify_unavailable)
    assert payload["feed_status"] == "fallback"
    assert all(item["href"].startswith("https://") for item in payload["signals"])


def test_public_endpoint_is_read_only_and_cacheable() -> None:
    original_cache, original_expiry = intelligence._cache, intelligence._cache_expires_at
    try:
        intelligence._cache = _build_public_intelligence(
            fetch_ecb=lambda: _parse_ecb_rates(ECB_SAMPLE),
            fetch_shopify=lambda: _parse_shopify_changelog(SHOPIFY_SAMPLE),
        )
        intelligence._cache_expires_at = float("inf")
        response = create_app().test_client().get("/v1/public-intelligence")
    finally:
        intelligence._cache, intelligence._cache_expires_at = original_cache, original_expiry
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=300"
    assert response.json["privacy"] == "public_sources_only"
    assert "orders" not in response.get_data(as_text=True).lower()


if __name__ == "__main__":
    test_structured_ecb_feed_updates_only_exchange_rate_signal()
    test_source_failure_keeps_reviewed_fallback()
    test_public_endpoint_is_read_only_and_cacheable()
    print("Public intelligence tests passed")
