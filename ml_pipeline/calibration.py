"""Monotone Platt calibration fitted on a time-separated validation interval."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit


def reliability(y, probability, n_bins=10):
    y, probability = np.asarray(y, dtype=float), np.asarray(probability, dtype=float)
    groups = np.minimum((np.clip(probability, 0, 1) * n_bins).astype(int), n_bins - 1)
    bins = []
    for group in range(n_bins):
        selected = groups == group
        bins.append({'lower': group / n_bins, 'upper': (group + 1) / n_bins,
                     'count': int(selected.sum()),
                     'mean_prediction': float(probability[selected].mean()) if selected.any() else None,
                     'observed_rate': float(y[selected].mean()) if selected.any() else None})
    ece = sum(b['count'] / len(y) * abs(b['mean_prediction'] - b['observed_rate']) for b in bins if b['count'])
    return {'brier_score': float(np.mean((y - probability) ** 2)), 'ece': float(ece), 'bins': bins}


def fit_calibrator_from_margins(margins, targets, dates, source_name='validation_only', fit_period=None):
    margin = np.asarray(margins, dtype=float)
    target = np.asarray(targets, dtype=float)
    if len(margin) == 0 or np.unique(target).size < 2:
        raise ValueError('数据区间不足以拟合概率校准器')
    center, scale = float(margin.mean()), float(margin.std())
    scale = max(scale, 1e-8)
    x = (margin - center) / scale
    date_series = pd.Series(dates)
    counts = date_series.map(date_series.value_counts()).to_numpy(dtype=float)
    weights = 1.0 / counts
    weights /= weights.sum()
    prior = float(np.average(target, weights=weights))

    def objective(parameters):
        slope, intercept = parameters
        z = slope * x + intercept
        loss = np.sum(weights * (np.logaddexp(0, z) - target * z)) + 1e-6 * slope ** 2
        residual = weights * (expit(z) - target)
        gradient = np.array([np.dot(residual, x) + 2e-6 * slope, residual.sum()])
        return loss, gradient

    fit = minimize(objective, [1.0, float(logit(np.clip(prior, 1e-6, 1 - 1e-6)))],
                   jac=True, method='L-BFGS-B', bounds=[(0.0, 50.0), (-30.0, 30.0)])
    if not fit.success:
        raise RuntimeError(f'概率校准未收敛：{fit.message}')
    unique_dates = date_series.unique()
    if fit_period is None:
        fit_period = [str(min(unique_dates))[:10], str(max(unique_dates))[:10]]
    return {'method': 'monotone_platt', 'slope': float(fit.x[0]), 'intercept': float(fit.x[1]),
            'margin_center': center, 'margin_scale': scale,
            'fit_source': source_name, 'fit_rows': len(margin),
            'fit_dates': int(len(unique_dates)),
            'fit_period': fit_period,
            'date_weighting': 'equal_weight_per_date', 'ranking_policy': 'raw_lightgbm_score',
            'weak_validation_signal': bool(fit.x[0] <= 1e-6),
            'target': 'outperform_same_date_candidate_mean',
            'note': '校准概率不等于收益预测或置信区间；SHAP 解释原始 LightGBM log-odds。'}


def fit_calibrator_oof(train, features, params, n_splits=3):
    """基于训练集内部时序折样本外预测（OOF）拟合校准器，严格避免未来泄漏。"""
    from models.model_trainer import _date_grouped_splits
    import lightgbm as lgb

    folds = _date_grouped_splits(train, n_splits=n_splits)
    if not folds:
        raise ValueError('训练集不足以切分时序折')

    oof_margins, oof_targets, oof_dates = [], [], []
    for tr_idx, va_idx in folds:
        fold_train = train.iloc[tr_idx]
        fold_val = train.iloc[va_idx]
        clf = lgb.LGBMClassifier(**params)
        clf.fit(fold_train[features], fold_train['target_up'])
        margin = clf.predict(fold_val[features], raw_score=True)
        oof_margins.extend(margin)
        oof_targets.extend(fold_val['target_up'].tolist())
        oof_dates.extend(fold_val['date'].tolist())

    return fit_calibrator_from_margins(
        oof_margins, oof_targets, oof_dates,
        source_name='oof_cross_validation'
    )


def fit_calibrator(model, validation, features, train=None, params=None, fallback_to_oof=True):
    if validation.empty or validation.target_up.nunique() < 2:
        raise ValueError('验证区间不足以拟合概率校准器')
    margin = np.asarray(model.predict(validation[features], raw_score=True), dtype=float)
    target = validation.target_up.to_numpy(dtype=float)
    spec = fit_calibrator_from_margins(margin, target, validation['date'], source_name='validation_only')
    if spec.get('weak_validation_signal') and fallback_to_oof and train is not None and params is not None:
        try:
            oof_spec = fit_calibrator_oof(train, features, params)
            if not oof_spec.get('weak_validation_signal'):
                oof_spec['note'] = '验证集斜率归零（弱信号），已安全回退至训练期时序折样本外（OOF）校准。'
                return oof_spec
        except Exception:
            pass
    return spec


def calibrate_margin(margin, calibration):
    if not calibration or calibration.get('method') != 'monotone_platt':
        return None
    z = (np.asarray(margin, dtype=float) - calibration['margin_center']) / calibration['margin_scale']
    return expit(calibration['slope'] * z + calibration['intercept'])
