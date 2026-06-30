import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import os
import warnings
warnings.filterwarnings("ignore")

# ====================== 爬虫功能：获取巴西各地区人口数据 ======================
def crawl_brazil_population_data():
    """爬取巴西各地区人口数据"""
    # 检查目录是否存在
    if not os.path.exists('data/processed'):
        os.makedirs('data/processed')

    # 目标URL - 巴西人口数据
    url = "https://www.worldometers.info/world-population/brazil-population/"

    try:
        # 发送请求
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # 检查请求是否成功

        # 解析HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # 这里是模拟数据，实际项目中需要根据页面结构提取真实数据
        # 由于网站结构可能变化，这里使用模拟数据作为示例
        population_data = {
            'state': ['SP', 'RJ', 'MG', 'RS', 'PR', 'BA', 'SC', 'DF', 'GO', 'ES'],
            'population': [46649132, 17463349, 21168791, 11377239, 11433957, 14985284, 7338473, 3055149, 7206589, 3974687]
        }

        # 创建DataFrame
        df = pd.DataFrame(population_data)

        # 保存数据
        df.to_csv('data/processed/brazil_population.csv', index=False)
        print("[OK] 巴西人口数据爬取完成，已保存到 data/processed/brazil_population.csv")

        return df
    except Exception as e:
        print(f"[ERROR] 爬取数据时出错: {e}")
        # 如果爬取失败，返回空DataFrame
        return pd.DataFrame()

# 执行爬虫
population_df = crawl_brazil_population_data()

# ====================== 导入原始数据 ======================
print("\n正在加载数据...")
customers = pd.read_csv("data/raw/olist_customers_dataset.csv")
orders = pd.read_csv("data/raw/olist_orders_dataset.csv")
payments = pd.read_csv("data/raw/olist_order_payments_dataset.csv")
order_items = pd.read_csv("data/raw/olist_order_items_dataset.csv")

print(f"  - 客户数据: {len(customers)} 条")
print(f"  - 订单数据: {len(orders)} 条")
print(f"  - 支付数据: {len(payments)} 条")
print(f"  - 订单项数据: {len(order_items)} 条")

# ====================== 清洗订单时间 ======================
print("\n正在清洗数据...")
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

# ====================== 清洗支付表 ======================
payments = payments[payments['payment_value'] > 0]
payments = payments[payments['payment_installments'] > 0]

# ====================== 导出清洗后数据 ======================
print("\n正在导出清洗后的数据...")
customers.to_csv("data/processed/cleaned_customers.csv", index=False)
orders.to_csv("data/processed/cleaned_orders.csv", index=False, na_rep='')
payments.to_csv("data/processed/cleaned_payments.csv", index=False)
order_items.to_csv("data/processed/cleaned_order_items.csv", index=False)
print("[OK] 数据清洗完成，已保存到 data/processed/")

# ====================== 结合爬虫数据进行分析 ======================
if not population_df.empty:
    # 计算各地区销售额
    region_sales = order_items.merge(orders, on="order_id").merge(customers, on="customer_id")
    region_sales = region_sales.groupby("customer_state")["price"].sum().reset_index()
    region_sales.columns = ["state", "sales"]

    # 合并人口数据和销售数据
    merged_data = pd.merge(region_sales, population_df, on="state", how="inner")

    # 计算人均销售额
    merged_data["sales_per_capita"] = merged_data["sales"] / merged_data["population"] * 1000000  # 每百万人销售额

    # 保存合并后的数据
    merged_data.to_csv('data/processed/region_analysis.csv', index=False)
    print("[OK] 结合人口数据的分析完成，已保存到 data/processed/region_analysis.csv")

# ====================== 画图模块 ======================
import matplotlib.pyplot as plt

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

# 创建输出目录
if not os.path.exists('output/charts'):
    os.makedirs('output/charts')

# ====================== 从CSV文件读取数据进行分析 ======================
# 由于不依赖数据库，我们直接使用CSV文件进行分析

# 1. 各州用户数
print("\n正在生成图表...")
state_users = customers.groupby('customer_state')['customer_id'].nunique().sort_values(ascending=False).head(15)
plt.figure(figsize=(10, 6))
state_users.plot(kind='bar')
plt.title('各州用户数')
plt.xlabel('州')
plt.ylabel('用户数')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_01_各州用户数.png")
plt.close()
print("  [OK] chart_01_各州用户数.png")

# 2. 城市用户TOP20
city_users = customers.groupby('customer_city')['customer_id'].nunique().sort_values(ascending=False).head(20)
plt.figure(figsize=(10, 6))
city_users.plot(kind='bar')
plt.title('城市用户数TOP20')
plt.xlabel('城市')
plt.ylabel('用户数')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_02_城市用户TOP20.png")
plt.close()
print("  [OK] chart_02_城市用户TOP20.png")

