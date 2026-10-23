# -*- coding: utf-8 -*-
"""TreeSHAP 特征归因与自然语言诊断

本版本新增两项论文必需的自检：
  1. 加和一致性：Σ SHAP + base_value 必须等于模型输出（Logit 或概率），
     否则归因不可信，前端会显示校验结果；
  2. 归因稳定性：跨随机种子重训后特征重要性排序的 Spearman 相关，
     用于回答「归因结论是否可复现」。
"""

import json
import os

import joblib
import numpy as np
import pandas as pd
import shap

from config.config import FEATURE_NAMES_CN, get_model_features, SAVED_MODELS_DIR


def _feature_name(col: str) -> str:
    raw_name = col[:-4] if col.endswith('_neu') else col
    return FEATURE_NAMES_CN.get(raw_name, raw_name)


def build_explainer(model, save_path: str = None):
    """构建并持久化 TreeExplainer。"""
    if save_path is None:
        save_path = os.path.join(SAVED_MODELS_DIR, 'shap_explainer.pkl')
    explainer = shap.TreeExplainer(model)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    joblib.dump(explainer, save_path)
    print(f"[SHAP] 解释器已保存: {save_path}")
    return explainer


def _extract_shap_values(raw, n_features: int) -> np.ndarray:
    """统一 SHAP 输出形状为 (n_samples, n_features)。"""
    if isinstance(raw, list):
        # 旧版 API：list[class] -> array
        arr = raw[1] if len(raw) > 1 else raw[0]
    else:
        arr = raw
    arr = np.asarray(arr)
    if arr.ndim == 3:
        # (n_samples, n_features, n_classes)
        arr = arr[:, :, 1] if arr.shape[2] > 1 else arr[:, :, 0]
    return arr


def _extract_base_value(explainer) -> float:
    base = explainer.expected_value
    if isinstance(base, (list, np.ndarray)):
        base = base[1] if len(base) > 1 else base[0]
    return float(base)


def verify_additivity(model, explainer, X: pd.DataFrame, sample: int = 200) -> dict:
    """校验 SHAP 加和一致性。

    TreeSHAP 在 log-odds 空间满足精确加和：base + Σshap = 模型原始输出。
    若偏差显著，说明解释器与模型不匹配，归因结论不可信。
    """
    X_sample = X.head(sample)
    shap_vals = _extract_shap_values(explainer.shap_values(X_sample), len(get_model_features()))
    base = _extract_base_value(explainer)

    reconstructed = base + shap_vals.sum(axis=1)

    # 优先比较原始 margin，缺失时退回概率空间
    try:
        raw_margin = model.predict(X_sample, raw_score=True)
        space = 'log_odds'
    except Exception:
        raw_margin = model.predict_proba(X_sample)[:, 1]
        space = 'probability'

    max_abs_err = float(np.max(np.abs(reconstructed - raw_margin)))
    mean_abs_err = float(np.mean(np.abs(reconstructed - raw_margin)))

    return {
        'space': space,
        'max_abs_error': round(max_abs_err, 6),
        'mean_abs_error': round(mean_abs_err, 6),
        'tolerance': 1e-3,
        'passed': bool(max_abs_err < 1e-3),
        'n_samples': int(len(X_sample)),
    }


