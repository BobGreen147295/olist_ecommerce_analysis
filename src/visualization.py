"""
图表生成模块（基于 Plotly 2026 技术栈）

替代 matplotlib，生成：
- 交互式 HTML 图表（可嵌入 Streamlit/Flask）
- PNG 回退
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "output" / "charts"

import sys

if str(PROJECT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "src"))

logger = logging.getLogger(__name__)

HAS_PLOTLY = False
HAS_MPL = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    logger.warning("Plotly 未安装，尝试使用 matplotlib 回退")

if not HAS_PLOTLY:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial"]
        plt.rcParams["axes.unicode_minus"] = False
        HAS_MPL = True
    except ImportError:
        HAS_MPL = False


def _save(fig, name: str, output_dir: Path) -> Optional[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{name}.html"
    png_path = output_dir / f"{name}.png"

    if HAS_PLOTLY:
        try:
            fig.write_html(html_path)
            fig.write_image(png_path, engine="kaleido")
            return png_path
        except Exception:
            try:
                fig.write_html(html_path)
                return html_path
            except Exception as e:
                logger.error(f"保存图表 {name} 失败: {e}")
                return None
    elif HAS_MPL:
        try:
            fig.savefig(png_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return png_path
        except Exception as e:
            logger.error(f"matplotlib 保存失败: {e}")
            return None
    return None


# ============ 1. 州用户/销售分布 ============

def chart_state_users(customers: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> Optional[Path]:
    data = (
        customers.groupby("customer_state")["customer_id"]
        .nunique()
        .sort_values(ascending=False)
        .head(15)
        .reset_index()
    )
    data.columns = ["state", "users"]

    if HAS_PLOTLY:
        fig = px.bar(data, x="state", y="users", title="各州用户数",
                     labels={"state": "州", "users": "用户数"},
                     color_discrete_sequence=["#3498db"])
        fig.update_layout(xaxis_tickangle=-45, bargap=0.2)
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(data["state"], data["users"], color="#3498db")
        ax.set_title("各州用户数")
        ax.set_xlabel("州")
        ax.set_ylabel("用户数")
        ax.tick_params(axis="x", rotation=45)
    else:
        return None

    return _save(fig, "chart_01_state_users", output_dir)


def chart_state_revenue(fact_orders: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> Optional[Path]:
    data = (
        fact_orders.groupby("customer_state")["payment_value"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    data.columns = ["state", "revenue"]

    if HAS_PLOTLY:
        fig = px.bar(data, x="state", y="revenue", title="各州购买力（总销售额）",
                     labels={"state": "州", "revenue": "总销售额 R$"},
                     color_discrete_sequence=["#27ae60"])
        fig.update_layout(xaxis_tickangle=-45, bargap=0.2)
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(data["state"], data["revenue"], color="#27ae60")
        ax.set_title("各州购买力（总销售额）")
        ax.set_xlabel("州")
        ax.set_ylabel("总销售额 R$")
        ax.tick_params(axis="x", rotation=45)
    else:
        return None
    return _save(fig, "chart_04_state_revenue", output_dir)


# ============ 2. 城市 TOP N ============

def chart_city_users(customers: pd.DataFrame, output_dir: Path = OUTPUT_DIR, top_n: int = 20) -> Optional[Path]:
    data = (
        customers.groupby("customer_city")["customer_id"]
        .nunique()
        .sort_values(ascending=False)
        .head(top_n)
        .reset_index()
    )
    data.columns = ["city", "users"]

    if HAS_PLOTLY:
        fig = px.bar(data, x="city", y="users", title=f"城市用户数 TOP{top_n}",
                     labels={"city": "城市", "users": "用户数"},
                     color_discrete_sequence=["#2980b9"])
        fig.update_layout(xaxis_tickangle=-45)
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(12, 7))
        ax.bar(data["city"], data["users"], color="#2980b9")
        ax.set_title(f"城市用户数 TOP{top_n}")
        ax.set_xlabel("城市")
        ax.set_ylabel("用户数")
        ax.tick_params(axis="x", rotation=45)
    else:
        return None
    return _save(fig, f"chart_02_city_users_top{top_n}", output_dir)


def chart_city_revenue(fact_orders: pd.DataFrame, output_dir: Path = OUTPUT_DIR, top_n: int = 15) -> Optional[Path]:
    data = (
        fact_orders.groupby("customer_city")["payment_value"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .reset_index()
    )
    data.columns = ["city", "revenue"]

    if HAS_PLOTLY:
        fig = px.bar(data, x="city", y="revenue", title=f"城市购买力 TOP{top_n}",
                     labels={"city": "城市", "revenue": "购买力 R$"},
                     color_discrete_sequence=["#16a085"])
        fig.update_layout(xaxis_tickangle=-45)
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(12, 7))
        ax.bar(data["city"], data["revenue"], color="#16a085")
        ax.set_title(f"城市购买力 TOP{top_n}")
        ax.set_xlabel("城市")
        ax.set_ylabel("购买力 R$")
        ax.tick_params(axis="x", rotation=45)
    else:
        return None
    return _save(fig, f"chart_03_city_revenue_top{top_n}", output_dir)


# ============ 3. 支付方式 ============

def chart_payment_distribution(fact_orders: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> Optional[Path]:
    if "payment_type" not in fact_orders.columns:
        return None
    counts = fact_orders["payment_type"].value_counts().reset_index()
    counts.columns = ["payment_type", "count"]

    if HAS_PLOTLY:
        fig = px.pie(counts, values="count", names="payment_type",
                     title="支付方式偏好", hole=0.3)
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(counts["count"], labels=counts["payment_type"], autopct="%1.1f%%")
        ax.set_title("支付方式偏好")
    else:
        return None
    return _save(fig, "chart_05_payment_distribution", output_dir)


# ============ 4. 时间维度 ============

def chart_weekly_pattern(orders: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> Optional[Path]:
    if "weekday" not in orders.columns:
        return None
    weekday_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    by_weekday = orders.groupby("weekday").size().reset_index(name="orders")
    by_weekday["weekday_label"] = by_weekday["weekday"].map(lambda i: weekday_labels[i] if i < 7 else str(i))

    if HAS_PLOTLY:
        fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=by_weekday["weekday_label"], y=by_weekday["orders"], name="订单量"))
        fig.update_layout(title="一周订单量分布", xaxis_title="星期", yaxis_title="订单量")
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(by_weekday["weekday_label"], by_weekday["orders"], color="#f39c12")
        ax.set_title("一周订单量分布")
        ax.set_xlabel("星期")
        ax.set_ylabel("订单量")
    else:
        return None
    return _save(fig, "chart_06_weekly_orders", output_dir)


def chart_hourly_pattern(orders: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> Optional[Path]:
    if "hour" not in orders.columns:
        return None
    by_hour = orders.groupby("hour").size().reset_index(name="orders")

    if HAS_PLOTLY:
        fig = px.line(by_hour, x="hour", y="orders", markers=True, title="24小时订单量",
                      labels={"hour": "小时", "orders": "订单量"})
        fig.update_xaxes(dtick=2)
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(by_hour["hour"], by_hour["orders"], marker="o", color="#8e44ad")
        ax.set_title("24小时订单量")
        ax.set_xlabel("小时")
        ax.set_ylabel("订单量")
        ax.set_xticks(range(0, 24, 2))
    else:
        return None
    return _save(fig, "chart_08_hourly_orders", output_dir)


def chart_monthly_trend(orders: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> Optional[Path]:
    if "year" not in orders.columns or "month" not in orders.columns:
        return None
    monthly = (
        orders.groupby(["year", "month"])
        .size()
        .reset_index(name="orders")
        .sort_values(["year", "month"])
    )
    monthly["period"] = monthly["year"].astype(str) + "-" + monthly["month"].astype(str).str.zfill(2)

    if HAS_PLOTLY:
        fig = px.line(monthly, x="period", y="orders", markers=True, title="月度订单趋势",
                      labels={"period": "月份", "orders": "订单数"})
        fig.update_layout(xaxis_tickangle=-45)
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(monthly["period"], monthly["orders"], marker="o", color="#c0392b")
        ax.set_title("月度订单趋势")
        ax.set_xlabel("月份")
        ax.set_ylabel("订单数")
        ax.tick_params(axis="x", rotation=45)
    else:
        return None
    return _save(fig, "chart_12_monthly_orders", output_dir)


# ============ 5. 人均销售额（地理） ============

def chart_per_capita_sales(
    region_analysis: Optional[pd.DataFrame] = None,
    state_revenue: Optional[pd.DataFrame] = None,
    population: Optional[pd.DataFrame] = None,
    output_dir: Path = OUTPUT_DIR,
) -> Optional[Path]:
    if region_analysis is None:
        if state_revenue is None or population is None:
            return None
        merged = state_revenue.merge(population, left_on="customer_state", right_on="state", how="left")
        if "sales_per_million" not in merged.columns:
            merged["sales_per_million"] = merged["total_revenue"] / merged["population"] * 1_000_000
        region_analysis = merged.sort_values("sales_per_million", ascending=False)

    if "sales_per_million" not in region_analysis.columns:
        return None
    state_col = "state" if "state" in region_analysis.columns else "customer_state"
    data = region_analysis.dropna(subset=["sales_per_million", state_col]).copy()

    if HAS_PLOTLY:
        fig = px.bar(data, x=state_col, y="sales_per_million",
                     title="巴西各地区人均销售额（每百万人）",
                     labels={state_col: "州", "sales_per_million": "每百万人销售额 R$"},
                     color_discrete_sequence=["#e67e22"])
        fig.update_layout(xaxis_tickangle=-45)
    elif HAS_MPL:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.bar(data[state_col], data["sales_per_million"], color="#e67e22")
        ax.set_title("巴西各地区人均销售额（每百万人）")
        ax.set_xlabel("州")
        ax.set_ylabel("每百万人销售额 R$")
        ax.tick_params(axis="x", rotation=45)
    else:
        return None
    return _save(fig, "chart_13_per_capita_sales", output_dir)


# ============ 6. 批量生成 ============

def generate_all(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    fact_orders: pd.DataFrame,
    region_analysis: Optional[pd.DataFrame] = None,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Optional[Path]]:
    """批量生成所有分析图表"""
    results = {
        "state_users": chart_state_users(customers, output_dir),
        "city_users": chart_city_users(customers, output_dir),
        "city_revenue": chart_city_revenue(fact_orders, output_dir),
        "state_revenue": chart_state_revenue(fact_orders, output_dir),
        "payment": chart_payment_distribution(fact_orders, output_dir),
        "weekly": chart_weekly_pattern(orders, output_dir),
        "hourly": chart_hourly_pattern(orders, output_dir),
        "monthly": chart_monthly_trend(orders, output_dir),
    }
    if region_analysis is not None:
        results["per_capita"] = chart_per_capita_sales(region_analysis=region_analysis, output_dir=output_dir)

    logger.info(f"已生成 {sum(v is not None for v in results.values())} 张图表到 {output_dir}")
    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 50)
    print("  图表生成模块 (Plotly 2026 技术栈)")
    print("=" * 50)
    print(f"Plotly 可用: {HAS_PLOTLY}")
    print(f"Matplotlib 回退: {HAS_MPL if not HAS_PLOTLY else 'N/A'}")

    from data_cleaning import build_fact_table, load_raw_data, clean_orders, clean_payments
    customers, orders, payments, order_items = load_raw_data()
    orders = clean_orders(orders)
    payments = clean_payments(payments)
    fact = build_fact_table(customers, orders, payments, order_items)

    results = generate_all(customers, orders, fact)
    print("\n生成结果:")
    for name, path in results.items():
        status = f"✅ {path}" if path else "❌ 失败"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
