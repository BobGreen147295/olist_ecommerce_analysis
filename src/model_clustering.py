"""
KMeans 客户聚类模型模块

输入: 客户特征（消费频次、金额、时间、地理）
输出: 用户分群结果 + 每个群的业务画像 + 差异化运营策略
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "processed"

import sys

if str(PROJECT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "src"))

logger = logging.getLogger(__name__)

try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import silhouette_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("scikit-learn 未安装，KMeans 模型不可用")


@dataclass
class ClusterResult:
    labels: pd.Series
    centers: pd.DataFrame
    profile: pd.DataFrame  # 每个 cluster 的业务画像
    k: int
    silhouette: Optional[float]
    feature_cols: list[str]


def build_features(
    fact_orders: pd.DataFrame,
    rfm_data: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """构建聚类特征：RFM + 地理 + 时间偏好"""
    # RFM 特征
    if rfm_data is None:
        from analysis_rfm import compute_rfm
        rfm_result = compute_rfm(fact_orders=fact_orders)
        rfm_data = rfm_result.rfm_data

    feat = rfm_data[["customer_id", "recency", "frequency", "monetary"]].copy()

    # 地理特征（州 one-hot top N，否则用州收入贡献）
    if "customer_state" in fact_orders.columns:
        state_rev = (
            fact_orders.groupby(["customer_id", "customer_state"])["payment_value"]
            .sum()
            .reset_index()
        )
        # 取每个客户最大贡献州
        state_rev = state_rev.sort_values("payment_value", ascending=False).drop_duplicates("customer_id")
        state_rev = state_rev.rename(columns={"customer_state": "top_state"})
        feat = feat.merge(state_rev[["customer_id", "top_state"]], on="customer_id", how="left")

        # 州编码（高基数用频率编码）
        state_freq = feat["top_state"].value_counts(normalize=True).to_dict()
        feat["state_freq"] = feat["top_state"].map(state_freq).fillna(0)
        feat = feat.drop(columns=["top_state"])

    # 时间偏好：下单 weekday
    if "weekday" in fact_orders.columns and "hour" in fact_orders.columns:
        time_pref = fact_orders.groupby("customer_id").agg(
            pref_weekday=("weekday", lambda s: s.mode().iat[0] if len(s) > 0 else 3),
            pref_hour=("hour", lambda s: s.mode().iat[0] if len(s) > 0 else 15),
        ).reset_index()
        feat = feat.merge(time_pref, on="customer_id", how="left")

    feat = feat.set_index("customer_id").fillna(0)
    logger.info(f"聚类特征构建完成: {feat.shape}")
    return feat


def run_kmeans(
    features: pd.DataFrame,
    n_clusters: int = 3,
    random_state: int = 42,
    max_iter: int = 300,
) -> ClusterResult:
    """运行 KMeans 聚类"""
    if not HAS_SKLEARN:
        raise RuntimeError("scikit-learn 未安装")

    feature_cols = list(features.columns)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features[feature_cols])

    model = KMeans(
        n_clusters=n_clusters,
        random_state=random_state,
        max_iter=max_iter,
        n_init=10,
    )
    labels = pd.Series(model.fit_predict(scaled), index=features.index, name="cluster")

    # 轮廓系数
    try:
        sil = float(silhouette_score(scaled, labels.values, sample_size=10_000, random_state=random_state))
    except Exception:
        sil = None

    # 逆标准化的中心（可读）
    centers = pd.DataFrame(
        scaler.inverse_transform(model.cluster_centers_),
        columns=feature_cols,
    )
    centers.index.name = "cluster"

    # 业务画像
    raw = features.join(labels)
    profile = raw.groupby("cluster").agg(["mean", "count"]).round(2)

    result = ClusterResult(
        labels=labels,
        centers=centers,
        profile=profile,
        k=n_clusters,
        silhouette=sil,
        feature_cols=feature_cols,
    )
    logger.info(
        f"KMeans k={n_clusters} 完成，轮廓系数={sil:.3f}" if sil is not None
        else f"KMeans k={n_clusters} 完成"
    )
    return result


def label_clusters(result: ClusterResult) -> dict[int, str]:
    """基于中心值给聚类打业务标签"""
    centers = result.centers
    labels_map: dict[int, str] = {}
    medians = centers.median()

    for cid, row in centers.iterrows():
        tags = []
        # Recency 低（最近买过）+ Frequency 高 → 活跃
        if row["recency"] < medians["recency"] and row["frequency"] > medians["frequency"]:
            tags.append("活跃用户")
        # Monetary 高 → 高价值
        if row["monetary"] > medians["monetary"]:
            tags.append("高价值")
        # Recency 高 + Frequency 低 → 沉睡
        if row["recency"] > medians["recency"] and row["frequency"] < medians["frequency"]:
            tags.append("沉睡用户")
        # Monetary 低 + Frequency 低 → 价格敏感
        if row["monetary"] < medians["monetary"]:
            tags.append("价格敏感")
        if not tags:
            tags.append("普通用户")
        labels_map[cid] = "·".join(tags)
    return labels_map


def generate_cluster_strategies(
    result: ClusterResult, cluster_labels: dict[int, str],
) -> list[dict]:
    """生成聚类运营策略"""
    raw_profile = result.profile
    recs: list[dict] = []

    for cid in range(result.k):
        label = cluster_labels.get(cid, f"群{cid}")
        # 尝试从 MultiIndex 中取 count
        try:
            if ("frequency", "count") in raw_profile.columns:
                count = int(raw_profile.loc[cid, ("frequency", "count")])
            else:
                count = int(raw_profile.loc[cid, raw_profile.columns[0]])
        except Exception:
            count = 0

        actions = []
        expected = {}
        priority = "P2"

        if "高价值" in label and "活跃" in label:
            priority = "P0"
            actions = [
                "VIP 专属客服 + 1v1 个性化推荐",
                "高端品牌 / 新品优先体验",
                "设置消费里程碑奖励（积分+礼券）",
            ]
            expected = {"repurchase_rate": "+15-25%", "gmv_contribution": "核心 40%+"}
        elif "沉睡用户" in label:
            priority = "P1"
            actions = [
                "沉睡优惠券（满减+免邮），有效期 7 天制造紧迫感",
                "WhatsApp/EDM 个性化召回内容",
                "爆款 / 同类推荐 + 限时折扣",
            ]
            expected = {"awakening_rate": "5-8%", "reactivation_cost": "R$2-5/人"}
        elif "价格敏感" in label:
            priority = "P2"
            actions = [
                "Push 9.9 包邮 + 平台券",
                "拼团 / 秒杀频道定向推送",
                "大促节点重点触达（黑五、双 11 巴版）",
            ]
            expected = {"order_frequency": "+3-5%", "price_promotion_roi": "1:3"}
        else:
            actions = [
                "常规内容+个性化推荐",
                "A/B 测试推送时间和文案",
            ]
            expected = {"conversion": "+2-3%"}

        recs.append({
            "cluster_id": cid,
            "label": label,
            "customer_count": count,
            "title": f"聚类群{cid}: {label} 运营策略",
            "priority": priority,
            "actions": actions,
            "expected": expected,
        })

    logger.info(f"已生成 {len(recs)} 条聚类运营策略")
    return recs


def run_pipeline(
    fact_orders: pd.DataFrame,
    n_clusters: int = 3,
    save_path: Optional[Path] = None,
) -> tuple[ClusterResult, dict[int, str], list[dict]]:
    save_path = save_path or (DATA_DIR / "user_clusters.csv")
    features = build_features(fact_orders)
    result = run_kmeans(features, n_clusters=n_clusters)
    cluster_labels = label_clusters(result)

    # 保存结果：含 Agent query_user_segments 所需的 order_count / total_spent
    feat_reset = features.reset_index()
    out = feat_reset[["customer_id"]].copy()
    out["cluster"] = result.labels.values
    out["cluster_label"] = out["cluster"].map(cluster_labels)
    if "frequency" in feat_reset.columns:
        out["order_count"] = feat_reset["frequency"].values
    if "monetary" in feat_reset.columns:
        out["total_spent"] = feat_reset["monetary"].values
    save_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(save_path, index=False)
    logger.info(f"用户聚类结果已保存: {save_path}")

    strategies = generate_cluster_strategies(result, cluster_labels)
    return result, cluster_labels, strategies


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 50)
    print("  KMeans 客户聚类模型模块")
    print("=" * 50)

    from data_cleaning import build_fact_table, load_raw_data, clean_orders, clean_payments
    customers, orders, payments, order_items = load_raw_data()
    orders = clean_orders(orders)
    payments = clean_payments(payments)
    fact = build_fact_table(customers, orders, payments, order_items)

    result, labels, strategies = run_pipeline(fact, n_clusters=3)

    print(f"\n聚类 k={result.k}，轮廓系数={result.silhouette}")
    print("\n聚类标签:")
    for cid, lbl in labels.items():
        print(f"  群{cid}: {lbl}")

    print("\n聚类运营策略:")
    for r in strategies:
        print(f"\n[{r['priority']}] 群{r['cluster_id']} ({r['label']}, {r['customer_count']:,}人)")
        for a in r["actions"]:
            print(f"    • {a}")
        print(f"  预期: {r['expected']}")


if __name__ == "__main__":
    main()
