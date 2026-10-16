# -*- coding: utf-8 -*-
"""SHAP 特征归因与可解释性 AI 诊断引擎
利用 TreeSHAP 解释 LightGBM 模型预测，输出局部瀑布图归因、自然语言诊断理由及全市场宏观特征重要性
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
import shap

from config.config import FEATURE_COLS, FEATURE_NAMES_CN, SAVED_MODELS_DIR


def build_and_save_explainer(model, save_path=None) -> shap.TreeExplainer:
    """
    基于训练好的 LightGBM 模型构建 TreeSHAP 解释器并持久化
    """
    if save_path is None:
        save_path = os.path.join(SAVED_MODELS_DIR, "shap_explainer.pkl")
        
    explainer = shap.TreeExplainer(model)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    joblib.dump(explainer, save_path)
    print(f"[SHAP] TreeExplainer 构建完成并保存至: {save_path}")
    return explainer


def generate_natural_language_reason(
    stock_name: str,
    stock_code: str,
    top_pos_features: list,
    top_neg_features: list,
    score: float,
    rank: int = 1
) -> str:
    """
    根据 TreeSHAP 特征贡献度，自动生成条理清晰的自然语言投资诊断理由
    """
    pos_desc_list = []
    for f in top_pos_features[:3]:
        name_cn = f["name_cn"]
        val = f["feature_value"]
        shap_val = f["shap_value"]
        pos_desc_list.append(f"{name_cn}(值: {val})正向赋能 +{shap_val:.3f}")

    neg_desc_list = []
    for f in top_neg_features[:2]:
        name_cn = f["name_cn"]
        val = f["feature_value"]
        shap_val = f["shap_value"]
        neg_desc_list.append(f"{name_cn}(值: {val})抑制影响 {shap_val:.3f}")

    reason = f"【AI 选股模型诊断报告】标的【{stock_name} ({stock_code})】综合预测看涨得分/概率为 {score:.3f}，当前推荐排位第 {rank} 名。\n"

    if pos_desc_list:
        reason += "★ 核心看多动能：模型判定该股具备上涨催化逻辑，主因在于 " + "，以及 ".join(pos_desc_list) + "。\n"

    if neg_desc_list:
        reason += "▲ 风险压制因子：值得注意的是，" + "，以及 ".join(neg_desc_list) + "，建议投资者注意对应技术位与仓位控制。"
    else:
        reason += "▲ 风险排查：该标的多维量价与动量指标健康，未发现显著空头抑制因子。"

    return reason


def explain_stock_recommendation(
    test_df: pd.DataFrame,
    explainer: shap.TreeExplainer,
    stock_code: str,
    date: str = None
) -> dict:
    """
    为指定股票生成详尽的 SHAP 瀑布图与诊断数据
    """
    if test_df is None or test_df.empty:
        return None

    clean_code = str(stock_code).zfill(6)
    code_col = "stock_code" if "stock_code" in test_df.columns else ("代码" if "代码" in test_df.columns else None)
    if not code_col:
        return None

    sub = test_df[test_df[code_col].astype(str).str.zfill(6) == clean_code]
    if sub.empty:
        return None

    date_col = "date" if "date" in sub.columns else ("更新日期" if "更新日期" in sub.columns else None)
    if date and date_col:
        row_candidates = sub[sub[date_col] == date]
        row = row_candidates.iloc[0] if not row_candidates.empty else sub.iloc[-1]
    else:
        row = sub.iloc[-1]

    # 提取特征：优先从股票自身历史数据中获取最新特征向量
    from data.data_fetcher import get_stock_data
    df_feat = get_stock_data(clean_code)
    if df_feat is not None and len(df_feat) > 0:
        latest_feat = df_feat[FEATURE_COLS].iloc[[-1]].astype(float)
        X_single = latest_feat
    elif all(c in row for c in FEATURE_COLS):
        X_single = row[FEATURE_COLS].to_frame().T.astype(float)
    else:
        return None

    raw_shap = explainer.shap_values(X_single)

    if isinstance(raw_shap, list):
        shap_vals = raw_shap[1][0] if len(raw_shap) > 1 else raw_shap[0][0]
    elif len(np.shape(raw_shap)) == 3:
        shap_vals = raw_shap[0, :, 1]
    else:
        shap_vals = raw_shap[0]

    base_val = explainer.expected_value
    if isinstance(base_val, (list, np.ndarray)):
        base_val = float(base_val[-1])
    else:
        base_val = float(base_val)

    # 组装特征贡献
    feature_contributions = []
    for col, sv in zip(FEATURE_COLS, shap_vals):
        val = float(X_single[col].iloc[0])
        feature_contributions.append({
            "feature_key": col,
            "name_cn": FEATURE_NAMES_CN.get(col, col),
            "feature_value": round(val, 2) if abs(val) > 1 else round(val, 4),
            "shap_value": round(float(sv), 4)
        })

    # 分离正负贡献
    pos_features = sorted([f for f in feature_contributions if f["shap_value"] > 0], key=lambda x: x["shap_value"], reverse=True)
    neg_features = sorted([f for f in feature_contributions if f["shap_value"] < 0], key=lambda x: x["shap_value"])

    # 瀑布图排序（按绝对值降序）
    waterfall_items = sorted(feature_contributions, key=lambda x: abs(x["shap_value"]), reverse=True)

    score = float(row.get("预测看涨概率", row.get("predicted_score", row.get("predicted_prob", 0.5))))
    rank = int(row.get("推荐排名", row.get("predicted_rank", 1)))
    stock_name = str(row.get("名称", row.get("stock_name", clean_code)))
    date_val = str(row.get("更新日期", row.get("date", "")))

    reason = generate_natural_language_reason(
        stock_name=stock_name,
        stock_code=clean_code,
        top_pos_features=pos_features,
        top_neg_features=neg_features,
        score=score,
        rank=rank
    )

    return {
        "stock_code": clean_code,
        "stock_name": stock_name,
        "industry": str(row.get("行业", row.get("industry", "全市场A股"))),
        "date": date_val,
        "predicted_score": round(score, 4),
        "predicted_rank": rank,
        "base_value": round(base_val, 4),
        "final_value": round(score, 4),
        "features": waterfall_items,
        "top_positive": pos_features,
        "top_negative": neg_features,
        "top_positive_features": pos_features,
        "top_negative_features": neg_features,
        "waterfall_data": waterfall_items,
        "natural_language_reason": reason
    }


def compute_and_save_global_importance(
    test_df: pd.DataFrame,
    explainer: shap.TreeExplainer,
    save_path=None
) -> list:
    """
    计算并保存全市场全局 Mean |SHAP| 特征重要性
    """
    if save_path is None:
        save_path = os.path.join(SAVED_MODELS_DIR, "global_importance.json")

    X_all = test_df[FEATURE_COLS].astype(float)
    raw_shap = explainer.shap_values(X_all)

    if isinstance(raw_shap, list):
        shap_matrix = raw_shap[1] if len(raw_shap) > 1 else raw_shap[0]
    elif len(np.shape(raw_shap)) == 3:
        shap_matrix = raw_shap[:, :, 1]
    else:
        shap_matrix = raw_shap

    mean_abs_shap = np.mean(np.abs(shap_matrix), axis=0)
    total_shap = np.sum(mean_abs_shap) + 1e-9

    records = []
    for col, mean_val in zip(FEATURE_COLS, mean_abs_shap):
        records.append({
            "feature": col,
            "name_cn": FEATURE_NAMES_CN.get(col, col),
            "mean_abs_shap": round(float(mean_val), 4),
            "importance_ratio": round(float(mean_val / total_shap), 4)
        })

    records = sorted(records, key=lambda x: x["mean_abs_shap"], reverse=True)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[SHAP] 全局特征重要性已保存至: {save_path}")
    return records
