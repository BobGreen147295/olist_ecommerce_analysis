#!/usr/bin/env python
"""
一键跑通离线流水线，产出 Agent / Streamlit 所需的 processed CSV。

用法（在项目根目录）:
    python src/run_pipeline.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 50)
    print("  Olist 离线流水线（清洗 → 分析 → 建模 → 出图）")
    print("=" * 50)

    from data_cleaning import run_full_pipeline
    from analysis_rfm import run_and_save
    from analysis_geo import run as run_geo
    from analysis_payment import run as run_payment
    from model_clustering import run_pipeline as run_clustering
    from model_churn import run_pipeline as run_churn
    from visualization import generate_all

    cleaned = run_full_pipeline()
    fact = cleaned["fact_orders"]

    run_and_save(fact_orders=fact)
    geo = run_geo(fact_orders=fact)
    run_payment(fact)
    run_clustering(fact, n_clusters=3)
    run_churn(fact)
    generate_all(
        customers=cleaned["customers"],
        orders=cleaned["orders"],
        fact_orders=fact,
        region_analysis=geo.region_per_capita,
    )

    print("\n流水线完成。可接着运行:")
    print('  python src/agent/run_agent.py "分析最近半年的销售趋势"')
    print("  streamlit run dashboard/dashboard.py")


if __name__ == "__main__":
    main()
