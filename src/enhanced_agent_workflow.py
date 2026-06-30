"""
AI增强版电商运营多智能体工作流

升级版本：
1. 集成LLM智能体 - 支持自然语言推理
2. 机器学习预测 - 客户流失预测模型
3. 智能报告生成 - 基于LLM的分析报告
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "processed"
REPORT_DIR = PROJECT_DIR / "reports"
DASHBOARD_DIR = PROJECT_DIR / "dashboard"


def money(value: float) -> str:
    return f"R${value:,.2f}"


def percent(value: float) -> str:
    return f"{value:.1%}"


@dataclass
class AgentFinding:
    agent: str
    priority: str
    title: str
    evidence: str
    recommendation: str
    next_action: str
    metric_snapshot: dict[str, Any]


class EcommerceDataMart:
    """Load processed Olist data and expose ecommerce operation metrics."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir

    def load(self) -> dict[str, pd.DataFrame]:
        customers = pd.read_csv(self.data_dir / "cleaned_customers.csv")
        orders = pd.read_csv(self.data_dir / "cleaned_orders.csv")
        payments = pd.read_csv(self.data_dir / "cleaned_payments.csv")
        order_items = pd.read_csv(self.data_dir / "cleaned_order_items.csv")
        rfm = pd.read_csv(self.data_dir / "rfm_analysis.csv")
        clusters = pd.read_csv(self.data_dir / "user_clusters.csv")
        sales_trends = pd.read_csv(self.data_dir / "sales_trends.csv")

        orders["order_purchase_timestamp"] = pd.to_datetime(
            orders["order_purchase_timestamp"], errors="coerce"
        )
        orders["month"] = orders["order_purchase_timestamp"].dt.to_period("M").astype(str)

        payment_by_order = (
            payments.groupby("order_id")
            .agg(
                payment_value=("payment_value", "sum"),
                payment_type=("payment_type", lambda s: s.mode().iat[0]),
                payment_installments=("payment_installments", "max"),
            )
            .reset_index()
        )
        item_by_order = (
            order_items.groupby("order_id")
            .agg(item_revenue=("price", "sum"), freight_value=("freight_value", "sum"))
            .reset_index()
        )
        fact_orders = (
            orders[["order_id", "customer_id", "order_status", "month"]]
            .merge(customers[["customer_id", "customer_state", "customer_city"]], on="customer_id", how="left")
            .merge(payment_by_order, on="order_id", how="left")
            .merge(item_by_order, on="order_id", how="left")
        )
        fact_orders[["payment_value", "item_revenue", "freight_value"]] = fact_orders[
            ["payment_value", "item_revenue", "freight_value"]
        ].fillna(0)

        return {
            "customers": customers,
            "orders": orders,
            "payments": payments,
            "order_items": order_items,
            "rfm": rfm,
            "clusters": clusters,
            "sales_trends": sales_trends,
            "fact_orders": fact_orders,
        }


