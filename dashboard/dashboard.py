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
    get_answer_quality_summary,
    get_feedback_operations_summary,
    get_quality_summary,
    list_feedback_issues,
    load_feedback,
    record_run_metric,
    save_feedback,
    update_feedback_issue,
)
from src.agent.regression_eval import run_tool_routing_regression
from src.agent.alerting import generate_operational_alerts
from src.agent.commerce_store import (
    get_active_data_source,
    get_connected_data_health,
    get_connected_sales_trend,
    import_order_csv,
    list_data_sources,
    preview_order_csv,
)
from src.agent.task_store import (
    check_database_connection,
    complete_task,
    create_task,
    launch_simulated_campaign,
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


def _format_money(value: object, currency: str = "USD") -> str:
    """金额永远带币种，避免跨境经营场景把数值误读为同一口径。"""
    return f"{str(currency).upper()} {float(value or 0):,.2f}"


def _single_result_currency(results: list[dict]) -> str | None:
    currencies = {str(item.get("currency", "USD")).upper() for item in results}
    return next(iter(currencies)) if len(currencies) == 1 else None


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

    st.title("🌍 Olist RevenueOps Agent")
    st.caption("登录后可恢复自己的跨境经营分析、活动草稿与实验复盘。")
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
        feedback_type = existing.get("feedback_type", "content")
        if existing["rating"] == -1 and feedback_type == "content":
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
                update_feedback_issue(
                    existing["feedback_id"], "resolved", "已基于用户反馈生成新回答", username
                )
                st.rerun()
        elif existing["rating"] == -1:
            type_label = "数据复核" if feedback_type == "data" else "产品体验待办"
            st.caption(f"该反馈已进入管理员{type_label}流程，不触发 Agent 重写。")
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
            feedback_type = st.selectbox(
                "反馈类型",
                options=["content", "data", "experience"],
                format_func=lambda value: {
                    "content": "回答内容问题（可重新生成）",
                    "data": "数据准确性问题（人工复核）",
                    "experience": "页面 / 交互体验问题（产品待办）",
                }[value],
            )
            reason = st.text_area("哪里需要改进？（可选）", max_chars=500)
            submitted = st.form_submit_button("提交反馈", use_container_width=True)
        if submitted:
            save_feedback(message_id, conversation_id, username, -1, reason, feedback_type)
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
    page_title="Olist RevenueOps Agent",
    page_icon="🛒",
    layout="wide",
)

