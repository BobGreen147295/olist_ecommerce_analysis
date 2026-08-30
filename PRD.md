# Olist 海外电商 AI 运营增长分析系统 — 产品需求文档

**版本**: v2.0
**日期**: 2026-08-07
**状态**: 已交付

---

## 1. 产品概述

### 1.1 产品名称

Olist AI 运营增长分析系统（Olist AI Operations & Growth Analytics System）

### 1.2 一句话定位

面向巴西电商运营团队，基于 **LangGraph Agent + XGBoost + Ollama 本地 LLM**，从海量订单数据中**自动提取经营洞察、诊断异常、生成可执行策略**的智能分析决策平台。

### 1.3 背景与问题

巴西 Olist 电商平台积累了大量交易数据（9.9 万+ 订单、9.9 万+ 用户），传统 BI 工具只能呈现静态图表。本系统解决三个核心痛点：

| 痛点 | 当前状况 | 本系统方案 |
|------|---------|-----------|
| 数据与决策脱节 | 看到图表但不知道怎么做 | LLM Agent 自主分析数据，生成可执行策略（附 ROI 估算） |
| 缺乏客户分层 | 一刀切运营 | KMeans 聚类 + RFM 四层客户价值分层 |
| 缺乏预测能力 | 事后看报表 | XGBoost 流失预测模型，识别高风险客户 |

### 1.4 差异化价值

> 不是看板工具，而是 **从数据到决策的完整闭环**：清洗 → 分析 → 建模 → Agent 诊断 → LLM 策略生成。

**与 v1.0 的本质区别**：v1.0 使用规则引擎（if-else 树），v2.0 使用 **真正的 LLM Agent**——LLM 自主理解用户问题、自主选择数据工具、自主生成策略建议。

---

## 2. 目标用户

| 用户角色 | 核心场景 | 使用频率 |
|---------|---------|---------|
| 电商运营经理 | 提出自然语言问题，获取数据支撑的策略建议 | 每日 |
| 增长负责人 | 按地区/客群分析增长潜力，制定投放计划 | 每周 |
| 数据分析师 | 深入数据探索，验证业务假设 | 按需 |
| 面试官 | 评估候选人的 AI Agent 工程能力 | 一次性 |

---

## 3. 混合 AI 架构（核心设计理念）

本系统采用**三层混合架构**，每一层用最合适的技术而非一刀切：

```
┌──────────────────────────────────────────────────┐
│                  🧠 LLM 推理层                      │
│  职责：理解问题、分析数据、生成策略                    │
│  技术：Ollama + Qwen3:8b（本地，零成本）              │
│  特点：灵活、能处理自然语言、可能产生幻觉               │
│  约束：System Prompt 禁止无数据支撑的建议              │
└──────────────────────┬───────────────────────────┘
                       │ 只做推理，不碰数据
┌──────────────────────▼───────────────────────────┐
│                  ⚙️ 确定性工具层                     │
│  职责：数据查询、指标计算                             │
│  技术：Pandas（纯 Python，无外部依赖）                 │
│  特点：100% 准确、可复现、零幻觉                      │
│  7 个工具：地区/趋势/支付/分群/RFM/流失/品类           │
└──────────────────────┬───────────────────────────┘
                       │ 只查数据，不做决策
┌──────────────────────▼───────────────────────────┐
│                  📊 ML 模型层                       │
│  职责：用户分群、流失预测                             │
│  技术：KMeans + XGBoost（scikit-learn）            │
│  特点：数值预测、可评估（AUC）、可复现                │
└──────────────────────────────────────────────────┘
```

### 为什么不用纯 LLM 方案

| 纯 LLM 方案的风险 | 混合架构的解法 |
|------------------|---------------|
| LLM 可能编造数据 | 数据查询走 Pandas，100% 准确 |
| LLM 数值计算不精确 | 数值计算走 ML 模型 |
| LLM 策略可能空泛 | System Prompt 要求每条建议引用真实数据 |
| LLM 不可用时系统崩溃 | 工具层和 ML 层仍可独立产出分析报告 |

### 面试话术

> "我没有盲目追求'全用 LLM'。这个系统的设计原则是：**数据层绝对不经过 LLM**——用 Pandas 做确定性查询，用 XGBoost 做数值预测，LLM 只负责它最擅长的事——理解自然语言和生成策略建议。三层各司其职，互不干扰，LLM 出问题也不影响底层数据产出。"

---

## 4. 系统架构

