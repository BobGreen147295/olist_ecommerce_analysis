"""不调用模型的 Agent 工具路由回归评测。

这套用例用于验证模型失败后的保底路由与确定性数据工具仍覆盖核心运营场景。
它不评估语言模型的文案质量，也不会消耗 OpenAI/Ollama 调用额度。
"""

from __future__ import annotations

from typing import Any

from .agent_graph import _fallback_tool_calls
from .tools import execute_tool


EVAL_CASES: tuple[dict[str, Any], ...] = (
    # 地区销售（4）
    {"id": "region_01", "query": "圣保罗州销售怎么样", "tools": ("query_sales_by_region",), "args": {"region": "SP"}},
    {"id": "region_02", "query": "SP州的销售排名是多少", "tools": ("query_sales_by_region",), "args": {"region": "SP"}},
    {"id": "region_03", "query": "里约地区表现如何", "tools": ("query_sales_by_region",), "args": {"region": "RJ"}},
    {"id": "region_04", "query": "米纳斯州的人均销售额", "tools": ("query_sales_by_region",), "args": {"region": "MG"}},
    # 销售趋势（5）
    {"id": "trend_01", "query": "分析最近半年的销售趋势", "tools": ("query_sales_trend",), "args": {"months": 6}},
    {"id": "trend_02", "query": "最近销量变化怎么样", "tools": ("query_sales_trend",), "args": {"months": 6}},
    {"id": "trend_03", "query": "月度订单是否在下降", "tools": ("query_sales_trend",), "args": {"months": 6}},
    {"id": "trend_04", "query": "最近几个月营收趋势", "tools": ("query_sales_trend",), "args": {"months": 6}},
    {"id": "trend_05", "query": "销售额有什么变化", "tools": ("query_sales_trend",), "args": {"months": 6}},
    # 支付方式（4）
    {"id": "payment_01", "query": "支付方式分布有问题吗", "tools": ("query_payment_distribution",), "args": {}},
    {"id": "payment_02", "query": "客户主要用什么付款", "tools": ("query_payment_distribution",), "args": {}},
    {"id": "payment_03", "query": "分期订单占比如何", "tools": ("query_payment_distribution",), "args": {}},
    {"id": "payment_04", "query": "信用卡支付表现", "tools": ("query_payment_distribution",), "args": {}},
    # 用户分群（4）
    {"id": "segment_01", "query": "客户分群情况怎么样", "tools": ("query_user_segments",), "args": {}},
    {"id": "segment_02", "query": "给我看客群结构", "tools": ("query_user_segments",), "args": {}},
    {"id": "segment_03", "query": "用户画像有哪些类型", "tools": ("query_user_segments",), "args": {}},
    {"id": "segment_04", "query": "分群用户占比", "tools": ("query_user_segments",), "args": {}},
    # RFM 客户价值（4）
    {"id": "rfm_01", "query": "RFM 客户价值分层", "tools": ("query_rfm_summary",), "args": {}},
    {"id": "rfm_02", "query": "高价值客户有多少", "tools": ("query_rfm_summary",), "args": {}},
    {"id": "rfm_03", "query": "低价值客户消费如何", "tools": ("query_rfm_summary",), "args": {}},
    {"id": "rfm_04", "query": "客户价值结构", "tools": ("query_rfm_summary",), "args": {}},
    # 流失与召回（5）
    {"id": "churn_01", "query": "客户流失风险情况如何", "tools": ("query_churn_risk", "query_rfm_summary"), "args": {}},
    {"id": "churn_02", "query": "哪些客户应该优先召回", "tools": ("query_churn_risk", "query_rfm_summary"), "args": {}},
    {"id": "churn_03", "query": "高风险客户怎么挽回", "tools": ("query_churn_risk", "query_rfm_summary"), "args": {}},
    {"id": "churn_04", "query": "用户风险分布", "tools": ("query_churn_risk", "query_rfm_summary"), "args": {}},
    {"id": "churn_05", "query": "流失人群价值高吗", "tools": ("query_churn_risk", "query_rfm_summary"), "args": {}},
    # 商品与品类（4）
    {"id": "category_01", "query": "热销商品有哪些", "tools": ("query_top_categories",), "args": {"n": 10}},
    {"id": "category_02", "query": "哪个品类卖得最好", "tools": ("query_top_categories",), "args": {"n": 10}},
    {"id": "category_03", "query": "产品销售排行", "tools": ("query_top_categories",), "args": {"n": 10}},
    {"id": "category_04", "query": "热销 SKU 排名", "tools": ("query_top_categories",), "args": {"n": 10}},
)


def run_tool_routing_regression() -> dict[str, Any]:
    """执行 30 条核心场景，校验路由、参数与工具数据可用性。"""
    results: list[dict[str, Any]] = []
    for case in EVAL_CASES:
        calls = _fallback_tool_calls(case["query"])
        selected_tools = tuple(call.get("tool") for call in calls)
        expected_tools = case["tools"]
        routing_passed = selected_tools == expected_tools
        expected_args = case["args"]
        parameter_passed = all(
            all(call.get("args", {}).get(key) == value for key, value in expected_args.items())
            for call in calls
        )
        tool_results = [execute_tool(call["tool"], **call.get("args", {})) for call in calls]
        execution_passed = bool(tool_results) and all(result.get("success") for result in tool_results)
        passed = routing_passed and parameter_passed and execution_passed
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected_tools": list(expected_tools),
                "selected_tools": list(selected_tools),
                "passed": passed,
                "routing_passed": routing_passed,
                "parameter_passed": parameter_passed,
                "execution_passed": execution_passed,
            }
        )
    total = len(results)
    passed_count = sum(item["passed"] for item in results)
    return {
        "total": total,
        "passed": passed_count,
        "pass_rate": (passed_count / total) if total else 0.0,
        "routing_accuracy": sum(item["routing_passed"] for item in results) / total if total else 0.0,
        "parameter_accuracy": sum(item["parameter_passed"] for item in results) / total if total else 0.0,
        "tool_execution_success_rate": sum(item["execution_passed"] for item in results) / total if total else 0.0,
        "results": results,
    }
