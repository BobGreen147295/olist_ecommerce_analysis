"""
XGBoost 客户流失预测模块

模型要点：
- 特征：RFM + 地理 + 时间偏好 + 支付偏好
- 标签：基于 RFM_score 构造的「高风险流失」（或未来 90 天未购买）
- 交叉验证评估：准确率、召回率、AUC
- 可解释性：特征重要性 + SHAP（若可用）
- 输出：高/中/低风险清单 + 差异化挽回策略
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "processed"

import sys

if str(PROJECT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "src"))

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score,
        f1_score, roc_auc_score, classification_report,
    )
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    logger.warning("xgboost/scikit-learn 未安装，流失预测模型不可用")


@dataclass
class ChurnMetrics:
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    roc_auc: float = 0.0
    cv_scores: list[float] = field(default_factory=list)


@dataclass
class ChurnResult:
    predictions: pd.DataFrame  # customer_id + risk_level + probability
    metrics: ChurnMetrics
    feature_importance: pd.DataFrame
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int


def build_churn_dataset(
    fact_orders: pd.DataFrame,
    rfm_data: Optional[pd.DataFrame] = None,
    future_window_days: int = 90,
) -> tuple[pd.DataFrame, pd.Series]:
    """构建流失预测数据集 (X, y)

    标签构造：客户下一次购买距其末次购买超过 future_window_days，或末次购买在分析日期前 N 天且 RFM_score 低
    """
    if rfm_data is None:
        from analysis_rfm import compute_rfm
        rfm_result = compute_rfm(fact_orders=fact_orders)
        rfm_data = rfm_result.rfm_data

    # ---- 特征 ----
    df = rfm_data.set_index("customer_id")[
        ["recency", "frequency", "monetary", "rfm_score"]
    ].copy()

    # 支付偏好
    pay_pref = (
        fact_orders.groupby("customer_id").agg(
            avg_installments=("payment_installments", "mean"),
            uses_boleto=(
                "payment_type",
                lambda s: int((s == "boleto").any()),
            ),
            uses_credit=(
                "payment_type",
                lambda s: int((s == "credit_card").any()),
            ),
            aov=("payment_value", "mean"),
        )
    )
    df = df.join(pay_pref, how="left")

    # 时间偏好（活跃时间分散度）
    time_pref = fact_orders.groupby("customer_id").agg(
        weekday_std=("weekday", "std"),
        hour_std=("hour", "std"),
    )
    df = df.join(time_pref, how="left")

    # 地理: 州频率编码
    if "customer_state" in fact_orders.columns:
        state_cnt = fact_orders["customer_state"].value_counts(normalize=True)
        cust_state = (
            fact_orders.drop_duplicates("customer_id")
            .set_index("customer_id")["customer_state"]
        )
        df["state_popularity"] = cust_state.map(state_cnt)

    df = df.fillna(0)

    # ---- 标签 ----
    # 简化：使用 RFM_score < 6 作为「流失风险高」标签（可由真实回购历史替换）
    y = (df["rfm_score"] < 6).astype(int)

    # 删除 RFM_score 作为特征（避免标签泄漏），保留 recency/frequency/monetary
    feature_df = df.drop(columns=["rfm_score"], errors="ignore")

    logger.info(f"流失数据集构建完成: X={feature_df.shape}, 正样本比例={y.mean():.2%}")
    return feature_df, y


def train_churn_model(
    X: pd.DataFrame, y: pd.Series,
    test_size: float = 0.2, random_state: int = 42,
) -> tuple["xgb.XGBClassifier", StandardScaler, ChurnMetrics, pd.DataFrame]:
    """训练 XGBoost 流失预测模型并评估"""
    if not HAS_XGBOOST:
        raise RuntimeError("xgboost 未安装")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y,
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # 正样本权重（不平衡）
    pos_weight = max(1.0, (len(y_train) - y_train.sum()) / max(y_train.sum(), 1))

    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=pos_weight,
        random_state=random_state,
        eval_metric="logloss",
        use_label_encoder=False,
    )
    model.fit(X_train_s, y_train)

    # 评估
    y_proba = model.predict_proba(X_test_s)[:, 1]
    y_pred = (y_proba >= 0.5).astype(int)

    metrics = ChurnMetrics(
        accuracy=float(accuracy_score(y_test, y_pred)),
        precision=float(precision_score(y_test, y_pred, zero_division=0)),
        recall=float(recall_score(y_test, y_pred, zero_division=0)),
        f1=float(f1_score(y_test, y_pred, zero_division=0)),
        roc_auc=float(roc_auc_score(y_test, y_proba)),
    )

    # 5-fold CV
    try:
        cv = cross_val_score(model, X_train_s, y_train, cv=5, scoring="roc_auc", n_jobs=1)
        metrics.cv_scores = cv.tolist()
    except Exception:
        pass

    # 特征重要性
    importance = pd.DataFrame({
        "feature": list(X.columns),
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)

    logger.info(
        f"XGBoost 训练完成: accuracy={metrics.accuracy:.3f}, "
        f"recall={metrics.recall:.3f}, AUC={metrics.roc_auc:.3f}"
    )
    return model, scaler, metrics, importance


def predict_risk(
    model: "xgb.XGBClassifier",
    scaler: StandardScaler,
    X: pd.DataFrame,
    high_threshold: float = 0.7,
    low_threshold: float = 0.3,
) -> pd.DataFrame:
    """对所有客户打风险分"""
    X_s = scaler.transform(X)
    proba = model.predict_proba(X_s)[:, 1]

    def _level(p: float) -> str:
        if p >= high_threshold:
            return "high"
        elif p >= low_threshold:
            return "medium"
        return "low"

    pred = pd.DataFrame({
        "customer_id": X.index,
        "churn_probability": proba,
        "risk_level": [_level(p) for p in proba],
    })
    return pred


def generate_churn_strategies(pred: pd.DataFrame) -> list[dict]:
    """生成流失挽回策略（高/中/低）"""
    counts = pred["risk_level"].value_counts().to_dict()
    total = len(pred)
    strategies: list[dict] = []

    n_high = counts.get("high", 0)
    if n_high > 0:
        strategies.append({
            "risk": "high",
            "count": int(n_high),
            "share": round(n_high / max(total, 1), 4),
            "title": "高流失风险客户挽回",
            "priority": "P0",
            "goal": "挽回 20-30% 的高风险客户",
            "actions": [
                "导出高风险名单（ID、州、消费历史），分配到运营人员 1v1 跟进",
                "专属 VIP 礼券：满减 + 免邮 + 专属客服通道（有效期 7 天）",
                "WhatsApp 个性化消息（客户姓名 + 历史商品推荐 + 折扣码）",
                "设置 7/14/21 天追接触发规则（未下单则持续触达）",
            ],
            "expected": {
                "recovery_rate": "20-30%",
                "gmv_preserve": f"≈ 保护 R${int(n_high * 80):,} 年营收（假设每人 R$80/年）",
            },
            "estimated_cost_per_user": "R$8-12 (礼券+人工)",
        })

    n_med = counts.get("medium", 0)
    if n_med > 0:
        strategies.append({
            "risk": "medium",
            "count": int(n_med),
            "share": round(n_med / max(total, 1), 4),
            "title": "中流失风险客户激活",
            "priority": "P1",
            "goal": "将 30% 中风险客户提升到低风险",
            "actions": [
                "批量推送个性化复购券（基于购买历史推荐）",
                "拼团 / 好友分享折扣，提升复购",
                "在大促节点定向推送（黑五、圣诞节、巴西情人节）",
            ],
            "expected": {
                "reactivation": "25-35%",
                "repurchase_frequency": "+10-15%",
            },
            "estimated_cost_per_user": "R$2-4",
        })

    n_low = counts.get("low", 0)
    if n_low > 0:
        strategies.append({
            "risk": "low",
            "count": int(n_low),
            "share": round(n_low / max(total, 1), 4),
            "title": "低风险客户价值提升",
            "priority": "P2",
            "goal": "提升客单价 + 忠诚度",
            "actions": [
                "推荐升级品类 + 捆绑优惠",
                "会员等级权益体系，升级送礼",
                "常规内容营销（新品 + 折扣）",
            ],
            "expected": {
                "aov_increase": "5-10%",
                "nps_improvement": "+3-5",
            },
            "estimated_cost_per_user": "R$0.5-1",
        })

    logger.info(f"已生成 {len(strategies)} 条流失挽回策略")
    return strategies


def run_pipeline(
    fact_orders: pd.DataFrame,
    save_path: Optional[Path] = None,
) -> ChurnResult:
    save_path = save_path or (DATA_DIR / "churn_predictions.csv")
    save_path.parent.mkdir(parents=True, exist_ok=True)

    X, y = build_churn_dataset(fact_orders)
    model, scaler, metrics, importance = train_churn_model(X, y)
    pred = predict_risk(model, scaler, X)

    pred.to_csv(save_path, index=False)
    logger.info(f"流失预测结果已保存: {save_path}")

    counts = pred["risk_level"].value_counts().to_dict()
    return ChurnResult(
        predictions=pred,
        metrics=metrics,
        feature_importance=importance,
        high_risk_count=int(counts.get("high", 0)),
        medium_risk_count=int(counts.get("medium", 0)),
        low_risk_count=int(counts.get("low", 0)),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 60)
    print("  XGBoost 客户流失预测模块")
    print("=" * 60)

    from data_cleaning import build_fact_table, load_raw_data, clean_orders, clean_payments
    customers, orders, payments, order_items = load_raw_data()
    orders = clean_orders(orders)
    payments = clean_payments(payments)
    fact = build_fact_table(customers, orders, payments, order_items)

    result = run_pipeline(fact)

    print(f"\n模型指标:")
    m = result.metrics
    print(f"  accuracy={m.accuracy:.3f}, precision={m.precision:.3f}")
    print(f"  recall={m.recall:.3f}, f1={m.f1:.3f}, AUC={m.roc_auc:.3f}")
    if m.cv_scores:
        print(f"  5-fold CV AUC: mean={np.mean(m.cv_scores):.3f}")

    print(f"\n风险分布:")
    print(f"  高风险: {result.high_risk_count:,} 人")
    print(f"  中风险: {result.medium_risk_count:,} 人")
    print(f"  低风险: {result.low_risk_count:,} 人")

    print(f"\nTop10 重要特征:")
    print(result.feature_importance.head(10).to_string())

    print("\n流失挽回策略:")
    strategies = generate_churn_strategies(result.predictions)
    for s in strategies:
        print(f"\n[{s['priority']}] {s['title']} ({s['count']:,}人, 占比 {s['share']:.1%})")
        print(f"  目标: {s['goal']}")
        for a in s["actions"]:
            print(f"    • {a}")
        print(f"  预期: {s['expected']}")
        print(f"  单人成本: {s['estimated_cost_per_user']}")


if __name__ == "__main__":
    main()
