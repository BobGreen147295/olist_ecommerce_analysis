# Olist 电商数据分析项目

这是一个基于巴西 Olist 真实电商数据集的完整数据分析项目，涵盖数据清洗、数据分析、机器学习建模和可视化展示的全流程。

## 项目亮点

- **完整的数据分析流程**：从数据理解、清洗、分析到建模的全流程实现
- **机器学习应用**：KMeans 用户分群、逻辑回归购买预测、线性回归销量预测、RFM 客户价值分析
- **爬虫功能**：爬取巴西各地区人口数据，结合销售数据进行人均销售额分析
- **多种可视化方案**：Streamlit 交互式仪表盘、HTML 静态仪表盘、Matplotlib 图表
- **AI 运营智能系统**：动态筛选和实时分析的运营决策支持系统

## 核心成果

- **总订单数**：99,441
- **总销售额**：R$16,008,872.12
- **客户数**：99,441
- **平均客单价**：R$160.99
- **重点地区**：SP、RJ、MG
- **高价值客户**：12,032 人
- **潜在高价值客户**：36,989 人

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 数据处理 | Python, Pandas, NumPy |
| 数据可视化 | Matplotlib, Seaborn, ECharts |
| 机器学习 | Scikit-learn (KMeans, Logistic Regression, Linear Regression) |
| 交互式仪表盘 | Streamlit |
| 爬虫 | Requests, BeautifulSoup |
| 数据库 | MySQL, PyMySQL |

## 项目结构

```
olist_project/
├── data/
│   ├── raw/                          # 原始数据
│   │   ├── olist_customers_dataset.csv
│   │   ├── olist_orders_dataset.csv
│   │   ├── olist_order_payments_dataset.csv
│   │   └── olist_order_items_dataset.csv
│   └── processed/                    # 处理后的数据
│       ├── cleaned_customers.csv     # 清洗后的客户数据
│       ├── cleaned_orders.csv        # 清洗后的订单数据
│       ├── cleaned_payments.csv      # 清洗后的支付数据
│       ├── cleaned_order_items.csv   # 清洗后的订单项数据
│       ├── user_clusters.csv         # 用户分群结果
│       ├── rfm_analysis.csv          # RFM分析结果
│       ├── sales_trends.csv          # 销量趋势数据
│       ├── brazil_population.csv     # 巴西人口数据
│       └── region_analysis.csv       # 地区分析数据
├── src/                              # 源代码
│   ├── olist_analysis.py             # 主分析脚本（含爬虫、清洗、分析、建模）
│   ├── olist_analysis_simple.py      # 简化版分析脚本
│   ├── interactive_analysis.py       # 交互式分析仪表盘
│   ├── generate_dashboard.py         # 生成HTML仪表盘脚本
│   ├── ai_insight_engine.py          # AI洞察引擎
│   └── generate_ai_operations_system.py  # 生成AI运营系统
├── dashboard/                        # 仪表盘
│   ├── dashboard.py                  # Streamlit交互式仪表盘
│   ├── dashboard.html                # HTML仪表盘
│   ├── static_dashboard.html         # 静态HTML仪表盘
│   └── ai_operations_system.html     # AI运营智能系统
├── reports/                          # 报告文档
│   ├── ai_operations_interview_notes.md  # AI运营面试说明
│   └── interview_demo_script.md      # 面试演示脚本
├── output/charts/                    # 生成的图表
├── README.md                         # 项目说明
└── requirements.txt                  # 依赖配置
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行主分析脚本

```bash
python src/olist_analysis.py
```

这将自动完成：
- 数据清洗和预处理
- 生成13张可视化图表
- 执行机器学习建模（用户分群、购买预测、销量预测、RFM分析）
- 保存所有结果到 `data/processed/` 和 `output/charts/`

### 3. 启动交互式仪表盘

**Streamlit 仪表盘**（推荐）：
```bash
streamlit run dashboard/dashboard.py
```

**HTML 仪表盘**：
```bash
# 生成HTML仪表盘
python src/generate_dashboard.py

# 打开 dashboard/dashboard.html
```

**AI 运营智能系统**：
```bash
# 生成AI运营系统
python src/generate_ai_operations_system.py

# 打开 dashboard/ai_operations_system.html
```

## 功能模块

### 1. 数据清洗与预处理
- 处理缺失值、重复数据、异常订单
- 时间格式统一化
- 数据质量验证

### 2. 数据分析与可视化
- **用户分析**：各州用户数、城市用户TOP20
- **销售分析**：城市购买力TOP15、各州购买力、月度订单趋势
- **时间分析**：一周订单量、24小时订单量、24小时销售额
- **支付分析**：支付方式偏好
- **商品分析**：商品单价TOP15
- **订单分析**：订单状态分布
- **地区分析**：各地区人均销售额（结合爬虫数据）

### 3. 机器学习建模

#### 用户分群（KMeans）
- 基于订单数和消费金额进行聚类
- 识别高消费用户、高频用户、普通用户
- 为精准营销提供目标群体

#### 购买预测（逻辑回归）
- 预测用户是否会在2018年有购买行为
- 模型准确率和F1-score评估
- 识别潜在高价值客户

#### 销量趋势预测（线性回归）
- 按地区预测销量趋势
- R2评分评估预测效果
- 为库存管理提供参考

#### RFM 客户价值分析
- 基于最近购买时间、购买频率、消费金额
- 将客户分为高价值、潜在高价值、一般价值、低价值四个群体
- 为差异化运营提供依据

### 4. 爬虫功能
- 爬取巴西各地区人口数据
- 结合销售数据计算人均销售额
- 识别高消费潜力地区

### 5. AI 运营智能系统
- 动态筛选地区、客户分层、时间范围
- 实时计算经营指标
- AI 运营诊断和建议
- 活动预算模拟器
- 面试讲解提示

## 运营建议

### 地区策略
- **SP、RJ、MG** 是重点销售地区，适合优先投放广告和配置活动资源
- 其他地区可根据人均销售额评估增长潜力

### 客户运营
- **高价值客户**：提供会员权益和复购激励
- **潜在高价值客户**：使用优惠券、关联推荐推动二次购买
- **一般价值客户**：定期触达，提升购买频率
- **低价值客户**：控制成本，采用自动化触达

### 支付优化
- 信用卡是主流支付方式，可设计支付优惠、分期免息等策略
- 关注其他支付方式的使用场景，优化支付体验

## 可扩展方向

- 接入店铺后台 API，实现每日自动更新
- 接入大模型，自动生成运营日报和活动复盘
- 增加商品维度，做爆品识别和滞销品预警
- 加入广告数据，计算投放 ROI
- 加入评论文本分析，自动提取差评原因和商品优化建议

## 面试演示建议

1. **开场**：介绍项目是"基于真实电商数据的全流程分析项目"
2. **数据流程**：展示从原始数据到分析结果的完整流程
3. **核心指标**：展示订单数、销售额、客户数等关键指标
4. **可视化**：展示月度趋势、地区销售、支付方式等图表
5. **机器学习**：重点讲解用户分群和RFM分析如何转化为运营动作
6. **AI系统**：展示动态AI运营智能系统的实时分析能力

## 作者

- **项目类型**：数据分析实习项目
- **技术栈**：Python + MySQL + Scikit-learn + Streamlit
- **GitHub**：https://github.com/BobGreen147295/olist_ecommerce_analysis

## 许可证

本项目仅供学习和面试展示使用。
