"""
LangGraph 三节点 Agent 编排（v2.1 支持多轮对话）

节点: fetch_data → analyze → recommend
- fetch_data: LLM 解析用户问题 → 选择工具 → 执行 → 汇总结果
- analyze: LLM 分析数据关键发现
- recommend: LLM 生成可执行运营策略

新增 v2.1:
- 对话历史上下文注入，支持追问和多轮交互
- run_with_history() 接口，ChatSession 封装
"""

import json
import os
import time
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END
from .tools import execute_tool, TOOL_REGISTRY
from .observability import append_run_log, build_run_meta


class AgentState(TypedDict, total=False):
    user_query: str
    tool_results: list[dict]
    analysis: str
    recommendation: str
    diagnosis: dict
    action_drafts: list[dict]
    error: Optional[str]
    conversation_history: list[dict]  # [{"role":"user"|"assistant", "content":"..."}]


# 可用工具元数据（给 LLM 看）
TOOL_SCHEMA = """
可用工具列表（JSON 格式）:
- query_sales_by_region(region: str): 查询某州每百万人销售额和排名，region 为州代码如 "SP"、"BA"
- query_sales_trend(months: int): 查询近N个月销售趋势，默认6个月
- query_payment_distribution(): 查询支付方式分布
- query_user_segments(): 查询用户分群概况
- query_rfm_summary(): 查询 RFM 分层统计
- query_churn_risk(): 查询流失风险分布（优先使用 XGBoost 结果）
- query_top_categories(n: int): 查询热销商品 TOP N（按 product_id），默认10

选择规则:
- 用户问地区销量/某州数据 → query_sales_by_region
- 用户问趋势/变化/最近 → query_sales_trend
- 用户问支付/付款方式 → query_payment_distribution
- 用户问用户/客户分群 → query_user_segments
- 用户问 RFM/客户价值 → query_rfm_summary
- 用户问流失/召回/风险客户 → query_churn_risk + query_rfm_summary
- 用户问产品/品类/热销 → query_top_categories
- 如果不确定，同时调用 query_sales_trend + query_rfm_summary 获取全面数据
"""


def _get_llm():
    """按环境变量选择本地 Ollama 或云端 OpenAI 兼容模型。"""
    provider = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=os.environ.get("OLLAMA_MODEL", "qwen3:8b"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            temperature=0.1,
        )
    if provider in {"openai", "cloud"}:
        from langchain_openai import ChatOpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_PROVIDER=openai 时必须设置 OPENAI_API_KEY")
        kwargs = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "api_key": api_key,
            "temperature": 0.1,
        }
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)
    raise ValueError(f"不支持的 LLM_PROVIDER: {provider}，可选 ollama/openai")


def _format_history(history: list[dict], max_turns: int = 4) -> str:
    """将对话历史转为 prompt 文本，仅保留最近 N 轮"""
    if not history:
        return ""

    # 截取最近 max_turns 轮（每轮 = user + assistant）
    recent = history[-(max_turns * 2):]
    lines = ["\n## 对话历史（上下文）\n"]
    for msg in recent:
        role_label = "👤 用户" if msg["role"] == "user" else "🤖 助手"
        # 截断过长的内容，保留前 300 字
        content = msg.get("content", "")
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines) + "\n"


def _fallback_tool_calls(query: str) -> list[dict]:
    """LLM 路由失败时的保底意图识别，保证常见问题仍可查询数据。"""
    text = query.lower()
    calls: list[dict] = []
    region_aliases = {
        "圣保罗": "SP", "são paulo": "SP", "sao paulo": "SP", "sp州": "SP",
        "里约": "RJ", "rio de janeiro": "RJ", "rj州": "RJ",
        "米纳斯": "MG", "minas gerais": "MG", "mg州": "MG",
        "巴伊亚": "BA", "bahia": "BA", "ba州": "BA",
    }
    region = next((code for alias, code in region_aliases.items() if alias in text), None)
    if region:
        calls = [{"tool": "query_sales_by_region", "args": {"region": region}}]
    elif any(word in text for word in ["流失", "召回", "风险", "挽回"]):
        calls = [
            {"tool": "query_churn_risk", "args": {}},
            {"tool": "query_rfm_summary", "args": {}},
        ]
    elif any(word in text for word in ["支付", "付款", "分期"]):
        calls = [{"tool": "query_payment_distribution", "args": {}}]
    elif any(word in text for word in ["分群", "客群", "用户画像"]):
        calls = [{"tool": "query_user_segments", "args": {}}]
    elif any(word in text for word in ["rfm", "客户价值", "高价值客户", "低价值客户"]):
        calls = [{"tool": "query_rfm_summary", "args": {}}]
    elif any(word in text for word in ["产品", "品类", "热销", "商品"]):
        calls = [{"tool": "query_top_categories", "args": {"n": 10}}]
    elif any(word in text for word in ["趋势", "变化", "最近", "月份", "月度"]):
        calls = [{"tool": "query_sales_trend", "args": {"months": 6}}]
    else:
        calls = [
            {"tool": "query_sales_trend", "args": {"months": 6}},
            {"tool": "query_rfm_summary", "args": {}},
        ]
    return calls


