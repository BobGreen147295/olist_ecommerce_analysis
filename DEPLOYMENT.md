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
5. 在 Secrets 中设置 `LLM_PROVIDER`、`OPENAI_API_KEY` 和 `OPENAI_MODEL`；
6. 部署后通过生成的 `streamlit.app` 地址访问。

Community Cloud 会根据仓库中的 `requirements.txt` 安装 Python 依赖。应用需要使用的 CSV 也必须在仓库中或从外部数据源加载。

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
- 多用户版本应将任务迁移到数据库；
- 不要把真实客户姓名、邮箱、电话等敏感信息提交到 GitHub；
- 不要把 Ollama 端口直接暴露到公网，应通过带认证的后端服务访问；
- 部署前应先确认当前模型服务支持结构化 JSON 输出。
