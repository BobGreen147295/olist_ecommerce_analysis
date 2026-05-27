import pandas as pd
import json

# 读取数据
customers = pd.read_csv("data/processed/cleaned_customers.csv")
orders = pd.read_csv("data/processed/cleaned_orders.csv")
payments = pd.read_csv("data/processed/cleaned_payments.csv")
order_items = pd.read_csv("data/processed/cleaned_order_items.csv")
user_clusters = pd.read_csv("data/processed/user_clusters.csv")
rfm_analysis = pd.read_csv("data/processed/rfm_analysis.csv")
sales_trends = pd.read_csv("data/processed/sales_trends.csv")

# 计算关键指标
total_orders = len(orders)
total_sales = order_items['price'].sum()
total_users = len(customers)

# 支付方式分布
payment_distribution = payments['payment_type'].value_counts().to_dict()

# 用户聚类分布
cluster_distribution = user_clusters['cluster'].value_counts().to_dict()
cluster_stats = user_clusters.groupby('cluster').agg({
    'total_spent': 'mean',
    'order_count': 'mean'
}).to_dict()

# RFM客户价值分布
rfm_distribution = rfm_analysis['customer_segment'].value_counts().to_dict()
rfm_stats = rfm_analysis.groupby('customer_segment')['monetary'].mean().to_dict()

# 地区销量分布
region_sales = orders.merge(customers, on='customer_id').merge(order_items, on='order_id').groupby('customer_state')['price'].sum().sort_values(ascending=False).head(10).to_dict()

# 月度订单趋势
monthly_orders = orders.groupby(orders['order_purchase_timestamp'].str[:7]).size().to_dict()

# 地区销量趋势数据（在Python中处理好）
region_trend_data = []
top_regions = list(region_sales.keys())[:3]
for region in top_regions:
    region_data = sales_trends[sales_trends['customer_state'] == region]
    region_monthly = region_data.groupby('month')['total_sales'].sum().to_dict()
    region_trend_data.append({
        'name': region,
        'data': region_monthly
    })

# 获取所有月份
all_months = sorted(sales_trends['month'].unique())

# 填充缺失的月份数据
for region in region_trend_data:
    region['data'] = [region['data'].get(month, 0) for month in all_months]