def _parse_json_object(raw: str) -> dict:
    """解析模型返回的 JSON 对象，兼容 markdown 代码块和前后解释文字。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON 对象")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型返回结果必须是 JSON 对象")
    return value


def _fallback_diagnosis(tool_results: list[dict]) -> dict:
    """结构化输出失败时，基于工具摘要生成可追溯的最低限度诊断。"""
    findings = []
    for result in tool_results:
        if result.get("success"):
            findings.append({
                "title": result.get("tool", "数据查询") + " 已完成",
                "evidence": [result.get("summary", "")],
                "source": result.get("tool", "unknown"),
                "confidence": 0.5,
            })
    return {"findings": findings, "data_sufficient": bool(findings)}


def _render_diagnosis(diagnosis: dict) -> str:
    lines = ["## 关键发现"]
    for i, finding in enumerate(diagnosis.get("findings", []), 1):
        title = finding.get("title", "未命名发现")
        lines.append(f"{i}. **{title}**")
        evidence = finding.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [evidence]
        for item in evidence:
            lines.append(f"   - 证据：{item}")
        if finding.get("source"):
            lines.append(f"   - 来源：{finding['source']}")
        if finding.get("confidence") is not None:
            lines.append(f"   - 置信度：{finding['confidence']}")
    return "\n".join(lines)


def _render_actions(action_drafts: list[dict]) -> str:
    lines = ["## 策略建议"]
    for action in action_drafts:
        lines.append(f"### [{action.get('priority', 'P2')}] {action.get('title', '运营策略')}")
        for item in action.get("actions", []):
            lines.append(f"- 行动：{item}")
        for key, label in [("audience", "目标人群"), ("channel", "渠道"),
                           ("budget", "预算"), ("duration_days", "周期"),
                           ("expected_metric", "预期指标"), ("expected_effect", "预期效果")]:
            if action.get(key) is not None:
                lines.append(f"- {label}：{action[key]}")
    return "\n".join(lines)


# ============ 节点 1: fetch_data ============

def fetch_data_node(state: AgentState) -> dict:
    """LLM 解析用户问题（含对话上下文），决定调用哪些工具，执行并汇总"""
    query = state.get("user_query", "")
    history = state.get("conversation_history", [])
    llm = _get_llm()

    # 构建上下文
    history_text = _format_history(history)

    prompt = f"""
你是电商数据分析 Agent 的工具选择器。
根据用户问题（及对话历史），选择最必要的工具（1-3 个），以 JSON 数组格式返回。
如果需要传参数，用 args 字段。

{TOOL_SCHEMA}
{history_text}
用户当前问题: "{query}"

注意:
- 如果用户追问上一轮结论的细节（如"展开第二条"、"SP州具体怎么样"），结合历史选择合适的工具
- 如果用户切换话题，忽略历史，聚焦当前问题

返回格式示例:
[{{"tool": "query_sales_trend", "args": {{"months": 6}}}}, {{"tool": "query_rfm_summary", "args": {{}}}}]

