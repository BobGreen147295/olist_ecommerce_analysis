"""跨境电商订单数据源：安全导入、标准化与销售趋势查询。

本模块只保存经营分析所需的订单级数据。原始邮箱、手机号、地址等 PII 不在
该模型中存储，也不会进入 Agent prompt。真实外部触达必须由后续渠道连接器在
商家批准后处理。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from .task_store import _connect_database, _use_database


REQUIRED_ORDER_FIELDS = ("order_id", "ordered_at", "total_amount")
OPTIONAL_ORDER_FIELDS = (
    "customer_id", "status", "currency", "market", "timezone", "customer_locale", "marketing_consent",
)
MAX_IMPORT_ROWS = 200_000
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_MARKET_PATTERN = re.compile(r"^[A-Z]{2}$|^GLOBAL$")
_CONSENT_VALUES = {
    "true": "granted", "yes": "granted", "y": "granted", "1": "granted", "subscribed": "granted",
    "granted": "granted", "opted_in": "granted", "opt-in": "granted",
    "false": "denied", "no": "denied", "n": "denied", "0": "denied", "unsubscribed": "denied",
    "denied": "denied", "opted_out": "denied", "opt-out": "denied",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _add_column_if_missing(cursor: Any, statement: str) -> None:
    """兼容已创建的 PostgreSQL / SQLite 表；重复字段时安全跳过。"""
    # PostgreSQL marks a transaction as failed after a duplicate-column error.
    # A savepoint lets us recover without losing the rest of the schema migration.
    cursor.execute("SAVEPOINT commerce_column_migration")
    try:
        cursor.execute(statement)
        cursor.execute("RELEASE SAVEPOINT commerce_column_migration")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT commerce_column_migration")
        cursor.execute("RELEASE SAVEPOINT commerce_column_migration")
        if not any(token in str(exc).lower() for token in ("duplicate column", "already exists")):
            raise


def _ensure_schema() -> None:
    if not _use_database():
        raise RuntimeError("通用数据连接需要配置 DATABASE_URL")
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS commerce_data_sources (
                source_id VARCHAR(32) PRIMARY KEY,
                display_name VARCHAR(120) NOT NULL,
                source_type VARCHAR(24) NOT NULL,
                status VARCHAR(24) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT FALSE,
                created_by VARCHAR(32) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                record_count INTEGER NOT NULL,
                coverage_start VARCHAR(40),
                coverage_end VARCHAR(40),
                mapping_json TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS commerce_orders (
                source_id VARCHAR(32) NOT NULL,
                order_id VARCHAR(120) NOT NULL,
                customer_id VARCHAR(120),
                ordered_at VARCHAR(40) NOT NULL,
                total_amount DOUBLE PRECISION NOT NULL,
                currency VARCHAR(12),
                status VARCHAR(48),
                market VARCHAR(16),
                timezone VARCHAR(64),
                customer_locale VARCHAR(32),
                marketing_consent VARCHAR(16),
                PRIMARY KEY (source_id, order_id)
            )
            """
        )
        # Existing deployments created before v4 only have the original fields.
        _add_column_if_missing(cursor, "ALTER TABLE commerce_orders ADD COLUMN market VARCHAR(16)")
        _add_column_if_missing(cursor, "ALTER TABLE commerce_orders ADD COLUMN timezone VARCHAR(64)")
        _add_column_if_missing(cursor, "ALTER TABLE commerce_orders ADD COLUMN customer_locale VARCHAR(32)")
        _add_column_if_missing(cursor, "ALTER TABLE commerce_orders ADD COLUMN marketing_consent VARCHAR(16)")
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def list_data_sources(owner: str | None = None) -> list[dict[str, Any]]:
    _ensure_schema()
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        query = """SELECT source_id, display_name, source_type, status, is_active, created_by, created_at,
                   record_count, coverage_start, coverage_end FROM commerce_data_sources"""
        if owner is not None:
            query += f" WHERE created_by = {placeholder}"
            cursor.execute(query + " ORDER BY is_active DESC, created_at DESC", (owner,))
        else:
            cursor.execute(query + " ORDER BY is_active DESC, created_at DESC")
        rows = cursor.fetchall()
        cursor.close()
        fields = (
            "source_id", "display_name", "source_type", "status", "is_active", "created_by", "created_at",
            "record_count", "coverage_start", "coverage_end",
        )
        return [dict(zip(fields, row)) for row in rows]
    finally:
        conn.close()