# 生成HTML文件
html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Olist电商数据分析仪表盘</title>
    <link href="https://cdn.jsdelivr.net/npm/antd@5.12.8/dist/reset.css" rel="stylesheet">
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background-color: #f0f2f5;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #1890ff;
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .header p {{
            color: #666;
            font-size: 16px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .stat-number {{
            font-size: 24px;
            font-weight: bold;
            color: #1890ff;
            margin-bottom: 5px;
        }}
        .stat-label {{
            font-size: 14px;
            color: #666;
        }}
        .charts-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .chart-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .chart-card h3 {{
            margin-top: 0;
            margin-bottom: 20px;
            color: #333;
            font-size: 16px;
        }}
        .chart-container {{
            width: 100%;
            height: 300px;
        }}
        .full-width {{
            grid-column: 1 / -1;
        }}
        .tab-container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        .tabs {{
            display: flex;
            margin-bottom: 20px;
            border-bottom: 1px solid #e8e8e8;
        }}
        .tab {{
            padding: 10px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.3s;
        }}
        .tab.active {{
            color: #1890ff;
            border-bottom-color: #1890ff;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Olist电商数据分析仪表盘</h1>
            <p>基于巴西Olist真实电商数据集的全流程分析</p>
        </div>

        <!-- 关键指标卡片 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{total_orders:,}</div>
                <div class="stat-label">总订单数</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">R${total_sales:,.2f}</div>
                <div class="stat-label">总销售额</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_users:,}</div>
                <div class="stat-label">总用户数</div>
            </div>
        </div>

        <!-- 支付方式分布 -->
        <div class="charts-grid">
            <div class="chart-card">
                <h3>支付方式分布</h3>
                <div id="paymentChart" class="chart-container"></div>
            </div>
            <div class="chart-card">
                <h3>用户聚类分布</h3>
                <div id="clusterChart" class="chart-container"></div>
            </div>
        </div>

        <!-- 订单趋势 -->
        <div class="chart-card full-width">
            <h3>月度订单趋势</h3>
            <div id="trendChart" class="chart-container" style="height: 400px;"></div>
        </div>

        <!-- 标签页内容 -->
        <div class="tab-container">
            <div class="tabs">
                <div class="tab active" data-tab="userCluster">用户分群分析</div>
                <div class="tab" data-tab="rfm">RFM客户价值分析</div>
                <div class="tab" data-tab="region">地区销量分析</div>
            </div>

            <div class="tab-content active" id="userCluster">
                <div class="charts-grid">
                    <div class="chart-card">
                        <h3>各聚类平均消费</h3>
                        <div id="clusterSpendChart" class="chart-container"></div>
                    </div>
                    <div class="chart-card">
                        <h3>各聚类平均订单数</h3>
                        <div id="clusterOrderChart" class="chart-container"></div>
                    </div>
                </div>
            </div>

            <div class="tab-content" id="rfm">
                <div class="charts-grid">
                    <div class="chart-card">
                        <h3>客户价值分布</h3>
                        <div id="rfmChart" class="chart-container"></div>
                    </div>
                    <div class="chart-card">
                        <h3>各群体平均消费金额</h3>
                        <div id="rfmSpendChart" class="chart-container"></div>
                    </div>
                </div>
            </div>

            <div class="tab-content" id="region">
                <div class="charts-grid">
                    <div class="chart-card">
                        <h3>地区销量TOP10</h3>
                        <div id="regionChart" class="chart-container"></div>
                    </div>
                    <div class="chart-card">
                        <h3>地区销量趋势</h3>
                        <div id="regionTrendChart" class="chart-container"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // 数据
        const paymentData = {json.dumps(payment_distribution)};
        const clusterData = {json.dumps(cluster_distribution)};
        const clusterSpendData = {json.dumps(cluster_stats['total_spent'])};
        const clusterOrderData = {json.dumps(cluster_stats['order_count'])};
        const rfmData = {json.dumps(rfm_distribution)};
        const rfmSpendData = {json.dumps(rfm_stats)};
        const regionData = {json.dumps(region_sales)};
        const monthlyData = {json.dumps(monthly_orders)};
        const regionTrendData = {json.dumps(region_trend_data)};
        const months = {json.dumps(all_months)};

        // 初始化图表
        document.addEventListener('DOMContentLoaded', function() {{
            // 支付方式分布
            const paymentChart = echarts.init(document.getElementById('paymentChart'));
            const paymentChartData = Object.entries(paymentData).map(([name, value]) => ({{name, value}}));
            paymentChart.setOption({{
                tooltip: {{
                    trigger: 'item',
                    formatter: '{{a}} <br/>{{b}}: {{c}} ({{d}}%)'
                }},
                legend: {{
                    orient: 'vertical',
                    left: 'left',
                    data: paymentChartData.map(d => d.name)
                }},
                series: [{{
                    name: '支付方式',
                    type: 'pie',
                    radius: '60%',
                    data: paymentChartData,
                    emphasis: {{
                        itemStyle: {{
                            shadowBlur: 10,
                            shadowOffsetX: 0,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        }}
                    }}
                }}]
            }});

            // 用户聚类分布
            const clusterChart = echarts.init(document.getElementById('clusterChart'));
            const clusterChartData = Object.entries(clusterData).map(([name, value]) => ({{name: '聚类' + name, value}}));
            clusterChart.setOption({{
                tooltip: {{
                    trigger: 'axis',
                    axisPointer: {{
                        type: 'shadow'
                    }}
                }},
                xAxis: {{
                    type: 'category',
                    data: clusterChartData.map(d => d.name)
                }},
                yAxis: {{
                    type: 'value'
                }},
                series: [{{
                    data: clusterChartData.map(d => d.value),
                    type: 'bar',
                    itemStyle: {{
                        color: '#1890ff'
                    }}
                }}]
            }});

            // 月度订单趋势
            const trendChart = echarts.init(document.getElementById('trendChart'));
            const monthlyKeys = Object.keys(monthlyData).sort();
            const monthlyValues = monthlyKeys.map(key => monthlyData[key]);
            trendChart.setOption({{
                tooltip: {{
                    trigger: 'axis'
                }},
                xAxis: {{
                    type: 'category',
                    data: monthlyKeys
                }},
                yAxis: {{
                    type: 'value'
                }},
                series: [{{
                    data: monthlyValues,
                    type: 'line',
                    smooth: true,
                    lineStyle: {{
                        color: '#1890ff',
                        width: 2
                    }},
                    areaStyle: {{
                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                            {{offset: 0, color: 'rgba(24, 144, 255, 0.3)'}},
                            {{offset: 1, color: 'rgba(24, 144, 255, 0.1)'}}
                        ])
                    }}
                }}]
            }});

            // 各聚类平均消费
            const clusterSpendChart = echarts.init(document.getElementById('clusterSpendChart'));
            const clusterSpendKeys = Object.keys(clusterSpendData).sort();
            const clusterSpendValues = clusterSpendKeys.map(key => parseFloat(clusterSpendData[key]).toFixed(2));
            clusterSpendChart.setOption({{
                tooltip: {{
                    trigger: 'axis',
                    axisPointer: {{
                        type: 'shadow'
                    }}
                }},
                xAxis: {{
                    type: 'category',
                    data: clusterSpendKeys.map(k => '聚类' + k)
                }},
                yAxis: {{
                    type: 'value',
                    name: '平均消费 (R$)'
                }},
                series: [{{
                    data: clusterSpendValues,
                    type: 'bar',
                    itemStyle: {{
                        color: '#52c41a'
                    }}
                }}]
            }});

            // 各聚类平均订单数
            const clusterOrderChart = echarts.init(document.getElementById('clusterOrderChart'));
            const clusterOrderKeys = Object.keys(clusterOrderData).sort();
            const clusterOrderValues = clusterOrderKeys.map(key => parseFloat(clusterOrderData[key]).toFixed(2));
            clusterOrderChart.setOption({{
                tooltip: {{
                    trigger: 'axis',
                    axisPointer: {{
                        type: 'shadow'
                    }}
                }},
                xAxis: {{
                    type: 'category',
                    data: clusterOrderKeys.map(k => '聚类' + k)
                }},
                yAxis: {{
                    type: 'value',
                    name: '平均订单数'
                }},
                series: [{{
                    data: clusterOrderValues,
                    type: 'bar',
                    itemStyle: {{
                        color: '#fa8c16'
                    }}
                }}]
            }});

            // 客户价值分布
            const rfmChart = echarts.init(document.getElementById('rfmChart'));
            const rfmChartData = Object.entries(rfmData).map(([name, value]) => ({{name, value}}));
            rfmChart.setOption({{
                tooltip: {{
                    trigger: 'item',
                    formatter: '{{a}} <br/>{{b}}: {{c}} ({{d}}%)'
                }},
                legend: {{
                    orient: 'vertical',
                    left: 'left',
                    data: rfmChartData.map(d => d.name)
                }},
                series: [{{
                    name: '客户群体',
                    type: 'pie',
                    radius: '60%',
                    data: rfmChartData,
                    emphasis: {{
                        itemStyle: {{
                            shadowBlur: 10,
                            shadowOffsetX: 0,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        }}
                    }}
                }}]
            }});

            // 各群体平均消费金额
            const rfmSpendChart = echarts.init(document.getElementById('rfmSpendChart'));
            const rfmSpendChartData = Object.entries(rfmSpendData).map(([name, value]) => ({{name, value}}));
            rfmSpendChart.setOption({{
                tooltip: {{
                    trigger: 'axis',
                    axisPointer: {{
                        type: 'shadow'
                    }}
                }},
                xAxis: {{
                    type: 'category',
                    data: rfmSpendChartData.map(d => d.name),
                    axisLabel: {{
                        rotate: 45
                    }}
                }},
                yAxis: {{
                    type: 'value',
                    name: '平均消费 (R$)'
                }},
                series: [{{
                    data: rfmSpendChartData.map(d => parseFloat(d.value).toFixed(2)),
                    type: 'bar',
                    itemStyle: {{
                        color: '#722ed1'
                    }}
                }}]
            }});

            // 地区销量TOP10
            const regionChart = echarts.init(document.getElementById('regionChart'));
            const regionChartData = Object.entries(regionData).map(([name, value]) => ({{name, value}}));
            regionChart.setOption({{
                tooltip: {{
                    trigger: 'axis',
                    axisPointer: {{
                        type: 'shadow'
                    }}
                }},
                xAxis: {{
                    type: 'category',
                    data: regionChartData.map(d => d.name),
                    axisLabel: {{
                        rotate: 45
                    }}
                }},
                yAxis: {{
                    type: 'value',
                    name: '销售额 (R$)'
                }},
                series: [{{
                    data: regionChartData.map(d => parseFloat(d.value).toFixed(2)),
                    type: 'bar',
                    itemStyle: {{
                        color: '#13c2c2'
                    }}
                }}]
            }});

            // 地区销量趋势
            const regionTrendChart = echarts.init(document.getElementById('regionTrendChart'));
            regionTrendChart.setOption({{
                tooltip: {{
                    trigger: 'axis'
                }},
                legend: {{
                    data: regionTrendData.map(d => d.name)
                }},
                xAxis: {{
                    type: 'category',
                    data: months
                }},
                yAxis: {{
                    type: 'value',
                    name: '销售额 (R$)'
                }},
                series: regionTrendData.map(d => ({{
                    name: d.name,
                    type: 'line',
                    data: d.data.map(v => parseFloat(v).toFixed(2)),
                    smooth: true
                }}))
            }});

            // 标签页切换
            const tabs = document.querySelectorAll('.tab');
            tabs.forEach(tab => {{
                tab.addEventListener('click', function() {{
                    tabs.forEach(t => t.classList.remove('active'));
                    this.classList.add('active');
                    
                    const tabContents = document.querySelectorAll('.tab-content');
                    tabContents.forEach(content => content.classList.remove('active'));
                    const tabId = this.getAttribute('data-tab');
                    document.getElementById(tabId).classList.add('active');
                }});
            }});

            // 响应式调整
            window.addEventListener('resize', function() {{
                paymentChart.resize();
                clusterChart.resize();
                trendChart.resize();
                clusterSpendChart.resize();
                clusterOrderChart.resize();
                rfmChart.resize();
                rfmSpendChart.resize();
                regionChart.resize();
                regionTrendChart.resize();
            }});
        }});
    </script>
</body>
</html>'''

# 写入HTML文件
with open("dashboard/dashboard.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML仪表盘已更新！")
print("访问地址: http://localhost:8080/dashboard.html")