# -*- coding: utf-8 -*-
"""推荐系统离线评测与基线对比

关于「不写兜底数字」
--------------------
早期版本在异常分支里硬编码了一组好看的指标（NDCG@5=0.7410 等），
导致评测脚本一旦出错就静默写入假数据，README 与真实产物互相矛盾。
本版本移除全部兜底字面量：任何模型评测失败都会记入 errors 字段并在
结果中显式标记，绝不伪造数值。

指标口径
--------
所有排序指标按「截面」计算：同一天的候选股票作为一个推荐列表，
Top-K 取自该列表。跨截面取均值。
"""

import json
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from config.config import FEATURE_COLS, get_model_features, SAVED_MODELS_DIR

TOP_K_VALUES = (5, 10)
TOP_K_CURVE_MAX = 20


def _dcg(relevances: np.ndarray, k: int) -> float:
    rel = np.asarray(relevances, dtype=float)[:k]
    if rel.size == 0:
        return 0.0
    discounts = np.log2(np.arange(rel.size) + 2)
    return float(np.sum((2 ** rel - 1) / discounts))


def _ndcg(ranked_rel: np.ndarray, ideal_rel: np.ndarray, k: int) -> float:
    ideal = _dcg(ideal_rel, k)
    return _dcg(ranked_rel, k) / ideal if ideal > 0 else 0.0


def evaluate_ranking(panel: pd.DataFrame, score_col: str, label_col: str = 'target_up') -> dict:
    """按截面计算 NDCG / Precision / HitRate。

    Returns:
        指标字典；若没有任何有效截面则返回空字典（由调用方处理）。
    """
    if panel.empty or score_col not in panel.columns:
        return {}

    ndcg = {k: [] for k in TOP_K_VALUES}
    prec = {k: [] for k in TOP_K_VALUES}
    hit = {k: [] for k in TOP_K_VALUES}

    for _date, group in panel.groupby('date'):
        if len(group) < max(TOP_K_VALUES):
            continue

        ranked = group.sort_values(score_col, ascending=False)
        rel = ranked[label_col].to_numpy()
        ideal = np.sort(group[label_col].to_numpy())[::-1]

        for k in TOP_K_VALUES:
            ndcg[k].append(_ndcg(rel, ideal, k))
            prec[k].append(float(np.mean(rel[:k])))
            hit[k].append(1.0 if rel[:k].sum() > 0 else 0.0)

    if not ndcg[5]:
        return {}

    out = {}
    for k in TOP_K_VALUES:
        out[f'NDCG@{k}'] = round(float(np.mean(ndcg[k])), 4)
        out[f'Precision@{k}'] = round(float(np.mean(prec[k])), 4)
        out[f'HitRate@{k}'] = round(float(np.mean(hit[k])), 4)
    return out


def evaluate_topk_curves(panel: pd.DataFrame, score_columns: dict,
                         label_col: str = 'target_up', max_k: int = TOP_K_CURVE_MAX,
                         random_repeats: int = 50, random_seed: int = 42):
    """在相同测试截面上逐 K 计算 Precision@K 与 NDCG@K。

    只纳入所有候选评分和标签均完整、且候选数不少于 10 的日期；
    K 上限由这些日期中的最小候选数决定，确保每个 K 使用相同日期集合。
    随机排序基线通过固定随机种子的多次排列取均值，降低单次随机抽样噪声。
    """
    score_columns = {name: col for name, col in score_columns.items()
                     if col in panel.columns}
    required = [label_col, *score_columns.values()]
    if panel.empty or not score_columns or any(col not in panel.columns for col in required):
        return {}, {'n_dates': 0, 'total_dates': int(panel['date'].nunique()) if 'date' in panel else 0,
                    'max_k': 0}

    complete = panel.dropna(subset=required)
    groups = [(date, group) for date, group in complete.groupby('date', sort=True)
              if len(group) >= 10]
    if not groups:
        return {}, {'n_dates': 0, 'total_dates': int(panel['date'].nunique()), 'max_k': 0}

    curve_max_k = min(int(max_k), min(len(group) for _, group in groups))
    ks = list(range(1, curve_max_k + 1))
    if not ks:
        return {}, {'n_dates': 0, 'total_dates': int(panel['date'].nunique()), 'max_k': 0}

    accumulated = {
        name: {'precision': [[] for _ in ks], 'ndcg': [[] for _ in ks]}
        for name in score_columns
    }
    random_rng = np.random.default_rng(random_seed)
    for _, group in groups:
        labels = group[label_col].to_numpy(dtype=float)
        ideal = np.sort(labels)[::-1]
        for name, score_col in score_columns.items():
            if name == 'Random Guess':
                rankings = (labels[random_rng.permutation(len(labels))]
                            for _ in range(max(1, int(random_repeats))))
            else:
                ranked = group.sort_values(score_col, ascending=False, kind='mergesort')
                rankings = (ranked[label_col].to_numpy(dtype=float),)
            for relevance in rankings:
                for index, k in enumerate(ks):
                    accumulated[name]['precision'][index].append(float(np.mean(relevance[:k])))
                    accumulated[name]['ndcg'][index].append(_ndcg(relevance, ideal, k))

    curves = {
        name: {
            'ks': ks,
            'precision': [round(float(np.mean(values)), 6)
                          for values in metrics['precision']],
            'ndcg': [round(float(np.mean(values)), 6)
                     for values in metrics['ndcg']],
        }
        for name, metrics in accumulated.items()
    }
    return curves, {
        'n_dates': len(groups),
        'total_dates': int(panel['date'].nunique()),
        'max_k': curve_max_k,
        'eligible_dates_min_candidates': min(len(group) for _, group in groups),
        'random_baseline_repeats': max(1, int(random_repeats)) if 'Random Guess' in score_columns else 0,
        'random_seed': int(random_seed),
    }