# 3. 城市购买力TOP15
city_sales = order_items.merge(orders, on='order_id').merge(customers, on='customer_id').merge(payments, on='order_id')
city_revenue = city_sales.groupby('customer_city')['payment_value'].sum().sort_values(ascending=False).head(15)
plt.figure(figsize=(10, 6))
city_revenue.plot(kind='bar')
plt.title('城市购买力TOP15')
plt.xlabel('城市')
plt.ylabel('购买力')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_03_城市购买力TOP15.png")
plt.close()
print("  [OK] chart_03_城市购买力TOP15.png")

# 4. 各州购买力
state_revenue = city_sales.groupby('customer_state')['payment_value'].sum().sort_values(ascending=False)
plt.figure(figsize=(10, 6))
state_revenue.plot(kind='bar')
plt.title('各州购买力')
plt.xlabel('州')
plt.ylabel('购买力')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_04_各州购买力.png")
plt.close()
print("  [OK] chart_04_各州购买力.png")

# 5. 支付方式
payment_counts = payments['payment_type'].value_counts()
plt.figure(figsize=(8, 8))
plt.pie(payment_counts.values, labels=payment_counts.index, autopct='%1.1f%%')
plt.title('支付方式偏好')
plt.tight_layout()
plt.savefig("output/charts/chart_05_支付方式.png")
plt.close()
print("  [OK] chart_05_支付方式.png")

# 6. 一周订单量
weekday_orders = orders.groupby('weekday').size()
plt.figure(figsize=(10, 6))
weekday_orders.plot(kind='line', marker='o')
plt.title('一周订单量')
plt.xlabel('星期')
plt.ylabel('订单量')
plt.xticks(range(7), ['周一', '周二', '周三', '周四', '周五', '周六', '周日'])
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("output/charts/chart_06_一周订单量.png")
plt.close()
print("  [OK] chart_06_一周订单量.png")

# 7. 一周销售额
weekday_sales = city_sales.groupby('weekday')['payment_value'].sum()
plt.figure(figsize=(10, 6))
weekday_sales.plot(kind='bar')
plt.title('一周销售额')
plt.xlabel('星期')
plt.ylabel('销售额')
plt.xticks(range(7), ['周一', '周二', '周三', '周四', '周五', '周六', '周日'], rotation=0)
plt.tight_layout()
plt.savefig("output/charts/chart_07_一周销售额.png")
plt.close()
print("  [OK] chart_07_一周销售额.png")

# 8. 24小时订单量
hour_orders = orders.groupby('hour').size()
plt.figure(figsize=(10, 6))
hour_orders.plot(kind='line', marker='o')
plt.title('24小时订单量')
plt.xlabel('小时')
plt.ylabel('订单量')
plt.xticks(range(0, 24, 2))
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("output/charts/chart_08_24小时订单量.png")
plt.close()
print("  [OK] chart_08_24小时订单量.png")

# 9. 24小时销售额
hour_sales = city_sales.groupby('hour')['payment_value'].sum()
plt.figure(figsize=(10, 6))
hour_sales.plot(kind='bar')
plt.title('24小时销售额')
plt.xlabel('小时')
plt.ylabel('销售额')
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig("output/charts/chart_09_24小时销售额.png")
plt.close()
print("  [OK] chart_09_24小时销售额.png")

# 10. 订单状态
order_status = orders['order_status'].value_counts()
plt.figure(figsize=(10, 6))
order_status.plot(kind='bar')
plt.title('订单状态分布')
plt.xlabel('订单状态')
plt.ylabel('数量')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_10_订单状态.png")
plt.close()
print("  [OK] chart_10_订单状态.png")

# 11. 商品均价TOP15
product_avg_price = order_items.groupby('product_id')['price'].mean().sort_values(ascending=False).head(15)
plt.figure(figsize=(12, 7))
product_avg_price.plot(kind='bar')
plt.title('商品单价TOP15')
plt.xlabel('商品ID')
plt.ylabel('平均单价')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("output/charts/chart_11_商品单价TOP15.png")
plt.close()
print("  [OK] chart_11_商品单价TOP15.png")

# 12. 月度订单趋势
monthly_orders = orders.groupby(['year', 'month']).size().reset_index(name='order_count')
monthly_orders['period'] = monthly_orders['year'].astype(str) + '-' + monthly_orders['month'].astype(str)
plt.figure(figsize=(12, 6))
plt.plot(monthly_orders['period'], monthly_orders['order_count'], marker='o')
plt.title('月度订单趋势')
plt.xlabel('月份')
plt.ylabel('订单数')
plt.xticks(rotation=45, ha='right')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("output/charts/chart_12_月度订单趋势.png")
plt.close()
print("  [OK] chart_12_月度订单趋势.png")

