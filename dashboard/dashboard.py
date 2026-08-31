"""
Olist 电商 AI 运营分析系统 — Streamlit 仪表盘 v2.1

Tab 1: 📊 数据看板 — KPI 指标 + 交互图表
Tab 2: 💬 AI 运营顾问 — 多轮对话 Agent，自然语言诊断
"""

import sys
import os

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from src.agent.evaluation import evaluate_experiment
from src.agent.account_store import (
    append_message,
    authenticate_user,
    create_conversation,
    create_user,
    ensure_admin_account,
    list_conversations,
    load_messages,
)
from src.agent.feedback_store import (
    get_quality_summary,
    load_feedback,
    record_run_metric,
    save_feedback,
)
from src.agent.task_store import (
    check_database_connection,
    complete_task,
    create_task,
    load_tasks,
    storage_mode,
    update_task,
)


# ── 访问控制与成本保护 ─────────────────────────────
def _get_setting(name: str, default: str = "") -> str:
    """优先读取 Streamlit Secrets，再读取环境变量，便于本地和云端共用代码。"""
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return str(value or os.environ.get(name, default)).strip()


def _safe_markdown(text: object) -> str:
    """避免金额中的 $ 被 Markdown 误识别为 LaTex 数学公式分隔符。"""
    return str(text).replace("$", "\\$")


def _require_login() -> None:
    """使用数据库账号登录；未配置数据库时回退为本地开发免登录。"""
    if not _get_setting("DATABASE_URL"):
        st.session_state.current_user = {"username": "local", "role": "admin"}
        return
    admin_username = _get_setting("APP_ADMIN_USERNAME", "olist_admin")
    admin_password = _get_setting("APP_ADMIN_PASSWORD")
    if not admin_password:
        st.error("缺少 APP_ADMIN_PASSWORD，请在 Streamlit Secrets 中配置管理员密码。")
        st.stop()
    try:
        reset_admin_password = _get_setting("APP_ADMIN_RESET_PASSWORD", "false").lower() == "true"
        ensure_admin_account(admin_username, admin_password, reset_password=reset_admin_password)
    except Exception as exc:
        st.error(f"账号服务暂不可用：{type(exc).__name__}")
        st.stop()

    if st.session_state.get("current_user"):
        return

    st.title("🛒 Olist AI 运营分析系统")
    st.caption("登录后可恢复自己的历史分析和运营任务。")
    login_tab, register_tab = st.tabs(["登录", "创建账号"])
    with login_tab:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
        if submitted:
            user = authenticate_user(username.strip(), password)
            if user:
                st.session_state.current_user = user
                st.session_state.agent_calls = 0
                st.rerun()
            st.error("用户名或密码不正确")
    with register_tab:
        registration_code = _get_setting("APP_REGISTRATION_CODE")
        if not registration_code:
            st.info("管理员暂未开放注册邀请码，请联系管理员获取账号。")
        else:
            with st.form("register_form"):
                username = st.text_input("用户名（3-32 位英文、数字、_ 或 -）", key="register_username")
                password = st.text_input("密码（至少 8 位）", type="password", key="register_password")
                invite_code = st.text_input("邀请码", type="password")
                submitted = st.form_submit_button("创建账号", use_container_width=True)
            if submitted:
                try:
                    user = create_user(username.strip(), password, invite_code, registration_code)
                    st.session_state.current_user = user
                    st.session_state.agent_calls = 0
                    st.success("账号创建成功，正在进入系统。")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    st.stop()


def _check_usage_limit() -> bool:
    """限制单个浏览会话的 Agent 调用次数，避免公开演示时无限消耗 API。"""
    try:
        limit = int(_get_setting("MAX_AGENT_CALLS_PER_SESSION", "20"))
    except ValueError:
        limit = 20
    used = int(st.session_state.get("agent_calls", 0))
    if used >= max(1, limit):
        st.warning(f"本次会话已达到 Agent 调用上限（{limit} 次），请联系管理员重置。")
        return False
    st.session_state.agent_calls = used + 1
    return True


def _restore_conversation(conversation_id: str | None, username: str) -> None:
    """从数据库恢复某个会话，同时让 Agent 获得同一份多轮上下文。"""
    messages = load_messages(conversation_id, username) if conversation_id else []
    history = [
        {"message_id": item.get("message_id"), "role": item["role"], "content": item["content"]}
        for item in messages
    ]
    st.session_state.active_conversation_id = conversation_id
    st.session_state.chat_history = history
    if st.session_state.get("agent_session"):
        st.session_state.agent_session.history = [
            {"role": item["role"], "content": item["content"]} for item in history
        ]


