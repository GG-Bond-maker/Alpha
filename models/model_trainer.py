# -*- coding: utf-8 -*-
"""LightGBM 训练与 Optuna 超参数寻优

修复的泄漏点
------------
早期版本有两处前视泄漏：
  1. 在全部数据上 ffill().bfill() —— bfill 把未来值回填到过去；
  2. Optuna 调参后又在全量 X,y 上 refit —— 验证集信息进入最终模型。

本版本：
  - 特征清洗在 dataset.build_panel 内完成，只用 ffill；
  - 调参用训练集内部的 TimeSeriesSplit；
  - 特征筛选与调参都只使用训练数据；最终模型只用训练集拟合，
    验证集与测试集仅用于报告结果。
"""

import os
import warnings

import joblib
import numpy as np
import optuna
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, accuracy_score
from sklearn.model_selection import TimeSeriesSplit

from config.config import FEATURE_COLS, get_model_features, MODEL_DIR, SAVED_MODELS_DIR
from ml_pipeline.dataset import build_factor_panel, time_split
from config.config import TARGET_DAYS
from ml_pipeline.factor_diagnosis import diagnose_all, factors_for_model
from ml_pipeline.backtest import is_limit_up as flag_signal_limit
from ml_pipeline.model_selection import date_weights

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

DEFAULT_PARAMS = {
    'n_estimators': 200,
    'learning_rate': 0.05,
    'max_depth': 5,
    'num_leaves': 31,
    'subsample': 0.85,
    'subsample_freq': 1,
    'n_jobs': 4,
    'colsample_bytree': 0.85,
    'reg_alpha': 0.1,
    'reg_lambda': 0.1,
    'random_state': 42,
    'verbose': -1,
}


def _date_grouped_splits(train: pd.DataFrame, n_splits: int = 3,
                         embargo_days: int = TARGET_DAYS):
    """只按完整交易日切折，并清除验证起点前尚未成熟的标签。"""
    dates = np.sort(train['date'].unique())
    if len(dates) < n_splits + embargo_days + 2:
        return []
    splitter = TimeSeriesSplit(n_splits=n_splits)
    splits = []
    for fold_train_idx, fold_val_idx in splitter.split(dates):
        val_start = int(fold_val_idx[0])
        usable_train_end = max(0, val_start - embargo_days)
        train_dates = dates[fold_train_idx[fold_train_idx < usable_train_end]]
        val_dates = dates[fold_val_idx]
        if train_dates.size == 0 or val_dates.size == 0:
            continue
        tr_idx = np.flatnonzero(train['date'].isin(train_dates).to_numpy())
        va_idx = np.flatnonzero(train['date'].isin(val_dates).to_numpy())
        if 'label_end_date' in train:
            mature = (pd.to_datetime(train['label_end_date']) < pd.Timestamp(val_dates[0])).to_numpy()
            tr_idx = tr_idx[mature[tr_idx]]
        if tr_idx.size and va_idx.size:
            splits.append((tr_idx, va_idx))
    return splits


def _section_auc(y_true: pd.Series, probability: np.ndarray,
                 dates: pd.Series) -> float | None:
    """每个截面分别计算 AUC，再对日期等权平均。"""
    frame = pd.DataFrame({
        'date': dates.to_numpy(), 'target': y_true.to_numpy(), 'prob': probability,
    })
    scores = []
    for _, group in frame.groupby('date'):
        if len(group) >= 8 and group['target'].nunique() == 2:
            scores.append(roc_auc_score(group['target'], group['prob']))
    return float(np.mean(scores)) if scores else None


def optimize_hyperparameters(train: pd.DataFrame, feature_cols: list,
                              n_trials: int = 25,
                              candidate_factors: list = None) -> dict:
    """Optuna 寻优；折内按日期分组、隔离标签并在折内重新筛选因子。"""
    y = train['target_up']
    if len(train) < 200 or y.nunique() < 2 or n_trials <= 1:
        return dict(DEFAULT_PARAMS)

    dates = np.sort(train['date'].unique())
    n_splits = min(3, max(2, len(dates) // 250))
    folds = _date_grouped_splits(train, n_splits=n_splits)
    if not folds:
        return dict(DEFAULT_PARAMS)

    fold_data = []
    for tr_idx, va_idx in folds:
        fold_train = train.iloc[tr_idx]
        fold_val = train.iloc[va_idx]
        if candidate_factors:
            fold_report = diagnose_all(fold_train, candidate_factors)
            fold_factors, _ = factors_for_model(fold_report)
            fold_features = [f + '_neu' for f in fold_factors]
        else:
            fold_features = feature_cols
        fold_features = [f for f in fold_features
                         if f in fold_train.columns and f in fold_val.columns]
        if fold_features:
            fold_data.append((fold_train, fold_val, fold_features))
    if not fold_data:
        return dict(DEFAULT_PARAMS)

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 100, 400),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2, log=True),
            'max_depth': trial.suggest_int('max_depth', 3, 8),
            'num_leaves': trial.suggest_int('num_leaves', 8, 63),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'subsample_freq': 1,
            'n_jobs': 4,
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-4, 5.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-4, 5.0, log=True),
            'random_state': 42,
            'verbose': -1,
        }

        scores = []
        for fold_train, fold_val, fold_features in fold_data:
            X_tr, X_va = fold_train[fold_features], fold_val[fold_features]
            y_tr, y_va = fold_train['target_up'], fold_val['target_up']
            if y_tr.nunique() < 2 or y_va.nunique() < 2:
                continue
            model = lgb.LGBMClassifier(**params)
            model.fit(X_tr, y_tr)
            try:
                prob = model.predict_proba(X_va)[:, 1]
                score = _section_auc(y_va, prob, fold_val['date'])
                if score is not None:
                    scores.append(score)
            except ValueError:
                pass

        return float(np.mean(scores)) if scores else 0.5

    try:
        study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        best = dict(study.best_params)
        best['random_state'] = 42
        best['verbose'] = -1
        best['subsample_freq'] = 1
        best['n_jobs'] = 4
        print(f"[Optuna] 最优验证 AUC: {study.best_value:.4f}（{n_trials} 轮）")
        return best
    except Exception as e:
        print(f"[Optuna] 寻优异常，回退默认参数: {e}")
        return dict(DEFAULT_PARAMS)