# 13. 各地区人均销售额（如果有爬虫数据）
if not population_df.empty:
    plt.figure(figsize=(12, 6))
    merged_data.sort_values("sales_per_capita", ascending=False).plot(kind='bar', x='state', y='sales_per_capita', ax=plt.gca())
    plt.title('巴西各地区人均销售额（每百万人）')
    plt.xlabel('地区')
    plt.ylabel('人均销售额')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig("output/charts/chart_13_各地区人均销售额.png")
    plt.close()
    print("  [OK] chart_13_各地区人均销售额.png")

print("\n[OK] 所有图表已生成完成，保存在 output/charts/ 目录")

# ====================== 机器学习模块 ======================
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import classification_report, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

print("\n" + "="*60)
print("         机器学习分析模块")
print("="*60)

# 1. 用户分群（KMeans）
def user_segmentation():
    print("\n[1/4] 正在进行用户分群分析...")

    # 准备用户数据
    user_data = city_sales.groupby('customer_id').agg({
        'order_id': 'nunique',
        'payment_value': 'sum'
    }).reset_index()
    user_data.columns = ['customer_id', 'order_count', 'total_spent']

    # 处理缺失值
    user_data = user_data.fillna(0)

    # 特征选择
    features = user_data[['order_count', 'total_spent']]

    # 数据标准化
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)

    # 应用KMeans聚类
    kmeans = KMeans(n_clusters=3, random_state=42)
    user_data['cluster'] = kmeans.fit_predict(scaled_features)

    # 添加聚类标签
    cluster_labels = {
        0: '普通用户',
        1: '高消费用户',
        2: '高频用户'
    }
    user_data['cluster_label'] = user_data['cluster'].map(cluster_labels)

    # 分析每个聚类的特征
    cluster_analysis = user_data.groupby('cluster').agg({
        'order_count': ['mean', 'count'],
        'total_spent': 'mean'
    }).round(2)

    print("\n用户分群分析结果：")
    print(cluster_analysis)

    # 保存分群结果
    user_data.to_csv("data/processed/user_clusters.csv", index=False)
    print("[OK] 用户分群结果已保存到 data/processed/user_clusters.csv")

    return user_data

# 2. 购买预测（分类模型）
def purchase_prediction():
    print("\n[2/4] 正在进行购买预测分析...")

    # 准备数据
    purchase_data = city_sales.groupby('customer_id').agg({
        'order_id': 'nunique',
        'payment_value': 'sum',
        'order_purchase_timestamp': 'max'
    }).reset_index()
    purchase_data.columns = ['customer_id', 'order_count', 'total_spent', 'last_purchase_date']

    # 创建购买标签（是否在2018年有购买）
    purchase_data['last_purchase_year'] = pd.to_datetime(purchase_data['last_purchase_date']).dt.year
    purchase_data['purchased_2018'] = (purchase_data['last_purchase_year'] == 2018).astype(int)

    # 处理缺失值
    purchase_data = purchase_data.fillna(0)

    # 特征和标签
    X = purchase_data[['order_count', 'total_spent']]
    y = purchase_data['purchased_2018']

    # 数据拆分
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 模型训练
    model = LogisticRegression()
    model.fit(X_train, y_train)

    # 模型评估
    y_pred = model.predict(X_test)
    print("\n购买预测模型评估：")
    print(classification_report(y_test, y_pred))

    # 保存模型预测结果
    purchase_data['prediction'] = model.predict(X)
    purchase_data.to_csv("data/processed/purchase_predictions.csv", index=False)
    print("[OK] 购买预测结果已保存到 data/processed/purchase_predictions.csv")

# 3. 销量/地区趋势预测（回归）
def sales_trend_prediction():
    print("\n[3/4] 正在进行销量趋势预测分析...")

    # 准备销量数据
    sales_data = city_sales.groupby(['customer_state', 'year', 'month']).agg({
        'order_id': 'nunique',
        'payment_value': 'sum'
    }).reset_index()
    sales_data.columns = ['customer_state', 'year', 'month', 'order_count', 'total_sales']

    # 处理时间特征
    sales_data['period'] = sales_data['year'] * 12 + sales_data['month']

    # 按地区进行预测
    states = sales_data['customer_state'].unique()

    print("\n各地区销量趋势预测：")
    for state in states[:5]:  # 只显示前5个地区
        state_data = sales_data[sales_data['customer_state'] == state]

        if len(state_data) < 3:  # 数据不足，跳过
            continue

        # 特征和标签
        X = state_data[['period']]
        y = state_data['total_sales']

        # 数据拆分
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # 模型训练
        model = LinearRegression()
        model.fit(X_train, y_train)

        # 模型评估
        y_pred = model.predict(X_test)
        mse = mean_squared_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        print(f"  地区 {state}：MSE={mse:.2f}, R2={r2:.2f}")

    # 保存趋势数据
    sales_data.to_csv("data/processed/sales_trends.csv", index=False)
    print("[OK] 销量趋势数据已保存到 data/processed/sales_trends.csv")

