import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from matplotlib.widgets import Button, RadioButtons, CheckButtons

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用黑体显示中文
plt.rcParams['axes.unicode_minus'] = False

# 加载数据
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

# 预处理数据
orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"])
orders["month"] = orders["order_purchase_timestamp"].dt.to_period("M")
monthly_orders = orders.groupby("month").size().reset_index(name="订单数")
monthly_orders["month"] = monthly_orders["month"].astype(str)

# 计算关键指标
total_orders = len(orders)
total_sales = order_items["price"].sum()
total_customers = len(customers)

# 初始化图表
fig = plt.figure(figsize=(15, 10))
fig.suptitle('Olist电商数据分析仪表盘', fontsize=16)

# 子图布局
gs = fig.add_gridspec(3, 2, height_ratios=[1, 2, 2])
ax1 = fig.add_subplot(gs[0, 0])  # 关键指标
ax2 = fig.add_subplot(gs[0, 1])  # 支付方式
ax3 = fig.add_subplot(gs[1, :])  # 订单趋势
ax4 = fig.add_subplot(gs[2, 0])  # 用户分群
ax5 = fig.add_subplot(gs[2, 1])  # RFM分析

# 调整布局
plt.tight_layout(rect=[0, 0, 0.85, 0.95])

# 侧边栏控件区域
ax_radio = plt.axes([0.87, 0.7, 0.12, 0.2])
radio = RadioButtons(ax_radio, ['订单趋势', '用户分群', 'RFM分析', '地区销量'])

# 初始化显示内容
def update_view(label):
    # 清除所有子图
    ax1.clear()
    ax2.clear()
    ax3.clear()
    ax4.clear()
    ax5.clear()
    
    # 显示关键指标
    ax1.axis('off')
    ax1.text(0.1, 0.7, f'总订单数: {total_orders}', fontsize=12)
    ax1.text(0.1, 0.4, f'总销售额: R${total_sales:,.2f}', fontsize=12)
    ax1.text(0.1, 0.1, f'总用户数: {total_customers}', fontsize=12)
    
    # 显示支付方式
    payment_type_counts = payments["payment_type"].value_counts().reset_index()
    payment_type_counts.columns = ["支付方式", "次数"]
    sns.barplot(x="支付方式", y="次数", data=payment_type_counts, ax=ax2)
    ax2.set_title('支付方式分布')
    ax2.tick_params(axis='x', rotation=45)
    
    if label == '订单趋势':
        # 订单时间趋势
        ax3.plot(monthly_orders["month"], monthly_orders["订单数"])
        ax3.set_title('月度订单趋势')
        ax3.set_xlabel('月份')
        ax3.set_ylabel('订单数')
        ax3.tick_params(axis='x', rotation=45)
        
        # 用户分群
        cluster_counts = user_clusters["cluster"].value_counts().reset_index()
        cluster_counts.columns = ["聚类", "用户数"]
        sns.barplot(x="聚类", y="用户数", data=cluster_counts, ax=ax4)
        ax4.set_title('用户聚类分布')
        
        # RFM分析
        rfm_counts = rfm_analysis["customer_segment"].value_counts().reset_index()
        rfm_counts.columns = ["客户群体", "数量"]
        sns.barplot(x="客户群体", y="数量", data=rfm_counts, ax=ax5)
        ax5.set_title('客户价值分布')
        ax5.tick_params(axis='x', rotation=45)
        
    elif label == '用户分群':
        # 订单时间趋势
        ax3.plot(monthly_orders["month"], monthly_orders["订单数"])
        ax3.set_title('月度订单趋势')
        ax3.set_xlabel('月份')
        ax3.set_ylabel('订单数')
        ax3.tick_params(axis='x', rotation=45)
        
        # 用户分群详细分析
        cluster_stats = user_clusters.groupby("cluster").agg({
            "customer_id": "count",
            "total_spent": "mean",
            "order_count": "mean"
        }).reset_index()
        cluster_stats.columns = ["聚类", "用户数", "平均消费", "平均订单数"]
        
        # 绘制用户分群的平均消费
        sns.barplot(x="聚类", y="平均消费", data=cluster_stats, ax=ax4)
        ax4.set_title('各聚类平均消费')
        
        # 绘制用户分群的平均订单数
        sns.barplot(x="聚类", y="平均订单数", data=cluster_stats, ax=ax5)
        ax5.set_title('各聚类平均订单数')
        
    elif label == 'RFM分析':
        # 订单时间趋势
        ax3.plot(monthly_orders["month"], monthly_orders["订单数"])
        ax3.set_title('月度订单趋势')
        ax3.set_xlabel('月份')
        ax3.set_ylabel('订单数')
        ax3.tick_params(axis='x', rotation=45)
        
        # RFM详细分析
        rfm_stats = rfm_analysis.groupby("customer_segment").agg({
            "recency": "mean",
            "frequency": "mean",
            "monetary": "mean"
        }).reset_index()
        rfm_stats.columns = ["客户群体", "平均最近购买天数", "平均购买频率", "平均消费金额"]
        
        # 绘制平均最近购买天数
        sns.barplot(x="客户群体", y="平均最近购买天数", data=rfm_stats, ax=ax4)
        ax4.set_title('各群体平均最近购买天数')
        ax4.tick_params(axis='x', rotation=45)
        
        # 绘制平均消费金额
        sns.barplot(x="客户群体", y="平均消费金额", data=rfm_stats, ax=ax5)
        ax5.set_title('各群体平均消费金额')
        ax5.tick_params(axis='x', rotation=45)
        
    elif label == '地区销量':
        # 地区销量分布
        region_sales = order_items.merge(orders, on="order_id").merge(customers, on="customer_id")
        region_sales = region_sales.groupby("customer_state")["price"].sum().reset_index()
        region_sales = region_sales.sort_values("price", ascending=False).head(10)
        
        ax3.bar(region_sales["customer_state"], region_sales["price"])
        ax3.set_title('地区销量TOP10')
        ax3.set_xlabel('地区')
        ax3.set_ylabel('销售额')
        ax3.tick_params(axis='x', rotation=45)
        
        # 销量趋势预测
        if len(sales_trends) > 0:
            top_regions = sales_trends["customer_state"].value_counts().head(5).index.tolist()
            filtered_trends = sales_trends[sales_trends["customer_state"].isin(top_regions)]
            
            for region in top_regions:
                region_data = filtered_trends[filtered_trends["customer_state"] == region]
                ax4.plot(region_data["month"], region_data["order_count"], label=region)
            ax4.set_title('地区销量趋势')
            ax4.set_xlabel('月份')
            ax4.set_ylabel('销量')
            ax4.legend()
            ax4.tick_params(axis='x', rotation=45)
        
        # 隐藏第五个子图
        ax5.set_visible(False)
    
    # 重新绘制图表
    fig.canvas.draw_idle()

# 绑定事件
radio.on_clicked(update_view)

# 初始显示
update_view('订单趋势')

# 显示图表
plt.show()