def train_market_model(panel: pd.DataFrame = None, n_trials: int = 20,
                       force_retrain: bool = False, codes: list = None,
                       candidate_factors: list = None, training_plan: dict = None) -> dict:
    """训练市场通用模型并返回模型、切分数据与指标。

    Returns:
        dict，含 model / panel / train / val / test / metrics / params
    """
    model_file = os.path.join(SAVED_MODELS_DIR, "lgbm_market_classifier.pkl")

    if not force_retrain and os.path.exists(model_file):
        try:
            saved = joblib.load(model_file)
            if saved.get('feature_cols') == get_model_features():
                print("[Train] 复用已保存模型（特征集一致）")
                return saved
            print("[Train] 特征集已变更，强制重训")
        except Exception:
            pass

    if panel is None:
        panel = build_factor_panel(codes)

    train, val, test = time_split(panel)
    if training_plan is not None:
        from ml_pipeline.model_selection import fit_frame
        train = fit_frame(train, training_plan['selected_profile'])

    feature_cols = get_model_features()
    missing = [col for col in feature_cols if col not in panel.columns]
    if missing:
        raise ValueError(f"面板缺少模型特征: {missing}")
    X_tr, y_tr = train[feature_cols], train['target_up']
    X_va, y_va = val[get_model_features()], val['target_up']

    print(f"[Train] 训练集 {len(train)} 行 / 验证集 {len(val)} 行 / 测试集 {len(test)} 行")
    print(f"[Train] 正样本占比 — 训练 {y_tr.mean():.3f} / 验证 {y_va.mean():.3f}")

    params = dict(training_plan['params']) if training_plan else optimize_hyperparameters(
        train, feature_cols, n_trials=n_trials,
        candidate_factors=candidate_factors,
    )
    print(f"[Train] 采用超参: {params}")

    # 轮数在训练期内固定/选择，不根据外部验证集或测试集早停。
    model = lgb.LGBMClassifier(**params)
    evals_result = {}
    model.fit(
        X_tr,
        y_tr,
        sample_weight=date_weights(train) if training_plan else None,
        eval_set=[(X_tr, y_tr), (X_va, y_va)],
        eval_names=['train', 'validation'],
        eval_metric='binary_logloss',
        callbacks=[lgb.record_evaluation(evals_result)],
    )

    # 记录每轮训练/验证对数损失供可视化和论文分析；不据此对测试集调参。
    train_loss = evals_result.get('train', {}).get('binary_logloss', [])
    validation_loss = evals_result.get('validation', {}).get('binary_logloss', [])
    loss_history = {
        'metric': 'binary_logloss',
        'iterations': list(range(1, min(len(train_loss), len(validation_loss)) + 1)),
        'train': [float(v) for v in train_loss],
        'validation': [float(v) for v in validation_loss],
    }

    # 指标只在验证集与测试集上计算，训练集仅作参考
    metrics = {}
    for name, split in (('train', train), ('val', val), ('test', test)):
        y_true = split['target_up']
        prob = model.predict_proba(split[get_model_features()])[:, 1]
        metrics[name] = {
            'auc': round(float(roc_auc_score(y_true, prob)), 4) if y_true.nunique() > 1 else None,
            'section_auc': (round(_section_auc(y_true, prob, split['date']), 4)
                            if _section_auc(y_true, prob, split['date']) is not None else None),
            'accuracy': round(float(accuracy_score(y_true, (prob >= 0.5).astype(int))), 4),
            'n_rows': int(len(split)),
            'n_dates': int(split['date'].nunique()),
            'pos_rate': round(float(y_true.mean()), 4),
        }

    print(f"[Train] 验证 AUC={metrics['val']['auc']}  测试 AUC={metrics['test']['auc']}")

    from ml_pipeline.calibration import fit_calibrator, calibrate_margin, reliability
    from ml_pipeline.selection import fit_factor_ranker
    calibration = fit_calibrator(model, val, feature_cols)
    factor_ranker = fit_factor_ranker(train, feature_cols)
    calibration_report = {'calibrator': calibration, 'evaluations': {}}
    for name, split in [('validation_fit', val), ('held_out_test', test)]:
        margin = model.predict(split[feature_cols], raw_score=True)
        probability = model.predict_proba(split[feature_cols])[:, 1]
        calibrated = calibrate_margin(margin, calibration)
        calibration_report['evaluations'][name] = {
            'rows': len(split), 'raw': reliability(split.target_up, probability),
            'calibrated': reliability(split.target_up, calibrated),
        }
    os.makedirs(SAVED_MODELS_DIR, exist_ok=True)
    with open(os.path.join(SAVED_MODELS_DIR, 'calibration_report.json'), 'w', encoding='utf-8') as handle:
        import json
        json.dump(calibration_report, handle, ensure_ascii=False, indent=2, allow_nan=False)

    result = {
        'model': model,
        'panel': panel,
        'train': train,
        'val': val,
        'test': test,
        'metrics': metrics,
        'params': params,
        'loss_history': loss_history,
        'feature_cols': get_model_features(),
        'label_mode': 'excess',
        'label_definition': 'probability of exceeding the same-date candidate-universe mean over the next five sessions',
        'calibration': calibration,
        'factor_ranker': factor_ranker,
        'model_selection': training_plan,
    }

    os.makedirs(SAVED_MODELS_DIR, exist_ok=True)
    # 为轻量持久化与 Git 提交，裁剪保存包中的冗余大体积全量面板，压缩存储
    cols_to_keep = list(dict.fromkeys(['date', 'stock_code', 'ret_5d_fwd', 'excess_ret_5d', 'industry', 'score_lgb', 'target_up', 'label_end_date', 'entry_date', 'pct_chg'] + get_model_features() + [c for c in (candidate_factors or []) if c in train.columns]))
    train_sub = train[[c for c in cols_to_keep if c in train.columns]].copy()
    test_sub = test[[c for c in cols_to_keep if c in test.columns]].copy()
    # 保留模型输入和收益的完整精度，避免保存后改变树分支或回测结果。

    saved_payload = {
        'model': model,
        'train': train_sub,
        'test': test_sub,
        'metrics': metrics,
        'params': params,
        'loss_history': loss_history,
        'feature_cols': get_model_features(),
        'label_mode': 'excess',
        'label_definition': 'probability of exceeding the same-date candidate-universe mean over the next five sessions',
        'calibration': calibration,
        'factor_ranker': factor_ranker,
        'model_selection': training_plan,
    }
    joblib.dump(saved_payload, model_file, compress=3)
    print(f"[Train] 模型已保存: {model_file}")
    return result


