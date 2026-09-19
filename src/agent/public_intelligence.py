"""Privacy-safe public intelligence for the cross-border operations radar.

Only structured, official public data is refreshed automatically. Editorial
signals stay on an allowlisted, reviewed baseline so a source-page redesign
cannot silently turn into merchant advice.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import time
from typing import Any, Callable
from xml.etree import ElementTree

import requests


ECB_DAILY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
CACHE_TTL_SECONDS = 60 * 60

REVIEWED_SIGNALS: list[dict[str, str]] = [
    {
        "id": "eu-low-value-duty",
        "category": "合规",
        "market": "欧盟",
        "level": "高影响",
        "date": "2026-07-20",
        "title": "欧盟低价值进口商品已适用临时关税",
        "summary": "自 2026 年 7 月 1 日起，价值不超过 150 欧元的进口商品按不同税则项目适用临时 3 欧元关税。",
        "action": "复核欧盟订单的落地成本、税则分类与结账页费用说明，避免利润和到货体验偏差。",
        "source": "欧盟委员会税务与关税联盟",
        "href": "https://taxation-customs.ec.europa.eu/news/guidance-and-legal-text-temporary-flat-fee-low-value-imports-which-will-apply-until-1-july-2028-2026-06-08_en",
        "update_mode": "reviewed",
    },
    {
        "id": "shopify-disclosures",
        "category": "平台",
        "market": "全球",
        "level": "中影响",
        "date": "2026-06-17",
        "title": "Shopify 商品信息支持结构化披露字段",
        "summary": "商家可在后台维护产品警示与自定义披露；支持的主题会在商品详情页展示这些信息。",
        "action": "若销售受监管商品，抽查重点 SKU 的披露字段、主题呈现和自定义店面渲染是否一致。",
        "source": "Shopify Changelog",
        "href": "https://changelog.shopify.com/posts/product-listings-now-support-a-disclosures-field",
        "update_mode": "reviewed",
    },
    {
        "id": "us-cargo-description",
        "category": "物流",
        "market": "美国",
        "level": "中影响",
        "date": "2025-02-24",
        "title": "美国入境货物需要准确、可识别的商品描述",
        "summary": "美国海关公开了可接受与不可接受的货物描述示例，强调描述应足以识别商品特征。",
        "action": "检查承运商模板中的英文品名，避免只填品牌名、模糊简称或与实际商品不一致的描述。",
        "source": "U.S. Customs and Border Protection",
        "href": "https://www.cbp.gov/trade/basic-import-export/e-commerce/examples-unacceptable-vs-acceptable-cargo-descriptions",
        "update_mode": "reviewed",
    },
    {
        "id": "ecb-reference-rates",
        "category": "汇率",
        "market": "欧盟",
        "level": "观察",
        "date": "2026-09-18",
        "title": "欧洲央行工作日更新欧元参考汇率",
        "summary": "欧洲央行通常在每个工作日约 16:00 CET 发布欧元对主要货币的参考汇率，仅供信息参考。",
        "action": "把汇率变化作为毛利敏感度信号；实际定价、结算和对冲仍应使用支付渠道的成交数据。",
        "source": "European Central Bank",
        "href": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
        "update_mode": "official_feed",
    },
]

_cache: dict[str, Any] | None = None
_cache_expires_at = 0.0


def _parse_ecb_rates(xml: bytes) -> tuple[str, dict[str, str]]:
    root = ElementTree.fromstring(xml)
    daily = root.find(".//{*}Cube[@time]")
    if daily is None or not daily.attrib.get("time"):
        raise ValueError("ECB feed has no dated rate set")
    rates = {
        node.attrib["currency"]: node.attrib["rate"]
        for node in daily.findall("{*}Cube")
        if node.attrib.get("currency") and node.attrib.get("rate")
    }
    if not {"USD", "GBP", "CNY"}.issubset(rates):
        raise ValueError("ECB feed is missing required currencies")
    return daily.attrib["time"], rates


def _fetch_ecb_rates() -> tuple[str, dict[str, str]]:
    response = requests.get(
        ECB_DAILY_RATES_URL,
        headers={"User-Agent": "OlistRevenueOps/1.0 public-intelligence"},
        timeout=8,
    )
    response.raise_for_status()
    return _parse_ecb_rates(response.content)


def _build_public_intelligence(
    fetch_ecb: Callable[[], tuple[str, dict[str, str]]] = _fetch_ecb_rates,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = now or datetime.now(timezone.utc)
    signals = deepcopy(REVIEWED_SIGNALS)
    feed_status = "live"
    try:
        rate_date, rates = fetch_ecb()
        ecb = next(signal for signal in signals if signal["id"] == "ecb-reference-rates")
        ecb["date"] = rate_date
        ecb["summary"] = (
            f"欧洲央行 {rate_date} 参考汇率：1 EUR = {rates['USD']} USD / "
            f"{rates['GBP']} GBP / {rates['CNY']} CNY。该汇率仅供信息参考。"
        )
    except (requests.RequestException, ElementTree.ParseError, ValueError, StopIteration):
        feed_status = "fallback"

    return {
        "generated_at": checked_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_status": feed_status,
        "signals": signals,
        "privacy": "public_sources_only",
    }


def get_public_intelligence() -> dict[str, Any]:
    """Return a cached public feed; source failure falls back to reviewed data."""
    global _cache, _cache_expires_at
    current = time.monotonic()
    if _cache is None or current >= _cache_expires_at:
        _cache = _build_public_intelligence()
        _cache_expires_at = current + CACHE_TTL_SECONDS
    return deepcopy(_cache)
