"""通用电商订单数据源：CSV 连接器的持久化与标准化查询层。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import pandas as pd

from .task_store import _connect_database, _use_database


REQUIRED_ORDER_FIELDS = ("order_id", "ordered_at", "total_amount")
OPTIONAL_ORDER_FIELDS = ("customer_id", "status", "currency")
MAX_IMPORT_ROWS = 200_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
                PRIMARY KEY (source_id, order_id)
            )
            """
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def list_data_sources() -> list[dict[str, Any]]:
    _ensure_schema()
    conn, _ = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT source_id, display_name, source_type, status, is_active, created_by, created_at,
               record_count, coverage_start, coverage_end FROM commerce_data_sources
               ORDER BY is_active DESC, created_at DESC"""
        )
        rows = cursor.fetchall()
        cursor.close()
        fields = (
            "source_id", "display_name", "source_type", "status", "is_active", "created_by", "created_at",
            "record_count", "coverage_start", "coverage_end",
        )
        return [dict(zip(fields, row)) for row in rows]
    finally:
        conn.close()


def get_active_data_source() -> dict[str, Any] | None:
    sources = list_data_sources()
    return next((source for source in sources if source["is_active"]), None)


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


def _normalize_orders(frame: pd.DataFrame, mapping: dict[str, str]) -> tuple[pd.DataFrame, int]:
    missing_targets = [field for field in REQUIRED_ORDER_FIELDS if not mapping.get(field)]
    if missing_targets:
        raise ValueError(f"缺少必填映射：{', '.join(missing_targets)}")
    missing_columns = [column for column in mapping.values() if column and column not in frame.columns]
    if missing_columns:
        raise ValueError(f"映射列不存在：{', '.join(missing_columns)}")
    output = pd.DataFrame()
    output["order_id"] = frame[mapping["order_id"]].astype(str).str.strip()
    output["ordered_at"] = pd.to_datetime(frame[mapping["ordered_at"]], errors="coerce", utc=True)
    amount_text = frame[mapping["total_amount"]].astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
    output["total_amount"] = pd.to_numeric(amount_text, errors="coerce")
    for field in OPTIONAL_ORDER_FIELDS:
        source_column = mapping.get(field)
        output[field] = frame[source_column].astype(str).str.strip() if source_column else ""
    valid = (
        output["order_id"].ne("")
        & output["ordered_at"].notna()
        & output["total_amount"].notna()
        & output["total_amount"].ge(0)
    )
    rejected_count = int((~valid).sum())
    output = output.loc[valid].drop_duplicates(subset=["order_id"], keep="last").copy()
    if output.empty:
        raise ValueError("没有可导入的有效订单：请检查订单号、下单时间和订单金额映射")
    output["ordered_at"] = output["ordered_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return output, rejected_count


def import_order_csv(
    content: bytes,
    display_name: str,
    mapping: dict[str, str],
    created_by: str,
) -> dict[str, Any]:
    """导入订单 CSV，自动设为唯一激活数据源。"""
    _ensure_schema()
    raw = _read_csv(content)
    if len(raw) > MAX_IMPORT_ROWS:
        raise ValueError(f"单次最多导入 {MAX_IMPORT_ROWS:,} 行订单数据")
    normalized, rejected_count = _normalize_orders(raw, mapping)
    source_id = f"csv_{uuid.uuid4().hex[:12]}"
    created_at = _now()
    coverage_start = normalized["ordered_at"].min()
    coverage_end = normalized["ordered_at"].max()
    clean_mapping = {field: column for field, column in mapping.items() if column}
    conn, placeholder = _connect_database()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE commerce_data_sources SET is_active = FALSE")
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
                created_at, len(normalized), coverage_start, coverage_end, json.dumps(clean_mapping, ensure_ascii=False),
            ),
        )
        insert_order = (
            "INSERT INTO commerce_orders (source_id, order_id, customer_id, ordered_at, total_amount, currency, status) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})"
        )
        rows = [
            (
                source_id, row.order_id, row.customer_id or None, row.ordered_at, float(row.total_amount),
                row.currency or None, row.status or None,
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
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connected_sales_trend(months: int = 6) -> dict[str, Any] | None:
    """读取激活数据源的销售趋势；无连接数据时返回 None，由 Olist 工具回退。"""
    source = get_active_data_source()
    if not source:
        return None
    months = int(months)
    if not 1 <= months <= 36:
        return {"success": False, "data": None, "summary": "months 必须是 1 到 36 之间的整数"}
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
        return {"success": False, "data": None, "summary": "已连接数据源没有可用订单"}
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
    summary = (
        f"已连接数据源「{source['display_name']}」近 {len(data)} 个月销售趋势；"
        f"最新月 {latest['period']} 销售额 R$ {latest['total_sales']:,.2f}，订单 {latest['total_orders']} 笔"
    )
    return {"success": True, "data": data, "summary": summary, "source": source["display_name"]}