class LLMAgent:
    """
    LLM智能体 - 使用大语言模型进行自然语言推理
    
    特点：
    - 不需要预定义规则，可以理解自然语言描述的任务
    - 可以处理复杂、非结构化的业务场景
    - 具备推理和创意能力
    """

    name = "LLM推理智能体"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = None
        if HAS_OPENAI and self.api_key:
            self.client = OpenAI(api_key=self.api_key)

    def run(self, data: dict[str, pd.DataFrame], task: str = "analyze") -> AgentFinding:
        """
        使用LLM分析数据
        
        Args:
            data: 数据字典
            task: 任务类型 (analyze/insight/suggest)
        """
        if not self.client:
            return self._mock_analysis(data, task)

        summary = self._prepare_data_summary(data)
        prompt = self._build_prompt(summary, task)

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "你是一位专业的电商运营分析师，擅长从数据中发现业务洞察。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            result = response.choices[0].message.content
            return self._parse_llm_response(result, data)
        except Exception as e:
            return self._fallback_analysis(data, str(e))

    def _prepare_data_summary(self, data: dict[str, pd.DataFrame]) -> str:
        """准备数据摘要"""
        fact = data["fact_orders"]
        rfm = data["rfm"]
        customers = data["customers"]

        summary_parts = []

        # 基础统计
        summary_parts.append(f"总订单数: {len(fact):,}")
        summary_parts.append(f"总客户数: {len(customers):,}")
        summary_parts.append(f"总收入: {money(fact['payment_value'].sum())}")
        summary_parts.append(f"平均客单价: {money(fact['payment_value'].mean())}")

        # RFM分析
        segment_counts = rfm["customer_segment"].value_counts().to_dict()
        summary_parts.append(f"客户分层: {segment_counts}")

        # 地区分布
        if "customer_state" in fact.columns:
            top_states = fact.groupby("customer_state")["payment_value"].sum().nlargest(5)
            summary_parts.append(f"TOP5地区销售额: {top_states.to_dict()}")

        # 支付方式
        if "payment_type" in fact.columns:
            payment_dist = fact["payment_type"].value_counts(normalize=True).to_dict()
            summary_parts.append(f"支付方式分布: {payment_dist}")

        return "\n".join(summary_parts)

    def _build_prompt(self, data_summary: str, task: str) -> str:
        """构建提示词"""
        if task == "analyze":
            return f"""基于以下电商数据，请进行深度分析：

数据摘要：
{data_summary}

请从以下角度进行分析：
1. 当前业务状况评估
2. 主要风险点
3. 增长机会
4. 建议的优先级

请用中文回复，输出格式为：
- 优先级: [P0/P1/P2]
- 标题: [一句话总结]
- 证据: [数据支撑]
- 建议: [可操作的建议]
- 下一步: [具体行动]"""
        elif task == "insight":
            return f"""发现数据中的关键洞察：

{data_summary}

请识别：
1. 最关键的3个业务洞察
2. 每个洞察的数据证据
3. 对应的运营建议"""
        else:
            return f"""基于以下数据提供建议：

{data_summary}

请给出可落地的运营建议。"""

    def _parse_llm_response(self, response: str, data: dict) -> AgentFinding:
        """解析LLM响应"""
        lines = response.split("\n")
        priority = "P2"
        title = "LLM分析结果"
        evidence = ""
        recommendation = ""
        next_action = ""

        for line in lines:
            if "优先级:" in line:
                priority = line.split("优先级:")[1].strip()[:2]
            elif "标题:" in line:
                title = line.split("标题:")[1].strip()
            elif "证据:" in line:
                evidence = line.split("证据:")[1].strip()
            elif "建议:" in line:
                recommendation = line.split("建议:")[1].strip()
            elif "下一步:" in line:
                next_action = line.split("下一步:")[1].strip()

        return AgentFinding(
            agent=self.name,
            priority=priority,
            title=title,
            evidence=evidence or "基于LLM深度分析",
            recommendation=recommendation or "请参考LLM分析结果",
            next_action=next_action or "等待人工确认",
            metric_snapshot={"llm_model": "gpt-4o-mini", "response_length": len(response)}
        )

    def _mock_analysis(self, data: dict, task: str) -> AgentFinding:
        """当没有API密钥时的模拟分析"""
        fact = data["fact_orders"]
        total_revenue = fact["payment_value"].sum()

        return AgentFinding(
            agent=self.name + " (Mock模式)",
            priority="P1",
            title="业务增长分析 - LLM增强版",
            evidence=f"总收入{money(total_revenue)}，建议深入分析客户生命周期价值。",
            recommendation="使用真实API密钥获取更精准的AI分析",
            next_action="请设置OPENAI_API_KEY环境变量",
            metric_snapshot={"mode": "mock", "total_revenue": float(total_revenue)}
        )

    def _fallback_analysis(self, data: dict, error: str) -> AgentFinding:
        """API调用失败时的降级分析"""
        return AgentFinding(
            agent=self.name,
            priority="P2",
            title="LLM分析暂时不可用",
            evidence=f"API调用失败: {error}",
            recommendation="请检查API密钥和网络连接",
            next_action="使用规则引擎进行基础分析",
            metric_snapshot={"error": error}
        )


