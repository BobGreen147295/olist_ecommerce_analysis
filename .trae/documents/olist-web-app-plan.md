# Olist 电商智能分析网站实现计划

## Context（背景）

当前项目已完成数据分析、多智能体工作流、静态看板等模块，但都以脚本/命令行方式运行。用户希望升级成一个**带智能体对话框的网站**，用于面试展示和实际运营分析。要求：Flask + 华丽前端 + Streamlit 都用上，包含数据看板、智能体诊断报告、ChatGPT 风格对话框，对话能力采用"有 API Key 用 GPT-4o、无 Key 降级到规则匹配"的混合方案。

## 复用现有代码（不重复造轮子）

| 现有文件 | 复用点 |
|---------|--------|
| `src/enhanced_agent_workflow.py` | `EnhancedEcommerceAgentWorkflow`（诊断报告）、`EcommerceDataMart`（数据加载）、`LLMAgent`（OpenAI 客户端初始化逻辑） |
| `src/ecommerce_agent_workflow.py` | `EcommerceAgentWorkflow`（5智能体findings，对话上下文）、`get_chat_response`（规则匹配降级） |
| `dashboard/dashboard.py` | Streamlit 数据探索页（直接复用，iframe 嵌入） |
| `dashboard/dashboard.html` | ECharts 图表配置参考（配色、option 模式） |

**关键决策**：诊断报告用 `EnhancedEcommerceAgentWorkflow`（展示 AI+ML 亮点）；对话用 `EcommerceAgentWorkflow` 的 findings（5智能体覆盖客户/地区/活动/经营/支付，规则匹配命中率高），LLM 在其上层增强。

## 项目结构（新增 web/ 目录，不污染 src/）

```
web/
├── app.py                 # Flask 主应用（路由 + API）
├── chat_agent.py          # 【核心】统一对话接口（LLM + 规则混合）
├── data_service.py        # 数据服务层（lru_cache 缓存 + 图表数据聚合）
├── run.py                 # 启动脚本（同时拉起 Flask + Streamlit）
├── templates/
│   ├── base.html          # 基础布局（导航栏 + 玻璃态主题）
│   ├── dashboard.html     # 数据看板页
│   ├── diagnosis.html     # 智能体诊断报告页
│   ├── chat.html          # 智能体对话页
│   └── explore.html       # Streamlit 嵌入页（iframe）
└── static/
    ├── css/{main,dashboard,chat}.css
    └── js/{dashboard,diagnosis,chat}.js
```

## 关键模块设计

### 1. `web/data_service.py` — 数据服务层
- `@lru_cache(maxsize=1)` 缓存 `EcommerceDataMart.load()` 结果（避免重复加载 18MB orders.csv）
- 5 个聚合函数：`get_overview()`、`get_sales_trend()`、`get_customer_segments()`、`get_region_distribution()`、`get_payment_structure()`
- 对应 5 个 `/api/dashboard/*` 路由

### 2. `web/chat_agent.py` — 统一对话接口（核心新模块）
```
ChatAgent 类：
  __init__: 启动时跑 EcommerceAgentWorkflow 缓存 findings + 初始化 LLMAgent
  respond(user_input) -> ChatResponse:
    if LLM 可用:
        try: 调 GPT-4o（把 findings 作为上下文注入 prompt）→ source="llm"
        except: 降级
    降级: 复用 get_chat_response(user_input, findings, result) → source="rule"
```
- **LLM 上下文增强**：即使有 LLM，也把规则引擎 findings 注入 prompt，让 GPT-4o 基于真实数据回答（而非编造）
- **三级降级**：LLM → 规则匹配 → 默认兜底

### 3. `web/app.py` — Flask 路由
| 路由 | 说明 |
|------|------|
| `/dashboard` `/diagnosis` `/chat` `/explore` | 4 个页面 |
| `/api/dashboard/*` (5个) | 看板图表数据 |
| `/api/diagnosis/run` (POST) | 一键运行诊断（进程级缓存，不重复训练 XGBoost） |
| `/api/chat` (POST) | 对话接口，返回 {reply, source, mode} |
| `/api/chat/suggestions` | 推荐问题（快捷入口） |

### 4. 前端 — 深色科技风 + 玻璃态
- **配色**：渐变深色背景 `#0f172a→#1e293b`，玻璃态卡片 `backdrop-filter: blur`，主色蓝紫绿
- **图表**：ECharts 5.4.3（CDN），复用现有 dashboard.html 的 option 配置
- **对话框**：ChatGPT 风格气泡（用户右对齐/AI 左对齐）+ 打字指示器 + 快捷问题 chips + 来源标识（LLM/规则引擎）
- **动画**：KPI 数字滚动、卡片 hover 发光、消息打字机效果、页面淡入

### 5. Streamlit 融入
- Streamlit 独立进程跑在 8501 端口，Flask `/explore` 页用 iframe 嵌入
- 启动参数：`--server.enableXsrfProtection=false --server.enableCORS=false`（允许 iframe）
- 复用现有 `dashboard/dashboard.py`，无需大改

### 6. 启动脚本 `web/run.py` + `run_web.bat`
- 同时拉起 Streamlit（8501）和 Flask（5000），自动打开浏览器

## requirements.txt 修改
新增：`flask>=3.0.0`（其余不变）

## 实现步骤

1. **骨架与依赖**：改 requirements.txt，建 web/ 目录，最小 Flask 应用验证可跑
2. **数据服务层**：`data_service.py` 5 个聚合函数 + 5 个 API 路由，验证 JSON 输出
3. **看板前端**：base.html + main.css（深色主题）+ dashboard.html/js（KPI + ECharts）
4. **诊断报告**：`/api/diagnosis/run`（缓存）+ diagnosis.html/js（一键运行 + 优先级卡片）
5. **统一对话接口**：`chat_agent.py`（LLM 优先 + 规则降级 + findings 上下文）
6. **对话前端**：chat.html/css/js（ChatGPT 风格 + 打字指示器 + 快捷问题 + 来源标识）
7. **Streamlit 集成**：explore.html（iframe）+ run.py（双进程启动）+ run_web.bat
8. **打磨**：UI 走查、无 API Key 全站可用验证、README 更新

## 验证方式

1. `pip install flask` 后运行 `python web/run.py`，浏览器打开 `http://localhost:5000`
2. **看板页**：4 个 KPI 卡片有数据 + 5 个 ECharts 图表正常渲染
3. **诊断页**：点击"一键运行"→ 显示 loading → 渲染优先级排序的诊断卡片（无 Key 时 LLM 显示 Mock 模式）
4. **对话页**：输入"高价值客户有多少？"→ 返回带数据的回复 + 来源标识；无 Key 时显示"规则引擎"，有 Key 时显示"LLM (GPT-4o)"
5. **探索页**：iframe 内 Streamlit 正常显示，筛选器可用
6. **降级验证**：不设 OPENAI_API_KEY，全站功能正常（诊断 Mock + 对话规则匹配）
