"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Locale = "zh-CN" | "en";

const STORAGE_KEY = "revenueops_locale";

const messages = {
  "zh-CN": {
    skip: "跳到主要内容", closeNav: "关闭导航", openNav: "打开导航", workspace: "工作区",
    overview: "总览", opportunities: "机会", campaigns: "活动", learning: "实验复盘", data: "数据连接",
    overviewMeta: "Overview", opportunitiesMeta: "Opportunities", campaignsMeta: "Campaigns", learningMeta: "Learning", dataMeta: "Data",
    copilotTitle: "AI Co-pilot", copilotBody: "基于证据生成建议，执行始终由你确认。", copilotCta: "开始智能问答",
    growthLead: "增长负责人", accountOptions: "账户选项", online: "服务在线", openCopilot: "打开 AI 智能问答",
    createCampaign: "新建活动", language: "界面语言", chinese: "中文", english: "English",
    overviewKicker: "收入情报", overviewTitle1: "今天，先做", overviewTitle2: "这件事。",
    overviewSummary: "从 Shopify 聚合数据中识别优先级，生成可审批的实验方案，并跟踪真实增量。",
    shopifySynced: "Shopify 已同步", waitingData: "等待真实数据",
    shopifyOrders: "Shopify 订单", shopifyCustomers: "Shopify 客户", shopifyProducts: "Shopify 产品", inventoryItems: "库存项",
    authorizedCount: "授权店铺聚合数量", inventoryLimit: "最多读取 250 个库存项", firstBaseline: "首次同步基线",
    noIdentity: "不保存客户身份信息", readOnlySync: "只读汇总同步", connectBaseline: "连接店铺后生成基线",
    netSales: "净销售额", noVerifiedData: "尚无可验证的真实数据", noDemoFill: "不使用演示数据填充",
    realOpportunities: "真实机会", modelingGate: "尚未达到建模门槛", connectData: "待完成数据连接",
    measuredUplift: "已测量增量", noRealExperiment: "尚未运行真实实验", noRevenuePromise: "不做收入承诺",
    syntheticQueue: "合成演示机会队列", viewAllDemo: "查看全部演示机会", opportunity: "机会", owner: "负责人",
    estimatedOpportunity: "预计机会", compositeScore: "综合分", status: "状态", demoLabel: "合成演示",
    opportunitiesTitle: "机会中心", opportunitiesDescription: "按证据强度、收入潜力与可执行性排序；真实信号与合成演示始终分开。",
    campaignsTitle: "活动工作台", campaignsDescription: "将真实机会转换为可审核的执行包；任何客户触达仍由商家在自己的渠道平台最终确认。",
    learningTitle: "实验学习", learningDescription: "优先展示真实执行的商家汇总结果；演示数据始终独立标记。",
    dataTitle: "数据连接", dataDescription: "跨境商家的真实价值来自可授权的数据连接，而不是替代商家保存或猜测业务数据。", requestConnector: "申请连接器",
    introStatus: "Shopify 数据连接就绪", introKicker: "收入决策操作系统", introTitle1: "从数据异常，", introTitle2: "到可验证增长。",
    introSummary: "发现收入机会，设计可控实验，并用真实结果验证每一次增长决策。", enterWorkspace: "进入 RevenueOps",
    humanApproval: "所有行动需人工确认", separatedData: "演示数据与真实数据明确隔离",
  },
  en: {
    skip: "Skip to main content", closeNav: "Close navigation", openNav: "Open navigation", workspace: "Workspace",
    overview: "Overview", opportunities: "Opportunities", campaigns: "Campaigns", learning: "Learning", data: "Data connections",
    overviewMeta: "Revenue overview", opportunitiesMeta: "Prioritized actions", campaignsMeta: "Campaign workspace", learningMeta: "Experiment results", dataMeta: "Authorized sources",
    copilotTitle: "AI Co-pilot", copilotBody: "Evidence-backed guidance. You approve every action.", copilotCta: "Ask the co-pilot",
    growthLead: "Growth lead", accountOptions: "Account options", online: "Service online", openCopilot: "Open AI co-pilot",
    createCampaign: "Create campaign", language: "Interface language", chinese: "中文", english: "English",
    overviewKicker: "Revenue intelligence", overviewTitle1: "Start today with", overviewTitle2: "the highest-impact action.",
    overviewSummary: "Prioritize opportunities from aggregated Shopify data, build approval-ready experiments, and track verified incremental impact.",
    shopifySynced: "Shopify synced", waitingData: "Waiting for real data",
    shopifyOrders: "Shopify orders", shopifyCustomers: "Shopify customers", shopifyProducts: "Shopify products", inventoryItems: "Inventory items",
    authorizedCount: "Authorized store aggregate", inventoryLimit: "Up to 250 inventory items", firstBaseline: "Initial sync baseline",
    noIdentity: "Customer identity is not stored", readOnlySync: "Read-only aggregate sync", connectBaseline: "Connect a store to create a baseline",
    netSales: "Net sales", noVerifiedData: "No verified real data yet", noDemoFill: "Demo data is never used as a substitute",
    realOpportunities: "Real opportunities", modelingGate: "Modeling threshold not reached", connectData: "Complete a data connection",
    measuredUplift: "Measured uplift", noRealExperiment: "No real experiment completed", noRevenuePromise: "No revenue claims without evidence",
    syntheticQueue: "Synthetic opportunity queue", viewAllDemo: "View all demo opportunities", opportunity: "Opportunity", owner: "Owner",
    estimatedOpportunity: "Estimated impact", compositeScore: "Score", status: "Status", demoLabel: "Synthetic demo",
    opportunitiesTitle: "Opportunity center", opportunitiesDescription: "Prioritized by evidence strength, revenue potential, and executability. Real signals and synthetic demos always stay separate.",
    campaignsTitle: "Campaign workspace", campaignsDescription: "Turn real opportunities into reviewable execution packages. Merchants retain final approval in their own channel platform.",
    learningTitle: "Experiment learning", learningDescription: "Real merchant aggregate outcomes come first. Demo results remain clearly labeled and separate.",
    dataTitle: "Data connections", dataDescription: "Cross-border value begins with merchant-authorized data—not stored substitutes or guessed business data.", requestConnector: "Request connector",
    introStatus: "Shopify data connection ready", introKicker: "Revenue decision operating system", introTitle1: "From data signals", introTitle2: "to measurable growth.",
    introSummary: "Find revenue opportunities, design controlled experiments, and validate every growth decision with real outcomes.", enterWorkspace: "Enter RevenueOps",
    humanApproval: "Every action requires human approval", separatedData: "Demo and real data remain clearly separated",
  },
} as const;

export type MessageKey = keyof typeof messages["zh-CN"];
type I18nValue = { locale: Locale; setLocale: (locale: Locale) => void; t: (key: MessageKey) => string };
const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>("zh-CN");

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "zh-CN") {
      document.documentElement.lang = saved;
      Promise.resolve().then(() => setLocale(saved));
    }
  }, []);

  function chooseLocale(next: Locale) {
    document.documentElement.lang = next;
    localStorage.setItem(STORAGE_KEY, next);
    setLocale(next);
  }

  return <I18nContext.Provider value={{ locale, setLocale: chooseLocale, t: (key) => messages[locale][key] }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
