"""Point-in-time screening and a training-only, interpretable factor comparator."""
import json
import numpy as np
import pandas as pd

from config.config import FEATURE_NAMES_CN
from ml_pipeline.factor_diagnosis import compute_ic_series, hac_t_stat
from ml_pipeline.calibration import calibrate_margin


def fit_factor_ranker(train, features):
    if 'excess_ret_5d' not in train:
        return {'status': 'missing_return_labels', 'factors': []}
    records = []
    for feature in features:
        ic = compute_ic_series(train, feature, ret_col='excess_ret_5d')
        if not len(ic):
            continue
        mean = float(ic.mean())
        records.append({'feature': feature, 'name_cn': FEATURE_NAMES_CN.get(feature.removesuffix('_neu'), feature),
                        'ic': mean, 'hac_t': hac_t_stat(ic.to_numpy()), 'direction': 1 if mean >= 0 else -1,
                        'weight': abs(mean)})
    total = sum(r['weight'] for r in records)
    if total <= 1e-12:
        return {'factors': [], 'status': 'insufficient_training_signal'}
    for record in records:
        record['weight'] /= total
    return {'status': 'fitted', 'factors': records, 'fit_source': 'training_only',
            'fit_period': [str(train.date.min())[:10], str(train.date.max())[:10]],
            'method': 'abs_training_rank_ic_weighted_directional_percentiles',
            'note': '多因子分数为 0–100 的对照排名，不是跑赢概率；默认排序仍使用 LightGBM。'}


def screen_candidates(frame, as_of_date, min_amount=0.0, exclude_limit_up=False):
    """Use signal-time data only. Unknown data fails screening, with explicit reasons."""
    frame = frame.copy()
    reasons = [[] for _ in range(len(frame))]
    def reject(mask, reason):
        for position in np.flatnonzero(np.asarray(mask, dtype=bool)):
            reasons[position].append(reason)
    date_column = frame.get('更新日期', pd.Series('', index=frame.index)).astype(str)
    reject(date_column != str(as_of_date), '行情日期不一致')
    price = pd.to_numeric(frame.get('最新收盘价', pd.Series(np.nan, index=frame.index)), errors='coerce')
    reject(~np.isfinite(price) | (price <= 0), '缺少有效价格')
    volume = pd.to_numeric(frame.get('volume', pd.Series(np.nan, index=frame.index)), errors='coerce')
    reject(~np.isfinite(volume) | (volume <= 0), '当日无成交或成交量未知')
    history = pd.to_numeric(frame.get('history_days', pd.Series(np.nan, index=frame.index)), errors='coerce')
    reject(history.isna() | (history < 120), '历史行情不足120个有效交易日')
    names = frame.get('名称', pd.Series('', index=frame.index)).astype(str)
    reject(names.str.contains(r'ST|退', case=False, regex=True, na=False), '当前名称含风险警示标记')
    if min_amount > 0:
        amount = pd.to_numeric(frame.get('avg_amount_20d', pd.Series(np.nan, index=frame.index)), errors='coerce')
        reject(~np.isfinite(amount) | (amount < min_amount), '20日平均成交额未达筛选门槛')
    if exclude_limit_up:
        reject(frame.get('是否涨停', pd.Series('未知', index=frame.index)).isin(['是', '未知']), '信号日涨停或状态未知')
    frame['rule_reasons'] = [json.dumps(r, ensure_ascii=False) for r in reasons]
    frame['rule_eligible'] = [not r for r in reasons]
    counts = {}
    for row in reasons:
        for reason in row:
            counts[reason] = counts.get(reason, 0) + 1
    return frame, {'input_count': len(frame), 'eligible_count': sum(not r for r in reasons),
                   'excluded_count': sum(bool(r) for r in reasons), 'reason_counts': counts,
                   'policy': {'min_history_days': 120, 'min_avg_amount_20d': min_amount,
                              'exclude_signal_limit_up': exclude_limit_up},
                   'note': '筛选仅使用信号日已知数据；不保证下一交易日可成交。筛选不重新计算历史回测。'}


def enrich_recommendations(frame, panel, bundle):
    """Persist full-precision inputs, factor evidence, and calibrated output together."""
    latest = panel[panel.date == panel.date.max()].copy()
    latest['stock_code'] = latest.stock_code.astype(str).str.zfill(6)
    lookup = latest.set_index('stock_code')
    result = frame.copy()
    codes = result['代码'].astype(str).str.zfill(6)
    for field in ['volume', 'avg_amount_20d', 'history_days']:
        result[field] = codes.map(lookup[field]) if field in lookup else np.nan
    calibration = bundle.get('calibration') if bundle else None
    if calibration:
        features = bundle['feature_cols']
        margins = bundle['model'].predict(result[features], raw_score=True)
        result['calibrated_probability'] = calibrate_margin(margins, calibration)
        result['calibration_status'] = (
            'weak_validation_signal_constant'
            if calibration.get('weak_validation_signal')
            else ('oof_fitted' if calibration.get('fit_source') == 'oof_cross_validation' else 'validation_fitted')
        )
    else:
        result['calibrated_probability'] = np.nan
        result['calibration_status'] = 'not_fitted'
    factors = (bundle or {}).get('factor_ranker', {}).get('factors', [])
    scores = np.zeros(len(result))
    coverage = np.zeros(len(result))
    breakdown = [[] for _ in range(len(result))]
    for spec in factors:
        if spec['feature'] not in result:
            continue
        values = pd.to_numeric(result[spec['feature']], errors='coerce')
        percentiles = (values * spec['direction']).rank(pct=True, method='average')
        valid = percentiles.notna().to_numpy()
        scores += percentiles.fillna(0).to_numpy() * spec['weight']
        coverage += valid * spec['weight']
        for i, percentile in enumerate(percentiles):
            breakdown[i].append({**spec, 'percentile': float(percentile) if pd.notna(percentile) else None,
                                 'contribution': float(percentile * spec['weight'] * 100) if pd.notna(percentile) else None})
    result['factor_score'] = np.where(coverage >= 1 - 1e-9, scores * 100, np.nan) if factors else np.nan
    result['factor_breakdown'] = [json.dumps(row, ensure_ascii=False) for row in breakdown]
    result['factor_rank'] = result['factor_score'].rank(ascending=False, method='min').astype('Int64')
    result, _ = screen_candidates(result, str(latest.date.max())[:10])
    return result