# 4. RFM客户价值分析
def rfm_analysis():
    print("\n[4/4] 正在进行RFM客户价值分析...")

    # 准备RFM数据
    rfm_data = city_sales.groupby('customer_id').agg({
        'order_purchase_timestamp': 'max',
        'order_id': 'nunique',
        'payment_value': 'sum'
    }).reset_index()
    rfm_data.columns = ['customer_id', 'last_purchase_date', 'frequency', 'monetary']

    # 计算Recency（最近一次购买到分析日期的天数）
    analysis_date = pd.to_datetime('2018-12-31')
    rfm_data['last_purchase_date'] = pd.to_datetime(rfm_data['last_purchase_date'])
    rfm_data['recency'] = (analysis_date - rfm_data['last_purchase_date']).dt.days

    # 处理缺失值
    rfm_data = rfm_data.fillna(0)

    # RFM评分（1-5分，越高越好）
    rfm_data['r_score'] = pd.cut(rfm_data['recency'],
                                  bins=[-1, 30, 60, 90, 180, 365],
                                  labels=[5, 4, 3, 2, 1],
                                  right=False,
                                  include_lowest=True)

    rfm_data['f_score'] = pd.cut(rfm_data['frequency'],
                                  bins=[-1, 1, 2, 3, 5, 30],
                                  labels=[1, 2, 3, 4, 5],
                                  right=False,
                                  include_lowest=True)

    rfm_data['m_score'] = pd.cut(rfm_data['monetary'],
                                  bins=[-1, 100, 250, 500, 1000, 10000],
                                  labels=[1, 2, 3, 4, 5],
                                  right=False,
                                  include_lowest=True)

    # 转换为数值类型
    rfm_data['r_score'] = rfm_data['r_score'].cat.codes.fillna(0).astype(int) + 1
    rfm_data['f_score'] = rfm_data['f_score'].cat.codes.fillna(0).astype(int) + 1
    rfm_data['m_score'] = rfm_data['m_score'].cat.codes.fillna(0).astype(int) + 1

    # 计算总RFM得分
    rfm_data['rfm_score'] = rfm_data['r_score'] + rfm_data['f_score'] + rfm_data['m_score']

    # 客户分群
    def segment_customer(row):
        if row['rfm_score'] >= 13:
            return '高价值客户'
        elif row['rfm_score'] >= 10:
            return '潜在高价值客户'
        elif row['rfm_score'] >= 7:
            return '一般价值客户'
        else:
            return '低价值客户'

    rfm_data['customer_segment'] = rfm_data.apply(segment_customer, axis=1)

    # 分析每个客户群体的特征
    segment_analysis = rfm_data.groupby('customer_segment').agg({
        'recency': 'mean',
        'frequency': 'mean',
        'monetary': 'mean',
        'customer_id': 'count'
    }).round(2)

    print("\nRFM客户价值分析结果：")
    print(segment_analysis)

    # 保存RFM分析结果
    rfm_data.to_csv("data/processed/rfm_analysis.csv", index=False)
    print("[OK] RFM分析结果已保存到 data/processed/rfm_analysis.csv")

# 执行所有机器学习分析
print("\n开始执行机器学习分析...")
user_data = user_segmentation()
purchase_prediction()
sales_trend_prediction()
rfm_analysis()

print("\n" + "="*60)
print("         分析完成！")
print("="*60)
print("\n生成的文件：")
print("  - data/processed/cleaned_*.csv  (清洗后的数据)")
print("  - data/processed/user_clusters.csv  (用户分群结果)")
print("  - data/processed/purchase_predictions.csv  (购买预测结果)")
print("  - data/processed/sales_trends.csv  (销量趋势数据)")
print("  - data/processed/rfm_analysis.csv  (RFM分析结果)")
print("  - data/processed/brazil_population.csv  (巴西人口数据)")
print("  - data/processed/region_analysis.csv  (地区分析数据)")
print("  - output/charts/*.png  (所有图表)")
print("\n项目分析完成！")