仅返回 JSON，不要其他文字。
"""

    try:
        resp = llm.invoke(prompt)
        raw = resp.content.strip()
        # 清理可能的 markdown 包裹
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        tool_calls = json.loads(raw)
        if not isinstance(tool_calls, list):
            raise ValueError("工具选择结果必须是 JSON 数组")
        tool_calls = tool_calls[:3]
    except Exception as e:
        tool_calls = _fallback_tool_calls(query)
        # 路由失败不等于数据查询失败；只要保底工具能返回数据，后续分析仍应继续。

    # 执行工具
    results = []
    for call in tool_calls:
        if not isinstance(call, dict):
            results.append({"tool": "?", "success": False, "summary": "工具调用格式无效"})
            continue
        tool_name = call.get("tool", "")
        args = call.get("args", {})
        if not isinstance(args, dict):
            results.append({"tool": tool_name, "success": False, "summary": "工具参数必须是 JSON 对象"})
            continue
        if tool_name not in TOOL_REGISTRY:
            results.append({"tool": tool_name, "success": False, "summary": f"未知工具: {tool_name}"})
            continue
        result = execute_tool(tool_name, **args)
        result["tool"] = tool_name
        results.append(result)

    # 检查是否全部失败
    all_failed = all(not r.get("success", False) for r in results)
    if all_failed:
        summaries = [r.get("summary", "") for r in results]
        return {
            "tool_results": results,
            "error": f"所有工具调用失败: {'; '.join(summaries)}",
        }

    return {"tool_results": results, "error": None}


# ============ 节点 2: analyze ============

def analyze_node(state: AgentState) -> dict:
    """LLM 基于数据做分析（含对话历史上下文）"""
    if state.get("error"):
        return {"analysis": "数据查询失败，无法进行分析", "error": state["error"]}

    tool_results = state.get("tool_results", [])
    query = state.get("user_query", "")
    history = state.get("conversation_history", [])
    llm = _get_llm()

    history_text = _format_history(history)

    # 汇总数据：同时传摘要和有限长度的结构化明细，减少模型自行猜数字。
    data_parts = []
    for r in tool_results:
        tool_name = r.get("tool", "?")
        summary = r.get("summary", "")
        detail = json.dumps(r.get("data"), ensure_ascii=False, default=str)[:4000]
        data_parts.append(f"- [{tool_name}] {summary}\n  明细: {detail}")
    data_summary = "\n".join(data_parts)

    prompt = f"""
你是资深电商分析师。基于以下数据（和对话历史上下文），回答用户问题并给出 3-5 条关键发现。

{history_text}
用户当前问题: "{query}"

数据汇总:
{data_summary}

要求:
1. 用中文输出
2. 每条发现引用具体数据
3. 客观描述，不要给出建议（建议由下游节点生成）
4. 如果数据不足，明确指出缺少什么数据
5. 如果是追问，聚焦于用户追问的细节，不必重复之前说过的全部内容

请严格返回 JSON 对象，不要返回 Markdown。格式:
{{
  "data_sufficient": true,
  "findings": [
    {{
      "title": "发现标题",
      "evidence": ["具体指标和数值"],
      "source": "工具名称或文件名",
      "confidence": 0.0
    }}
  ]
}}
"""

    try:
        resp = llm.invoke(prompt)
        analysis = resp.content.strip()
    except Exception as e:
        analysis = f"分析失败: {str(e)}"

    diagnosis = _fallback_diagnosis(tool_results)
    try:
        diagnosis_candidate = _parse_json_object(analysis)
        if isinstance(diagnosis_candidate.get("findings"), list):
            diagnosis = diagnosis_candidate
    except (ValueError, json.JSONDecodeError):
        pass
    return {"analysis": _render_diagnosis(diagnosis), "diagnosis": diagnosis}


# ============ 节点 3: recommend ============

def recommend_node(state: AgentState) -> dict:
    """LLM 生成运营策略（含对话历史上下文）"""
    if state.get("error"):
        return {"recommendation": "因数据查询失败，无法生成策略", "error": state["error"]}

    query = state.get("user_query", "")
    analysis = state.get("analysis", "")
    tool_results = state.get("tool_results", [])
    history = state.get("conversation_history", [])
    llm = _get_llm()

    history_text = _format_history(history)

    # 详细数据
    detailed_data = ""
    for r in tool_results:
        if r.get("success") and r.get("data"):
            detailed_data += f"\n[{r.get('tool')}]: {json.dumps(r['data'], ensure_ascii=False)[:800]}"

    prompt = f"""
你是服务跨境 DTC 商家的 Revenue Operations 顾问。基于分析结果和数据（及对话历史），生成 3-5 条可执行、可复盘的运营策略。

{history_text}
用户当前问题: "{query}"
分析结论:
{analysis}

详细数据:
{detailed_data}

要求:
1. 每条策略包含: 优先级(P0/P1/P2)、策略标题、3个具体行动点
2. 行动点必须具体（渠道、金额、时间），不能空泛；不得建议未经人工批准的自动触达
3. 明确目标市场、内容语言和 1-90 天归因窗口；不知道时必须写“待确认”，不要编造
4. 预估预期效果（数字）必须说明需要通过 A/B 测试验证
5. 如果是追问，聚焦用户追问的方向，给出更具体的建议
6. 如果数据不足，给出数据补充建议；没有营销同意状态时，不得声称可以触达真实客户

