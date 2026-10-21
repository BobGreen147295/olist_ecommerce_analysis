"""Explicit, tenant-bound aggregate report. No model, arbitrary SQL or recommendations."""
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from math import isfinite
from numbers import Integral, Real
import re

from . import tools

REPORT_QUERIES = (
    "核对最近6个有订单月份的订单趋势（不调用模型）",
    "Check order trends for the last 6 months with orders (no model call)",
)
COMPARISON_QUERIES = (
    "核对近两期订单金额变化（不调用模型）",
    "Compare order amounts for the last two periods (no model call)",
)


def report_language(message: str) -> bool | None:
    """Bounded, auditable intents; never guess at causal/advice questions."""
    text = message.strip().rstrip("。.!！?？")
    if text in (REPORT_QUERIES[0], COMPARISON_QUERIES[0], "核对近两期订单金额变化", "核对最近两个月订单金额", "对比最近两个月订单金额"):
        return False
    if text.lower() in {REPORT_QUERIES[1].lower(), COMPARISON_QUERIES[1].lower(), "compare order amounts for the last two periods"}:
        return True
    return None
CONTRACT = {
    "version": "order-trend/v1",
    "grain": "UTC month",
    "window": "Last 6 observed months in the active source, not 6 calendar months ending today; missing months are not zero-filled.",
    "total_orders": "Distinct imported order IDs per month; import keeps the last duplicate ID. No order-status exclusion.",
    "total_amount": "Sum of imported total_amount in one currency, displayed to 2 decimals; not net revenue or profit. No refund deduction.",
}

ISSUES = {
    "source_required": ("没有可核对的已导入订单。请到数据页导入授权订单；连接成功或同步计数不等于已有订单明细。", "No imported orders available. Import authorized orders on the Data page; connection or sync counts alone are not order history."),
    "mixed_currency": ("币种不唯一或缺失，已停止合计。请按币种拆分导入；不会自动换汇。", "Currency is mixed or missing. Totals are blocked; import one currency at a time. No automatic FX conversion."),
    "empty_source": ("当前来源没有订单，无法比较两期；请检查导入结果。", "The current source has no orders. Check the import result before comparing periods."),
    "invalid_source_rows": ("订单日期或金额无效，已停止核对。请核对源文件后重新导入；不会静默跳过异常行。", "Invalid order dates or amounts. Check the source file and reimport; invalid rows are not silently skipped."),
    "data_service_unavailable": ("订单数据查询失败。可稍后重试或检查数据库；不是模型额度问题。", "Order data lookup failed. Retry later or check the database; this is not a model quota error."),
    "invalid_aggregate": ("汇总数据无效，已停止核对；请检查日期、币种、金额和期间顺序。", "Invalid aggregates. Check dates, currency, amounts and period ordering."),
    "snapshot_only": ("CSV 是一次导入的快照，不会自动同步。查询时间不是同步时间，完整月份也不代表订单已全部收齐。", "CSV is an imported snapshot, not a live sync. Query time is not sync time; a closed month does not prove complete order coverage."),
    "snapshot_stale": ("导入快照已超过 24 小时，仅可核对历史；如需当前结果，请手动重新导入。", "The import snapshot is over 24 hours old. Historical comparison only; manually reimport for current results."),
    "metadata_unknown": ("缺少可信的导入时间或来源覆盖信息，无法确认新鲜度；请核对数据页。", "Trusted import time or source coverage is missing. Freshness is unknown; check the Data page."),
    "period_gap": ("两期不是相邻自然月；中间缺月不能当作零订单，也不能称为环比。", "These are not consecutive calendar months. Missing months are not zero-order months; this is not month-over-month growth."),
    "open_period": ("比较包含尚未结束的 UTC 月份，不是两个完整月的对照。", "The comparison includes an unfinished UTC month, not two complete calendar months."),
    "future_period": ("订单期间晚于当前 UTC 月份，已停止核对；请检查源文件日期。", "An order period is later than the current UTC month. Check source dates before comparing."),
    "one_period": ("只有一个有订单月份，无法计算两期差额或变化率。", "Only one observed month is available. A two-period difference or percentage cannot be calculated."),
}