def _ensure_active_conversation(username: str, first_message: str) -> str | None:
    """仅在首次提问时创建会话，避免产生空白对话记录。"""
    if not _get_setting("DATABASE_URL"):
        return None
    conversation_id = st.session_state.get("active_conversation_id")
    if conversation_id:
        return conversation_id
    conversation = create_conversation(username, first_message.replace("\n", " ")[:60])
    st.session_state.active_conversation_id = conversation["conversation_id"]
    return conversation["conversation_id"]


def _show_evidence_cards(diagnosis: dict) -> None:
    """把 Agent 的结构化诊断渲染为可核验的证据卡片。"""
    findings = diagnosis.get("findings", []) if isinstance(diagnosis, dict) else []
    if not findings:
        return
    st.subheader("📌 证据与可信度")
    st.caption("以下内容来自 Agent 工具查询和结构化诊断，建议结合原始数据快照复核。")
    for index, finding in enumerate(findings, 1):
        title = finding.get("title", f"诊断结论 {index}")
        priority = finding.get("priority", "P2")
        confidence = finding.get("confidence")
        if isinstance(confidence, (int, float)):
            confidence_text = f"{confidence:.0%}"
        else:
            confidence_text = str(confidence or "未提供")
        with st.expander(f"[{priority}] {title}", expanded=index == 1):
            left, right = st.columns([3, 1])
            with left:
                evidence = finding.get("evidence", [])
                if not isinstance(evidence, list):
                    evidence = [evidence]
                for item in evidence:
                    st.markdown(_safe_markdown(f"- {item}"))
            with right:
                st.metric("置信度", confidence_text)
                st.caption(f"来源：{finding.get('source', '未标注')}")
            snapshot = finding.get("metric_snapshot")
            if isinstance(snapshot, dict) and snapshot:
                st.json(snapshot, expanded=False)


def _experiment_verdict(result: dict) -> tuple[str, str]:
    """将确定性实验指标翻译为便于运营人员理解的结论标签。"""
    roi = result.get("roi")
    uplift = float(result.get("conversion_uplift_pp", 0) or 0)
    if roi is None:
        return "成本未录入", "请补充活动成本后再判断投入回报。"
    if roi > 0 and uplift > 0:
        return "建议扩大验证", "转化与投入回报均为正，建议扩大样本并继续观察。"
    if uplift > 0:
        return "转化有效，成本待优化", "活动带来转化提升，但当前成本仍需要优化。"
    return "建议复盘优化", "当前实验未证明策略带来正向转化增量，建议调整人群或渠道。"


def _show_message_feedback(
    message: dict,
    feedback_by_message: dict,
    conversation_id: str | None,
    username: str,
) -> None:
    """在每条持久化的 Agent 回复后提供一次可追踪反馈。"""
    message_id = message.get("message_id")
    if not message_id or not conversation_id:
        return
    existing = feedback_by_message.get(message_id)
    if existing:
        label = "👍 已标记为有帮助" if existing["rating"] == 1 else "👎 已标记为需要改进"
        st.caption(label)
        if existing["rating"] == -1:
            if st.button("🔄 基于反馈重新生成", key=f"regenerate_{message_id}", use_container_width=True):
                original_question = ""
                history = st.session_state.get("chat_history", [])
                for index, item in enumerate(history):
                    if item.get("message_id") != message_id:
                        continue
                    for previous in reversed(history[:index]):
                        if previous.get("role") == "user":
                            original_question = previous.get("content", "")
                            break
                    break
                st.session_state.pending_regeneration = {
                    "question": original_question or st.session_state.get("last_question", ""),
                    "reason": existing.get("reason") or "请补充更明确的数据证据和可执行行动方案。",
                }
                st.rerun()
        return
    up_col, down_col = st.columns(2)
    if up_col.button("👍 有帮助", key=f"feedback_up_{message_id}", use_container_width=True):
        save_feedback(message_id, conversation_id, username, 1)
        st.rerun()
    if down_col.button("👎 需要改进", key=f"feedback_down_{message_id}", use_container_width=True):
        st.session_state.feedback_target = message_id
        st.rerun()
    if st.session_state.get("feedback_target") == message_id:
        with st.form(f"feedback_form_{message_id}"):
            reason = st.text_area("哪里需要改进？（可选）", max_chars=500)
            submitted = st.form_submit_button("提交反馈", use_container_width=True)
        if submitted:
            save_feedback(message_id, conversation_id, username, -1, reason)
            st.session_state.pop("feedback_target", None)
            st.rerun()

# ── 中文字体设置 ──────────────────────────────────
plt.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


# ═══════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════

