export const workspace = {
  name: "Northstar Commerce",
  mode: "示例工作区",
  updatedAt: "2026-08-31 09:42 UTC",
  dataSource: "Olist 历史样本 + 合成活动结果",
};

export const opportunities = [
  {
    id: "opp-001",
    title: "挽回高价值流失风险客户",
    priority: "P0",
    score: 86,
    segment: "近 90 天未复购、高历史贡献客户",
    potential: "$18,420",
    evidence: "复购间隔明显拉长，过去 30 天沉默比例上升",
    owner: "Lifecycle",
    status: "待审批",
  },
  {
    id: "opp-002",
    title: "提高美国新客的首单后复购",
    priority: "P1",
    score: 74,
    segment: "美国市场首次购买 14–30 天客户",
    potential: "$11,680",
    evidence: "首单后第二次购买转化低于工作区基线",
    owner: "CRM",
    status: "待设计",
  },
  {
    id: "opp-003",
    title: "控制高折扣订单的利润侵蚀",
    priority: "P1",
    score: 69,
    segment: "折扣高于 20% 的复购订单",
    potential: "$7,950",
    evidence: "折扣提升订单量，但净收入增量尚未验证",
    owner: "Growth",
    status: "需验证",
  },
];

export const campaigns = [
  {
    id: "cmp-102",
    name: "高价值客户挽回 / 邮件 A/B 测试",
    objective: "验证个性化提醒是否提升 14 天复购",
    audience: "200 位高流失风险、高历史贡献客户",
    channel: "Email",
    budget: "$100",
    state: "待审批",
  },
  {
    id: "cmp-099",
    name: "新客第二单激励 / 美国市场",
    objective: "提升首单后 30 天复购率",
    audience: "美国 14–30 天首购客户",
    channel: "Email + SMS",
    budget: "$240",
    state: "进行中",
  },
];