def _timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    return parsed.astimezone(timezone.utc)


def _money(value):
    with localcontext() as context:
        context.prec = 350  # Accommodate every finite stored double, including invalidly large totals.
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _bounds(period):
    year, month = map(int, period.split("-"))
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    return {"start": start.date().isoformat(),
            "end_exclusive": (start + timedelta(days=monthrange(year, month)[1])).date().isoformat()}


def order_trend_report(*, owner: str, english: bool = False) -> dict:
    """Use only the current account's active source and whitelist aggregate fields."""
    now = datetime.now(timezone.utc)
    report = {"status": "unavailable", "model_called": False, "contract": dict(CONTRACT),
              "generated_at": now.isoformat(), "source": None,
              "currency": None, "rows": [], "window": None, "comparison": None,
              "provenance": None, "issues": []}
    response = {"mode": "data", "report": report, "action_drafts": [], "evidence": [],
                "error": "order_trend_unavailable", "error_code": "order_trend_unavailable",
                "error_stage": "data_query",
                "answer": "Data check incomplete. No model call or recommendation. Check the Data page for an active order source, a single currency and valid amounts; retry if the data service is unavailable."
                if english else "数据核对未完成；未调用模型，也未生成建议。请在数据页检查是否已有可用订单、单一币种及有效金额；若数据服务暂不可用，请稍后重试。"}

    def issue(code):
        report["issues"].append({"code": code, "message": ISSUES[code][int(english)]})

    def fail(code):
        issue(code)
        response.update(error=code, error_code=code,
                        answer=ISSUES[code][int(english)] + (" No model call or recommendation." if english else " 未调用模型，也未生成建议。"))
        return response
    if not owner:
        return fail("source_required")
    try:
        result = tools.execute_tool("query_sales_trend", months=6, owner=owner)
    except Exception:
        # Never forward database details, credentials or raw rows into the chat.
        return fail("data_service_unavailable")
    if not isinstance(result, dict) or not result.get("success"):
        code = result.get("error_code") if isinstance(result, dict) else None
        return fail(code if code in ("source_required", "mixed_currency", "empty_source", "invalid_source_rows", "data_service_unavailable") else "data_service_unavailable")
    currency, source, data = result.get("currency"), result.get("source"), result.get("data")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        return fail("invalid_aggregate")
    if not isinstance(source, str) or not source.strip() or not isinstance(data, list) or not 1 <= len(data) <= 6:
        return fail("invalid_aggregate")
    rows = []
    for item in data:
        if not isinstance(item, dict):
            return fail("invalid_aggregate")
        period, orders, amount = item.get("period"), item.get("total_orders"), item.get("total_sales")
        if not isinstance(period, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period) or period[:4] in ("0000", "9999"):
            return fail("invalid_aggregate")
        if isinstance(orders, bool) or not isinstance(orders, Integral) or orders < 0:
            return fail("invalid_aggregate")
        if isinstance(amount, bool) or not isinstance(amount, Real) or not isfinite(amount) or amount < 0:
            return fail("invalid_aggregate")
        if rows and period <= rows[-1]["period"]:
            return fail("invalid_aggregate")
        rows.append({"period": period, "total_orders": int(orders), "total_amount": float(_money(amount))})
    if rows[-1]["period"] > now.strftime("%Y-%m"):
        return fail("future_period")
    metadata = result.get("source_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    provenance = {"source_type": metadata.get("source_type"), "imported_at": None,
                  "coverage_start": None, "coverage_end": None, "freshness": "unknown", "timezone": "UTC"}
    try:
        imported = _timestamp(metadata["created_at"])
        start, end = _timestamp(metadata["coverage_start"]), _timestamp(metadata["coverage_end"])
        if imported > now + timedelta(minutes=5) or start > end or end > imported + timedelta(minutes=5):
            raise ValueError("Invalid coverage")
        provenance.update(imported_at=imported.isoformat(), coverage_start=start.isoformat(), coverage_end=end.isoformat(),
                          freshness="stale" if now - imported > timedelta(hours=24) else "recent_import")
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        issue("metadata_unknown")
    if provenance["source_type"] == "csv":
        issue("snapshot_only")
    if provenance["freshness"] == "stale":
        issue("snapshot_stale")
    comparison = None
    if len(rows) >= 2:
        previous, current = rows[-2:]
        baseline, latest = _money(previous["total_amount"]), _money(current["total_amount"])
        delta = latest - baseline
        # A zero baseline has no defined percentage, including 0 -> 0.
        percentage = float(_money(delta / baseline * 100)) if baseline else None
        if not isfinite(float(delta)) or (percentage is not None and not isfinite(percentage)):
            return fail("invalid_aggregate")
        comparison = {"previous": {**previous, **_bounds(previous["period"])},
                      "current": {**current, **_bounds(current["period"])},
                      "amount_delta": float(delta), "change_pct": percentage,
                      "percentage_status": "defined" if baseline else "zero_baseline",
                      "orders_delta": current["total_orders"] - previous["total_orders"],
                      "consecutive": _bounds(previous["period"])["end_exclusive"] == _bounds(current["period"])["start"]}
        if not comparison["consecutive"]:
            issue("period_gap")
        if current["period"] == now.strftime("%Y-%m"):
            issue("open_period")
    else:
        issue("one_period")
    report.update(status="ready", source=source, currency=currency, rows=rows,
                  comparison=comparison, provenance=provenance,
                  window={"requested_observed_months": 6, "returned_months": len(rows),
                          "first_period": rows[0]["period"], "last_period": rows[-1]["period"]})
    if english:
        lines = ["Data check · No model call", f"Source: {source} · Currency: {currency}",
                 f"Window: {rows[0]['period']} – {rows[-1]['period']}; {len(rows)} observed UTC months with orders (up to 6).",
                 "Months without records are not zero-filled. This is not the last 6 complete calendar months or proof of complete store history.",
                 "Definition: distinct imported orders per month; duplicate IDs keep the last row. Amount is the imported total_amount sum, with no cancelled-order exclusion or refund deduction; not net revenue or profit."]
        lines.extend(f"{row['period']}: {row['total_orders']} orders · {currency} {row['total_amount']:,.2f}" for row in rows)
        lines.append("No repeat-purchase, attribution, profit or causal conclusion; no action was drafted or executed.")
    else:
        lines = ["数据核对 · 未调用模型", f"来源：{source} · 币种：{currency}",
                 f"窗口：{rows[0]['period']} 至 {rows[-1]['period']}；最近 {len(rows)} 个有订单的 UTC 月份（最多 6 个）。",
                 "没有记录的月份不补零；不等于截至今天最近 6 个完整自然月，也不证明店铺历史完整。",
                 "口径：按月去重计数导入订单，同一订单 ID 重复时保留最后一行；金额为导入 total_amount 合计，未排除取消订单、未扣退款，不是净收入或利润。"]
        lines.extend(f"{row['period']}：{row['total_orders']} 笔订单 · {currency} {row['total_amount']:,.2f}" for row in rows)
        lines.append("本报告不推断复购、归因、利润或原因；没有生成或执行行动建议。")
    if comparison:
        pct = f"{comparison['change_pct']:+.2f}%" if comparison["change_pct"] is not None else ("undefined (zero baseline)" if english else "不可计算（基期为零）")
        lines.insert(1, (f"Latest two observed months: {previous['period']} → {current['period']}; amount difference {currency} {float(delta):+,.2f}; percentage {pct}."
                        if english else f"最近两期：{previous['period']} → {current['period']}；订单金额差额 {currency} {float(delta):+,.2f}；变化率 {pct}。"))
    lines.extend(item["message"] for item in report["issues"])
    lines.append(("Generated at: " if english else "查询时间：") + report["generated_at"])
    response.update(answer="\n".join(lines), error=None, error_code=None, error_stage=None,
                    evidence=[{"tool": "query_sales_trend", "success": True,
                               "summary": f"{source} · {currency} · {rows[0]['period']} – {rows[-1]['period']} · order-trend/v1"}])
    return response