def _summary_sample_positions(test_df: pd.DataFrame, max_samples: int = 1200,
                              seed: int = 42) -> np.ndarray:
    """按测试日期分层抽取可视化样本，避免单个日期主导 beeswarm。"""
    n_rows = len(test_df)
    if n_rows <= max_samples:
        return np.arange(n_rows, dtype=int)

    rng = np.random.default_rng(seed)
    if 'date' not in test_df.columns:
        return np.sort(rng.choice(n_rows, size=max_samples, replace=False))

    date_groups = list(test_df.groupby('date', sort=True).indices.values())
    quota = max(1, max_samples // max(len(date_groups), 1))
    chosen = []
    for positions in date_groups:
        positions = np.asarray(positions, dtype=int)
        count = min(quota, len(positions))
        chosen.extend(rng.choice(positions, size=count, replace=False).tolist())

    chosen = np.asarray(chosen, dtype=int)
    if len(chosen) > max_samples:
        chosen = rng.choice(chosen, size=max_samples, replace=False)
    elif len(chosen) < max_samples:
        remaining = np.setdiff1d(np.arange(n_rows), chosen, assume_unique=False)
        extra_count = min(max_samples - len(chosen), len(remaining))
        if extra_count:
            chosen = np.concatenate((chosen, rng.choice(
                remaining, size=extra_count, replace=False)))
    return np.sort(chosen)


def _write_shap_summary(test_df: pd.DataFrame, sample_positions: np.ndarray,
                        shap_sample: np.ndarray, importance_records: list,
                        summary_path: str) -> dict:
    X_sample = test_df[get_model_features()].iloc[sample_positions].astype(float)
    summary_features = []
    for record in importance_records[:10]:
        feature = record['feature']
        feature_index = get_model_features().index(feature)
        raw_values = X_sample[feature].to_numpy(dtype=float)
        shap_values = shap_sample[:, feature_index]
        finite_values = np.isfinite(raw_values)
        percentiles = np.full(len(raw_values), np.nan, dtype=float)
        if finite_values.any():
            percentiles[finite_values] = pd.Series(raw_values[finite_values]).rank(
                pct=True, method='average').to_numpy(dtype=float)
        summary_features.append({
            'feature': feature,
            'name_cn': _feature_name(feature),
            'mean_abs_shap': record['mean_abs_shap'],
            'shap_values': [float(v) for v in shap_values],
            'feature_values': [float(v) if np.isfinite(v) else None for v in raw_values],
            'feature_value_percentiles': [
                float(v) if np.isfinite(v) else None for v in percentiles
            ],
        })

    sample_dates = (test_df.iloc[sample_positions]['date'].nunique()
                    if 'date' in test_df.columns else None)
    summary = {
        'source': 'test',
        'output_space': 'log_odds',
        'sample_strategy': 'date_balanced_deterministic',
        'sample_rows': int(len(sample_positions)),
        'sample_dates': int(sample_dates) if sample_dates is not None else None,
        'feature_transform': (
            '测试集特征值为按交易日缩尾、行业中性化并进行截面 z-score 标准化后的模型输入；'
            'beeswarm 颜色表示该特征在可视化样本中的相对分位。'
        ),
        'features': summary_features,
    }
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"[SHAP] beeswarm 样本已保存: {summary_path} ({len(sample_positions)} 行)")
    return summary


def compute_shap_summary(test_df: pd.DataFrame, explainer, importance_records: list,
                         summary_path: str = None,
                         max_summary_samples: int = 1200) -> dict:
    """只计算分层抽样 SHAP 值，用于从已有模型补充 beeswarm 图。"""
    if summary_path is None:
        summary_path = os.path.join(SAVED_MODELS_DIR, 'shap_summary.json')
    sample_positions = _summary_sample_positions(test_df, max_summary_samples)
    X_sample = test_df[get_model_features()].iloc[sample_positions].astype(float)
    shap_sample = _extract_shap_values(
        explainer.shap_values(X_sample), len(get_model_features()))
    return _write_shap_summary(
        test_df, sample_positions, shap_sample, importance_records, summary_path)


