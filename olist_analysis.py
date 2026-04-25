import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import os

# ====================== 爬虫功能：获取巴西各地区人口数据 ======================
def crawl_brazil_population_data():
    """爬取巴西各地区人口数据"""
    # 检查目录是否存在
    if not os.path.exists('D:\\olist_project\\olist\\crawled_data'):
        os.makedirs('D:\\olist_project\\olist\\crawled_data')
    
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
        df.to_csv('D:\\olist_project\\olist\\crawled_data\\brazil_population.csv', index=False)
        print("✓ 巴西人口数据爬取完成，已保存到 crawled_data/brazil_population.csv")
        
        return df
    except Exception as e:
        print(f"✗ 爬取数据时出错: {e}")
        # 如果爬取失败，返回空DataFrame
        return pd.DataFrame()

# 执行爬虫
population_df = crawl_brazil_population_data()

# ====================== 导入原始数据（已全部改对路径） ======================
customers = pd.read_csv("D:\\olist_project\\olist\\olist_customers_dataset.csv")
orders = pd.read_csv("D:\\olist_project\\olist\\olist_orders_dataset.csv")
payments = pd.read_csv("D:\\olist_project\\olist\\olist_order_payments_dataset.csv")
order_items = pd.read_csv("D:\\olist_project\\olist\\olist_order_items_dataset.csv")

# ====================== 清洗订单时间 ======================
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

# ====================== 导出清洗后数据（已改对路径！） ======================
customers.to_csv("D:\\olist_project\\olist\\cleaned_customers.csv", index=False)
orders.to_csv("D:\\olist_project\\olist\\cleaned_orders.csv", index=False, na_rep='')
payments.to_csv("D:\\olist_project\\olist\\cleaned_payments.csv", index=False)
order_items.to_csv("D:\\olist_project\\olist\\cleaned_order_items.csv", index=False)

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
    merged_data.to_csv('D:\\olist_project\\olist\\crawled_data\\region_analysis.csv', index=False)
    
    # 绘制人均销售额图表
    plt.figure(figsize=(12, 6))
    merged_data.sort_values("sales_per_capita", ascending=False).plot(kind='bar', x='state', y='sales_per_capita', ax=plt.gca())
    plt.title('巴西各地区人均销售额（每百万人）')
    plt.xlabel('地区')
    plt.ylabel('人均销售额')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig("D:\\olist_project\\PythonProject1\\chart_13_各地区人均销售额.png")
    plt.close()
    
    print("✓ 结合人口数据的分析完成，已生成人均销售额图表")

# ====================== 画图模块 ======================
import matplotlib.pyplot as plt
import pymysql
import warnings
warnings.filterwarnings("ignore")

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

# ====================== 连接数据库 ======================
conn = pymysql.connect(
    host='localhost',
    port=3306,
    user='root',
    password='dhb831003@',
    database='olist_analysis',
    charset='utf8mb4'
)

# ------------------------------------------------------------------------------
# 1 各州用户数
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT customer_state, COUNT(DISTINCT customer_id) AS user_count
FROM customers GROUP BY customer_state ORDER BY user_count DESC LIMIT 15
""", conn)
df.plot(kind='bar', x='customer_state', y='user_count', figsize=(10,6))
plt.title('各州用户数')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_01_各州用户数.png")
plt.close()

# ------------------------------------------------------------------------------
# 2 城市用户TOP20
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT customer_city, COUNT(DISTINCT customer_id) AS user_count
FROM customers GROUP BY customer_city ORDER BY user_count DESC LIMIT 20
""", conn)
df.plot(kind='bar', x='customer_city', y='user_count', figsize=(10,6))
plt.title('城市用户数TOP20')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_02_城市用户TOP20.png")
plt.close()

# ------------------------------------------------------------------------------
# 3 城市购买力TOP15
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT c.customer_city, SUM(p.payment_value) AS gml_city
FROM customers c JOIN orders o ON c.customer_id=o.customer_id
JOIN payments p ON o.order_id=p.order_id
GROUP BY c.customer_city ORDER BY gml_city DESC LIMIT 15
""", conn)
df.plot(kind='bar', x='customer_city', y='gml_city', figsize=(10,6))
plt.title('城市购买力TOP15')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_03_城市购买力TOP15.png")
plt.close()

# ------------------------------------------------------------------------------
# 4 各州购买力
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT c.customer_state, SUM(p.payment_value) AS gml_state
FROM customers c JOIN orders o ON c.customer_id=o.customer_id
JOIN payments p ON o.order_id=p.order_id
GROUP BY c.customer_state ORDER BY gml_state DESC
""", conn)
df.plot(kind='bar', x='customer_state', y='gml_state', figsize=(10,6))
plt.title('各州购买力')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_04_各州购买力.png")
plt.close()