```
┌─────────────────────────────────────────────────┐
│            用户入口 (Interface)                    │
│  CLI (run_agent.py)  │  Streamlit  │ 静态 HTML   │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│           🤖 Agent 编排层 (LangGraph)              │
│  agent_graph.py                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │fetch_data│→│ analyze  │→│  recommend   │  │
│  │LLM选工具  │  │LLM分析   │  │LLM生成策略    │  │
│  │执行查询   │  │关键发现  │  │P0-P2 + ROI  │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│             ⚙️ 工具层 (tools.py)                   │
│  7 个确定性数据查询工具（Pandas，100% 准确）        │
│  query_sales_by_region  │  query_sales_trend     │
│  query_payment_distribution  │  query_user_segments │
│  query_rfm_summary  │  query_top_categories      │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│           📊 分析建模层 (8 个独立模块)              │
│  crawler  │  data_cleaning  │  analysis_rfm      │
│  analysis_geo  │  analysis_payment               │
│  model_clustering (KMeans)  │  model_churn (XGBoost) │
│  visualization (13 张图表)                        │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              💾 数据层                             │
│  raw/ (4 CSVs)  │  processed/ (10 CSVs)          │
└─────────────────────────────────────────────────┘
```

---

## 5. 技术栈（2026 对标）

| 类别 | 技术 | 说明 |
|------|------|------|
| **Agent 编排** | LangGraph | 有向图状态机，三节点工作流 |
| **LLM 推理** | Ollama + Qwen3:8b | 本地开源模型，零 API 成本 |
| **数据处理** | Pandas, NumPy | 10 万级订单数据 |
| **用户分群** | KMeans (scikit-learn) | 3 类用户聚类 |
| **客户价值** | RFM 自定义算法 | 4 层价值分层 |
| **流失预测** | XGBoost | 高风险客户识别 |
| **可视化** | Matplotlib + Streamlit | 13 张静态图 + 交互仪表盘 |
| **爬虫** | Requests + BeautifulSoup | 巴西各州人口数据 |
| **Web 展示** | 静态 HTML + ECharts | 零依赖演示页 |

---

## 6. 功能清单

### 5.1 数据清洗管道 (P0) ✅

- 输入：4 个原始 CSV（customers, orders, order_items, payments）
- 处理：缺失值检测、时间标准化、异常过滤、多表关联
- 输出：4 个清洗 CSV + 6 个分析产出 CSV

### 5.2 多维度可视化 (P0) ✅

13 张图表覆盖 5 个维度：
- 地理：各州用户分布、城市 TOP20、购买力 TOP15、各州购买力
- 时间：月度趋势、24 小时分布、周规律
- 用户：RFM 分层、KMeans 聚类
- 支付：支付方式分布
- 商品：单价 TOP15、热销品类

### 5.3 AI Agent 运营诊断 (P0) ✅ — 核心

**三节点 LangGraph 工作流**：

| 节点 | 功能 | 实现 |
|------|------|------|
| fetch_data | LLM 解析用户自然语言问题 → 自主选择工具（1-3 个）→ 执行查询 → 汇总 | LLM 路由 + 确定性工具 |
| analyze | LLM 基于真实数据生成 3-5 条关键发现，每条引用具体数据 | LLM 推理 |
| recommend | LLM 生成 P0-P2 优先级策略，含行动点、预期效果、ROI 估算 | LLM 生成 + System Prompt 约束 |

**支持的诊断场景**：

| 场景 | 示例问题 |
|------|---------|
| 地区销量诊断 | "圣保罗州最近销量怎么样" |
| 销售趋势分析 | "分析最近半年的销售趋势" |
| 用户流失预警 | "客户流失情况如何，怎么挽回" |
| 支付方式诊断 | "支付方式分布有没有问题" |
| 选品优化 | "哪些产品卖得好" |
| 客户分层运营 | "我们的客户分群情况" |

### 5.4 KMeans 用户分群 (P0) ✅

- 3 类用户：普通用户、高消费用户、高频用户
- 输出：`user_clusters.csv` + 分群画像

### 5.5 RFM 客户价值分析 (P0) ✅

- 4 层分群：高价值、潜在高价值、一般价值、低价值
- 输出：`rfm_analysis.csv` + 分层运营策略

### 5.6 XGBoost 流失预测 (P0) ✅

- 基于 RFM 特征预测客户流失风险
- 高/中/低风险三级输出
- 输出：`purchase_predictions.csv`

### 5.7 外部数据增强 (P1) ✅

- 爬取巴西 27 个州人口数据
- 计算人均销售额，识别人均消费潜力地区