def add_value_labels(ax, fmt="{:,.0f}"):
    """为柱状图的每个柱子添加数据标签"""
    for rect in ax.patches:
        height = rect.get_height()
        if height > 0:
            ax.text(
                rect.get_x() + rect.get_width() / 2.0,
                height + 0.02 * height,
                fmt.format(height),
                ha="center", va="bottom", fontsize=8,
            )


@st.cache_data
def load_data():
    """加载所有数据文件（缓存避免重复读取）"""
    data = {}
    file_map = {
        "customers": "cleaned_customers.csv",
        "orders": "cleaned_orders.csv",
        "payments": "cleaned_payments.csv",
        "order_items": "cleaned_order_items.csv",
        "user_clusters": "user_clusters.csv",
        "rfm_analysis": "rfm_analysis.csv",
        "sales_trends": "sales_trends.csv",
        "population_data": "brazil_population.csv",
        "region_analysis": "region_analysis.csv",
    }
    for key, filename in file_map.items():
        filepath = os.path.join(_project_root, "data", "processed", filename)
        try:
            data[key] = pd.read_csv(filepath)
        except FileNotFoundError:
            data[key] = pd.DataFrame()
    return data


# ═══════════════════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════════════════

st.set_page_config(
    page_title="Olist AI 运营分析系统",
    page_icon="🛒",
    layout="wide",
)

_require_login()

# ── 页面标题 ──────────────────────────────────────
st.title("🛒 Olist 电商 AI 运营分析系统")
st.caption("巴西电商数据集 · LangGraph Agent · Ollama Qwen3 · XGBoost")

# 加载数据
data = load_data()
customers = data["customers"]
orders = data["orders"]
payments = data["payments"]
order_items = data["order_items"]
user_clusters = data["user_clusters"]
rfm_analysis = data["rfm_analysis"]
sales_trends = data["sales_trends"]
population_data = data["population_data"]
region_analysis = data["region_analysis"]

# ═══════════════════════════════════════════════════════
# Tab 布局
# ═══════════════════════════════════════════════════════

tab_dashboard, tab_chat = st.tabs(["📊 数据看板", "💬 AI 运营顾问"])


# ╔═════════════════════════════════════════════════════╗
# ║              TAB 1: 数据看板                        ║
# ╚═════════════════════════════════════════════════════╝