def predict_signal(code: str, model, df: pd.DataFrame = None, panel: pd.DataFrame = None) -> dict:
    """对单只股票的最新截面做预测。

    模型训练用的是「行业中性化 + 标准化」后的因子列，因此推理端必须
    从完整横截面取值。LightGBM 原生处理缺失值，单股缺失因子不填成零。
    """
    clean_code = str(code).zfill(6)

    # 中性化与标准化必须依赖完整日期截面；单只股票独立处理会令特征失真。
    if panel is None or panel.empty:
        return None
    missing = [c for c in get_model_features() if c not in panel.columns]
    if missing:
        return None
    sub = panel[panel['stock_code'].astype(str).str.zfill(6) == clean_code]
    if sub.empty:
        return None
    latest_date = panel['date'].max()
    sub = sub[sub['date'] == latest_date]
    if sub.empty:
        return None
    latest_row = sub.iloc[-1]
    X = latest_row[get_model_features()].to_frame().T.astype(float)
    if np.isinf(X.to_numpy(dtype=float)).any():
        return None
    prob = float(model.predict_proba(X)[0, 1])

    # 分档必须在完整候选池排序后生成，单股原始分数不代替校准概率。
    rating = None

    latest_pct = float(latest_row.get('pct_chg', 0.0))
    latest_close = float(latest_row.get('close', 0.0))
    latest_date = latest_row['date']
    latest_date = latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else str(latest_date)

    return {
        'code': clean_code,
        'probability': prob,
        'rating': rating,
        'is_limit_up': '是' if flag_signal_limit(clean_code, latest_pct) else '否',
        'close': round(latest_close, 2),
        'pct_chg': round(latest_pct, 2),
        'update_date': latest_date,
        'features': {
            c: (float(X.iloc[0][c]) if pd.notna(X.iloc[0][c]) else None)
            for c in get_model_features()
        },
        'raw_features': {
            c: (round(float(latest_row[c]), 4) if pd.notna(latest_row.get(c)) else None)
            for c in FEATURE_COLS if c in latest_row.index
        },
    }
