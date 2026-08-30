"""
Agent 模块包

核心：LangGraph 编排的真正 Agent
  - LLM 决策：根据用户问题自主选择数据工具
  - 工具调用：7 个确定性数据查询工具（保证数据准确）
  - 结构化输出：分析 + 策略建议

子模块：
  - tools:        数据查询工具（7 个，含 TOOL_REGISTRY）
  - agent_graph:  LangGraph 三节点编排（fetch → analyze → recommend）
  - run_agent:    CLI 入口
"""