with tab_dashboard:

    # ── KPI 指标卡 ──────────────────────────────
    if not orders.empty and not order_items.empty and not customers.empty:
        col1, col2, col3, col4 = st.columns(4)
        total_orders = len(orders)
        # 统一与事实表/Agent 的销售额口径：使用支付金额，而不是商品行金额。
        total_sales = payments["payment_value"].sum() if "payment_value" in payments.columns else 0
        unique_customers = len(customers)
        avg_order_value = total_sales / total_orders if total_orders > 0 else 0

        col1.metric("📦 总订单数", f"{total_orders:,}")
        col2.metric("💰 总销售额", f"R$ {total_sales:,.0f}")
        col3.metric("👥 总用户数", f"{unique_customers:,}")
        col4.metric("🧾 平均客单价", f"R$ {avg_order_value:,.2f}")
    else:
        st.warning("⚠️ 数据文件未找到，请先运行数据清洗管道: `python src/data_cleaning.py`")

    st.divider()

    # ── 图表区：左右两栏 ─────────────────────────
    chart_col_left, chart_col_right = st.columns(2)

    # ---- 左栏 ----
    with chart_col_left:
        # 订单时间趋势
        st.subheader("📈 订单月度趋势")
        if not orders.empty:
            orders_plot = orders.copy()
            orders_plot["order_purchase_timestamp"] = pd.to_datetime(
                orders_plot["order_purchase_timestamp"]
            )
            orders_plot["month"] = orders_plot["order_purchase_timestamp"].dt.to_period("M")
            monthly_orders = (
                orders_plot.groupby("month").size().reset_index(name="订单数")
            )
            monthly_orders["month"] = monthly_orders["month"].astype(str)

            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(
                monthly_orders["month"], monthly_orders["订单数"],
                linewidth=2, marker="o", color="#1f77b4",
            )
            ax.ticklabel_format(style="plain", axis="y")
            plt.xticks(rotation=45, fontsize=8)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("暂无订单数据")

        # 支付方式分布
        st.subheader("💳 支付方式分布")
        if not payments.empty:
            payment_counts = payments["payment_type"].value_counts().reset_index()
            payment_counts.columns = ["支付方式", "次数"]

            fig, ax = plt.subplots(figsize=(8, 4))
            sns.barplot(x="支付方式", y="次数", data=payment_counts, ax=ax)
            plt.xticks(rotation=45, fontsize=8)
            plt.title("支付方式分布")
            add_value_labels(ax)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("暂无支付数据")

        # 用户聚类
        st.subheader("🧩 用户分群")
        if not user_clusters.empty and "cluster_label" in user_clusters.columns:
            cluster_counts = (
                user_clusters["cluster_label"].value_counts().reset_index()
            )
            cluster_counts.columns = ["分群", "用户数"]

            fig, ax = plt.subplots(figsize=(8, 4))
            bars = sns.barplot(x="分群", y="用户数", data=cluster_counts, ax=ax)
            plt.title("用户分群分布")
            add_value_labels(ax)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("暂无分群数据")

    # ---- 右栏 ----
    with chart_col_right:
        # 地区销量 TOP10
        st.subheader("🗺️ 地区销量 TOP10")
        if not payments.empty and not orders.empty and not customers.empty:
            region_sales = (
                payments.groupby("order_id", as_index=False)["payment_value"].sum()
                .merge(orders, on="order_id")
                .merge(customers, on="customer_id")
                .groupby("customer_state")["payment_value"]
                .sum()
                .reset_index()
                .sort_values("payment_value", ascending=False)
                .head(10)
            )
            region_sales = region_sales.rename(columns={"customer_state": "地区", "payment_value": "销售额"})

            fig, ax = plt.subplots(figsize=(8, 4))
            sns.barplot(x="地区", y="销售额", data=region_sales, ax=ax)
            plt.xticks(rotation=45, fontsize=8)
            plt.title("地区销量 TOP10")
            ax.ticklabel_format(style="plain", axis="y")
            for i, v in enumerate(region_sales["销售额"]):
                ax.text(i, v + 0.01 * max(region_sales["销售额"]),
                        f"{v:,.0f}", ha="center", va="bottom", fontsize=7)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("暂无地区数据")

        # RFM 客户价值
        st.subheader("💎 RFM 客户价值分层")
        if not rfm_analysis.empty and "customer_segment" in rfm_analysis.columns:
            rfm_counts = (
                rfm_analysis["customer_segment"].value_counts().reset_index()
            )
            rfm_counts.columns = ["客户群体", "数量"]

            fig, ax = plt.subplots(figsize=(8, 4))
            sns.barplot(x="客户群体", y="数量", data=rfm_counts, ax=ax)
            plt.xticks(rotation=45, fontsize=8)
            plt.title("RFM 客户价值分布")
            add_value_labels(ax)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("暂无 RFM 数据")

        # 人均销售额（如有爬虫数据）
        st.subheader("🏙️ 各州人均销售额")
        if not region_analysis.empty and "state" in region_analysis.columns:
            sorted_ra = region_analysis.sort_values("sales_per_capita", ascending=False)
            fig, ax = plt.subplots(figsize=(8, 4))
            sns.barplot(x="state", y="sales_per_capita", data=sorted_ra, ax=ax)
            plt.xticks(rotation=45, fontsize=7)
            plt.title("各州人均销售额")
            ax.ticklabel_format(style="plain", axis="y")
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("暂无人口/人均数据（需运行爬虫）")

    # ── 底部数据表 ──────────────────────────────
    st.divider()
    st.subheader("📋 数据快照")
    with st.expander("点击展开数据预览"):
        tab_rfm, tab_cluster, tab_trend = st.tabs(["RFM", "用户分群", "销售趋势"])
        with tab_rfm:
            if not rfm_analysis.empty:
                st.dataframe(rfm_analysis.head(20), use_container_width=True)
        with tab_cluster:
            if not user_clusters.empty:
                st.dataframe(user_clusters.head(20), use_container_width=True)
        with tab_trend:
            if not sales_trends.empty:
                st.dataframe(sales_trends.head(20), use_container_width=True)


# ╔═════════════════════════════════════════════════════╗
# ║              TAB 2: AI 运营顾问                    ║
# ╚═════════════════════════════════════════════════════╝