def run_baseline_comparison(result: dict, save_path: str = None) -> dict:
    """在测试集上对比 LightGBM 与基线模型。

    每个模型单独 try/except，失败时记录 error 并把该模型标记为不可用，
    绝不填充编造数值。
    """
    if save_path is None:
        save_path = os.path.join(SAVED_MODELS_DIR, "evaluation_metrics.json")

    test = result['test'].copy()
    model = result['model']
    X_test, y_test = test[get_model_features()], test['target_up']
    X_train = result['train'][get_model_features()].copy()
    medians = X_train.median().fillna(0.0)
    X_train_filled = X_train.fillna(medians).fillna(0.0)
    X_test_filled = X_test.fillna(medians).fillna(0.0)

    comparison = {}
    errors = {}

    # 1. 随机基线：用固定种子生成打分
    rng = np.random.default_rng(42)
    test['score_random'] = rng.random(len(test))
    comparison['Random Guess'] = evaluate_ranking(test, 'score_random')
    comparison['Random Guess']['AUC'] = 0.5000

    # 2. 逻辑回归（线性判别基线）
    try:
        scaler = StandardScaler().fit(X_train_filled)
        lr = LogisticRegression(max_iter=1000, random_state=42)
        lr.fit(scaler.transform(X_train_filled), result['train']['target_up'])
        test['score_lr'] = lr.predict_proba(scaler.transform(X_test_filled))[:, 1]
        comparison['Logistic Regression'] = evaluate_ranking(test, 'score_lr')
        comparison['Logistic Regression']['AUC'] = round(float(roc_auc_score(y_test, test['score_lr'])), 4)
    except Exception as e:
        errors['Logistic Regression'] = str(e)

    # 3. 随机森林
    try:
        rf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)
        rf.fit(X_train_filled, result['train']['target_up'])
        test['score_rf'] = rf.predict_proba(X_test_filled)[:, 1]
        comparison['Random Forest'] = evaluate_ranking(test, 'score_rf')
        comparison['Random Forest']['AUC'] = round(float(roc_auc_score(y_test, test['score_rf'])), 4)
    except Exception as e:
        errors['Random Forest'] = str(e)

    # 4. 本文方法：LightGBM
    try:
        test['score_lgb'] = model.predict_proba(X_test)[:, 1]
        comparison['LightGBM (Ours)'] = evaluate_ranking(test, 'score_lgb')
        comparison['LightGBM (Ours)']['AUC'] = round(float(roc_auc_score(y_test, test['score_lgb'])), 4)
    except Exception as e:
        errors['LightGBM (Ours)'] = str(e)

    score_columns = {
        'Random Guess': 'score_random',
        'Logistic Regression': 'score_lr',
        'Random Forest': 'score_rf',
        'LightGBM (Ours)': 'score_lgb',
    }
    score_columns = {name: column for name, column in score_columns.items()
                     if name in comparison and column in test.columns}
    ranking_curves, ranking_curve_meta = evaluate_topk_curves(test, score_columns)

    payload = {
        'comparison': comparison,
        'errors': errors,
        'ranking_curves': ranking_curves,
        'ranking_curve_meta': ranking_curve_meta,
        'meta': {
            'test_rows': int(len(test)),
            'test_dates': int(test['date'].nunique()),
            'feature_cols': get_model_features(),
            'label_mode': 'excess_return_5d',
            'test_pos_rate': round(float(y_test.mean()), 4),
            'loss_history': result.get('loss_history', {}),
        },
    }

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if errors:
        print(f"[Metrics] 以下模型评测失败，已如实记录: {list(errors)}")
    print(f"[Metrics] 基线对比已保存: {save_path}")
    return payload
