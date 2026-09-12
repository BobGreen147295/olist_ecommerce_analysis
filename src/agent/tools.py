"""Deterministic tools backed only by the active merchant connection."""

from .commerce_store import get_connected_sales_trend


def query_sales_trend(months: int = 6) -> dict:
    """Return an aggregate trend without falling back to bundled sample data."""
    try:
        months = int(months)
    except (TypeError, ValueError):
        return {"success": False, "data": None, "summary": "months 必须是整数"}
    if not 1 <= months <= 36:
        return {"success": False, "data": None, "summary": "months 必须是 1 到 36 之间的整数"}

    try:
        result = get_connected_sales_trend(months)
    except RuntimeError:
        result = None
    if result is not None:
        return result
    return {
        "success": False,
        "data": None,
        "summary": "尚无可用的已连接订单趋势，请先完成 Shopify 同步或导入脱敏订单。",
        "source": "none",
    }


TOOL_REGISTRY = {"query_sales_trend": query_sales_trend}


def execute_tool(tool_name: str, **kwargs) -> dict:
    """Execute a registered tool and include its name in the result."""
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return {"success": False, "data": None, "summary": f"未知工具: {tool_name}", "tool": tool_name}
    result = tool(**kwargs)
    result["tool"] = tool_name
    return result
