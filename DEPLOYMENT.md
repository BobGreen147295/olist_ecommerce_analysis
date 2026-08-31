# 部署指南

## 选择模型运行模式

项目支持两种模式：

### 本地开发模式

```powershell
$env:LLM_PROVIDER="ollama"
$env:OLLAMA_MODEL="qwen3:8b"
python -m streamlit run dashboard/dashboard.py
```

此模式要求运行机器安装 Ollama 并拥有 `qwen3:8b`。

### 云端部署模式

云端机器通常没有本地 Ollama，因此需要使用 OpenAI 兼容的云端模型服务：

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=你的密钥
OPENAI_MODEL=你的模型名
OPENAI_BASE_URL=可选的兼容接口地址
```

密钥必须配置在部署平台的 Secrets / Environment Variables 中，不要写进代码或提交到 Git。

## Streamlit Community Cloud

1. 将项目推送到 GitHub；
2. 在 Streamlit Community Cloud 创建应用；
3. 入口选择 `dashboard/dashboard.py`；
4. Python 版本选择 3.12；
5. 在 Secrets 中设置 `LLM_PROVIDER`、`OPENAI_API_KEY`、`OPENAI_MODEL`，并建议设置 `APP_PASSWORD`、`MAX_AGENT_CALLS_PER_SESSION` 和 `DATABASE_URL`；
6. 部署后通过生成的 `streamlit.app` 地址访问。

Community Cloud 会根据仓库中的 `requirements.txt` 安装 Python 依赖。应用需要使用的 CSV 也必须在仓库中或从外部数据源加载。

### 线上安全配置

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=你的密钥
OPENAI_MODEL=gpt-4o-mini
MAX_AGENT_CALLS_PER_SESSION=20
APP_ADMIN_USERNAME=olist_admin
APP_ADMIN_PASSWORD=管理员密码
APP_REGISTRATION_CODE=发给受邀用户的邀请码
APP_ADMIN_RESET_PASSWORD=false
```

`MAX_AGENT_CALLS_PER_SESSION` 用于限制单个浏览会话的 Agent 调用次数，避免公开演示时 API 费用失控。API Key、管理员密码和邀请码只能放在 Streamlit Secrets，不能提交到 GitHub。

配置 PostgreSQL 后，应用会创建轻量账号和对话表。管理员账号由 `APP_ADMIN_USERNAME` 与 `APP_ADMIN_PASSWORD` 首次启动时初始化；`APP_REGISTRATION_CODE` 用于控制新账号注册。密码仅保存 PBKDF2 哈希，不保存明文。若需要重置已有管理员密码，将 `APP_ADMIN_RESET_PASSWORD` 临时设为 `true` 并重启一次，成功登录后立即改回 `false`。

Agent 质量指标会保存调用耗时、工具成功数、结构化输出和错误状态；用户反馈只保存评分与最多 500 字的改进原因。负反馈分为回答内容、数据准确性和页面/交互体验：只有回答内容可触发重新生成，数据与体验问题进入管理员反馈待办。质量看板只对管理员账号显示，不展示原始密码或数据库连接串。

配置 `DATABASE_URL` 后，运营任务会保存到 PostgreSQL；未配置时继续保存到本地 JSON。应用首次连接数据库时会自动创建 `operation_tasks` 表，不需要手动执行建表 SQL。推荐使用 Supabase、Neon 等托管 PostgreSQL，并将完整连接串放入 Secrets。

项目同时提供 `scripts/postgres_schema.sql` 作为可审计的初始化脚本。页面侧边栏会显示当前任务存储模式和数据库连接状态，但不会展示连接地址或账号信息。

## Docker 部署

```bash
docker build -t olist-ai-ops .
docker run --rm -p 8501:8501 \
  -e LLM_PROVIDER=openai \
  -e OPENAI_API_KEY=你的密钥 \
  -e OPENAI_MODEL=你的模型名 \
  olist-ai-ops
```

打开 `http://localhost:8501` 即可访问。

## 重要限制

- `operation_tasks.json` 是单机原型存储，云端重启或多实例部署时不保证持久化；
- Agent 运行摘要默认写入 `agent_runs.jsonl`，只保存脱敏统计，不保存原始问题文本；
- 多用户版本应将任务迁移到数据库；
- 不要把真实客户姓名、邮箱、电话等敏感信息提交到 GitHub；
- 不要把 Ollama 端口直接暴露到公网，应通过带认证的后端服务访问；
- 部署前应先确认当前模型服务支持结构化 JSON 输出。
