import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

# 设置中文字体
plt.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题

# 为柱状图添加数据标签
def add_value_labels(ax, fmt="{:,.0f}"):
    """为柱状图的每个柱子添加数据标签"""
    for rect in ax.patches:
        height = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2., height + 0.05 * height,
                fmt.format(height),
                ha='center', va='bottom')

# 设置页面配置
st.set_page_config(page_title="Olist电商数据分析仪表盘", layout="wide")

# 加载数据
@st.cache(allow_output_mutation=True)
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
<<<<<<< HEAD
col1, col2, col3 = st.columns([1, 1.5, 1])  # 增加中间列的宽度
=======
col1, col2, col3 = st.columns(3)
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5

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

# 使用Matplotlib绘制订单时间趋势图表
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(monthly_orders["month"], monthly_orders["订单数"], linewidth=2, marker='o')
plt.xticks(rotation=45, fontsize=10)
plt.title("订单时间趋势")
plt.xlabel("月份")
plt.ylabel("订单数")
ax.ticklabel_format(style='plain', axis='y')
# 添加数据标签
for i, v in enumerate(monthly_orders["订单数"]):
    ax.text(i, v + 0.02 * max(monthly_orders["订单数"]), f"{v:,}", ha='center', va='bottom', fontsize=8)
plt.tight_layout()
st.pyplot(fig)

# 用户分群分析
st.subheader("用户分群分析")
cluster_counts = user_clusters["cluster"].value_counts().reset_index()
cluster_counts.columns = ["聚类", "用户数"]

# 计算每个聚类的平均消费
cluster_stats = user_clusters.groupby("cluster").agg({
    "customer_id": "count",
<<<<<<< HEAD
    "total_spent": "mean",
        "order_count": "mean"
=======
    "total_spend": "mean",
    "order_count": "mean"
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5
}).reset_index()
cluster_stats.columns = ["聚类", "用户数", "平均消费", "平均订单数"]

# 显示聚类统计
<<<<<<< HEAD
# 设置数字格式，确保显示具体准确的数字
st.dataframe(cluster_stats.style.format({
    "用户数": "{:,.0f}",
    "平均消费": "{:,.2f}",
    "平均订单数": "{:,.2f}"
}))
=======
st.dataframe(cluster_stats)
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5

# 聚类分布图表
fig, ax = plt.subplots()
sns.barplot(x="聚类", y="用户数", data=cluster_counts, ax=ax)
plt.title("用户聚类分布")
<<<<<<< HEAD
# 添加数据标签
add_value_labels(ax)
=======
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5
st.pyplot(fig)

# RFM客户价值分析
st.subheader("RFM客户价值分析")
rfm_counts = rfm_analysis["customer_segment"].value_counts().reset_index()
rfm_counts.columns = ["客户群体", "数量"]

<<<<<<< HEAD
# 计算RFM统计
rfm_stats = rfm_analysis.groupby("customer_segment").agg({
    "customer_id": "count",
    "recency": "mean",
    "frequency": "mean",
    "monetary": "mean"
}).reset_index()
rfm_stats.columns = ["客户群体", "用户数", "平均最近购买天数", "平均购买频次", "平均消费金额"]

# 显示RFM统计
# 设置数字格式，确保显示具体准确的数字
st.dataframe(rfm_stats.style.format({
    "用户数": "{:,.0f}",
    "平均最近购买天数": "{:,.2f}",
    "平均购买频次": "{:,.2f}",
    "平均消费金额": "{:,.2f}"
}))
=======
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
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5

# RFM分布图表
fig, ax = plt.subplots()
sns.barplot(x="客户群体", y="数量", data=rfm_counts, ax=ax)
plt.xticks(rotation=45)
plt.title("客户价值分布")
<<<<<<< HEAD
# 添加数据标签
add_value_labels(ax)
=======
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5
st.pyplot(fig)

# 地区销量分布
st.subheader("地区销量分布")
if region == "全部":
    region_sales = order_items.merge(orders, on="order_id").merge(customers, on="customer_id")
    region_sales = region_sales.groupby("customer_state")["price"].sum().reset_index()
<<<<<<< HEAD
    # 只显示前10个销量最高的地区
    region_sales = region_sales.sort_values("price", ascending=False).head(10)
=======
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5
else:
    region_sales = order_items.merge(orders, on="order_id").merge(customers, on="customer_id")
    region_sales = region_sales[region_sales["customer_state"] == region].groupby("customer_state")["price"].sum().reset_index()

<<<<<<< HEAD
# 重命名列名
region_sales.columns = ["地区", "销售额"]

# 显示地区销量数据
st.dataframe(region_sales.style.format({
    "销售额": "{:,.2f}"
}))

