import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.agent.public_intelligence as intelligence
from api.app import create_app
from src.agent.public_intelligence import _build_public_intelligence, _parse_ecb_rates


ECB_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube><Cube time="2026-09-18">
    <Cube currency="USD" rate="1.1780"/>
    <Cube currency="GBP" rate="0.86420"/>
    <Cube currency="CNY" rate="8.2711"/>
  </Cube></Cube>
</gesmes:Envelope>"""


def test_structured_ecb_feed_updates_only_exchange_rate_signal() -> None:
    date, rates = _parse_ecb_rates(ECB_SAMPLE)
    assert date == "2026-09-18"
    assert rates["USD"] == "1.1780"

    payload = _build_public_intelligence(
        fetch_ecb=lambda: (date, rates),
        now=datetime(2026, 9, 18, 16, 0, tzinfo=timezone.utc),
    )
    assert payload["feed_status"] == "live"
    assert payload["privacy"] == "public_sources_only"
    assert len(payload["signals"]) == 4
    exchange = next(item for item in payload["signals"] if item["id"] == "ecb-reference-rates")
    assert "1.1780 USD" in exchange["summary"]
    assert exchange["update_mode"] == "official_feed"


def test_source_failure_keeps_reviewed_fallback() -> None:
    def unavailable() -> tuple[str, dict[str, str]]:
        raise ValueError("offline")

    payload = _build_public_intelligence(fetch_ecb=unavailable)
    assert payload["feed_status"] == "fallback"
    assert all(item["href"].startswith("https://") for item in payload["signals"])


def test_public_endpoint_is_read_only_and_cacheable() -> None:
    original_cache, original_expiry = intelligence._cache, intelligence._cache_expires_at
    try:
        intelligence._cache = _build_public_intelligence(
            fetch_ecb=lambda: _parse_ecb_rates(ECB_SAMPLE),
        )
        intelligence._cache_expires_at = float("inf")
        response = create_app().test_client().get("/v1/public-intelligence")
    finally:
        intelligence._cache, intelligence._cache_expires_at = original_cache, original_expiry
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=900"
    assert response.json["privacy"] == "public_sources_only"
    assert "orders" not in response.get_data(as_text=True).lower()


if __name__ == "__main__":
    test_structured_ecb_feed_updates_only_exchange_rate_signal()
    test_source_failure_keeps_reviewed_fallback()
    test_public_endpoint_is_read_only_and_cacheable()
    print("Public intelligence tests passed")
