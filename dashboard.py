import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

# 设置页面配置
st.set_page_config(page_title="Olist电商数据分析仪表盘", layout="wide")

# 加载数据
@st.cache_data
def load_data():
    # 加载清洗后的数据
    customers = pd.read_csv("olist/cleaned_customers.csv")
    orders = pd.read_csv("olist/cleaned_orders.csv")
    payments = pd.read_csv("olist/cleaned_payments.csv")
    order_items = pd.read_csv("olist/cleaned_order_items.csv")
    
    # 加载机器学习结果
    user_clusters = pd.read_csv("olist/user_clusters.csv")
    rfm_analysis = pd.read_csv("olist/rfm_analysis.csv")
    sales_trends = pd.read_csv("olist/sales_trends.csv")
    
    return customers, orders, payments, order_items, user_clusters, rfm_analysis, sales_trends

# 加载数据
customers, orders, payments, order_items, user_clusters, rfm_analysis, sales_trends = load_data()

# 页面标题
st.title("Olist电商数据分析仪表盘")

# 侧边栏：筛选器
st.sidebar.header("筛选条件")
region = st.sidebar.selectbox("选择地区", ["全部"] + sorted(customers["customer_state"].unique()))

# 主内容区
col1, col2, col3 = st.columns(3)

# 关键指标卡片
with col1:
    total_orders = len(orders)
    st.metric("总订单数", total_orders)

with col2:
    total_sales = order_items["price"].sum()
    st.metric("总销售额", f"R${total_sales:,.2f}")

with col3:
    unique_customers = len(customers)
    st.metric("总用户数", unique_customers)

# 订单时间趋势
st.subheader("订单时间趋势")
orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"])
orders["month"] = orders["order_purchase_timestamp"].dt.to_period("M")
monthly_orders = orders.groupby("month").size().reset_index(name="订单数")
monthly_orders["month"] = monthly_orders["month"].astype(str)
st.line_chart(monthly_orders.set_index("month"))

# 用户分群分析
st.subheader("用户分群分析")
cluster_counts = user_clusters["cluster"].value_counts().reset_index()
cluster_counts.columns = ["聚类", "用户数"]

# 计算每个聚类的平均消费
cluster_stats = user_clusters.groupby("cluster").agg({
    "customer_id": "count",
    "total_spend": "mean",
    "order_count": "mean"
}).reset_index()
cluster_stats.columns = ["聚类", "用户数", "平均消费", "平均订单数"]

# 显示聚类统计
st.dataframe(cluster_stats)

# 聚类分布图表
fig, ax = plt.subplots()
sns.barplot(x="聚类", y="用户数", data=cluster_counts, ax=ax)
plt.title("用户聚类分布")
st.pyplot(fig)

# RFM客户价值分析
st.subheader("RFM客户价值分析")
rfm_counts = rfm_analysis["customer_segment"].value_counts().reset_index()
rfm_counts.columns = ["客户群体", "数量"]

# 计算每个客户群体的平均价值
rfm_stats = rfm_analysis.groupby("customer_segment").agg({
    "customer_id": "count",
    "Recency": "mean",
    "Frequency": "mean",
    "Monetary": "mean"
}).reset_index()
rfm_stats.columns = ["客户群体", "数量", "平均最近购买天数", "平均购买频率", "平均消费金额"]

# 显示RFM统计
st.dataframe(rfm_stats)

# RFM分布图表
fig, ax = plt.subplots()
sns.barplot(x="客户群体", y="数量", data=rfm_counts, ax=ax)
plt.xticks(rotation=45)
plt.title("客户价值分布")
st.pyplot(fig)

# 地区销量分布
st.subheader("地区销量分布")
if region == "全部":
    region_sales = order_items.merge(orders, on="order_id").merge(customers, on="customer_id")
    region_sales = region_sales.groupby("customer_state")["price"].sum().reset_index()
else:
    region_sales = order_items.merge(orders, on="order_id").merge(customers, on="customer_id")
    region_sales = region_sales[region_sales["customer_state"] == region].groupby("customer_state")["price"].sum().reset_index()

# 地区销量图表
fig, ax = plt.subplots(figsize=(12, 6))
sns.barplot(x="customer_state", y="price", data=region_sales, ax=ax)
plt.xticks(rotation=45)
plt.title("地区销量分布")
plt.xlabel("地区")
plt.ylabel("销售额")
st.pyplot(fig)

# 支付方式分析
st.subheader("支付方式分析")
payment_type_counts = payments["payment_type"].value_counts().reset_index()
payment_type_counts.columns = ["支付方式", "次数"]

# 支付方式图表
fig, ax = plt.subplots()
sns.barplot(x="支付方式", y="次数", data=payment_type_counts, ax=ax)
plt.xticks(rotation=45)
plt.title("支付方式分布")
st.pyplot(fig)

# 销量趋势预测
st.subheader("销量趋势预测")
# 显示前10个地区的销量趋势
if len(sales_trends) > 0:
    top_regions = sales_trends["region"].value_counts().head(10).index.tolist()
    filtered_trends = sales_trends[sales_trends["region"].isin(top_regions)]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    for region in top_regions:
        region_data = filtered_trends[filtered_trends["region"] == region]
        ax.plot(region_data["month"], region_data["sales"], label=region)
    plt.xticks(rotation=45)
    plt.title("地区销量趋势")
    plt.xlabel("月份")
    plt.ylabel("销量")
    plt.legend()
    st.pyplot(fig)

# 项目信息
st.sidebar.markdown("---")
st.sidebar.markdown("### 项目信息")
st.sidebar.markdown("- **项目名称**: Olist电商数据分析")
st.sidebar.markdown("- **技术栈**: Python, Pandas, Matplotlib, Scikit-learn")
st.sidebar.markdown("- **数据来源**: Olist电商平台公开数据集")
st.sidebar.markdown("- **分析维度**: 用户行为、销售趋势、客户价值")