st.markdown(
    """
    <style>
      :root { --ink: #0f172a; --muted: #64748b; --line: #e2e8f0; --brand: #0f766e; --surface: #f8fafc; }
      .stApp { background: #f8fafc; color: var(--ink); }
      [data-testid="stHeader"] { background: rgba(248,250,252,.92); border-bottom: 1px solid var(--line); }
      h1, h2, h3 { letter-spacing: -0.025em; color: #0f172a; }
      h1 { font-weight: 750; }
      [data-testid="stMetric"] { background: #ffffff; border: 1px solid var(--line); border-radius: 14px; padding: 16px; }
      [data-testid="stMetricLabel"] { color: var(--muted); font-size: .78rem; letter-spacing: .02em; text-transform: uppercase; }
      [data-testid="stMetricValue"] { color: var(--ink); font-weight: 700; }
      .stButton > button { border-radius: 9px; font-weight: 600; min-height: 38px; }
      [data-baseweb="tab-list"] { gap: 20px; border-bottom: 1px solid var(--line); }
      [data-baseweb="tab"] { height: 46px; padding: 0 2px; color: var(--muted); font-weight: 600; }
      [data-baseweb="tab"][aria-selected="true"] { color: var(--brand); }
      .ro-eyebrow { color: var(--brand); font-size: .72rem; letter-spacing: .12em; font-weight: 750; text-transform: uppercase; }
      .ro-hero { background: linear-gradient(120deg, #0f172a 0%, #134e4a 100%); color: white; border-radius: 18px; padding: 26px 30px; margin: 4px 0 24px; }
      .ro-hero h2 { color: white; margin: 3px 0 7px; }
      .ro-hero p { color: #d1fae5; margin: 0; max-width: 760px; }
      .ro-badge { display: inline-block; border-radius: 99px; padding: 3px 8px; font-size: .72rem; font-weight: 700; letter-spacing: .04em; }
      .ro-badge-sample { background:#fff7ed; color:#9a3412; }
      .ro-badge-imported { background:#ecfdf5; color:#047857; }
      .ro-card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 18px; margin: 8px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

_require_login()

# ── 页面标题 ──────────────────────────────────────
st.markdown('<div class="ro-eyebrow">Cross-border revenue operations</div>', unsafe_allow_html=True)
st.title("Olist RevenueOps")
st.caption("Find the next revenue opportunity. Review the action. Prove the outcome.")

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

# 外部订单源接入后，销售趋势与预警优先使用该源；未接入时保持 Olist 演示数据。
active_connected_source = None
connected_data_health = None
if _get_setting("DATABASE_URL"):
    try:
        connected_data_health = get_connected_data_health()
        connected_trend = get_connected_sales_trend(36)
        if connected_trend and connected_trend.get("success"):
            connected_frame = pd.DataFrame(connected_trend["data"])
            connected_frame["period"] = pd.to_datetime(connected_frame["period"], format="%Y-%m")
            sales_trends = pd.DataFrame({
                "customer_state": "CONNECTED",
                "year": connected_frame["period"].dt.year,
                "month": connected_frame["period"].dt.month,
                "order_count": connected_frame["total_orders"],
                "total_sales": connected_frame["total_sales"],
                "period": connected_frame["period"].dt.to_period("M").astype(str),
            })
            active_connected_source = connected_trend.get("source")
        elif connected_data_health:
            active_connected_source = connected_data_health["source"]["display_name"]
    except RuntimeError:
        pass

# Once merchant data is active, never render Olist-only breakdowns beside it.
# Those dimensions become available only after the corresponding connected field
# (customers, products, payment, etc.) is implemented.
if active_connected_source:
    if not connected_data_health or len(connected_data_health["currencies"]) != 1:
        sales_trends = pd.DataFrame()
    customers = pd.DataFrame()
    orders = pd.DataFrame()
    payments = pd.DataFrame()
    order_items = pd.DataFrame()
    user_clusters = pd.DataFrame()
    rfm_analysis = pd.DataFrame()
    population_data = pd.DataFrame()
    region_analysis = pd.DataFrame()

# ═══════════════════════════════════════════════════════
# Tab 布局
# ═══════════════════════════════════════════════════════

tab_dashboard, tab_connections, tab_alerts, tab_chat = st.tabs(
    ["Overview", "Data", "Opportunities", "Campaigns & Ask Agent"]
)


# ╔═════════════════════════════════════════════════════╗
# ║              TAB 1: 数据看板                        ║
# ╚═════════════════════════════════════════════════════╝

with tab_dashboard:
    page_user = st.session_state.get("current_user", {"username": "local", "role": "admin"})
    overview_owner = None if page_user.get("role") == "admin" else page_user["username"]
    overview_tasks = load_tasks(owner=overview_owner)
    overview_alerts, _ = generate_operational_alerts(
        sales_trends,
        pd.DataFrame() if active_connected_source else rfm_analysis,
        pd.DataFrame() if active_connected_source else region_analysis,
    )
    data_badge = "IMPORTED" if active_connected_source else "SAMPLE"
    badge_class = "ro-badge-imported" if active_connected_source else "ro-badge-sample"
    source_label = active_connected_source or "Olist sample baseline"
    st.markdown(
        f'<div class="ro-hero"><span class="ro-badge {badge_class}">{data_badge}</span>'
        f'<h2>Revenue decisions, not dashboard noise.</h2>'
        f'<p>Workspace: <b>{source_label}</b>. Opportunities are evidence-backed; campaigns always require human approval. '
        'No customer outreach is automated by this product.</p></div>',
        unsafe_allow_html=True,
    )
    observed_results = [
        task.get("result", {}) for task in overview_tasks
        if task.get("status") == "completed" and task.get("result", {}).get("measurement_mode") == "observed"
    ]
    observed_currency = _single_result_currency(observed_results) if observed_results else None
    observed_incremental = sum(float(item.get("incremental_revenue", 0) or 0) for item in observed_results)
    awaiting_approval = sum(task.get("status") == "draft" for task in overview_tasks)
    active_campaigns = sum(task.get("status") == "confirmed" for task in overview_tasks)
    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Open opportunities", f"{len(overview_alerts)}")
    metric_b.metric("Awaiting review", f"{awaiting_approval}")
    metric_c.metric("Campaigns in progress", f"{active_campaigns}")
    metric_d.metric(
        "Validated incremental revenue",
        _format_money(observed_incremental, observed_currency) if observed_currency else "No observed result",
        help="Only results explicitly marked as observed are shown. Simulations never appear in this metric.",
    )
    st.markdown("#### Your next best decision")
    if overview_alerts:
        top_opportunity = overview_alerts[0]
        left, right = st.columns([4, 1])
        with left:
            st.markdown(f"<div class='ro-card'><div class='ro-eyebrow'>{top_opportunity['severity']} priority · {top_opportunity['category']}</div>"
                        f"<h3>{top_opportunity['title']}</h3><p><b>Evidence:</b> {_safe_markdown(top_opportunity['evidence'])}</p>"
                        f"<p><b>Recommended next step:</b> {_safe_markdown(top_opportunity['suggested_action'])}</p></div>", unsafe_allow_html=True)
        with right:
            st.write("")
            if st.button("Review opportunity", key="overview_review_opportunity", use_container_width=True):
                st.session_state.pending_question = top_opportunity["agent_question"]
                st.success("Opportunity prepared for review in Campaigns & Ask Agent.")
    else:
        st.info("No opportunity currently meets the configured evidence threshold. Connect current merchant data to begin continuous monitoring.")
    if connected_data_health and connected_data_health["consent_known_rate"] == 0:
        st.warning("Customer marketing consent is not connected. Analysis and simulation are available; real audience activation is intentionally unavailable.")
    st.divider()
    st.markdown("#### Data context")

    # ── KPI 指标卡 ──────────────────────────────
    if connected_data_health:
        source = connected_data_health["source"]
        currencies = connected_data_health["currencies"]
        st.info(
            f"当前展示导入数据源：**{source['display_name']}**。"
            "所有金额仅在同一币种内汇总；数据为导入订单，不代表已验证的营销效果。"
        )
        if len(currencies) == 1 and not sales_trends.empty:
            currency = currencies[0]
            total_orders = int(sales_trends["order_count"].sum())
            total_sales = float(sales_trends["total_sales"].sum())
            avg_order_value = total_sales / total_orders if total_orders else 0
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("📦 导入订单数", f"{total_orders:,}")
            col2.metric("💰 导入销售额", f"{currency} {total_sales:,.0f}")
            col3.metric("🌐 覆盖市场", f"{len(connected_data_health['markets'])}")
            col4.metric("🧾 平均客单价", f"{currency} {avg_order_value:,.2f}")
        else:
            st.warning(
                "该数据源包含多个币种。为避免错误的 GMV/ROI，系统不会跨币种相加；"
                "请按市场或币种拆分导入，或等待后续 FX 报表模块。"
            )
    elif not orders.empty and not order_items.empty and not customers.empty:
        st.caption("当前为 Olist 样本数据演示，不是商家实时经营数据。")
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

    if connected_data_health and len(connected_data_health["currencies"]) == 1 and not sales_trends.empty:
        currency = connected_data_health["currencies"][0]
        st.subheader("📈 已连接店铺月度销售趋势")
        imported_chart = sales_trends[["period", "total_sales", "order_count"]].copy()
        imported_chart = imported_chart.set_index("period").rename(
            columns={"total_sales": f"销售额（{currency}）", "order_count": "订单数"}
        )
        st.line_chart(imported_chart)
        st.caption("趋势按订单原始币种计算；跨币种源不会在此处聚合。客户、商品和渠道归因洞察将在接入对应字段后启用。")

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
# ║              TAB 2: 数据连接                        ║
# ╚═════════════════════════════════════════════════════╝

with tab_connections:
    page_user = st.session_state.get("current_user", {"username": "local", "role": "admin"})
    st.subheader("Commerce data")
    st.caption("Start with a de-identified order CSV. Shopify OAuth is the next connector. Sales analysis uses the active source; currencies are never silently combined.")
    if page_user.get("role") != "admin":
        st.info("Data sources are workspace assets. Only administrators can connect or switch a source.")
    elif not _get_setting("DATABASE_URL"):
        st.warning("Configure PostgreSQL before connecting merchant data. A source cannot be safely stored in a browser session.")
    else:
        uploaded_orders = st.file_uploader("Upload order CSV", type=["csv"], key="order_csv_upload")
        if uploaded_orders is not None:
            try:
                preview = preview_order_csv(uploaded_orders.getvalue())
                st.success(f"Read {preview['row_count']:,} rows and detected {len(preview['columns'])} columns.")
                st.dataframe(pd.DataFrame(preview["sample"]), use_container_width=True, hide_index=True)
                columns = preview["columns"]
                mapping_options = ["", *columns]

                def suggested_index(candidates: tuple[str, ...]) -> int:
                    lowered = {column.lower(): index for index, column in enumerate(columns, start=1)}
                    for candidate in candidates:
                        if candidate in lowered:
                            return lowered[candidate]
                    return 0

                with st.form("order_mapping_form"):
                    source_name = st.text_input("Source name", value=uploaded_orders.name.rsplit(".", 1)[0])
                    st.markdown("**Map fields**: * is required. Do not upload email, phone, street address, or card data. Amount must be the final amount for one order.")
                    map_left, map_right = st.columns(2)
                    with map_left:
                        order_id_column = st.selectbox(
                            "Order ID *", mapping_options, index=suggested_index(("order_id", "id", "order_number", "name"))
                        )
                        ordered_at_column = st.selectbox(
                            "Order timestamp *", mapping_options,
                            index=suggested_index(("ordered_at", "created_at", "order_date", "order_created_at", "date")),
                        )
                        total_amount_column = st.selectbox(
                            "Order total *", mapping_options,
                            index=suggested_index(("total_amount", "total_price", "payment_value", "amount", "revenue")),
                        )
                    with map_right:
                        customer_id_column = st.selectbox(
                            "Customer ID (optional)", mapping_options,
                            index=suggested_index(("customer_id", "customer", "customer_email")),
                        )
                        status_column = st.selectbox(
                            "Order status (optional)", mapping_options, index=suggested_index(("status", "financial_status", "order_status"))
                        )
                        currency_column = st.selectbox(
                            "Currency (optional)", mapping_options, index=suggested_index(("currency", "currency_code"))
                        )
                        market_column = st.selectbox(
                            "Market / country (optional)", mapping_options,
                            index=suggested_index(("market", "country", "shipping_country", "customer_country")),
                        )
                        timezone_column = st.selectbox(
                            "Order timezone (optional)", mapping_options, index=suggested_index(("timezone", "time_zone"))
                        )
                    st.markdown("**Cross-border defaults**: Used per order when a source does not provide the field. These determine safe aggregation and scheduling.")
                    default_left, default_right, default_third = st.columns(3)
                    with default_left:
                        default_currency = st.text_input("Default currency *", value="USD", help="ISO 4217, e.g. USD / GBP / EUR")
                    with default_right:
                        default_market = st.text_input("Default market", value="GLOBAL", help="Two-letter country code, e.g. US / GB / DE, or GLOBAL")
                    with default_third:
                        default_timezone = st.text_input("Default timezone", value="UTC", help="IANA format, e.g. America/New_York")
                    consent_column = st.selectbox(
                        "Marketing consent (optional; required for live activation)", mapping_options,
                        index=suggested_index(("marketing_consent", "email_marketing_consent", "accepts_marketing", "subscribed")),
                    )
                    locale_column = st.selectbox(
                        "Customer language / locale (optional)", mapping_options,
                        index=suggested_index(("locale", "language", "customer_locale")),
                    )
                    import_submitted = st.form_submit_button("Import and activate source", use_container_width=True)
                if import_submitted:
                    try:
                        result = import_order_csv(
                            uploaded_orders.getvalue(), source_name,
                            {
                                "order_id": order_id_column, "ordered_at": ordered_at_column,
                                "total_amount": total_amount_column, "customer_id": customer_id_column,
                                "status": status_column, "currency": currency_column, "market": market_column,
                                "timezone": timezone_column, "marketing_consent": consent_column,
                                "customer_locale": locale_column,
                            },
                            page_user["username"],
                            {"currency": default_currency, "market": default_market, "timezone": default_timezone},
                        )
                        st.success(
                            f"已导入 {result['record_count']:,} 笔订单，覆盖 {result['coverage_start']} 至 {result['coverage_end']}；"
                            f"跳过 {result['rejected_count']:,} 行无效数据。"
                        )
                        st.caption(
                            f"币种：{', '.join(result['currencies'])} · 市场：{', '.join(result['markets'])} · "
                            f"含营销同意状态订单：{result['consent_known_rows']:,} 笔。"
                        )
                        st.rerun()
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
            except ValueError as exc:
                st.error(str(exc))
        sources = list_data_sources()
        if sources:
            st.markdown("##### 已连接数据源")
            source_rows = [
                {
                    "当前使用": "✓" if source["is_active"] else "",
                    "名称": source["display_name"], "类型": source["source_type"],
                    "订单数": source["record_count"], "数据覆盖开始": source["coverage_start"],
                    "数据覆盖结束": source["coverage_end"], "导入人": source["created_by"],
                }
                for source in sources
            ]
            st.dataframe(pd.DataFrame(source_rows), use_container_width=True, hide_index=True)
            if connected_data_health:
                st.markdown("##### 🛡️ 数据可执行性检查")
                health_a, health_b, health_c, health_d = st.columns(4)
                health_a.metric("币种", ", ".join(connected_data_health["currencies"]) or "未识别")
                health_b.metric("市场", f"{len(connected_data_health['markets'])} 个")
                health_c.metric("时区", f"{len(connected_data_health['timezones'])} 个")
                health_d.metric("营销同意覆盖", f"{connected_data_health['consent_known_rate']:.0%}")
                if len(connected_data_health["currencies"]) != 1:
                    st.warning("发现多币种。销售和 ROI 不会跨币种相加；请拆分市场数据或后续启用 FX 报表口径。")
                if connected_data_health["consent_known_rate"] == 0:
                    st.info("当前没有可用的营销同意状态。可进行分析和模拟，但不能用于真实受众触达。")
        else:
            st.info("尚未连接外部订单数据。未连接时，系统继续使用 Olist 演示数据。")


# ╔═════════════════════════════════════════════════════╗
# ║              TAB 3: 主动经营预警                    ║
# ╚═════════════════════════════════════════════════════╝

with tab_alerts:
    st.subheader("Prioritized opportunities")
    st.caption("Each opportunity is generated from deterministic data rules. Reviewing one creates a campaign brief; it never contacts a customer or changes spend automatically.")
    if active_connected_source:
        st.info(f"Active sales source: **{active_connected_source}**. Customer and market opportunities unlock only when those fields are connected.")
    alerts, data_notes = generate_operational_alerts(
        sales_trends,
        pd.DataFrame() if active_connected_source else rfm_analysis,
        pd.DataFrame() if active_connected_source else region_analysis,
    )
    if data_notes:
        with st.expander("🛡️ 数据完整性保护", expanded=False):
            for note in data_notes:
                st.warning(note)
    if not alerts:
        st.success("No opportunity currently reaches the evidence threshold.")
    severity_labels = {"high": "高", "medium": "中", "low": "低"}
    severity_icons = {"high": "🔴", "medium": "🟠", "low": "🟡"}
    for alert in alerts:
        with st.container(border=True):
            header, badge = st.columns([8, 1])
            header.markdown(f"#### {severity_icons[alert['severity']]} {alert['title']}")
            badge.metric("优先级", severity_labels[alert["severity"]])
            st.caption(f"{alert['category']} · 来源：{alert['source']}")
            st.markdown(f"**数据证据**：{_safe_markdown(alert['evidence'])}")
            st.markdown(f"**影响范围**：{alert['impact']}")
            st.markdown(f"**建议动作**：{alert['suggested_action']}")
            if st.button("🤖 交给 Agent 深入诊断", key=f"alert_diagnose_{alert['id']}", use_container_width=True):
                st.session_state.pending_question = alert["agent_question"]
                st.success("已将预警交给 Agent，正在生成带证据的深入诊断与任务草稿。")


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
    if _get_setting("DATABASE_URL"):
        try:
            active_source = get_active_data_source()
            if active_source:
                st.info(
                    f"当前 Agent 销售趋势数据源：**{active_source['display_name']}** · "
                    f"{active_source['record_count']:,} 笔订单 · "
                    f"覆盖至 {active_source['coverage_end']}"
                )
            else:
                st.caption("当前使用 Olist 演示数据。管理员可在“🔌 数据连接”接入自己的订单 CSV。")
        except RuntimeError:
            pass

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

    # ── Campaign workspace: human-reviewed, channel-safe execution ─────
    with st.expander("Campaign workspace", expanded=True):
        drafts = st.session_state.get("last_action_drafts", [])
        if drafts:
            st.caption("The Agent creates a brief, never a live send. Complete the four decision steps, then submit it for human review.")
            for idx, draft in enumerate(drafts):
                key_prefix = f"draft_{idx}"
                st.markdown(f"##### Draft: {draft.get('title', 'Retention campaign')}")
                with st.form(f"campaign_brief_{idx}"):
                    audience_step, message_step, measurement_step, approval_step = st.tabs([
                        "1 · Audience", "2 · Message & offer", "3 · Measurement", "4 · Approval",
                    ])
                    with audience_step:
                        audience = st.text_input("Eligible audience", value=str(draft.get("audience", "To be defined")))
                        st.caption("Use a pseudonymous segment rule. Live activation remains unavailable until marketing consent is connected.")
                    with message_step:
                        title = st.text_input("Campaign name", value=str(draft.get("title", "Retention campaign")))
                        channel = st.selectbox(
                            "Channel", options=["Email", "SMS", "WhatsApp", "Other / to be confirmed"],
                            index=0 if str(draft.get("channel", "")).lower() in {"", "email", "待确认"} else 3,
                        )
                        market, locale = st.columns(2)
                        with market:
                            market_value = st.text_input("Market", value=str(draft.get("market", "US")))
                        with locale:
                            locale_value = st.text_input("Content locale", value=str(draft.get("locale", "en-US")))
                    with measurement_step:
                        budget_default = float(draft.get("budget") or 0)
                        budget = st.number_input("Campaign cost budget", min_value=0.0, value=budget_default, step=100.0)
                        duration = st.number_input("Campaign duration (days)", min_value=1, max_value=90, value=int(draft.get("duration_days") or 7))
                        attribution_window = st.number_input(
                            "Attribution window (days)", min_value=1, max_value=90,
                            value=int(draft.get("attribution_window_days") or 7),
                        )
                        st.caption("Treatment and control outcomes must use one currency and this declared attribution window.")
                    with approval_step:
                        st.info("This saves a reviewable campaign brief. It does not send messages, issue discounts, or export customer contact details.")
                        consent_basis = st.selectbox(
                            "Activation readiness", ["Consent not connected — simulation only", "Merchant will verify consent before activation"],
                        )
                    save_draft = st.form_submit_button("Save campaign brief for review", use_container_width=True)
                if save_draft:
                    task = create_task(
                        {**draft, "title": title, "audience": audience, "channel": channel,
                         "budget": budget, "duration_days": duration, "market": market_value,
                         "locale": locale_value, "attribution_window_days": attribution_window,
                         "timezone": str(draft.get("timezone", "UTC")),
                         "consent_basis": consent_basis},
                        question=st.session_state.get("last_question", ""),
                        source_diagnosis=st.session_state.get("last_diagnosis", {}),
                        owner=current_username,
                    )
                    st.success(f"Campaign brief {task['task_id']} saved for review.")
                    st.rerun()
        else:
            st.info("Review an opportunity or ask the Agent to generate a campaign brief.")

        tasks = load_tasks(owner=task_owner)
        if tasks:
            st.divider()
            st.caption(f"{len(tasks)} saved campaign briefs")
            completed_results = [
                task.get("result", {}) for task in tasks
                if task.get("status") == "completed" and isinstance(task.get("result"), dict)
            ]
            if completed_results:
                st.markdown("##### Campaign learning")
                result_currency = _single_result_currency(completed_results)
                if result_currency:
                    total_incremental_revenue = sum(float(result.get("incremental_revenue", 0) or 0) for result in completed_results)
                    total_cost = sum(float(result.get("cost", 0) or 0) for result in completed_results)
                    portfolio_roi = ((total_incremental_revenue - total_cost) / total_cost) if total_cost else None
                    metric_a, metric_b, metric_c, metric_d = st.columns(4)
                    metric_a.metric("Completed evaluations", f"{len(completed_results)}")
                    metric_b.metric("Estimated incremental revenue", _format_money(total_incremental_revenue, result_currency))
                    metric_c.metric("Campaign cost", _format_money(total_cost, result_currency))
                    metric_d.metric("Portfolio ROI", f"{portfolio_roi:.0%}" if portfolio_roi is not None else "Cost missing")
                else:
                    st.info("Completed campaigns use multiple currencies. Revenue, cost, and ROI are not aggregated across currencies.")
            for task in tasks[:10]:
                task_id = task.get("task_id", "?")
                status = task.get("status", "draft")
                mode = (task.get("result") or {}).get("measurement_mode") or ((task.get("execution") or {}).get("mode")) or "review"
                st.markdown(f"**[{status.upper()} · {str(mode).upper()}] {task.get('title', 'Untitled campaign')}** · `{task_id}`")
                st.caption(
                    f"Audience: {task.get('audience', 'Not set')} · Channel: {task.get('channel', 'Not set')} · "
                    f"Market: {task.get('market', 'To confirm')} · Locale: {task.get('locale', 'To confirm')} · "
                    f"Budget: {task.get('budget', 0)}"
                )
                col_confirm, col_reject = st.columns(2)
                with col_confirm:
                    if status == "draft" and st.button("Approve campaign brief", key=f"confirm_{task_id}", use_container_width=True):
                        update_task(task_id, {"status": "confirmed"}, owner=task_owner)
                        st.rerun()
                with col_reject:
                    if status == "draft" and st.button("Decline brief", key=f"reject_{task_id}", use_container_width=True):
                        update_task(task_id, {"status": "rejected"}, owner=task_owner)
                        st.rerun()
                if status == "confirmed":
                    execution = task.get("execution") if isinstance(task.get("execution"), dict) else None
                    if not execution:
                        with st.form(f"launch_form_{task_id}"):
                            st.caption("Simulation only: no email, SMS, WhatsApp, coupon, or customer export is created. Live activation requires verified consent and merchant approval.")
                            audience_size = st.number_input(
                                "Simulated eligible recipients", min_value=1, value=200, step=50, key=f"audience_size_{task_id}"
                            )
                            exec_left, exec_right, exec_third = st.columns(3)
                            with exec_left:
                                execution_market = st.text_input("Execution market", value=str(task.get("market", "US")), key=f"market_{task_id}")
                            with exec_right:
                                execution_timezone = st.text_input("Execution timezone", value=str(task.get("timezone", "UTC")), key=f"timezone_{task_id}")
                            with exec_third:
                                execution_locale = st.text_input("Content locale", value=str(task.get("locale", "en-US")), key=f"locale_{task_id}")
                            attribution_window = st.number_input(
                                "Attribution window (days)", min_value=1, max_value=90,
                                value=int(task.get("attribution_window_days") or 7), key=f"window_{task_id}"
                            )
                            launch_submitted = st.form_submit_button("Create simulation", use_container_width=True)
                        if launch_submitted:
                            try:
                                launch_simulated_campaign(
                                    task_id, int(audience_size), market=execution_market, timezone_name=execution_timezone,
                                    locale=execution_locale, attribution_window_days=int(attribution_window), owner=task_owner,
                                )
                                st.success("Simulation created. Add treatment/control outcomes below when ready.")
                                st.rerun()
                            except ValueError as exc:
                                st.error(str(exc))
                    else:
                        st.success(
                            f"[SIMULATION] 活动 `{execution.get('campaign_id')}` 已启动 · "
                            f"{execution.get('channel', '待确认')} · 模拟触达 {execution.get('audience_size', 0):,} 人 · "
                            f"{execution.get('market', 'GLOBAL')} / {execution.get('locale', 'en')} · "
                            f"归因窗口 {execution.get('attribution_window_days', 7)} 天"
                        )
                    if not execution:
                        continue
                    with st.form(f"result_form_{task_id}"):
                        st.markdown("##### Learning input")
                        st.caption("Simulation result only. Enter treatment/control outcomes in one currency; the declared campaign attribution window is preserved.")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            treatment_users = st.number_input("Treatment recipients", min_value=1, value=100, key=f"tu_{task_id}")
                            treatment_orders = st.number_input("Treatment orders", min_value=0, value=10, key=f"to_{task_id}")
                            treatment_revenue = st.number_input("Treatment revenue", min_value=0.0, value=1000.0, step=100.0, key=f"tr_{task_id}")
                        with c2:
                            control_users = st.number_input("Control customers", min_value=1, value=100, key=f"cu_{task_id}")
                            control_orders = st.number_input("Control orders", min_value=0, value=8, key=f"co_{task_id}")
                            control_revenue = st.number_input("Control revenue", min_value=0.0, value=800.0, step=100.0, key=f"cr_{task_id}")
                        with c3:
                            cost = st.number_input("Campaign cost", min_value=0.0, value=float(task.get("budget") or 0), step=100.0, key=f"cost_{task_id}")
                            result_currency = st.text_input(
                                "Result currency", value=(connected_data_health["currencies"][0] if connected_data_health and len(connected_data_health["currencies"]) == 1 else "USD"),
                                key=f"currency_{task_id}", help="Treatment, control, and cost must use the same currency."
                            )
                        revenue_net_of_refunds = st.checkbox("Revenue is net of refunds / returns", value=False, key=f"refunds_{task_id}")
                        submitted = st.form_submit_button("Save simulated result", use_container_width=True)
                    if submitted:
                        try:
                            result = evaluate_experiment(
                                treatment_users, treatment_orders, treatment_revenue,
                                control_users, control_orders, control_revenue, cost,
                                currency=result_currency,
                                attribution_window_days=int(execution.get("attribution_window_days", 7)),
                                measurement_mode="simulation",
                                revenue_net_of_refunds=revenue_net_of_refunds,
                            )
                            complete_task(task_id, result, owner=task_owner)
                            st.success(f"Simulation result saved for campaign {task_id}.")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                if status == "completed" and task.get("result"):
                    result = task["result"]
                    roi = result.get("roi")
                    roi_text = f"{roi:.1%}" if roi is not None else "No cost entered"
                    verdict_title, verdict_detail = _experiment_verdict(result)
                    with st.container(border=True):
                        mode = str(result.get("measurement_mode", "simulation")).upper()
                        st.markdown(f"##### Learning result · {mode}")
                        if result.get("measurement_mode", "simulation") == "simulation":
                            st.warning("SIMULATION — This is a planning result, not verified merchant revenue. It is excluded from validated revenue on Overview.")
                        metric_a, metric_b, metric_c, metric_d = st.columns(4)
                        metric_a.metric("Treatment conversion", f"{result.get('treatment_conversion', 0):.2%}")
                        metric_b.metric("Conversion lift", f"{result.get('conversion_uplift_pp', 0):.2f} pp")
                        metric_c.metric("Estimated incremental revenue", _format_money(result.get("incremental_revenue"), result.get("currency", "USD")))
                        metric_d.metric("ROI", roi_text)
                        st.caption(
                            f"Control conversion: {result.get('control_conversion', 0):.2%} · "
                            f"Incremental orders: {float(result.get('incremental_orders', 0) or 0):,.1f} · "
                            f"Campaign cost: {_format_money(result.get('cost'), result.get('currency', 'USD'))} · "
                            f"Attribution: {result.get('attribution_window_days', 7)} days · "
                            f"Refund-adjusted: {'Yes' if result.get('revenue_net_of_refunds') else 'No'}"
                        )
                        st.info(f"**{verdict_title}**：{verdict_detail}")

    # ── 管理员质量看板 ─────────────────────────────
    if current_user.get("role") == "admin" and _get_setting("DATABASE_URL"):
        with st.expander("📈 Agent 质量看板", expanded=False):
            quality = get_quality_summary()
            feedback_operations = get_feedback_operations_summary()
            answer_quality = get_answer_quality_summary()
            all_tasks = load_tasks()
            completed_results = [
                task.get("result", {}) for task in all_tasks
                if task.get("status") == "completed" and isinstance(task.get("result"), dict)
            ]
            adopted_count = sum(task.get("status") in {"confirmed", "completed"} for task in all_tasks)
            result_currency = _single_result_currency(completed_results) if completed_results else None
            total_incremental_revenue = sum(float(result.get("incremental_revenue", 0) or 0) for result in completed_results)
            total_cost = sum(float(result.get("cost", 0) or 0) for result in completed_results)
            portfolio_roi = ((total_incremental_revenue - total_cost) / total_cost) if total_cost and result_currency else None
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
            metric_h.metric("已完成任务 ROI", f"{portfolio_roi:.0%}" if portfolio_roi is not None else "需同币种结果")
            st.caption(
                f"错误率：{quality['error_rate']:.0%} · 已完成实验：{len(completed_results)} 个 · "
                f"累计增量收入：{_format_money(total_incremental_revenue, result_currency)}"
                if result_currency else
                f"累计增量收入：多币种结果不做汇总"
            )
            st.markdown("##### 🔁 反馈闭环指标")
            ops_a, ops_b, ops_c, ops_d = st.columns(4)
            ops_a.metric("负反馈", f"{feedback_operations['negative_feedback_count']} 条")
            ops_b.metric("待处理", f"{feedback_operations['open_count']} 条")
            ops_c.metric(
                "已处理率",
                f"{feedback_operations['processed_rate']:.0%}"
                if feedback_operations["processed_rate"] is not None else "暂无反馈",
            )
            ops_d.metric(
                "平均闭环时长",
                f"{feedback_operations['avg_closure_hours']:.1f} 小时"
                if feedback_operations["avg_closure_hours"] is not None else "暂无数据",
            )
            type_labels = {"content": "回答内容", "data": "数据准确性", "experience": "页面 / 交互体验"}
            feedback_type_rows = [
                {
                    "类型": type_labels.get(feedback_type, feedback_type),
                    "反馈数": values["total"],
                    "待处理": values["open"],
                }
                for feedback_type, values in feedback_operations["by_type"].items()
            ]
            if feedback_operations["negative_feedback_count"]:
                st.bar_chart(pd.DataFrame(feedback_type_rows).set_index("类型")[["反馈数", "待处理"]])
            else:
                st.caption("暂无负反馈数据；收到反馈后将按类型展示产品改进优先级。")

            st.markdown("##### 🧠 真实回答质量（qa_v1）")
            st.info(
                "**评分说明**：综合质量分 = 证据覆盖率 × 45% + 来源标注率 × 25% + 策略完整度 × 30%。  "
                "证据覆盖率衡量每条结论是否附有数据证据；来源标注率衡量是否写明数据/工具来源；"
                "策略完整度衡量任务是否具备行动、人群、渠道、周期和目标指标。"
            )
            if answer_quality["evaluated_runs"]:
                answer_a, answer_b, answer_c, answer_d = st.columns(4)
                answer_a.metric("已评测回答", f"{answer_quality['evaluated_runs']} 次")
                answer_b.metric("综合质量分", f"{answer_quality['quality_score']:.0%}")
                answer_c.metric("证据覆盖率", f"{answer_quality['evidence_coverage']:.0%}")
                answer_d.metric("策略完整度", f"{answer_quality['action_completeness']:.0%}")
                model_quality_rows = [
                    {
                        "模型": f"{item['provider']} / {item['model']}",
                        "评测版本": item["version"],
                        "回答数": item["runs"],
                        "综合质量分": f"{item['quality_score']:.0%}",
                        "证据覆盖率": f"{item['evidence_coverage']:.0%}",
                        "来源标注率": f"{item['source_citation_rate']:.0%}",
                        "策略完整度": f"{item['action_completeness']:.0%}",
                    }
                    for item in answer_quality["by_model"]
                ]
                st.dataframe(pd.DataFrame(model_quality_rows), use_container_width=True, hide_index=True)
                st.caption("评分只基于结构化输出，不让模型自评；它用于比较回答的可核验性与可执行性，不替代人工业务判断。")
            else:
                st.caption("暂无 qa_v1 数据。完成一次新的 Agent 对话后，系统将自动记录真实回答质量。")

        with st.expander("📥 用户反馈待办中心", expanded=False):
            status_filter = st.selectbox(
                "处理状态",
                options=["open", "resolved", "dismissed"],
                format_func=lambda value: {"open": "待处理", "resolved": "已修复", "dismissed": "不处理"}[value],
            )
            issues = list_feedback_issues(status_filter)
            if not issues:
                st.info("当前没有符合条件的负反馈待办。")
            for issue in issues:
                type_label = {
                    "content": "回答内容",
                    "data": "数据准确性",
                    "experience": "页面 / 交互体验",
                }.get(issue["feedback_type"], "未分类")
                st.markdown(f"**[{type_label}] {issue['username']} 的反馈** · `{issue['feedback_id']}`")
                st.caption(f"提交时间：{issue['created_at']} · 描述：{issue['reason'] or '未填写'}")
                if issue["status"] == "open":
                    with st.form(f"issue_form_{issue['feedback_id']}"):
                        resolution = st.text_area(
                            "处理说明", max_chars=500, key=f"issue_resolution_{issue['feedback_id']}"
                        )
                        decision = st.radio(
                            "处理结果", options=["resolved", "dismissed"], horizontal=True,
                            format_func=lambda value: "已修复" if value == "resolved" else "不处理",
                            key=f"issue_decision_{issue['feedback_id']}",
                        )
                        submitted = st.form_submit_button("更新待办", use_container_width=True)
                    if submitted:
                        update_feedback_issue(issue["feedback_id"], decision, resolution, current_username)
                        st.rerun()
                else:
                    st.caption(
                        f"处理说明：{issue['resolution'] or '未填写'} · 处理人：{issue['resolved_by'] or '未记录'}"
                    )

        with st.expander("🧪 Agent 工具路由回归评测", expanded=False):
            st.caption("覆盖 30 个核心运营问题，验证模型不可用时的保底路由、参数和真实数据工具。不会调用 LLM，也不会消耗 API 额度。")
            if st.button("运行 30 条回归评测", key="run_tool_routing_regression", use_container_width=True):
                with st.spinner("正在验证工具路由与数据可用性..."):
                    st.session_state.tool_routing_regression = run_tool_routing_regression()
            regression = st.session_state.get("tool_routing_regression")
            if regression:
                reg_a, reg_b, reg_c, reg_d = st.columns(4)
                reg_a.metric("通过用例", f"{regression['passed']} / {regression['total']}")
                reg_b.metric("路由准确率", f"{regression['routing_accuracy']:.0%}")
                reg_c.metric("参数准确率", f"{regression['parameter_accuracy']:.0%}")
                reg_d.metric("工具执行成功率", f"{regression['tool_execution_success_rate']:.0%}")
                failed_cases = [item for item in regression["results"] if not item["passed"]]
                if failed_cases:
                    st.error(f"发现 {len(failed_cases)} 条未通过用例，请在改动模型、Prompt 或工具后修复。")
                    st.dataframe(pd.DataFrame(failed_cases), use_container_width=True, hide_index=True)
                else:
                    st.success("30 条核心运营场景全部通过，可作为当前版本的保底能力基线。")

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
                👋 你好！我是 **Olist RevenueOps Agent**。

                我基于 **LangGraph Agent + Ollama (Qwen3:8b)** 运行，可以:

                - 📊 **连接并查询数据**: 支持 Olist 演示基线与已导入的跨境订单数据
                - 🔍 **分析发现**: 基于可核验数据识别销售、留存与增长机会
                - 💡 **策略建议**: 生成可审核的市场、语言、渠道与归因窗口配置
                - 🔄 **多轮追问**: 支持连续追问，深入探讨某个方向

                当前不会自动向真实消费者发送任何内容；真实触达需要商家批准及可验证的营销同意状态。

                点击上方快捷问题开始，或在输入框自由提问 👆
                """)