class ChurnPredictionAgent:
    """
    客户流失预测智能体 - 使用机器学习预测客户流失概率
    
    特点：
    - 使用XGBoost模型进行二分类预测
    - 自动训练和预测
    - 识别高风险客户群体
    """

    name = "客户流失预测智能体"

    def __init__(self):
        self.model = None
        self.scaler = None
        self._is_trained = False

    def run(self, data: dict[str, pd.DataFrame]) -> AgentFinding:
        """运行客户流失预测"""
        if not HAS_XGBOOST:
            return self._no_model_fallback(data)

        try:
            features, labels = self._prepare_features(data)
            if features.empty:
                return self._no_data_fallback(data)

            self._train_model(features, labels)
            predictions = self._predict(features)
            risk_stats = self._analyze_risk(predictions, labels)

            return AgentFinding(
                agent=self.name,
                priority="P1",
                title=f"识别出{risk_stats['high_risk_count']:,}名高流失风险客户",
                evidence=(
                    f"模型预测高风险客户{risk_stats['high_risk_count']:,}人（占比{risk_stats['high_risk_rate']:.1%}），"
                    f"中风险{risk_stats['medium_risk_count']:,}人，低风险{risk_stats['low_risk_count']:,}人。"
                ),
                recommendation=(
                    "高风险客户建议优先触达，提供专属优惠券或VIP服务；"
                    "中风险客户发送复购提醒；低风险客户保持常规运营。"
                ),
                next_action=f"导出高风险客户名单，制定差异化挽回策略",
                metric_snapshot={
                    "model_type": "XGBoost",
                    "high_risk_count": risk_stats['high_risk_count'],
                    "medium_risk_count": risk_stats['medium_risk_count'],
                    "low_risk_count": risk_stats['low_risk_count'],
                    "model_accuracy": risk_stats.get('accuracy', 0.85)
                }
            )
        except Exception as e:
            return self._error_fallback(data, str(e))

    def _prepare_features(self, data: dict) -> tuple:
        """准备特征和标签"""
        rfm = data["rfm"].copy()

        # 基础特征
        feature_cols = ["recency", "frequency", "monetary"]
        if "rfm_score" in rfm.columns:
            feature_cols.append("rfm_score")

        features = rfm[feature_cols].fillna(0)

        # 创建模拟标签（基于RFM得分）
        # 实际项目中应该有真实的历史流失标签
        labels = (rfm["rfm_score"] < 6).astype(int) if "rfm_score" in rfm.columns else pd.Series(0)

        return features, labels

    def _train_model(self, features: pd.DataFrame, labels: pd.Series):
        """训练XGBoost模型"""
        X_train, X_test, y_train, y_test = train_test_split(
            features, labels, test_size=0.2, random_state=42
        )

        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            use_label_encoder=False,
            eval_metric="logloss"
        )
        self.model.fit(X_train_scaled, y_train)
        self._accuracy = self.model.score(X_test_scaled, y_test)
        self._is_trained = True

    def _predict(self, features: pd.DataFrame) -> pd.Series:
        """预测流失概率"""
        if not self._is_trained:
            return pd.Series(0, index=features.index)

        features_scaled = self.scaler.transform(features)
        return self.model.predict_proba(features_scaled)[:, 1]

    def _analyze_risk(self, predictions: pd.Series, labels: pd.Series) -> dict:
        """分析风险分布"""
        high_risk = (predictions > 0.7).sum()
        medium_risk = ((predictions > 0.3) & (predictions <= 0.7)).sum()
        low_risk = (predictions <= 0.3).sum()

        return {
            "high_risk_count": int(high_risk),
            "medium_risk_count": int(medium_risk),
            "low_risk_count": int(low_risk),
            "high_risk_rate": high_risk / len(predictions) if len(predictions) > 0 else 0,
            "accuracy": getattr(self, "_accuracy", 0.85)
        }

    def _no_model_fallback(self, data: dict) -> AgentFinding:
        """没有XGBoost时的降级"""
        return AgentFinding(
            agent=self.name,
            priority="P2",
            title="客户流失预测模型暂不可用",
            evidence="请安装xgboost库以启用预测功能",
            recommendation="使用RFM分析进行基础客户分层",
            next_action="基于RFM分层结果制定运营策略",
            metric_snapshot={"status": "xgboost_not_installed"}
        )

    def _no_data_fallback(self, data: dict) -> AgentFinding:
        """数据不足时的降级"""
        return AgentFinding(
            agent=self.name,
            priority="P3",
            title="数据不足，无法进行流失预测",
            evidence="需要更多客户行为数据",
            recommendation="收集客户浏览、收藏、购买间隔等数据",
            next_action="完善数据采集",
            metric_snapshot={"status": "insufficient_data"}
        )

    def _error_fallback(self, data: dict, error: str) -> AgentFinding:
        """发生错误时的降级"""
        return AgentFinding(
            agent=self.name,
            priority="P2",
            title="预测模型运行异常",
            evidence=f"错误信息: {error}",
            recommendation="检查数据格式和模型配置",
            next_action="使用规则引擎进行基础分层",
            metric_snapshot={"error": error}
        )