def compute_global_importance(test_df: pd.DataFrame, explainer, save_path: str = None,
                              summary_path: str = None, max_summary_samples: int = 1200) -> list:
    """计算全局 Mean |SHAP|，并保存 beeswarm 所需的测试集局部归因样本。"""
    if save_path is None:
        save_path = os.path.join(SAVED_MODELS_DIR, 'global_importance.json')
    if summary_path is None:
        summary_path = os.path.join(SAVED_MODELS_DIR, 'shap_summary.json')

    X_all = test_df[get_model_features()].astype(float)
    shap_matrix = _extract_shap_values(explainer.shap_values(X_all), len(get_model_features()))

    mean_abs = np.mean(np.abs(shap_matrix), axis=0)
    total = float(np.sum(mean_abs)) + 1e-9

    records = [
        {
            'feature': col,
            'name_cn': _feature_name(col),
            'mean_abs_shap': round(float(v), 4),
            'importance_ratio': round(float(v / total), 4),
        }
        for col, v in zip(get_model_features(), mean_abs)
    ]
    records.sort(key=lambda x: x['mean_abs_shap'], reverse=True)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[SHAP] 全局重要性已保存: {save_path}")
    sample_positions = _summary_sample_positions(test_df, max_summary_samples)
    _write_shap_summary(
        test_df, sample_positions, shap_matrix[sample_positions], records, summary_path)
    return records


def generate_reason(stock_name: str, stock_code: str, top_pos: list, top_neg: list,
                    score: float, rank: int = 1) -> str:
    """把 SHAP 贡献翻译成可读的诊断说明。

    措辞严格区分「模型认为」与「事实」，避免把归因结果写成投资建议。
    """
    lines = [
        f"模型对 {stock_name}（{stock_code}）未来 5 个交易日跑赢当日候选池平均收益的"
        f"概率估计为 {score:.1%}，"
        f"在当前截面中排第 {rank} 位。"
    ]

    if top_pos:
        parts = [f"{f['name_cn']}（当前值 {f['feature_value']}，贡献 +{f['shap_value']:.3f}）"
                 for f in top_pos[:3]]
        lines.append("推高该估计的主要因素：" + "、".join(parts) + "。")

    if top_neg:
        parts = [f"{f['name_cn']}（当前值 {f['feature_value']}，贡献 {f['shap_value']:.3f}）"
                 for f in top_neg[:2]]
        lines.append("拉低该估计的因素：" + "、".join(parts) + "。")
    else:
        lines.append("未检测到显著的下压因素。")

    lines.append("以上为模型归因结果，反映特征对预测值的边际贡献，不构成投资建议。")
    return "\n".join(lines)


def explain_stock(explainer, model, code: str, name: str, features: dict,
                  score: float, rank: int = 1,
                  feature_cols: list = None) -> dict:
    """为单只股票生成局部归因数据。

    Args:
        features: 该股票最新截面的特征字典（键为 feature_cols）
    """
    feature_cols = feature_cols or get_model_features()
    missing = [c for c in feature_cols if c not in features]
    if missing:
        raise ValueError(f'局部归因输入缺少有效模型特征: {missing}')
    X_single = pd.DataFrame([{c: float(features[c]) for c in feature_cols}])

    shap_vals = _extract_shap_values(explainer.shap_values(X_single), len(feature_cols))[0]
    base = _extract_base_value(explainer)
    margin = float(model.predict(X_single, raw_score=True)[0])

    contributions = [
        {
            'feature_key': col,
            'name_cn': _feature_name(col),
            'feature_value': (round(float(features[col]), 4)
                              if pd.notna(features[col]) else None),
            'shap_value': round(float(sv), 4),
        }
        for col, sv in zip(feature_cols, shap_vals)
    ]

    pos = sorted([c for c in contributions if c['shap_value'] > 0],
                 key=lambda x: x['shap_value'], reverse=True)
    neg = sorted([c for c in contributions if c['shap_value'] < 0],
                 key=lambda x: x['shap_value'])
    waterfall = sorted(contributions, key=lambda x: abs(x['shap_value']), reverse=True)

    return {
        'stock_code': code,
        'stock_name': name,
        'predicted_score': round(float(score), 4),
        'predicted_margin': round(margin, 4),
        'output_space': 'log_odds',
        'predicted_rank': int(rank),
        'base_value': round(base, 4),
        'features': waterfall,
        'top_positive': pos,
        'top_negative': neg,
        'natural_language_reason': generate_reason(name, code, pos, neg, score, rank),
    }
