"""
Agent 模块包

核心：LangGraph 编排的商家数据 Agent
  - LLM 决策：理解商家问题并选择生产安全的数据工具
  - 工具调用：只读取当前账户已连接的聚合数据
  - 结构化输出：分析 + 策略建议

子模块：
  - tools:        已连接商家数据工具与 TOOL_REGISTRY
  - agent_graph:  LangGraph 三节点编排（fetch → analyze → recommend）
"""
