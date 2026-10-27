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


def fit_calibrator(model, validation, features):
    if validation.empty or validation.target_up.nunique() < 2:
        raise ValueError('验证区间不足以拟合概率校准器')
    margin = np.asarray(model.predict(validation[features], raw_score=True), dtype=float)
    target = validation.target_up.to_numpy(dtype=float)
    center, scale = float(margin.mean()), float(margin.std())
    scale = max(scale, 1e-8)
    x = (margin - center) / scale
    weights = 1 / validation.groupby('date')['target_up'].transform('size').to_numpy(dtype=float)
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
    return {'method': 'monotone_platt', 'slope': float(fit.x[0]), 'intercept': float(fit.x[1]),
            'margin_center': center, 'margin_scale': scale,
            'fit_source': 'validation_only', 'fit_rows': len(validation),
            'fit_dates': int(validation.date.nunique()),
            'fit_period': [str(validation.date.min())[:10], str(validation.date.max())[:10]],
            'date_weighting': 'equal_weight_per_date', 'ranking_policy': 'raw_lightgbm_score',
            'weak_validation_signal': bool(fit.x[0] <= 1e-6),
            'target': 'outperform_same_date_candidate_mean',
            'note': '校准概率不等于收益预测或置信区间；SHAP 解释原始 LightGBM log-odds。'}


def calibrate_margin(margin, calibration):
    if not calibration or calibration.get('method') != 'monotone_platt':
        return None
    z = (np.asarray(margin, dtype=float) - calibration['margin_center']) / calibration['margin_scale']
    return expit(calibration['slope'] * z + calibration['intercept'])