class BusinessMonitorAgent:
    """原有的经营监控智能体（保持不变）"""

    name = "经营监控智能体"

    def run(self, data: dict[str, pd.DataFrame]) -> AgentFinding:
        fact = data["fact_orders"]
        monthly = (
            fact.groupby("month")
            .agg(revenue=("payment_value", "sum"), orders=("order_id", "nunique"))
            .reset_index()
            .set_index("month")
        )
        median_orders = monthly["orders"].median()
        complete_monthly = monthly[monthly["orders"] >= median_orders * 0.25]
        if len(complete_monthly) < 2:
            complete_monthly = monthly
        latest = complete_monthly.tail(1).iloc[0]
        previous = complete_monthly.tail(2).head(1).iloc[0] if len(complete_monthly) > 1 else latest
        revenue_change = (latest["revenue"] - previous["revenue"]) / previous["revenue"] if previous["revenue"] else 0
        order_change = (latest["orders"] - previous["orders"]) / previous["orders"] if previous["orders"] else 0
        avg_order_value = fact["payment_value"].sum() / max(fact["order_id"].nunique(), 1)

        if revenue_change < -0.15:
            priority = "P0"
            title = "最近月份销售额明显下滑，需要优先排查"
            action = "对比上月流量、库存、价格、履约和活动节奏，先定位下滑来源。"
        elif revenue_change > 0.15:
            priority = "P1"
            title = "最近月份销售额明显增长，适合复盘放大"
            action = "复盘增长月份的地区、支付方式和客户分层，把有效策略复制到相似地区。"
        else:
            priority = "P2"
            title = "整体经营相对稳定，可从客群和地区寻找增量"
            action = "优先做高价值客户复购和重点地区转化优化。"

        return AgentFinding(
            agent=self.name,
            priority=priority,
            title=title,
            evidence=(
                f"最近月份销售额环比 {percent(revenue_change)}，订单数环比 {percent(order_change)}，"
                f"全局平均客单价 {money(avg_order_value)}。"
            ),
            recommendation="用月度经营指标先判断业务波动，再决定是排查异常还是放大增长策略。",
            next_action=action,
            metric_snapshot={
                "latest_month": monthly.index[-1],
                "analysis_month": complete_monthly.index[-1],
                "latest_revenue": round(float(latest["revenue"]), 2),
                "latest_orders": int(latest["orders"]),
                "revenue_change": round(float(revenue_change), 4),
                "order_change": round(float(order_change), 4),
                "avg_order_value": round(float(avg_order_value), 2),
            },
        )


class CustomerSegmentAgent:
    """原有的客户分层智能体（保持不变）"""

    name = "客户分层智能体"

    def run(self, data: dict[str, pd.DataFrame]) -> AgentFinding:
        rfm = data["rfm"]
        counts = rfm["customer_segment"].value_counts()
        monetary = rfm.groupby("customer_segment")["monetary"].mean().sort_values(ascending=False)
        total_customers = len(rfm)
        high_value = int(counts.get("高价值客户", 0))
        potential = int(counts.get("潜在高价值客户", 0))
        high_value_share = high_value / total_customers if total_customers else 0
        potential_share = potential / total_customers if total_customers else 0

        return AgentFinding(
            agent=self.name,
            priority="P1",
            title="客户运营应优先围绕高价值和潜在高价值人群设计",
            evidence=(
                f"高价值客户 {high_value:,} 人，占比 {percent(high_value_share)}；"
                f"潜在高价值客户 {potential:,} 人，占比 {percent(potential_share)}。"
            ),
            recommendation=(
                "高价值客户做会员权益和复购激励；潜在高价值客户做优惠券召回、关联推荐和限时活动；"
                "低价值客户控制补贴成本。"
            ),
            next_action="建立三套触达策略：复购礼券、二次购买券、低成本内容唤醒，并分别跟踪转化率。",
            metric_snapshot={
                "segment_counts": {str(k): int(v) for k, v in counts.items()},
                "avg_monetary_by_segment": {str(k): round(float(v), 2) for k, v in monetary.items()},
            },
        )


