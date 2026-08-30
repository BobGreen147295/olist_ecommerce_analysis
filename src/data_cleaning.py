"""
数据清洗模块 - 加载原始数据并进行清洗
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_RAW_DIR = PROJECT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_DIR / "data" / "processed"

logger = logging.getLogger(__name__)


def load_raw_data(
    raw_dir: Optional[Path] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """加载原始 Olist 数据

    Returns:
        (customers, orders, payments, order_items)
    """
    raw_dir = raw_dir or DATA_RAW_DIR
    customers = pd.read_csv(raw_dir / "olist_customers_dataset.csv")
    orders = pd.read_csv(raw_dir / "olist_orders_dataset.csv")
    payments = pd.read_csv(raw_dir / "olist_order_payments_dataset.csv")
    order_items = pd.read_csv(raw_dir / "olist_order_items_dataset.csv")

    logger.info(
        f"加载数据: 客户{len(customers)} / 订单{len(orders)} / "
        f"支付{len(payments)} / 订单项{len(order_items)}"
    )
    return customers, orders, payments, order_items


def clean_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """清洗订单表：时间转换、有效过滤、时间维度提取"""
    time_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    for col in time_cols:
        if col in orders.columns:
            orders[col] = pd.to_datetime(orders[col], errors="coerce")

    # 只保留有购买时间的有效订单
    orders = orders.dropna(subset=["order_purchase_timestamp"])
    orders = orders[
        (orders["order_purchase_timestamp"] >= "2016-01-01")
        & (orders["order_purchase_timestamp"] <= "2018-12-31")
    ]

    # 提取时间维度
    ts = orders["order_purchase_timestamp"]
    orders["year"] = ts.dt.year
    orders["month"] = ts.dt.month
    orders["day"] = ts.dt.day
    orders["hour"] = ts.dt.hour
    orders["weekday"] = ts.dt.weekday
    orders["order_date"] = ts.dt.date.astype(str)

    logger.info(f"清洗后订单数: {len(orders)}")
    return orders


def clean_payments(payments: pd.DataFrame) -> pd.DataFrame:
    """清洗支付表：过滤异常值"""
    payments = payments[payments["payment_value"] > 0]
    if "payment_installments" in payments.columns:
        payments = payments[payments["payment_installments"] > 0]
    logger.info(f"清洗后支付记录: {len(payments)}")
    return payments


def clean_customers(customers: pd.DataFrame) -> pd.DataFrame:
    """清洗客户表（目前直接返回，保持扩展性）"""
    return customers


def clean_order_items(order_items: pd.DataFrame) -> pd.DataFrame:
    """清洗订单项表（目前直接返回，保持扩展性）"""
    return order_items


def build_fact_table(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    payments: pd.DataFrame,
    order_items: pd.DataFrame,
) -> pd.DataFrame:
    """构建宽表（事实表）：订单 + 客户 + 支付 + 订单项聚合"""
    payment_by_order = (
        payments.groupby("order_id")
        .agg(
            payment_value=("payment_value", "sum"),
            payment_type=(
                "payment_type",
                lambda s: s.mode().iat[0] if len(s) > 0 else "unknown",
            ),
            payment_installments=("payment_installments", "max"),
        )
        .reset_index()
    )

    item_by_order = (
        order_items.groupby("order_id")
        .agg(item_revenue=("price", "sum"), freight_value=("freight_value", "sum"))
        .reset_index()
    )

    fact = (
        orders[["order_id", "customer_id", "order_status", "year", "month", "hour", "weekday", "order_date"]]
        .merge(
            customers[["customer_id", "customer_state", "customer_city"]],
            on="customer_id",
            how="left",
        )
        .merge(payment_by_order, on="order_id", how="left")
        .merge(item_by_order, on="order_id", how="left")
    )

    for col in ["payment_value", "item_revenue", "freight_value"]:
        if col in fact.columns:
            fact[col] = fact[col].fillna(0)

    logger.info(f"事实表构建完成: {len(fact)} 行")
    return fact


def build_sales_trends(fact_orders: pd.DataFrame) -> pd.DataFrame:
    """按州 × 月汇总，供 Agent query_sales_trend 使用。"""
    required = {"customer_state", "year", "month", "order_id", "payment_value"}
    missing = required - set(fact_orders.columns)
    if missing:
        raise ValueError(f"事实表缺少列: {sorted(missing)}")

    trends = (
        fact_orders.dropna(subset=["customer_state", "year", "month"])
        .groupby(["customer_state", "year", "month"], as_index=False)
        .agg(
            order_count=("order_id", "nunique"),
            total_sales=("payment_value", "sum"),
        )
    )
    trends["period"] = (
        trends["year"].astype(int).astype(str)
        + "-"
        + trends["month"].astype(int).astype(str).str.zfill(2)
    )
    return trends.sort_values(["year", "month", "customer_state"]).reset_index(drop=True)


def save_processed(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    payments: pd.DataFrame,
    order_items: pd.DataFrame,
    processed_dir: Optional[Path] = None,
) -> None:
    """保存清洗后数据"""
    processed_dir = processed_dir or DATA_PROCESSED_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)

    customers.to_csv(processed_dir / "cleaned_customers.csv", index=False)
    orders.to_csv(processed_dir / "cleaned_orders.csv", index=False, na_rep="")
    payments.to_csv(processed_dir / "cleaned_payments.csv", index=False)
    order_items.to_csv(processed_dir / "cleaned_order_items.csv", index=False)
    logger.info(f"清洗数据已保存: {processed_dir}")


def run_full_pipeline() -> dict[str, pd.DataFrame]:
    """运行完整清洗流水线"""
    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    customers, orders, payments, order_items = load_raw_data()
    orders = clean_orders(orders)
    payments = clean_payments(payments)
    customers = clean_customers(customers)
    order_items = clean_order_items(order_items)
    fact = build_fact_table(customers, orders, payments, order_items)
    save_processed(customers, orders, payments, order_items)
    sales_trends = build_sales_trends(fact)
    sales_trends.to_csv(DATA_PROCESSED_DIR / "sales_trends.csv", index=False)
    logger.info(f"销售趋势已保存: {DATA_PROCESSED_DIR / 'sales_trends.csv'} ({len(sales_trends)} 行)")
    return {
        "customers": customers,
        "orders": orders,
        "payments": payments,
        "order_items": order_items,
        "fact_orders": fact,
        "sales_trends": sales_trends,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 50)
    print("  数据清洗模块")
    print("=" * 50)
    result = run_full_pipeline()
    for k, v in result.items():
        print(f"  {k}: {len(v)} 行")


if __name__ == "__main__":
    main()