请严格返回 JSON 对象，不要返回 Markdown。格式:
{{
  "action_drafts": [
    {{
      "priority": "P0",
      "title": "策略标题",
      "actions": ["具体行动1", "具体行动2", "具体行动3"],
      "audience": "目标人群",
      "channel": "触达渠道",
      "budget": null,
      "duration_days": 7,
      "market": "US 或 待确认",
      "timezone": "America/New_York 或 UTC",
      "locale": "en-US 或 待确认",
      "attribution_window_days": 7,
      "consent_basis": "待商家确认",
      "expected_metric": "预期指标",
      "expected_effect": "基于数据的预期效果",
      "status": "draft"
    }}
  ]
}}
"""

    try:
        resp = llm.invoke(prompt)
        recommendation = resp.content.strip()
    except Exception as e:
        recommendation = f"策略生成失败: {str(e)}"

    action_drafts = []
    try:
        candidate = _parse_json_object(recommendation)
        if isinstance(candidate.get("action_drafts"), list):
            action_drafts = candidate["action_drafts"]
    except (ValueError, json.JSONDecodeError):
        pass
    if not action_drafts:
        action_drafts = [{
            "priority": "P2",
            "title": "基于当前诊断制定小规模验证任务",
            "actions": ["先选择小样本人群", "设置对照组", "记录执行结果"],
            "audience": "待确认",
            "channel": "待确认",
            "budget": None,
            "duration_days": 7,
            "market": "待确认",
            "timezone": "UTC",
            "locale": "待确认",
            "attribution_window_days": 7,
            "consent_basis": "待商家确认",
            "expected_metric": "待确认",
            "expected_effect": "需通过 A/B 测试验证",
            "status": "draft",
        }]
    return {"recommendation": _render_actions(action_drafts), "action_drafts": action_drafts}


# ============ 图构建 ============

def should_continue(state: AgentState) -> str:
    """路由: fetch_data 后如果出错且无结果则跳到 END，否则继续"""
    if state.get("error") and not state.get("tool_results"):
        return END
    return "analyze"


def build_graph() -> StateGraph:
    """构建并编译 Agent 图"""
    graph = StateGraph(AgentState)

    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("recommend", recommend_node)

    graph.set_entry_point("fetch_data")
    graph.add_conditional_edges("fetch_data", should_continue)
    graph.add_edge("analyze", "recommend")
    graph.add_edge("recommend", END)

    return graph.compile()


# 全局 Agent 实例
agent = build_graph()


# ============ 公开接口 ============

def run(user_query: str) -> dict:
    """运行 Agent（单轮），向后兼容 CLI 调用"""
    return run_with_history(user_query, [])


def run_with_history(user_query: str, history: list[dict] = None) -> dict:
    """运行 Agent（多轮），携带对话历史上下文"""
    started_at = time.perf_counter()
    state: AgentState = {
        "user_query": user_query,
        "conversation_history": history or [],
    }
    result = agent.invoke(state)
    response = {
        "user_query": result.get("user_query", ""),
        "tool_results": result.get("tool_results", []),
        "analysis": result.get("analysis", ""),
        "recommendation": result.get("recommendation", ""),
        "diagnosis": result.get("diagnosis", {}),
        "action_drafts": result.get("action_drafts", []),
        "error": result.get("error"),
    }
    run_meta = build_run_meta(user_query, response, int((time.perf_counter() - started_at) * 1000))
    append_run_log(run_meta)
    response["run_meta"] = run_meta
    return response


# ============ 多轮对话会话管理 ============

class ChatSession:
    """多轮对话会话，自动管理历史记录"""

    def __init__(self):
        self.history: list[dict] = []

    def chat(self, user_query: str) -> dict:
        """发送一条消息，返回 Agent 结果并自动更新历史"""
        result = run_with_history(user_query, self.history)

        # 构建助手的完整回复（拼接分析 + 策略）
        assistant_reply_parts = []
        analysis = result.get("analysis", "")
        recommendation = result.get("recommendation", "")
        if analysis:
            assistant_reply_parts.append(analysis)
        if recommendation:
            assistant_reply_parts.append(recommendation)
        assistant_reply = "\n\n".join(assistant_reply_parts)

        # 更新历史
        self.history.append({"role": "user", "content": user_query})
        self.history.append({"role": "assistant", "content": assistant_reply})

        return result

    def clear(self):
        """清空对话历史"""
        self.history = []
