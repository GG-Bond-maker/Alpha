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
LightGBM Ranker Training Pipeline
Trains a LambdaMART Learning-to-Rank model optimizing NDCG@5 and NDCG@10.
Saves the trained model and inference artifacts for online FastAPI serving.
"""

import os
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from ml_pipeline.data_generator import FEATURE_COLUMNS, generate_simulated_dataset
from ml_pipeline.feature_builder import build_ltr_dataset, split_train_test


def train_lgbm_ranker(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    train_groups: np.ndarray,
    val_groups: np.ndarray
):
    """
    使用 LightGBM LambdaMART 算法训练截面股票排序推荐器
    """
    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["relevance_label"]
    
    X_val = val_df[FEATURE_COLUMNS]
    y_val = val_df["relevance_label"]

    ranker = lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        eval_at=[5, 10],
        n_estimators=150,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=5,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        importance_type="gain",
        verbose=-1
    )

    ranker.fit(
        X_train,
        y_train,
        group=train_groups,
        eval_set=[(X_val, y_val)],
        eval_group=[val_groups],
        callbacks=[lgb.early_stopping(stopping_rounds=25, verbose=False)]
    )

    return ranker


def run_training_pipeline():
    os.makedirs("saved_models", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)
    
    print("[1/4] Generating stock panel dataset...")
    raw_df = generate_simulated_dataset()
    labeled_df = build_ltr_dataset(raw_df)
    
    # 划分训练集、验证集和测试集
    # 2023-01 至 2024-03 训练；2024-04 至 2024-06 验证；2024-07 至 2024-12 测试
    train_split_df = labeled_df[labeled_df["date"] < "2024-04-01"].copy()
    val_split_df = labeled_df[(labeled_df["date"] >= "2024-04-01") & (labeled_df["date"] < "2024-07-01")].copy()
    test_split_df = labeled_df[labeled_df["date"] >= "2024-07-01"].copy()

    train_groups = train_split_df.groupby("date", sort=False).size().to_numpy()
    val_groups = val_split_df.groupby("date", sort=False).size().to_numpy()
    test_groups = test_split_df.groupby("date", sort=False).size().to_numpy()

    print(f"[2/4] Training LGBMRanker (Train: {len(train_groups)} dates, Val: {len(val_groups)} dates)...")
    ranker = train_lgbm_ranker(train_split_df, val_split_df, train_groups, val_groups)
    
    # 在全量测试集上预测推荐打分
    print("[3/4] Predicting test set recommendations...")
    X_test = test_split_df[FEATURE_COLUMNS]
    test_split_df["predicted_score"] = ranker.predict(X_test)
    
    # 截面内计算推荐排名（分值越高，排名越靠前）
    test_split_df["predicted_rank"] = test_split_df.groupby("date")["predicted_score"].rank(ascending=False, method="min").astype(int)

    # 保存模型与测试集
    model_path = "saved_models/lgbm_ranker.pkl"
    joblib.dump(ranker, model_path)
    test_split_df.to_csv("data/processed/test_recommendations.csv", index=False, encoding="utf-8-sig")
    labeled_df.to_csv("data/processed/full_labeled_dataset.csv", index=False, encoding="utf-8-sig")
    
    print(f"[4/4] Model saved to {model_path}, test results saved to data/processed/test_recommendations.csv")
    return ranker, test_split_df


if __name__ == "__main__":
    run_training_pipeline()