def get_active_data_source(owner: str | None = None) -> dict[str, Any] | None:
    return next((source for source in list_data_sources(owner) if source["is_active"]), None)


def _read_csv(content: bytes) -> pd.DataFrame:
    errors: list[Exception] = []
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return pd.read_csv(BytesIO(content), encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            errors.append(exc)
    raise ValueError("无法解析 CSV，请确认文件分隔符和编码（建议 UTF-8）") from errors[-1]


def preview_order_csv(content: bytes) -> dict[str, Any]:
    """返回上传文件的安全预览，不持久化原文件。"""
    frame = _read_csv(content)
    if len(frame) > MAX_IMPORT_ROWS:
        raise ValueError(f"单次最多导入 {MAX_IMPORT_ROWS:,} 行订单数据")
    return {
        "columns": [str(column) for column in frame.columns],
        "row_count": int(len(frame)),
        "sample": frame.head(5).fillna("").to_dict(orient="records"),
    }


def _column_text(frame: pd.DataFrame, column: str | None, default: str = "") -> pd.Series:
    if not column:
        return pd.Series(default, index=frame.index, dtype="object")
    return frame[column].fillna("").astype(str).str.strip()


def _normalize_currency(value: str) -> str:
    currency = value.upper().strip()
    if not _CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("币种必须是 3 位 ISO 4217 代码，例如 USD、GBP 或 EUR")
    return currency


def _normalize_market(value: str) -> str:
    market = value.upper().strip() or "GLOBAL"
    if not _MARKET_PATTERN.fullmatch(market):
        raise ValueError("市场必须是两位国家/地区代码（如 US、GB、DE）或 GLOBAL")
    return market


def _normalize_timezone(value: str) -> str:
    timezone_name = value.strip() or "UTC"
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("时区必须是 IANA 格式，例如 America/New_York、Europe/London 或 UTC") from exc
    return timezone_name


def _normalize_consent(value: str) -> str:
    clean = value.lower().strip()
    return _CONSENT_VALUES.get(clean, "unknown")


def _normalize_orders(
    frame: pd.DataFrame,
    mapping: dict[str, str],
    defaults: dict[str, str],
) -> tuple[pd.DataFrame, int]:
    missing_targets = [field for field in REQUIRED_ORDER_FIELDS if not mapping.get(field)]
    if missing_targets:
        raise ValueError(f"缺少必填映射：{', '.join(missing_targets)}")
    missing_columns = [column for column in mapping.values() if column and column not in frame.columns]
    if missing_columns:
        raise ValueError(f"映射列不存在：{', '.join(missing_columns)}")

    default_currency = _normalize_currency(defaults.get("currency", ""))
    default_market = _normalize_market(defaults.get("market", "GLOBAL"))
    default_timezone = _normalize_timezone(defaults.get("timezone", "UTC"))
    output = pd.DataFrame(index=frame.index)
    output["order_id"] = _column_text(frame, mapping["order_id"])
    output["ordered_at"] = pd.to_datetime(frame[mapping["ordered_at"]], errors="coerce", utc=True)
    amount_text = _column_text(frame, mapping["total_amount"]).str.replace(r"[^0-9.\-]", "", regex=True)
    output["total_amount"] = pd.to_numeric(amount_text, errors="coerce")
    output["customer_id"] = _column_text(frame, mapping.get("customer_id"))
    output["status"] = _column_text(frame, mapping.get("status"))
    output["currency"] = _column_text(frame, mapping.get("currency"), default_currency).replace("", default_currency).str.upper()
    output["market"] = _column_text(frame, mapping.get("market"), default_market).replace("", default_market).str.upper()
    output["timezone"] = _column_text(frame, mapping.get("timezone"), default_timezone).replace("", default_timezone)
    output["customer_locale"] = _column_text(frame, mapping.get("customer_locale"))
    output["marketing_consent"] = _column_text(frame, mapping.get("marketing_consent")).map(_normalize_consent)

    invalid_currency = ~output["currency"].map(lambda item: bool(_CURRENCY_PATTERN.fullmatch(item)))
    invalid_market = ~output["market"].map(lambda item: bool(_MARKET_PATTERN.fullmatch(item)))
    invalid_timezone = ~output["timezone"].map(lambda item: _is_valid_timezone(item))
    valid = (
        output["order_id"].ne("")
        & output["ordered_at"].notna()
        & output["total_amount"].notna()
        & output["total_amount"].ge(0)
        & ~invalid_currency
        & ~invalid_market
        & ~invalid_timezone
    )
    rejected_count = int((~valid).sum())
    output = output.loc[valid].drop_duplicates(subset=["order_id"], keep="last").copy()
    if output.empty:
        raise ValueError("没有可导入的有效订单：请检查订单号、下单时间、订单金额、币种、市场和时区")
    output["ordered_at"] = output["ordered_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return output, rejected_count


def _is_valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
        return True
    except ZoneInfoNotFoundError:
        return False


def import_order_csv(
    content: bytes,
    display_name: str,
    mapping: dict[str, str],
    created_by: str,
    defaults: dict[str, str] | None = None,
) -> dict[str, Any]:
    """导入订单 CSV，自动设为唯一激活数据源。

    `defaults` is explicit so amount fields never lose their currency / market meaning
    when a source does not provide per-order metadata.
    """
    _ensure_schema()
    raw = _read_csv(content)
    if len(raw) > MAX_IMPORT_ROWS:
        raise ValueError(f"单次最多导入 {MAX_IMPORT_ROWS:,} 行订单数据")
    normalized, rejected_count = _normalize_orders(raw, mapping, defaults or {"currency": "USD"})
    source_id = f"csv_{uuid.uuid4().hex[:12]}"
    created_at = _now()
    coverage_start = normalized["ordered_at"].min()
    coverage_end = normalized["ordered_at"].max()
    clean_mapping = {field: column for field, column in mapping.items() if column}
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE commerce_data_sources SET is_active = FALSE WHERE created_by = {placeholder}", (created_by,))
        insert_source = (
            "INSERT INTO commerce_data_sources (source_id, display_name, source_type, status, is_active, created_by, "
            "created_at, record_count, coverage_start, coverage_end, mapping_json) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, "
            f"{placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})"
        )
        cursor.execute(
            insert_source,
            (
                source_id, display_name.strip()[:120] or "未命名订单 CSV", "csv", "ready", True, created_by,
                created_at, len(normalized), coverage_start, coverage_end,
                json.dumps({"mapping": clean_mapping, "defaults": defaults or {"currency": "USD"}}, ensure_ascii=False),
            ),
        )
        insert_order = (
            "INSERT INTO commerce_orders (source_id, order_id, customer_id, ordered_at, total_amount, currency, status, "
            "market, timezone, customer_locale, marketing_consent) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, "
            f"{placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})"
        )
        rows = [
            (
                source_id, row.order_id, row.customer_id or None, row.ordered_at, float(row.total_amount),
                row.currency, row.status or None, row.market, row.timezone, row.customer_locale or None,
                row.marketing_consent,
            )
            for row in normalized.itertuples(index=False)
        ]
        cursor.executemany(insert_order, rows)
        conn.commit()
        cursor.close()
        return {
            "source_id": source_id,
            "display_name": display_name.strip()[:120] or "未命名订单 CSV",
            "record_count": len(normalized),
            "rejected_count": rejected_count,
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "currencies": sorted(normalized["currency"].unique().tolist()),
            "markets": sorted(normalized["market"].unique().tolist()),
            "consent_known_rows": int((normalized["marketing_consent"] != "unknown").sum()),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connected_data_health(owner: str | None = None) -> dict[str, Any] | None:
    """Return source metadata and safety-critical coverage, never raw customer data."""
    source = get_active_data_source(owner)
    if not source:
        return None
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT currency, market, timezone, marketing_consent FROM commerce_orders
                WHERE source_id = {placeholder}""",
            (source["source_id"],),
        )
        rows = cursor.fetchall()
        cursor.close()
    finally:
        conn.close()
    frame = pd.DataFrame(rows, columns=["currency", "market", "timezone", "marketing_consent"])
    return {
        "source": source,
        "currencies": sorted(frame["currency"].dropna().unique().tolist()) if not frame.empty else [],
        "markets": sorted(frame["market"].dropna().unique().tolist()) if not frame.empty else [],
        "timezones": sorted(frame["timezone"].dropna().unique().tolist()) if not frame.empty else [],
        "consent_known_rate": float((frame["marketing_consent"] != "unknown").mean()) if not frame.empty else 0.0,
    }


def get_connected_sales_trend(months: int = 6, owner: str | None = None) -> dict[str, Any] | None:
    """Read active-source sales trend without aggregating different currencies."""
    source = get_active_data_source(owner)
    if not source:
        return None
    months = int(months)
    if not 1 <= months <= 36:
        return {"success": False, "data": None, "summary": "months 必须是 1 到 36 之间的整数", "source": source["display_name"]}
    health = get_connected_data_health(owner)
    currencies = health["currencies"] if health else []
    if len(currencies) != 1:
        return {
            "success": False,
            "data": None,
            "source": source["display_name"],
            "summary": "当前数据源包含多币种订单，系统不会把不同币种直接相加为 GMV。请按市场/币种拆分导入，或后续配置明确的 FX 报表口径。",
            "currencies": currencies,
        }
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT order_id, ordered_at, total_amount FROM commerce_orders WHERE source_id = {placeholder}",
            (source["source_id"],),
        )
        rows = cursor.fetchall()
        cursor.close()
    finally:
        conn.close()
    frame = pd.DataFrame(rows, columns=["order_id", "ordered_at", "total_amount"])
    if frame.empty:
        return {"success": False, "data": None, "summary": "已连接数据源没有可用订单", "source": source["display_name"]}
    frame["ordered_at"] = pd.to_datetime(frame["ordered_at"], errors="coerce", utc=True)
    frame["total_amount"] = pd.to_numeric(frame["total_amount"], errors="coerce")
    frame = frame.dropna(subset=["ordered_at", "total_amount"])
    frame["period"] = frame["ordered_at"].dt.strftime("%Y-%m")
    monthly = (
        frame.groupby("period", as_index=False)
        .agg(total_orders=("order_id", "nunique"), total_sales=("total_amount", "sum"))
        .sort_values("period")
        .tail(months)
    )
    monthly["sales_change_pct"] = monthly["total_sales"].pct_change() * 100
    monthly["orders_change_pct"] = monthly["total_orders"].pct_change() * 100
    data = monthly.to_dict(orient="records")
    latest = data[-1]
    currency = currencies[0]
    summary = (
        f"已连接数据源「{source['display_name']}」近 {len(data)} 个月销售趋势；"
        f"最新月 {latest['period']} 销售额 {currency} {latest['total_sales']:,.2f}，订单 {latest['total_orders']} 笔"
    )
    return {"success": True, "data": data, "summary": summary, "source": source["display_name"], "currency": currency}