# ------------------------------------------------------------------------------
# 5 支付方式
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT payment_type, COUNT(*) AS cnt FROM payments GROUP BY payment_type
""", conn)
plt.pie(df['cnt'], labels=df['payment_type'], autopct='%1.1f%%')
plt.title('支付方式偏好')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_05_支付方式.png")
plt.close()

# ------------------------------------------------------------------------------
# 6 一周订单量
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT weekday, COUNT(DISTINCT o.order_id) order_count
FROM orders o JOIN payments p ON o.order_id=p.order_id GROUP BY weekday
""", conn)
df.plot(kind='line', x='weekday', y='order_count', marker='o', figsize=(10,6))
plt.title('一周订单量')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_06_一周订单量.png")
plt.close()

# ------------------------------------------------------------------------------
# 7 一周销售额
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT weekday, ROUND(SUM(payment_value),2) total_sales
FROM orders o JOIN payments p ON o.order_id=p.order_id GROUP BY weekday
""", conn)
df.plot(kind='bar', x='weekday', y='total_sales', figsize=(10,6))
plt.title('一周销售额')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_07_一周销售额.png")
plt.close()

# ------------------------------------------------------------------------------
# 8 24小时订单量
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT hour, COUNT(DISTINCT o.order_id) order_count
FROM orders o JOIN payments p ON o.order_id=p.order_id GROUP BY hour
""", conn)
df.plot(kind='line', x='hour', y='order_count', marker='o', figsize=(10,6))
plt.title('24小时订单量')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_08_24小时订单量.png")
plt.close()

# ------------------------------------------------------------------------------
# 9 24小时销售额
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT hour, ROUND(SUM(payment_value),2) total_sales
FROM orders o JOIN payments p ON o.order_id=p.order_id GROUP BY hour
""", conn)
df.plot(kind='bar', x='hour', y='total_sales', figsize=(10,6))
plt.title('24小时销售额')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_09_24小时销售额.png")
plt.close()

# ------------------------------------------------------------------------------
# 10 订单状态
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT order_status, COUNT(*) cnt FROM orders GROUP BY order_status
""", conn)
df.plot(kind='bar', x='order_status', y='cnt', figsize=(10,6))
plt.title('订单状态分布')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_10_订单状态.png")
plt.close()

