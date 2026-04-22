# Olist 电商数据分析项目

这是一个基于 **Olist** 电商平台数据集的数据分析项目，通过 Python 实现数据清洗、可视化分析和机器学习模型，为电商运营提供数据支持。

## 项目目标
本项目使用真实的 **Olist** 电商平台交易数据，通过 Python 进行全流程数据分析，包括数据清洗、用户行为分析、商品分析、支付方式分析、用户价值结构等，为电商运营决策提供数据支持。

## 技术栈
| 技术类别 | 工具 / 库 |
| :--- | :--- |
| 编程语言 | Python |
| 数据处理 | Pandas, NumPy |
| 数据可视化 | Matplotlib |
| 数据库 | MySQL |
| 机器学习 | Scikit-learn (KMeans, Logistic Regression, Linear Regression) |
| 版本控制 | Git, GitHub |

## 数据集说明
本项目使用 **Olist** 电商平台的公开数据集，包含以下业务维度：
- 订单信息（订单时间、订单状态、商品价格、运费等）
- 用户信息（用户 ID、用户所在地区等）
- 支付信息（支付方式、支付期数、支付金额）
- 商品信息（商品 ID、价格、运费等）

## 项目功能模块
### 1. 数据清洗与预处理
- 缺失值、异常值的识别与处理
- 时间数据转换为时间戳，提取时间格式标准化
- 数据集成与关联，构建完整数据模型

### 2. 数据可视化分析
- 订单趋势分析（时间、商品类别等维度）
- 支付方式分布统计与占比分析
- 订单状态全流程统计与转换路径分析
- 地区用户分布与购买力分析
- 24小时订单量与销售额分布

### 3. 机器学习模块
#### 3.1 用户分群（KMeans）
- 使用 KMeans 算法将用户分为 3 个聚类
- 分析每个聚类的特征（消费金额、订单频率等）
- 生成用户分群结果文件

#### 3.2 购买预测（分类模型）
- 使用逻辑回归模型预测用户是否在 2018 年有购买行为
- 模型评估与性能分析
- 生成购买预测结果文件

#### 3.3 销量/地区趋势预测（回归）
- 对每个地区的销量趋势进行线性回归预测
- 评估各地区预测模型性能
- 生成销量趋势数据文件

#### 3.4 RFM客户价值分析
- 基于最近购买时间（Recency）、购买频率（Frequency）和购买金额（Monetary）三个维度评估客户价值
- 将客户分为高价值客户、潜在高价值客户、一般价值客户和低价值客户四个群体
- 分析每个客户群体的特征和分布
- 生成RFM分析结果文件

## 项目结构
```
olist_project/
├── PythonProject1/           # 主项目目录
│   ├── olist_analysis.py     # 主分析脚本
│   ├── chart_01_各州用户数.png    # 生成的图表
│   ├── chart_02_城市用户TOP20.png
│   ├── chart_03_城市购买力TOP15.png
│   ├── chart_04_各州购买力.png
│   ├── chart_05_支付方式.png
│   ├── chart_06_一周订单量.png
│   ├── chart_07_一周销售额.png
│   ├── chart_08_24小时订单量.png
│   ├── chart_09_24小时销售额.png
│   ├── chart_10_订单状态.png
│   ├── chart_11_商品单价TOP15.png
│   └── chart_12_月度订单趋势.png
├── olist/                    # 数据集目录
│   ├── olist_customers_dataset.csv
│   ├── olist_orders_dataset.csv
│   ├── olist_order_payments_dataset.csv
│   ├── olist_order_items_dataset.csv
│   ├── cleaned_customers.csv     # 清洗后数据
│   ├── cleaned_orders.csv
│   ├── cleaned_payments.csv
│   ├── cleaned_order_items.csv
│   ├── user_clusters.csv          # 机器学习结果
│   ├── purchase_predictions.csv
│   ├── sales_trends.csv
│   └── rfm_analysis.csv           # RFM分析结果
├── README.md                 # 项目说明文档
└── .gitignore                # Git 忽略文件配置
```

## 如何运行
1. 确保安装了所需的依赖包：
   ```bash
   pip install pandas numpy matplotlib pymysql scikit-learn
   ```

2. 确保 MySQL 数据库已启动，并且创建了名为 `olist_analysis` 的数据库

3. 运行主分析脚本：
   ```bash
   python PythonProject1/olist_analysis.py
   ```

4. 运行完成后，生成的图表和分析结果将保存在对应目录中

## 生成的文件
### 图表文件
- `PythonProject1/` 目录下的 12 张图表，展示各种数据分析结果

### 数据文件
- `olist/cleaned_*.csv` - 清洗后的数据集
- `olist/user_clusters.csv` - 用户分群结果
- `olist/purchase_predictions.csv` - 购买预测结果
- `olist/sales_trends.csv` - 销量趋势数据
- `olist/rfm_analysis.csv` - RFM客户价值分析结果

## 项目价值
1. **客户洞察**：通过用户分群了解不同客户群体的行为特征
2. **预测能力**：预测客户购买行为和销量趋势
3. **决策支持**：基于数据驱动的决策，优化营销和销售策略
4. **数据资产**：建立结构化的数据分析流程和结果，形成企业数据资产

## 未来改进方向
1. 扩展数据源，整合产品信息、评价数据和卖家数据
2. 优化机器学习模型，尝试随机森林、XGBoost等算法
3. 构建交互式数据可视化仪表盘
4. 开发简单的Web应用，实现结果的在线展示

## 作者
段鸿博

---

本项目展示了从数据清洗、可视化分析到机器学习的完整数据分析流程，适合作为数据分析实习的项目展示。
