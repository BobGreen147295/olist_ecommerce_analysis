import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

for p in (ROOT / "src").rglob("*.py"):
    compile(p.read_text(encoding="utf-8"), str(p), "exec")
print("compile: ok")

import pandas as pd
from analysis_rfm import compute_rfm
from data_cleaning import build_sales_trends
from crawler import _population_frame
from agent.tools import _normalize_region_frame, query_sales_by_region

fact = pd.DataFrame(
    {
        "customer_id": ["a", "b"],
        "order_id": ["1", "2"],
        "order_date": ["2018-12-01", "2017-01-01"],
        "payment_value": [80.0, 80.0],
    }
)
result = compute_rfm(fact_orders=fact, analysis_date="2018-12-02")
scores = dict(zip(result.rfm_data["customer_id"], result.rfm_data["r_score"]))
assert scores["a"] > scores["b"], scores
print("rfm recency: ok", scores)

fact2 = pd.DataFrame(
    {
        "customer_state": ["SP", "SP", "RJ"],
        "year": [2018, 2018, 2018],
        "month": [1, 1, 2],
        "order_id": ["o1", "o2", "o3"],
        "payment_value": [10.0, 20.0, 5.0],
    }
)
trends = build_sales_trends(fact2)
assert list(trends.columns) == [
    "customer_state",
    "year",
    "month",
    "order_count",
    "total_sales",
    "period",
]
assert int(trends.loc[trends["customer_state"] == "SP", "order_count"].iloc[0]) == 2
print("sales_trends: ok")

pop = _population_frame()
assert not pop["state"].duplicated().any()
print("population unique:", len(pop))

old = pd.DataFrame(
    {
        "customer_state": ["SP"],
        "total_revenue": [100.0],
        "population": [50],
        "sales_per_million": [2e6],
    }
)
norm = _normalize_region_frame(old)
assert list(norm[["state", "sales", "sales_per_capita"]].iloc[0]) == ["SP", 100.0, 2e6]
print("region normalize: ok")

live = query_sales_by_region("SP")
print("query region:", live["success"], live.get("summary"))
assert live["success"]
print("all checks passed")
