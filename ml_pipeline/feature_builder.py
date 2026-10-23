# =============================================================================
# 注意：本模块属于「模拟数据方法验证」链路，不参与主训练流程。
#
# data_generator.py 使用 np.random 生成因子与未来收益，二者之间存在
# 人为设定的强线性关系，因此该链路上的任何指标都属于循环论证，
# 不能作为真实实证结果写入论文正文。
#
# 保留原因：记录「曾尝试 Learning-to-Rank 路线」的探索过程，可放入附录，
# 但所有展示处必须标注数据为模拟生成。
#
# 主流程请使用：python -m ml_pipeline.run_training
# =============================================================================
"""
Feature Builder & Learning-to-Rank Target Labeler
Computes relevance rank grades (0, 1, 2, 3) per cross-sectional date session.
Prepares datasets with group information for LightGBM LambdaMART.
"""

import os
import pandas as pd
import numpy as np
from ml_pipeline.data_generator import FEATURE_COLUMNS, FEATURE_NAMES_CN


def build_ltr_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    针对每一个截面（date），根据未来超额收益率生成分档相关度标签（Relevance Grades）
    3: 核心推荐标的 (Top 10%)
    2: 次优推荐标的 (10% - 30%)
    1: 表现平平标的 (30% - 60%)
    0: 回避/不推荐标的 (后 40%)
    """
    df = df.copy()
    
    # 截面内计算未来收益率降序排名
    df["rank_ground_truth"] = df.groupby("date")["forward_20d_return"].rank(ascending=False, method="min").astype(int)
    date_counts = df.groupby("date")["stock_code"].transform("count")
    pct = df["rank_ground_truth"] / date_counts
    
    labels = np.zeros(len(df), dtype=int)
    labels[pct <= 0.10] = 3
    labels[(pct > 0.10) & (pct <= 0.30)] = 2
    labels[(pct > 0.30) & (pct <= 0.60)] = 1
    labels[pct > 0.60] = 0
    
    df["relevance_label"] = labels
    return df


def split_train_test(df: pd.DataFrame, test_start_date="2024-06-01"):
    """
    严格基于时序切分，杜绝前视偏差 (No lookahead bias)
    Train/Val: < test_start_date
    Test: >= test_start_date (用于实证检验与推荐系统线上展示)
    """
    train_val_df = df[df["date"] < test_start_date].copy().sort_values(["date", "stock_code"])
    test_df = df[df["date"] >= test_start_date].copy().sort_values(["date", "stock_code"])
    
    # 统计每个截面的 group 大小（每个 date 包含多少只股票）
    train_groups = train_val_df.groupby("date", sort=False).size().to_numpy()
    test_groups = test_df.groupby("date", sort=False).size().to_numpy()
    
    return train_val_df, test_df, train_groups, test_groups


if __name__ == "__main__":
    from ml_pipeline.data_generator import generate_simulated_dataset
    raw_df = generate_simulated_dataset()
    labeled_df = build_ltr_dataset(raw_df)
    
    train_val, test, train_g, test_g = split_train_test(labeled_df)
    print(f"Total dataset: {labeled_df.shape}")
    print(f"Train/Val: {train_val.shape}, groups: {len(train_g)}")
    print(f"Test: {test.shape}, groups: {len(test_g)}")
    
    os.makedirs("data/processed", exist_ok=True)
    labeled_df.to_csv("data/processed/labeled_stock_dataset.csv", index=False, encoding="utf-8-sig")
    print("Saved labeled dataset.")