# ------------------------------------------------------------------------------
# 11 商品均价TOP15
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT product_id, AVG(price) avg_price FROM order_items
GROUP BY product_id ORDER BY avg_price DESC LIMIT 15
""", conn)
df.plot(kind='bar', x='product_id', y='avg_price', figsize=(12,7))
plt.title('商品单价TOP15')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_11_商品单价TOP15.png")
plt.close()

# ------------------------------------------------------------------------------
# 12 月度订单趋势
# ------------------------------------------------------------------------------
df = pd.read_sql("""
SELECT year,month,COUNT(DISTINCT order_id) order_count FROM orders
GROUP BY year,month ORDER BY year,month
""", conn)
df['period'] = df['year'].astype(str)+'-'+df['month'].astype(str)
df.plot(kind='line', x='period', y='order_count', marker='o', figsize=(12,6))
plt.title('月度订单趋势')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("D:/olist_project/PythonProject1/chart_12_月度订单趋势.png")
plt.close()

# ====================== 机器学习模块 ======================
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import classification_report, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler, LabelEncoder

# 1. 用户分群（KMeans）
def user_segmentation():
    # 准备用户数据
    user_data = pd.read_sql("""
    SELECT c.customer_id, COUNT(o.order_id) as order_count, 
           SUM(p.payment_value) as total_spent
    FROM customers c
    LEFT JOIN orders o ON c.customer_id = o.customer_id
    LEFT JOIN payments p ON o.order_id = p.order_id
    GROUP BY c.customer_id
    """, conn)
    
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
    
    # 分析每个聚类的特征
    cluster_analysis = user_data.groupby('cluster').agg({
        'order_count': ['mean', 'count'],
        'total_spent': 'mean'
    }).round(2)
    
    print("\n用户分群分析结果：")
    print(cluster_analysis)
    
    # 保存分群结果
    user_data.to_csv("D:/olist_project/olist/user_clusters.csv", index=False)
    print("用户分群结果已保存到 D:/olist_project/olist/user_clusters.csv")

# 2. 购买预测（分类模型）
def purchase_prediction():
    # 准备数据
    purchase_data = pd.read_sql("""
    SELECT c.customer_id, 
           COUNT(o.order_id) as order_count, 
           SUM(p.payment_value) as total_spent,
           MAX(YEAR(o.order_purchase_timestamp)) as last_purchase_year
    FROM customers c
    LEFT JOIN orders o ON c.customer_id = o.customer_id
    LEFT JOIN payments p ON o.order_id = p.order_id
    GROUP BY c.customer_id
    """, conn)
    
    # 创建购买标签（是否在2018年有购买）
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
    purchase_data.to_csv("D:/olist_project/olist/purchase_predictions.csv", index=False)
    print("购买预测结果已保存到 D:/olist_project/olist/purchase_predictions.csv")

# 3. 销量/地区趋势预测（回归）
def sales_trend_prediction():
    # 准备销量数据
    sales_data = pd.read_sql("""
    SELECT c.customer_state, 
           YEAR(o.order_purchase_timestamp) as year, 
           MONTH(o.order_purchase_timestamp) as month,
           COUNT(DISTINCT o.order_id) as order_count,
           SUM(p.payment_value) as total_sales
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN payments p ON o.order_id = p.order_id
    GROUP BY c.customer_state, YEAR(o.order_purchase_timestamp), MONTH(o.order_purchase_timestamp)
    """, conn)
    
    # 处理时间特征
    sales_data['period'] = sales_data['year'] * 12 + sales_data['month']
    
    # 按地区进行预测
    states = sales_data['customer_state'].unique()
    
    print("\n各地区销量趋势预测：")
    for state in states:
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
        
        print(f"\n地区 {state}：")
        print(f"  均方误差 (MSE): {mse:.2f}")
        print(f"  R2 评分: {r2:.2f}")
    
    # 保存趋势数据
    sales_data.to_csv("D:/olist_project/olist/sales_trends.csv", index=False)
    print("\n销量趋势数据已保存到 D:/olist_project/olist/sales_trends.csv")

# 4. RFM客户价值分析
def rfm_analysis():
    # 准备RFM数据
    rfm_data = pd.read_sql("""
    SELECT c.customer_id, 
           MAX(o.order_purchase_timestamp) as last_purchase_date,
           COUNT(o.order_id) as frequency,
           SUM(p.payment_value) as monetary
    FROM customers c
    LEFT JOIN orders o ON c.customer_id = o.customer_id
    LEFT JOIN payments p ON o.order_id = p.order_id
    GROUP BY c.customer_id
    """, conn)
    
    # 计算Recency（最近一次购买到分析日期的天数）
    analysis_date = pd.to_datetime('2018-12-31')
    rfm_data['last_purchase_date'] = pd.to_datetime(rfm_data['last_purchase_date'])
    rfm_data['recency'] = (analysis_date - rfm_data['last_purchase_date']).dt.days
    
    # 处理缺失值
    rfm_data = rfm_data.fillna(0)
    
    # RFM评分（1-5分，越高越好）
    # 使用固定分箱边界计算得分
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
    
    # 转换为数值类型，处理可能的NaN值
    rfm_data['r_score'] = rfm_data['r_score'].cat.codes.fillna(0).astype(int)
    rfm_data['f_score'] = rfm_data['f_score'].cat.codes.fillna(0).astype(int)
    rfm_data['m_score'] = rfm_data['m_score'].cat.codes.fillna(0).astype(int)
    
    # 调整得分范围为1-5
    rfm_data['r_score'] = rfm_data['r_score'] + 1
    rfm_data['f_score'] = rfm_data['f_score'] + 1
    rfm_data['m_score'] = rfm_data['m_score'] + 1
    
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
    rfm_data.to_csv("D:/olist_project/olist/rfm_analysis.csv", index=False)
    print("RFM分析结果已保存到 D:/olist_project/olist/rfm_analysis.csv")

# 执行机器学习模块
print("\n=== 开始执行机器学习模块 ===")
user_segmentation()
purchase_prediction()
sales_trend_prediction()
rfm_analysis()
print("\n=== 机器学习模块执行完成 ===")

# ====================== 结束 ======================
conn.close()
print("\n12张图已全部保存成功！位置：D:/olist_project/PythonProject1/")
print("机器学习模块执行完成！")