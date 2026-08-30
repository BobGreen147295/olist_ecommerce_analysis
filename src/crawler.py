"""
外部对照数据：巴西各州人口（用于人均销售额 / 市场渗透分析）。

Worldometers 页面结构不稳定，本模块使用可复现的对照表，避免把“请求成功”
误当成“解析成功”。网络请求仅作连通性探测，不参与写表。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"

# 州代码唯一；人口为对照数量级数据，供渗透率排序，非普查公报。
BRAZIL_STATE_POPULATION = [
    ("SP", 46649132),
    ("RJ", 17463349),
    ("MG", 21168791),
    ("RS", 11377239),
    ("PR", 11433957),
    ("BA", 14985284),
    ("SC", 7338473),
    ("DF", 3055149),
    ("GO", 7206589),
    ("ES", 3974687),
    ("PE", 9674793),
    ("CE", 9240580),
    ("PA", 8777124),
    ("MA", 7153262),
    ("MT", 3567234),
    ("AM", 4269995),
    ("MS", 2839188),
    ("PI", 3271199),
    ("PB", 4059905),
    ("RN", 3568760),
]


def _population_frame() -> pd.DataFrame:
    df = pd.DataFrame(BRAZIL_STATE_POPULATION, columns=["state", "population"])
    if df["state"].duplicated().any():
        raise ValueError("人口对照表存在重复州代码")
    return df


def crawl_brazil_population_data(save_path: Optional[Path] = None) -> pd.DataFrame:
    """写出巴西各州人口对照表。"""
    save_path = save_path or (DATA_DIR / "processed" / "brazil_population.csv")
    save_path.parent.mkdir(parents=True, exist_ok=True)
    df = _population_frame()

    df.to_csv(save_path, index=False)
    print(f"[Crawler] 人口数据已保存: {save_path}（{len(df)} 个州）")
    return df


def main() -> None:
    print("=" * 50)
    print("  爬虫模块 - 巴西人口对照数据")
    print("=" * 50)
    df = crawl_brazil_population_data()
    print(f"\n采集完成，共 {len(df)} 个州的数据")


if __name__ == "__main__":
    main()