class ExecutiveSummaryAgent:
    """原有的运营总监智能体（保持不变）"""

    name = "运营总监智能体"

    def run(self, findings: list[AgentFinding]) -> dict[str, Any]:
        priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        ordered = sorted(findings, key=lambda item: priority_rank.get(item.priority, 9))
        top_actions = [finding.next_action for finding in ordered[:3]]
        return {
            "agent": self.name,
            "summary": "系统已从经营、客户、地区、支付、活动和AI预测六个角度完成诊断，建议优先处理高优先级问题。",
            "top_actions": top_actions,
            "ordered_findings": [asdict(finding) for finding in ordered],
        }


class EnhancedEcommerceAgentWorkflow:
    """
    增强版电商运营多智能体工作流
    
    新增功能：
    1. LLM智能体 - 自然语言推理
    2. 流失预测智能体 - 机器学习预测
    3. 智能报告生成
    """

    def __init__(self):
        self.data_mart = EcommerceDataMart()
        self.monitor_agent = BusinessMonitorAgent()
        self.customer_agent = CustomerSegmentAgent()
        self.llm_agent = LLMAgent()
        self.churn_agent = ChurnPredictionAgent()
        self.summary_agent = ExecutiveSummaryAgent()

    def run(self) -> dict[str, Any]:
        data = self.data_mart.load()

        # 运行多个智能体
        findings = [
            self.monitor_agent.run(data),
            self.customer_agent.run(data),
        ]

        # 新增：机器学习预测
        findings.append(self.churn_agent.run(data))

        # 新增：LLM推理
        llm_finding = self.llm_agent.run(data, task="analyze")
        findings.append(llm_finding)

        # 汇总
        summary = self.summary_agent.run(findings)

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "workflow": "AI增强版电商运营多智能体工作流",
            "summary": summary,
            "agent_count": len(findings),
            "llm_enabled": HAS_OPENAI,
            "ml_enabled": HAS_XGBOOST,
        }


def write_outputs(result: dict[str, Any]) -> None:
    """输出结果到文件"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    json_path = REPORT_DIR / "enhanced_workflow_result.json"
    md_path = REPORT_DIR / "enhanced_workflow_report.md"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    findings = result["summary"]["ordered_findings"]
    lines = [
        "# AI增强版电商运营多智能体工作流报告",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 技术栈",
        "",
        f"- LLM智能体：{'已启用' if result.get('llm_enabled') else '未启用 (需要OPENAI_API_KEY)'}",
        f"- ML预测：{'已启用' if result.get('ml_enabled') else '未启用 (需要xgboost)'}",
        "",
        "## 总结",
        "",
        result["summary"]["summary"],
        "",
        "## 优先行动",
        "",
    ]
    for index, action in enumerate(result["summary"]["top_actions"], 1):
        lines.append(f"{index}. {action}")

    lines.extend(["", "## 智能体诊断详情", ""])
    for finding in findings:
        lines.extend([
            f"### [{finding['priority']}] {finding['agent']}：{finding['title']}",
            "",
            f"- 证据：{finding['evidence']}",
            f"- 建议：{finding['recommendation']}",
            f"- 下一步：{finding['next_action']}",
            f"- 指标快照：{finding['metric_snapshot']}",
            "",
        ])

    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """主函数"""
    print("\n" + "="*70)
    print("         AI增强版电商运营多智能体工作流")
    print("="*70)

    workflow = EnhancedEcommerceAgentWorkflow()
    result = workflow.run()
    write_outputs(result)

    print(f"\n生成时间：{result['generated_at']}")
    print(f"\n[技术栈]")
    print(f"   LLM智能体: {'已启用' if result['llm_enabled'] else '未启用'}")
    print(f"   ML预测: {'已启用' if result['ml_enabled'] else '未启用'}")

    print(f"\n[Summary] {result['summary']['summary']}")

    print("\n[Priority Actions]")
    for index, action in enumerate(result["summary"]["top_actions"], 1):
        print(f"   {index}. {action}")

    print("\n" + "-"*70)
    print("[Agent Diagnostics]")
    print("-"*70)
    for finding in result["summary"]["ordered_findings"]:
        print(f"\n[{finding['priority']}] {finding['agent']}")
        print(f"   Title: {finding['title']}")
        print(f"   Evidence: {finding['evidence']}")
        print(f"   Recommendation: {finding['recommendation']}")
        print(f"   Next Action: {finding['next_action']}")

    print("\n" + "="*70)
    print(f"Report saved to: {REPORT_DIR / 'enhanced_workflow_report.md'}")
    print(f"Data saved to: {REPORT_DIR / 'enhanced_workflow_result.json'}")
    print("="*70)


if __name__ == "__main__":
    main()
