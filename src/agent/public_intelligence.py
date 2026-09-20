"""Privacy-safe public intelligence for the cross-border operations radar.

Only structured, official public data is refreshed automatically. Editorial
signals stay on an allowlisted, reviewed baseline so a source-page redesign
cannot silently turn into merchant advice.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from html.parser import HTMLParser
import time
from typing import Any, Callable
from xml.etree import ElementTree

import requests


ECB_DAILY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
SHOPIFY_CHANGELOG_URL = "https://changelog.shopify.com/"
CACHE_TTL_SECONDS = 15 * 60
SHOPIFY_RELEVANCE_TERMS = (
    "international", "market", "multi-currency", "shipping",
    "tax", "dut", "customs", "checkout", "consent", "returns",
)

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


class _ShopifyChangelogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.posts: list[dict[str, str]] = []
        self._post: dict[str, str] | None = None
        self._post_depth = 0
        self._capture: str | None = None
        self._capture_end: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "div" and "changelog-post" in classes and self._post is None:
            self._post = {"tag": attributes.get("data-tag") or ""}
            self._post_depth = 1
        elif self._post is not None and tag == "div":
            self._post_depth += 1
        if self._post is None:
            return
        if tag == "span" and "heading--5" in classes:
            self._capture, self._capture_end = "date", "span"
        elif tag == "a" and "post-block__link" in classes:
            self._post["href"] = attributes.get("href") or ""
            self._capture, self._capture_end = "title", "a"
        elif tag == "div" and "post__content" in classes:
            self._capture, self._capture_end = "summary", "div"

    def handle_data(self, data: str) -> None:
        if self._post is not None and self._capture:
            self._post[self._capture] = f"{self._post.get(self._capture, '')} {data}".strip()

    def handle_endtag(self, tag: str) -> None:
        if self._post is None:
            return
        if tag == self._capture_end:
            self._capture = self._capture_end = None
        if tag == "div":
            self._post_depth -= 1
            if self._post_depth == 0:
                self.posts.append({key: " ".join(value.split()) for key, value in self._post.items()})
                self._post = None


def _parse_shopify_changelog(html: str, now: datetime | None = None) -> dict[str, str]:
    parser = _ShopifyChangelogParser()
    parser.feed(html)
    relevant = next((post for post in parser.posts if any(
        term in f"{post.get('tag', '')} {post.get('title', '')} {post.get('summary', '')}".lower()
        for term in SHOPIFY_RELEVANCE_TERMS
    )), None)
    if not relevant or not all(relevant.get(key) for key in ("date", "title", "summary", "href")):
        raise ValueError("Shopify changelog has no relevant dated post")
    checked_at = now or datetime.now(timezone.utc)
    published = datetime.strptime(
        f"{relevant['date']} {checked_at.year}", "%B %d %Y",
    ).replace(tzinfo=timezone.utc)
    if published > checked_at:
        published = published.replace(year=published.year - 1)
    return {
        "id": "shopify-changelog-live",
        "category": "平台",
        "market": "全球",
        "level": "观察",
        "date": published.date().isoformat(),
        "title": relevant["title"],
        "summary": relevant["summary"],
        "action": "检查该更新是否影响当前市场、结账或履约配置；先在测试环境验证，再决定是否调整。",
        "source": "Shopify Changelog",
        "href": f"https://changelog.shopify.com{relevant['href']}",
        "update_mode": "official_feed",
    }


def _fetch_shopify_changelog() -> dict[str, str]:
    response = requests.get(
        SHOPIFY_CHANGELOG_URL,
        headers={"User-Agent": "OlistRevenueOps/1.0 public-intelligence"},
        timeout=8,
    )
    response.raise_for_status()
    return _parse_shopify_changelog(response.text)


def _build_public_intelligence(
    fetch_ecb: Callable[[], tuple[str, dict[str, str]]] = _fetch_ecb_rates,
    fetch_shopify: Callable[[], dict[str, str]] = _fetch_shopify_changelog,
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

    try:
        signals = [signal for signal in signals if signal["id"] != "shopify-disclosures"]
        signals.append(fetch_shopify())
        feed_status = "live"
    except (requests.RequestException, ValueError):
        pass

    signals.sort(key=lambda signal: signal["date"], reverse=True)

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
