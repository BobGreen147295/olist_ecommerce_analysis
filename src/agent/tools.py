"""
Agent 工具层：确定性数据查询工具

本模块封装了一系列数据查询函数，从 processed CSV 文件中读取数据。
每个函数返回统一的 dict 格式：{"success": bool, "data": ..., "summary": str}
仅依赖 pandas，无需其他外部服务。
"""

import pandas as pd
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


def _read_csv(filename: str) -> Optional[pd.DataFrame]:
    """安全读取 CSV 文件"""
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return None
    try:
        return pd.read_csv(filepath)
    except Exception as e:
        print(f"读取 {filename} 失败: {e}")
        return None


def _first_existing_column(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    for name in candidates:
        if name in df.columns:
            return name
    return None


def _normalize_region_frame(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """兼容旧版 geo 输出（customer_state / total_revenue / sales_per_million）。"""
    out = df.copy()
    state_col = _first_existing_column(out, "state", "customer_state")
    sales_col = _first_existing_column(out, "sales", "total_revenue")
    per_col = _first_existing_column(out, "sales_per_capita", "sales_per_million")
    if not state_col or not sales_col or not per_col or "population" not in out.columns:
        return None
    out["state"] = out[state_col].astype(str)
    out["sales"] = out[sales_col]
    out["sales_per_capita"] = out[per_col]
    return out.drop_duplicates(subset=["state"], keep="first")


def query_sales_by_region(region: str) -> dict:
    """从 region_analysis.csv 查某地区每百万人销售额和排名"""
    try:
        df = _read_csv("region_analysis.csv")
        if df is None:
            return {"success": False, "data": None, "summary": "region_analysis.csv 文件不存在"}

        df = _normalize_region_frame(df)
        if df is None:
            return {
                "success": False,
                "data": None,
                "summary": "region_analysis.csv 缺少 state/sales/population/sales_per_capita 等列",
            }

        region_upper = region.upper().strip()
        row = df[df["state"].str.upper() == region_upper]

        if row.empty:
            return {
                "success": False,
                "data": None,
                "summary": f"未找到地区 '{region}' 的数据，可用地区: {', '.join(df['state'].tolist())}"
            }

        df_sorted = df.sort_values("sales_per_capita", ascending=False).reset_index(drop=True)
        rank = int(df_sorted[df_sorted["state"].str.upper() == region_upper].index[0]) + 1
        total = len(df)

        record = row.iloc[0]
        data = {
            "state": record["state"],
            "sales": float(record["sales"]),
            "population": int(record["population"]),
            "sales_per_capita": float(record["sales_per_capita"]),
            "rank": rank,
            "total_regions": total,
        }

        return {
            "success": True,
            "data": data,
            "summary": (
                f"{record['state']}州每百万人销售额 R${data['sales_per_capita']:.2f}，"
                f"排名第 {rank}/{total}"
            ),
        }
    except Exception as e:
        return {"success": False, "data": None, "summary": f"查询地区销售数据异常: {str(e)}"}


def query_sales_trend(months: int = 6) -> dict:
    """从 sales_trends.csv 查近 N 个月趋势"""
    try:
        df = _read_csv("sales_trends.csv")
        if df is None:
            return {"success": False, "data": None, "summary": "sales_trends.csv 文件不存在"}

        months = int(months)
        if not 1 <= months <= 36:
            return {"success": False, "data": None, "summary": "months 必须是 1 到 36 之间的整数"}

        # 取最近 N 个月
        df["period"] = df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2)
        monthly = df.groupby("period").agg(
            total_orders=("order_count", "sum"),
            total_sales=("total_sales", "sum")
        ).reset_index().sort_values("period").tail(months)

        if monthly.empty:
            return {"success": False, "data": None, "summary": "无销售趋势数据"}

        # 计算环比
        monthly["sales_change_pct"] = monthly["total_sales"].pct_change() * 100
        monthly["orders_change_pct"] = monthly["total_orders"].pct_change() * 100

        data = monthly.to_dict(orient="records")

        latest = data[-1]
        prev = data[-2] if len(data) > 1 else None

        summary_parts = [f"近 {months} 个月销售趋势"]
        summary_parts.append(f"最新月 ({latest['period']}) 销售额 R${latest['total_sales']:,.2f}，订单 {latest['total_orders']} 笔")
        if prev:
            change = latest["sales_change_pct"]
            direction = "增长" if change > 0 else "下降"
            summary_parts.append(f"环比{direction} {abs(change):.1f}%")

        return {
            "success": True,
            "data": data,
            "summary": "；".join(summary_parts)
        }
    except Exception as e:
        return {"success": False, "data": None, "summary": f"查询销售趋势异常: {str(e)}"}


def query_payment_distribution() -> dict:
    """从 cleaned_payments.csv 查支付方式分布"""
    try:
        df = _read_csv("cleaned_payments.csv")
        if df is None:
            return {"success": False, "data": None, "summary": "cleaned_payments.csv 文件不存在"}

        stats = df.groupby("payment_type").agg(
            order_count=("order_id", "nunique"),
            total_value=("payment_value", "sum"),
            avg_installments=("payment_installments", "mean"),
        ).reset_index()

        stats["order_share"] = (stats["order_count"] / stats["order_count"].sum() * 100).round(2)
        stats["aov"] = (stats["total_value"] / stats["order_count"]).round(2)
        stats = stats.sort_values("total_value", ascending=False)

        data = stats.to_dict(orient="records")

        top = data[0]
        total_orders = stats["order_count"].sum()
        summary = (
            f"支付方式共 {len(data)} 种，总订单 {total_orders} 笔；"
            f"{top['payment_type']} 占比 {top['order_share']:.1f}%，"
            f"客单价 R${top['aov']:.2f}"
        )

        return {
            "success": True,
            "data": data,
            "summary": summary
        }
    except Exception as e:
        return {"success": False, "data": None, "summary": f"查询支付分布异常: {str(e)}"}


def query_user_segments() -> dict:
    """从 user_clusters.csv 查用户分群概况"""
    try:
        df = _read_csv("user_clusters.csv")
        if df is None:
            return {"success": False, "data": None, "summary": "user_clusters.csv 文件不存在"}

        if "cluster_label" not in df.columns:
            return {"success": False, "data": None, "summary": "user_clusters.csv 缺少 cluster_label 列"}

        order_col = _first_existing_column(df, "order_count", "frequency")
        spent_col = _first_existing_column(df, "total_spent", "monetary")
        agg = {"user_count": ("customer_id", "nunique")}
        if order_col:
            agg["avg_order_count"] = (order_col, "mean")
        if spent_col:
            agg["avg_total_spent"] = (spent_col, "mean")
        stats = df.groupby("cluster_label").agg(**agg).reset_index()

        stats["user_share"] = (stats["user_count"] / stats["user_count"].sum() * 100).round(2)
        stats = stats.sort_values("user_count", ascending=False)

        data = stats.round(2).to_dict(orient="records")

        total_users = int(stats["user_count"].sum())
        parts = [f"用户分群共 {len(data)} 类，总计 {total_users} 位客户"]
        for row in data:
            parts.append(f"{row['cluster_label']}: {int(row['user_count'])} 人 ({row['user_share']:.1f}%)")
        summary = "；".join(parts)

        return {
            "success": True,
            "data": data,
            "summary": summary
        }
    except Exception as e:
        return {"success": False, "data": None, "summary": f"查询用户分群异常: {str(e)}"}


def query_rfm_summary() -> dict:
    """从 rfm_analysis.csv 查 RFM 分层统计"""
    try:
        df = _read_csv("rfm_analysis.csv")
        if df is None:
            return {"success": False, "data": None, "summary": "rfm_analysis.csv 文件不存在"}

        stats = df.groupby("customer_segment").agg(
            customer_count=("customer_id", "nunique"),
            avg_frequency=("frequency", "mean"),
            avg_monetary=("monetary", "mean"),
            avg_recency=("recency", "mean"),
            avg_rfm_score=("rfm_score", "mean"),
        ).reset_index()

        stats["customer_share"] = (stats["customer_count"] / stats["customer_count"].sum() * 100).round(2)
        stats = stats.sort_values("avg_monetary", ascending=False)

        data = stats.round(2).to_dict(orient="records")

        total = int(stats["customer_count"].sum())
        parts = [f"RFM 分层共 {len(data)} 类客户，总计 {total} 位"]
        for row in data:
            parts.append(
                f"{row['customer_segment']}: {int(row['customer_count'])} 人，"
                f"平均消费 R${row['avg_monetary']:,.2f}"
            )
        summary = "；".join(parts)

        return {
            "success": True,
            "data": data,
            "summary": summary
        }
    except Exception as e:
        return {"success": False, "data": None, "summary": f"查询 RFM 统计异常: {str(e)}"}


def query_churn_risk() -> dict:
    """查询客户流失风险分布；优先使用 XGBoost 产物，兼容旧版购买预测产物。"""
    try:
        df = _read_csv("churn_predictions.csv")
        source = "churn_predictions.csv"
        if df is None:
            df = _read_csv("purchase_predictions.csv")
            source = "purchase_predictions.csv"
        if df is None:
            return {"success": False, "data": None, "summary": "未找到流失风险预测结果，请先运行 model_churn.py"}

        if "risk_level" in df.columns:
            stats = df.groupby("risk_level").agg(
                customer_count=("customer_id", "nunique"),
                avg_probability=("churn_probability", "mean"),
            ).reset_index().rename(columns={"risk_level": "risk"})
        elif "prediction" in df.columns:
            stats = df.groupby("prediction").agg(
                customer_count=("customer_id", "nunique"),
            ).reset_index().rename(columns={"prediction": "risk"})
            stats["avg_probability"] = None
        else:
            return {"success": False, "data": None, "summary": f"{source} 缺少风险字段"}

        total = stats["customer_count"].sum()
        stats["customer_share"] = (stats["customer_count"] / total * 100).round(2)
        data = stats.round(4).to_dict(orient="records")
        summary = f"流失风险结果来自 {source}，共 {int(total):,} 位客户；"
        summary += "；".join(
            f"{row['risk']}: {int(row['customer_count']):,} 人（{row['customer_share']:.1f}%）"
            for row in data
        )
        return {"success": True, "data": data, "summary": summary}
    except Exception as e:
        return {"success": False, "data": None, "summary": f"查询流失风险异常: {str(e)}"}


def query_top_categories(n: int = 10) -> dict:
    """从 cleaned_order_items.csv 查热销商品（按 product_id，数据集无品类表）"""
    try:
        df = _read_csv("cleaned_order_items.csv")
        if df is None:
            return {"success": False, "data": None, "summary": "cleaned_order_items.csv 文件不存在"}

        n = int(n)
        if not 1 <= n <= 100:
            return {"success": False, "data": None, "summary": "n 必须是 1 到 100 之间的整数"}

        # 按 product_id 统计销量和销售额
        stats = df.groupby("product_id").agg(
            order_count=("order_id", "nunique"),
            total_sales=("price", "sum"),
            avg_price=("price", "mean"),
            avg_freight=("freight_value", "mean"),
        ).reset_index()

        top_n = stats.sort_values("total_sales", ascending=False).head(n)
        top_n["sales_share"] = (top_n["total_sales"] / stats["total_sales"].sum() * 100).round(2)
        top_n = top_n.round(2)

        data = top_n.to_dict(orient="records")

        total_products = len(stats)
        total_sales_sum = stats["total_sales"].sum()
        top_revenue = top_n["total_sales"].sum()

        summary = (
            f"热销 TOP{n} 商品（按 product_id），共 {total_products} 个 SKU；"
            f"TOP{n} 总销售额 R${top_revenue:,.2f}，占全站 {top_revenue/total_sales_sum*100:.1f}%"
        )

        return {
            "success": True,
            "data": data,
            "summary": summary
        }
    except Exception as e:
        return {"success": False, "data": None, "summary": f"查询热销品类异常: {str(e)}"}


# 工具注册表：函数名 -> 函数映射
TOOL_REGISTRY = {
    "query_sales_by_region": query_sales_by_region,
    "query_sales_trend": query_sales_trend,
    "query_payment_distribution": query_payment_distribution,
    "query_user_segments": query_user_segments,
    "query_rfm_summary": query_rfm_summary,
    "query_churn_risk": query_churn_risk,
    "query_top_categories": query_top_categories,
}


def execute_tool(tool_name: str, **kwargs) -> dict:
    """统一的工具执行入口"""
    if tool_name not in TOOL_REGISTRY:
        return {"success": False, "data": None, "summary": f"未知工具: {tool_name}"}
    return TOOL_REGISTRY[tool_name](**kwargs)