# 地区销量图表
fig, ax = plt.subplots(figsize=(12, 8))  # 增加图表高度
sns.barplot(x="地区", y="销售额", data=region_sales, ax=ax)
plt.xticks(rotation=45, fontsize=10)
plt.title("地区销量分布（TOP10）")
plt.xlabel("地区")
plt.ylabel("销售额")
# 设置y轴为普通数字格式，避免科学计数法
ax.ticklabel_format(style='plain', axis='y')
# 调整y轴标签格式
ax.set_yticklabels([f"{int(y):,}" for y in ax.get_yticks()])
# 添加数据标签，使用两位小数格式，调整字体大小
for i, v in enumerate(region_sales["销售额"]):
    ax.text(i, v + 0.02 * max(region_sales["销售额"]), f"{v:,.2f}", ha='center', va='bottom', fontsize=9)
=======
# 地区销量图表
fig, ax = plt.subplots(figsize=(12, 6))
sns.barplot(x="customer_state", y="price", data=region_sales, ax=ax)
plt.xticks(rotation=45)
plt.title("地区销量分布")
plt.xlabel("地区")
plt.ylabel("销售额")
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5
st.pyplot(fig)

# 支付方式分析
st.subheader("支付方式分析")
payment_type_counts = payments["payment_type"].value_counts().reset_index()
payment_type_counts.columns = ["支付方式", "次数"]

<<<<<<< HEAD
# 显示支付方式分布数据
st.dataframe(payment_type_counts.style.format({
    "次数": "{:,.0f}"
}))

=======
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5
# 支付方式图表
fig, ax = plt.subplots()
sns.barplot(x="支付方式", y="次数", data=payment_type_counts, ax=ax)
plt.xticks(rotation=45)
plt.title("支付方式分布")
<<<<<<< HEAD
# 添加数据标签
add_value_labels(ax)
=======
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5
st.pyplot(fig)

# 销量趋势预测
st.subheader("销量趋势预测")
<<<<<<< HEAD
if len(sales_trends) > 0:
    # 计算每个地区的总销量，按销量排序
    region_totals = sales_trends.groupby("customer_state")["total_sales"].sum().reset_index()
    sorted_regions = region_totals.sort_values("total_sales", ascending=False)["customer_state"].tolist()
    
    # 全地区销量趋势 - 使用分面图表
    # 计算需要的子图数量
    num_regions = len(sorted_regions)
    num_cols = 3  # 每行显示3个图表
    num_rows = (num_regions + num_cols - 1) // num_cols  # 计算行数
    
    fig, axes = plt.subplots(num_rows, num_cols, figsize=(15, 3*num_rows))
    axes = axes.flatten()  # 将二维数组转换为一维，便于遍历
    
    # 为每个地区创建单独的子图
    for i, r in enumerate(sorted_regions):
        ax = axes[i]
        region_data = sales_trends[sales_trends["customer_state"] == r]
        ax.plot(region_data["month"], region_data["total_sales"], linewidth=2)
        ax.set_title(f"{r}地区")
        ax.set_xlabel("月份")
        ax.set_ylabel("销量")
        ax.ticklabel_format(style='plain', axis='y')
        ax.set_ylim(bottom=0)
        ax.grid(True, alpha=0.3)
        # 旋转x轴标签
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    # 隐藏多余的子图
    for i in range(num_regions, len(axes)):
        axes[i].set_visible(False)
    
    plt.suptitle("全地区销量趋势", fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.96])  # 为标题留出空间
    st.pyplot(fig)

# 主要地区销量趋势对比
st.subheader("主要地区销量趋势对比")
if len(sales_trends) > 0:
    # 显示前5个销量最高的地区
    top5_regions = region_totals.sort_values("total_sales", ascending=False).head(5)["customer_state"].tolist()
    filtered_trends = sales_trends[sales_trends["customer_state"].isin(top5_regions)]
    
    fig, ax = plt.subplots(figsize=(12, 8))
    # 使用对比明显的颜色
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    markers = ['o', 's', '^', 'D', 'v']
    
    for i, r in enumerate(top5_regions):
        region_data = filtered_trends[filtered_trends["customer_state"] == r]
        ax.plot(region_data["month"], region_data["total_sales"], 
                label=r, color=colors[i], marker=markers[i], linewidth=2, markersize=6)
    
    plt.xticks(rotation=45, fontsize=10)
    plt.title("主要地区销量趋势对比（TOP5）")
    plt.xlabel("月份")
    plt.ylabel("销量")
    ax.ticklabel_format(style='plain', axis='y')
    ax.set_ylim(bottom=0)
    plt.legend(loc='upper right', fontsize=10)
    plt.tight_layout()
=======
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
>>>>>>> 7f955359891447f7fc5052608088d68d044c1ff5
    st.pyplot(fig)

# 项目信息
st.sidebar.markdown("---")
st.sidebar.markdown("### 项目信息")
st.sidebar.markdown("- **项目名称**: Olist电商数据分析")
st.sidebar.markdown("- **技术栈**: Python, Pandas, Matplotlib, Scikit-learn")
st.sidebar.markdown("- **数据来源**: Olist电商平台公开数据集")
st.sidebar.markdown("- **分析维度**: 用户行为、销售趋势、客户价值")