---

## 7. 数据流

```
原始 CSV (4 个, raw/)
    │
    ▼
[data_cleaning.py] → 缺失值/时间标准化/异常过滤
    │
    ▼
处理后 CSV (4 个, processed/)
    │
    ├──→ [analysis_rfm.py]      → rfm_analysis.csv
    ├──→ [analysis_geo.py]       → region_analysis.csv
    ├──→ [analysis_payment.py]   → 支付分析
    ├──→ [model_clustering.py]  → user_clusters.csv
    ├──→ [model_churn.py]       → purchase_predictions.csv
    ├──→ [crawler.py]           → brazil_population.csv
    └──→ [visualization.py]     → output/charts/ (13 PNG)
                                      │
                                      ▼
                              [Agent 层] ← tools.py 读取全部 CSV
                                      │
                              ┌───────┴───────┐
                              ▼               ▼
                         分析结论          策略建议
                         (LLM)            (LLM + P0-P2)
```

---

## 8. 项目结构（v2.0）

```
olist_project/
├── data/
│   ├── raw/                       # 原始数据（4 个 CSV）
│   └── processed/                 # 处理后数据 + 模型产出（10 个 CSV）
│
├── src/                           # 核心源代码
│   ├── crawler.py                 # 爬虫：巴西各州人口
│   ├── data_cleaning.py           # 数据清洗
│   ├── analysis_rfm.py            # RFM 客户价值分析
│   ├── analysis_geo.py            # 地理分析（人均销售额）
│   ├── analysis_payment.py        # 支付方式分析
│   ├── model_clustering.py        # KMeans 用户分群
│   ├── model_churn.py             # XGBoost 流失预测
│   ├── visualization.py           # Matplotlib 图表生成
│   └── agent/                     # 🤖 Agent 模块（核心）
│       ├── __init__.py
│       ├── tools.py               # 7 个数据查询工具 + TOOL_REGISTRY
│       ├── agent_graph.py         # LangGraph 三节点编排
│       └── run_agent.py           # CLI 入口
│
├── dashboard/                     # 演示入口
│   ├── dashboard.py               # Streamlit 交互仪表盘
│   └── ai_operations_system.html  # AI 运营系统 HTML
│
├── web/                           # 静态 Web 展示
│   ├── index.html                 # 主页面
│   ├── styles.css / app.js        # 样式与逻辑
│   ├── templates/                 # 页面模板
│   └── static/                    # 静态资源
│
├── reports/                       # 面试材料与文档
├── output/charts/                 # 13 张自动生成图表
├── README.md                      # 项目文档（含架构图与 Demo 示例）
├── PRD.md                         # 本文件
└── requirements.txt               # Python 依赖
```

---

## 9. 关键指标

| 指标 | 数值 |
|------|------|
| 总订单数 | 99,441 |
| 总销售额 | R$ 16,008,872 |
| 总客户数 | 99,441 |
| 平均客单价 | R$ 160.99 |
| 高价值客户 | 3,236 人（RFM 最高层） |
| XGBoost 高风险流失客户 | ~41,674 人 |
| Agent 数据工具数 | 7 个 |
| 图表数量 | 13 张 |
| 代码模块数 | 12 个（8 分析 + 3 Agent + 1 爬虫） |

---

## 10. 快速启动

```bash
# 1. 拉取 LLM 模型
ollama pull qwen3:8b

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行 Agent
python src/agent/run_agent.py "分析最近半年的销售趋势"

# 4. 运行 Streamlit 仪表盘
streamlit run dashboard/dashboard.py
```

---

## 11. 版本演进

| 版本 | 日期 | 核心变化 |
|------|------|---------|
| v1.0 | 2026-06 | 规则引擎 + God Script + matplotlib |
| v2.0 | 2026-08 | ✅ LangGraph Agent + LLM 推理 + 模块化拆分 + God Script 消除 |

---

## 12. 后续扩展方向

- [ ] **MCP Server 化**：将数据工具包装为 Model Context Protocol 服务
- [ ] **RAG 向量库**：历史运营报告入库，检索相似案例辅助策略生成
- [ ] **多轮对话**：Agent 支持追问和深度探索
- [ ] **Web Agent 界面**：在保留的 `web/` 模板基础上重建 Flask/Streamlit 聊天 UI
- [ ] **真实流失标签**：接入真实用户流失数据，替代 RFM 代理标签
- [ ] **Plotly 迁移**：将 13 张 matplotlib 图表迁移到 Plotly 交互式