with tab_chat:

    # ── 初始化会话状态 ───────────────────────────
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []   # 显示用的消息列表
    if "agent_session" not in st.session_state:
        # 延迟导入 Agent
        try:
            from src.agent.agent_graph import ChatSession
            st.session_state.agent_session = ChatSession()
            st.session_state.agent_available = True
        except Exception as e:
            st.session_state.agent_session = None
            st.session_state.agent_available = False
            st.session_state.agent_error = str(e)

    current_user = st.session_state.get("current_user", {"username": "local", "role": "admin"})
    current_username = current_user["username"]
    task_owner = None if current_user.get("role") == "admin" else current_username
    if _get_setting("DATABASE_URL"):
        conversations = list_conversations(current_username)
        if "active_conversation_id" not in st.session_state:
            latest_id = conversations[0]["conversation_id"] if conversations else None
            _restore_conversation(latest_id, current_username)

        with st.sidebar:
            st.divider()
            st.subheader("🗂️ 历史对话")
            if st.button("＋ 新建对话", use_container_width=True):
                _restore_conversation(None, current_username)
                st.rerun()
            conversation_map = {item["conversation_id"]: item["title"] for item in conversations}
            conversation_ids = [None, *conversation_map.keys()]
            active_id = st.session_state.get("active_conversation_id")
            selected_id = st.selectbox(
                "切换对话",
                options=conversation_ids,
                index=conversation_ids.index(active_id) if active_id in conversation_ids else 0,
                format_func=lambda value: "新对话（尚未保存）" if value is None else conversation_map[value],
            )
            if selected_id != active_id:
                _restore_conversation(selected_id, current_username)
                st.rerun()

    active_conversation_id = st.session_state.get("active_conversation_id")
    feedback_by_message = (
        load_feedback(active_conversation_id, current_username)
        if active_conversation_id and _get_setting("DATABASE_URL") else {}
    )

    # ── 快捷问题 ────────────────────────────────
    st.subheader("💬 AI 运营顾问")
    st.caption("用自然语言提问，Agent 自动查询数据、分析、生成策略。支持多轮追问。")

    quick_questions = [
        "分析最近半年的销售趋势",
        "圣保罗州最近销量怎么样",
        "客户流失情况如何，怎么挽回",
        "支付方式分布有没有问题",
        "哪些产品卖得好",
        "客户分群情况怎么样",
    ]

    # 快捷问题按钮行
    cols = st.columns(len(quick_questions))
    clicked_question = None
    for i, (col, q) in enumerate(zip(cols, quick_questions)):
        if col.button(q, key=f"quick_{i}", use_container_width=True):
            clicked_question = q

    st.divider()

    # ── 渲染聊天历史 ────────────────────────────
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(_safe_markdown(msg["content"]))
                if msg["role"] == "assistant":
                    _show_message_feedback(
                        msg, feedback_by_message, active_conversation_id, current_username
                    )

    # ── 处理快捷问题点击 ────────────────────────
    if clicked_question:
        st.session_state.pending_question = clicked_question

    # ── 聊天输入框 ──────────────────────────────
    user_input = st.chat_input(
        "输入你的运营问题，例如：\"分析最近半年的销售趋势\"",
        key="chat_input_main",
    )

    # 合并输入源；用户授权后，负反馈要求会注入下一轮 Agent 提示。
    regeneration = st.session_state.pop("pending_regeneration", None)
    actual_input = user_input or st.session_state.pop("pending_question", None)
    display_input = actual_input
    if regeneration:
        original_question = regeneration.get("question", "")
        feedback_reason = regeneration.get("reason", "")
        actual_input = (
            "请基于用户的负反馈重新回答这项运营问题。\n"
            f"原始问题：{original_question}\n"
            f"改进要求：{feedback_reason}\n"
            "要求：必须引用可核验的数据证据，明确说明结论、行动方案和验证指标。"
        )
        display_input = f"🔄 基于反馈重新生成：{original_question}"

    if actual_input:
        if st.session_state.agent_available and not _check_usage_limit():
            st.rerun()

        active_conversation_id = _ensure_active_conversation(current_username, display_input or actual_input)
        user_message_id = None
        if active_conversation_id:
            user_message_id = append_message(active_conversation_id, current_username, "user", display_input or actual_input)

        # 显示用户消息
        st.session_state.chat_history.append({
            "message_id": user_message_id, "role": "user", "content": display_input or actual_input
        })

        if not st.session_state.agent_available:
            # Agent 不可用
            error_msg = st.session_state.get("agent_error", "未知错误")
            fallback = (
                f"⚠️ **AI Agent 当前不可用**\n\n"
                f"错误: `{error_msg}`\n\n"
                f"请确认:\n"
                f"1. Ollama 已安装并正在运行\n"
                f"2. 模型已拉取: `ollama pull qwen3:8b`\n"
                f"3. Python 依赖已安装: `pip install -r requirements.txt`"
            )
            fallback_message_id = None
            if active_conversation_id:
                fallback_message_id = append_message(
                    active_conversation_id, current_username, "assistant", fallback
                )
            st.session_state.chat_history.append({
                "message_id": fallback_message_id, "role": "assistant", "content": fallback
            })
            st.rerun()

        # ── 调用 Agent ────────────────────────
        with st.spinner("🤖 Agent 思考中..."):
            try:
                result = st.session_state.agent_session.chat(actual_input)
            except Exception as e:
                result = {"error": str(e), "tool_results": [], "analysis": "", "recommendation": ""}

        # ── 构建回复消息 ──────────────────────
        st.session_state.last_action_drafts = result.get("action_drafts", [])
        st.session_state.last_diagnosis = result.get("diagnosis", {})
        st.session_state.last_run_meta = result.get("run_meta", {})
        st.session_state.last_question = display_input or actual_input
        if active_conversation_id:
            record_run_metric(current_username, active_conversation_id, result.get("run_meta", {}))
        if result.get("error") and not result.get("tool_results"):
            reply = f"❌ **执行出错**: {result['error']}"
        else:
            parts = []

            # 数据查询摘要
            tool_results = result.get("tool_results", [])
            if tool_results:
                parts.append("### 🔍 数据查询\n")
                for i, tr in enumerate(tool_results, 1):
                    status_icon = "✅" if tr.get("success") else "❌"
                    parts.append(f"{status_icon} **{tr.get('tool', '?')}**: {tr.get('summary', '')}")
                parts.append("")

            # 分析结果
            analysis = result.get("analysis", "")
            if analysis:
                parts.append(analysis)
                parts.append("")

            # 策略建议
            recommendation = result.get("recommendation", "")
            if recommendation:
                parts.append(recommendation)

            action_drafts = result.get("action_drafts", [])
            if action_drafts:
                parts.append("\n### 📝 可确认的运营任务草稿\n")
                for action in action_drafts:
                    priority = action.get("priority", "P2")
                    title = action.get("title", "运营策略")
                    parts.append(f"- **[{priority}] {title}**")
                    if action.get("audience"):
                        parts.append(f"  - 目标人群：{action['audience']}")
                    if action.get("channel"):
                        parts.append(f"  - 渠道：{action['channel']}")
                    if action.get("budget") is not None:
                        parts.append(f"  - 预算：{action['budget']}")
                    if action.get("duration_days") is not None:
                        parts.append(f"  - 周期：{action['duration_days']} 天")
                    parts.append("  - 状态：待用户确认")

            reply = "\n".join(parts)

        if not reply.strip():
            reply = "⚠️ Agent 未返回有效结果，请重试。"

        # 添加助手消息到历史
        assistant_message_id = None
        if active_conversation_id:
            assistant_message_id = append_message(
                active_conversation_id, current_username, "assistant", reply
            )
        st.session_state.chat_history.append({
            "message_id": assistant_message_id, "role": "assistant", "content": reply
        })

        # 限制历史长度（每轮 = user + assistant，保留最近 20 轮）
        max_messages = 40
        if len(st.session_state.chat_history) > max_messages:
            st.session_state.chat_history = st.session_state.chat_history[-max_messages:]

        st.rerun()

    # ── 结构化证据展示 ─────────────────────────────
    _show_evidence_cards(st.session_state.get("last_diagnosis", {}))

    # ── 运营任务：编辑、保存、确认/驳回 ─────────────────
    with st.expander("📝 运营任务中心", expanded=bool(st.session_state.get("last_action_drafts"))):
        drafts = st.session_state.get("last_action_drafts", [])
        if drafts:
            st.caption("以下任务来自最近一次 Agent 诊断，保存后仍需人工确认，不会自动触达客户。")
            for idx, draft in enumerate(drafts):
                key_prefix = f"draft_{idx}"
                title = st.text_input("任务标题", value=str(draft.get("title", "运营策略")), key=f"{key_prefix}_title")
                audience = st.text_input("目标人群", value=str(draft.get("audience", "待确认")), key=f"{key_prefix}_audience")
                channel = st.text_input("触达渠道", value=str(draft.get("channel", "待确认")), key=f"{key_prefix}_channel")
                budget_default = float(draft.get("budget") or 0)
                budget = st.number_input("预算", min_value=0.0, value=budget_default, step=100.0, key=f"{key_prefix}_budget")
                duration = st.number_input("执行周期（天）", min_value=1, max_value=90, value=int(draft.get("duration_days") or 7), key=f"{key_prefix}_duration")
                if st.button("保存为草稿", key=f"{key_prefix}_save", use_container_width=True):
                    task = create_task(
                        {**draft, "title": title, "audience": audience, "channel": channel,
                         "budget": budget, "duration_days": duration},
                        question=st.session_state.get("last_question", ""),
                        source_diagnosis=st.session_state.get("last_diagnosis", {}),
                        owner=current_username,
                    )
                    st.success(f"任务 {task['task_id']} 已保存为草稿")
                    st.rerun()
        else:
            st.info("完成一次 Agent 诊断后，这里会出现可编辑的运营任务草稿。")

        tasks = load_tasks(owner=task_owner)
        if tasks:
            st.divider()
            st.caption(f"已保存任务：{len(tasks)} 条")
            completed_results = [
                task.get("result", {}) for task in tasks
                if task.get("status") == "completed" and isinstance(task.get("result"), dict)
            ]
            if completed_results:
                total_incremental_revenue = sum(
                    float(result.get("incremental_revenue", 0) or 0) for result in completed_results
                )
                total_cost = sum(float(result.get("cost", 0) or 0) for result in completed_results)
                portfolio_roi = ((total_incremental_revenue - total_cost) / total_cost) if total_cost else None
                st.markdown("##### 📈 运营实验累计效果")
                metric_a, metric_b, metric_c, metric_d = st.columns(4)
                metric_a.metric("已完成实验", f"{len(completed_results)} 个")
                metric_b.metric("累计增量收入", f"R$ {total_incremental_revenue:,.0f}")
                metric_c.metric("累计活动成本", f"R$ {total_cost:,.0f}")
                metric_d.metric("组合 ROI", f"{portfolio_roi:.0%}" if portfolio_roi is not None else "待录入成本")
            for task in tasks[:10]:
                task_id = task.get("task_id", "?")
                status = task.get("status", "draft")
                st.markdown(f"**[{status}] {task.get('title', '未命名任务')}** · `{task_id}`")
                st.caption(f"人群：{task.get('audience', '未设置')} · 渠道：{task.get('channel', '未设置')} · 预算：{task.get('budget', 0)}")
                col_confirm, col_reject = st.columns(2)
                with col_confirm:
                    if status == "draft" and st.button("确认任务", key=f"confirm_{task_id}", use_container_width=True):
                        update_task(task_id, {"status": "confirmed"}, owner=task_owner)
                        st.rerun()
                with col_reject:
                    if status == "draft" and st.button("驳回任务", key=f"reject_{task_id}", use_container_width=True):
                        update_task(task_id, {"status": "rejected"}, owner=task_owner)
                        st.rerun()
                if status == "confirmed":
                    with st.form(f"result_form_{task_id}"):
                        st.caption("回填实验结果（实验组 / 对照组）")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            treatment_users = st.number_input("实验组人数", min_value=1, value=100, key=f"tu_{task_id}")
                            treatment_orders = st.number_input("实验组订单", min_value=0, value=10, key=f"to_{task_id}")
                            treatment_revenue = st.number_input("实验组收入", min_value=0.0, value=1000.0, step=100.0, key=f"tr_{task_id}")
                        with c2:
                            control_users = st.number_input("对照组人数", min_value=1, value=100, key=f"cu_{task_id}")
                            control_orders = st.number_input("对照组订单", min_value=0, value=8, key=f"co_{task_id}")
                            control_revenue = st.number_input("对照组收入", min_value=0.0, value=800.0, step=100.0, key=f"cr_{task_id}")
                        with c3:
                            cost = st.number_input("活动成本", min_value=0.0, value=float(task.get("budget") or 0), step=100.0, key=f"cost_{task_id}")
                        submitted = st.form_submit_button("提交结果并完成任务", use_container_width=True)
                    if submitted:
                        try:
                            result = evaluate_experiment(
                                treatment_users, treatment_orders, treatment_revenue,
                                control_users, control_orders, control_revenue, cost,
                            )
                            complete_task(task_id, result, owner=task_owner)
                            st.success(f"任务 {task_id} 已完成，效果结果已保存")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                if status == "completed" and task.get("result"):
                    result = task["result"]
                    roi = result.get("roi")
                    roi_text = f"{roi:.1%}" if roi is not None else "未计算（成本为 0）"
                    verdict_title, verdict_detail = _experiment_verdict(result)
                    with st.container(border=True):
                        st.markdown("##### 📊 实验复盘结果")
                        metric_a, metric_b, metric_c, metric_d = st.columns(4)
                        metric_a.metric("实验组转化率", f"{result.get('treatment_conversion', 0):.2%}")
                        metric_b.metric("转化提升", f"{result.get('conversion_uplift_pp', 0):.2f} 个百分点")
                        metric_c.metric("增量收入", f"R$ {float(result.get('incremental_revenue', 0) or 0):,.0f}")
                        metric_d.metric("ROI", roi_text)
                        st.caption(
                            f"对照组转化率：{result.get('control_conversion', 0):.2%} · "
                            f"增量订单：{float(result.get('incremental_orders', 0) or 0):,.1f} · "
                            f"活动成本：R$ {float(result.get('cost', 0) or 0):,.0f}"
                        )
                        st.info(f"**{verdict_title}**：{verdict_detail}")

    # ── 管理员质量看板 ─────────────────────────────
    if current_user.get("role") == "admin" and _get_setting("DATABASE_URL"):
        with st.expander("📈 Agent 质量看板", expanded=False):
            quality = get_quality_summary()
            all_tasks = load_tasks()
            completed_results = [
                task.get("result", {}) for task in all_tasks
                if task.get("status") == "completed" and isinstance(task.get("result"), dict)
            ]
            adopted_count = sum(task.get("status") in {"confirmed", "completed"} for task in all_tasks)
            total_incremental_revenue = sum(
                float(result.get("incremental_revenue", 0) or 0) for result in completed_results
            )
            total_cost = sum(float(result.get("cost", 0) or 0) for result in completed_results)
            portfolio_roi = ((total_incremental_revenue - total_cost) / total_cost) if total_cost else None
            metric_a, metric_b, metric_c, metric_d = st.columns(4)
            metric_a.metric("Agent 调用", f"{quality['total_runs']} 次")
            metric_b.metric("平均响应", f"{quality['avg_duration_ms']:.0f} ms")
            metric_c.metric(
                "工具成功率",
                f"{quality['tool_success_rate']:.0%}" if quality["tool_success_rate"] is not None else "暂无数据",
            )
            metric_d.metric("结构化输出率", f"{quality['structured_output_rate']:.0%}")
            metric_e, metric_f, metric_g, metric_h = st.columns(4)
            metric_e.metric(
                "用户满意度",
                f"{quality['helpful_rate']:.0%}" if quality["helpful_rate"] is not None else "暂无反馈",
            )
            metric_f.metric("反馈数量", f"{quality['feedback_count']} 条")
            metric_g.metric("任务采纳率", f"{adopted_count / len(all_tasks):.0%}" if all_tasks else "暂无任务")
            metric_h.metric("已完成任务 ROI", f"{portfolio_roi:.0%}" if portfolio_roi is not None else "暂无结果")
            st.caption(
                f"错误率：{quality['error_rate']:.0%} · 已完成实验：{len(completed_results)} 个 · "
                f"累计增量收入：R$ {total_incremental_revenue:,.0f}"
            )

    # ── 侧边栏: 会话控制 ────────────────────────
    with st.sidebar:
        st.divider()
        st.caption(f"当前账号：**{current_username}**（{current_user.get('role', 'operator')}）")
        if _get_setting("DATABASE_URL") and st.button("退出登录", use_container_width=True):
            for key in ("current_user", "active_conversation_id", "chat_history", "last_action_drafts", "last_diagnosis"):
                st.session_state.pop(key, None)
            st.session_state.agent_calls = 0
            if st.session_state.get("agent_session"):
                st.session_state.agent_session.clear()
            st.rerun()
        st.subheader("💬 对话控制")

        agent_status = "✅ Agent 就绪" if st.session_state.agent_available else "⚠️ Agent 不可用"
        st.caption(agent_status)

        if st.button("🗑️ 清空对话", use_container_width=True):
            st.session_state.chat_history = []
            if st.session_state.agent_session:
                st.session_state.agent_session.clear()
            st.rerun()

        if st.session_state.agent_available:
            session = st.session_state.agent_session
            turn_count = len(session.history) // 2 if session else 0
            st.caption(f"当前对话轮数: {turn_count}")
            run_meta = st.session_state.get("last_run_meta", {})
            if run_meta:
                st.caption(
                    f"最近一次运行：{run_meta.get('duration_ms', 0)} ms · "
                    f"工具 {run_meta.get('successful_tool_count', 0)}/{run_meta.get('tool_count', 0)} 成功"
                )
        current_storage = storage_mode()
        st.caption(f"任务存储：{current_storage}")
        if current_storage == "PostgreSQL":
            db_ok, db_message = check_database_connection()
            st.caption(("✅ " if db_ok else "⚠️ ") + f"数据库：{db_message}")

    # ── 空状态引导 ──────────────────────────────
    if not st.session_state.chat_history:
        with chat_container:
            with st.chat_message("assistant"):
                st.markdown("""
                👋 你好！我是 **Olist AI 运营顾问**。

                我基于 **LangGraph Agent + Ollama (Qwen3:8b)** 运行，可以:

                - 📊 **查询数据**: 自动调取地区销量、趋势、支付、分群、RFM、热销品类 6 类数据
                - 🔍 **分析发现**: 基于真实数据给出关键洞察
                - 💡 **策略建议**: 生成 P0-P2 优先级运营策略，含行动点和预期效果
                - 🔄 **多轮追问**: 支持连续追问，深入探讨某个方向

                点击上方快捷问题开始，或在输入框自由提问 👆
                """)
