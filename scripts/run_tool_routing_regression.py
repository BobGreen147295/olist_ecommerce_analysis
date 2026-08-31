"""运行 Agent 工具路由回归集：python scripts/run_tool_routing_regression.py"""

from src.agent.regression_eval import run_tool_routing_regression


if __name__ == "__main__":
    summary = run_tool_routing_regression()
    print(
        f"工具路由回归：{summary['passed']}/{summary['total']} 通过，"
        f"路由准确率 {summary['routing_accuracy']:.0%}，"
        f"参数准确率 {summary['parameter_accuracy']:.0%}，"
        f"工具执行成功率 {summary['tool_execution_success_rate']:.0%}"
    )
    failed = [item for item in summary["results"] if not item["passed"]]
    for item in failed:
        print(f"失败 {item['id']}: {item['query']} -> {item['selected_tools']}")
    raise SystemExit(0 if not failed else 1)
