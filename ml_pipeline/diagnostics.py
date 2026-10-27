"""Diagnostics from held-out predictions and settled backtest periods only."""
import json
import os

import numpy as np
import pandas as pd
from config.config import SAVED_MODELS_DIR
from ml_pipeline.factor_diagnosis import compute_ic_series, hac_t_stat


def build_diagnostics(test: pd.DataFrame, backtest: dict, path=None) -> dict:
    y = test['target_up'].to_numpy(dtype=float)
    p = test['score_lgb'].to_numpy(dtype=float)
    groups = np.minimum((p * 10).astype(int), 9)
    bins = []
    for group in range(10):
        mask = groups == group
        bins.append({'lower': group / 10, 'upper': (group + 1) / 10,
                     'count': int(mask.sum()),
                     'mean_prediction': float(p[mask].mean()) if mask.any() else None,
                     'observed_rate': float(y[mask].mean()) if mask.any() else None})
    ece = sum(row['count'] / len(y) * abs(row['mean_prediction'] - row['observed_rate'])
              for row in bins if row['count'])
    ic = compute_ic_series(test, 'score_lgb', ret_col='excess_ret_5d')
    rolling = ic.rolling(20, min_periods=20).mean()
    months = {}
    for row in backtest.get('rebalance_ledger', []):
        date = row.get('exit_date')
        if not date:
            continue
        month = date[:7]
        item = months.setdefault(month, {'month': month, 'strategy': 1.0, 'benchmark': 1.0, 'gross': 1.0, 'periods': 0})
        item['strategy'] *= 1 + row['period_net_return']
        item['benchmark'] *= 1 + row['benchmark_return']
        item['gross'] *= 1 + row['period_gross_return']
        item['periods'] += 1
    monthly = []
    for item in months.values():
        monthly.append({**item, **{k: round(item[k] - 1, 6) for k in ['strategy', 'benchmark', 'gross']}})
    payload = {
        'source': 'held_out_test',
        'date_range': [str(test['date'].min())[:10], str(test['date'].max())[:10]],
        'calibration': {'bins': bins, 'brier_score': float(np.mean((p - y) ** 2)),
                        'ece': float(ece), 'samples': len(y), 'calibrated': False,
                        'note': '模型未经概率校准；仅用于诊断，不使用测试标签调整模型。'},
        'rank_ic': {'dates': [str(x)[:10] for x in ic.index],
                    'values': [round(float(x), 6) for x in ic],
                    'rolling_20': [round(float(x), 6) if pd.notna(x) else None for x in rolling],
                    'mean': float(ic.mean()) if len(ic) else None,
                    'hac_t': hac_t_stat(ic.to_numpy()) if len(ic) else None,
                    'n_dates': len(ic)},
        'monthly_settled_returns': monthly,
        'monthly_note': '按平仓月份复利汇总已完成持有期，不是逐日盯市月收益；首末月可能不完整。',
    }
    calibration_path = os.path.join(SAVED_MODELS_DIR, 'calibration_report.json')
    if os.path.exists(calibration_path):
        with open(calibration_path, encoding='utf-8') as handle:
            report = json.load(handle)
        payload['calibration']['comparison'] = report['evaluations']['held_out_test']
        payload['calibration']['calibrator'] = report['calibrator']
    path = path or os.path.join(SAVED_MODELS_DIR, 'diagnostics.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return payload
