import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore")

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

print("="*60)
print("         Olist电商数据分析项目 - 简化版")
print("="*60)

# ====================== 导入数据 ======================
print("\n[1/4] 正在加载数据...")
customers = pd.read_csv("data/raw/olist_customers_dataset.csv")
orders = pd.read_csv("data/raw/olist_orders_dataset.csv")
payments = pd.read_csv("data/raw/olist_order_payments_dataset.csv")
order_items = pd.read_csv("data/raw/olist_order_items_dataset.csv")

print("  - 客户数据: %d 条" % len(customers))
print("  - 订单数据: %d 条" % len(orders))
print("  - 支付数据: %d 条" % len(payments))
print("  - 订单项数据: %d 条" % len(order_items))

# ====================== 数据清洗 ======================
print("\n[2/4] 正在清洗数据...")

# 清洗订单时间
time_cols = [
    'order_purchase_timestamp',
    'order_approved_at',
    'order_delivered_carrier_date',
    'order_delivered_customer_date',
    'order_estimated_delivery_date'
]
for col in time_cols:
    orders[col] = pd.to_datetime(orders[col], errors='coerce')

# 只保留有效订单
orders = orders.dropna(subset=['order_purchase_timestamp'])
orders = orders[(orders['order_purchase_timestamp'] >= '2016-01-01') &
                (orders['order_purchase_timestamp'] <= '2018-12-31')]

# 提取时间维度
orders['year'] = orders['order_purchase_timestamp'].dt.year
orders['month'] = orders['order_purchase_timestamp'].dt.month
orders['day'] = orders['order_purchase_timestamp'].dt.day
orders['hour'] = orders['order_purchase_timestamp'].dt.hour
orders['weekday'] = orders['order_purchase_timestamp'].dt.weekday

# 清洗支付表
payments = payments[payments['payment_value'] > 0]

print("  - 数据清洗完成")

# ====================== 数据分析和可视化 ======================
print("\n[3/4] 正在生成图表...")

# 创建输出目录
if not os.path.exists("output/charts"):
    os.makedirs("output/charts")

# 1. 各州用户数
df = customers.groupby('customer_state')['customer_id'].nunique().sort_values(ascending=False).head(15)
df.plot(kind='bar', figsize=(10,6))
plt.title('各州用户数')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_01_各州用户数.png")
plt.close()
print("  - chart_01_各州用户数.png")

# 2. 城市用户TOP20
city_counts = customers.groupby('customer_city')['customer_id'].nunique().sort_values(ascending=False).head(20)
city_counts.plot(kind='bar', figsize=(12,6))
plt.title('城市用户TOP20')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_02_城市用户TOP20.png")
plt.close()
print("  - chart_02_城市用户TOP20.png")

# 3. 各州购买力
state_sales = order_items.merge(orders, on="order_id").merge(customers, on="customer_id")
state_sales = state_sales.groupby("customer_state")["price"].sum().sort_values(ascending=False).head(15)
state_sales.plot(kind='bar', figsize=(10,6))
plt.title('各州购买力')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_03_各州购买力.png")
plt.close()
print("  - chart_03_各州购买力.png")

# 4. 支付方式分布
payment_counts = payments['payment_type'].value_counts()
payment_counts.plot(kind='bar', figsize=(10,6))
plt.title('支付方式分布')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_04_支付方式.png")
plt.close()
print("  - chart_04_支付方式.png")

# 5. 月度订单趋势
orders['month_year'] = orders['order_purchase_timestamp'].dt.to_period('M')
monthly_orders = orders.groupby('month_year')['order_id'].count()
monthly_orders.plot(kind='line', figsize=(12,6), marker='o')
plt.title('月度订单趋势')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_05_月度订单趋势.png")
plt.close()
print("  - chart_05_月度订单趋势.png")

# 6. 24小时订单分布
hourly_orders = orders.groupby('hour')['order_id'].count()
hourly_orders.plot(kind='bar', figsize=(10,6))
plt.title('24小时订单分布')
plt.tight_layout()
plt.savefig("output/charts/chart_06_24小时订单分布.png")
plt.close()
print("  - chart_06_24小时订单分布.png")

# 7. 订单状态分布
order_status = orders['order_status'].value_counts()
order_status.plot(kind='pie', autopct='%1.1f%%', figsize=(8,8))
plt.title('订单状态分布')
plt.ylabel('')
plt.tight_layout()
plt.savefig("output/charts/chart_07_订单状态分布.png")
plt.close()
print("  - chart_07_订单状态分布.png")

# 8. 商品价格分布
order_items['price'].plot(kind='hist', bins=50, figsize=(10,6))
plt.title('商品价格分布')
plt.xlabel('价格')
plt.tight_layout()
plt.savefig("output/charts/chart_08_商品价格分布.png")
plt.close()
print("  - chart_08_商品价格分布.png")

# ====================== 计算关键指标 ======================
print("\n[4/4] 正在计算关键指标...")

total_orders = len(orders)
total_sales = payments['payment_value'].sum()
total_customers = customers['customer_id'].nunique()
avg_order_value = total_sales / total_orders

print("\n关键指标汇总:")
print("────────────────────────")
print("总订单数: %d" % total_orders)
print("总销售额: R$%.2f" % total_sales)
print("总用户数: %d" % total_customers)
print("平均订单价值: R$%.2f" % avg_order_value)

print("\n" + "="*60)
print("         分析完成！")
print("="*60)
print("\n生成的图表已保存到: output/charts/")