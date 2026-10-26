# -*- coding: utf-8 -*-
"""策略参数敏感性与鲁棒性分析 (Parameter Sensitivity & Cliff Detection)

依据《Machine Learning for Algorithmic Trading》第 16 章规范：
1. 遍历组合规模 Top-K (K=5, 10, 15, 20) 与执行滑点 (0, 5, 10, 15 bps) 参数网格；
2. 计算各参数组合下的夏普比率、年化收益率、最大回撤与胜率；
3. 量化鲁棒性比率 (Robustness = 盈利参数组合占比)；
4. 断崖检测 (Cliff Detection)：检验相邻参数间是否存在剧烈性能跳水，防范过拟合尖峰；
5. 持久化至 saved_models/sensitivity_analysis.json 供前端研报展示。
"""

import json
import os
import sys
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd

from config.config import SAVED_MODELS_DIR
from ml_pipeline.backtest import run_backtest


def run_parameter_sensitivity(model_path: str = None) -> Dict[str, Any]:
    """执行参数网格遍历并检测过拟合断崖。"""
    if model_path is None:
        model_path = os.path.join(SAVED_MODELS_DIR, 'lgbm_market_classifier.pkl')

    if not os.path.exists(model_path):
        return {'error': '未找到模型权重文件'}

    bundle = joblib.load(model_path)
    model = bundle.get('model')
    feats = bundle.get('feature_cols', [])
    test_df = bundle.get('test')

    if model is None or test_df is None or not feats:
        return {'error': '模型对象内缺少必要组件'}

    test = test_df.copy()
    test['score_lgb'] = model.predict_proba(test[feats])[:, 1]

    # 定义敏感性网格
    k_list = [5, 10, 15, 20]
    slippage_bps_list = [0, 5, 10, 15]  # bps (1 bps = 0.0001)

    grid_results = []
    sharpe_matrix = {}

    for k in k_list:
        sharpe_matrix[str(k)] = {}
        for bps in slippage_bps_list:
            slippage_rate = bps / 10000.0
            bt = run_backtest(test, k=k, selection='neutral', slippage_rate=slippage_rate)
            strat = bt.get('strategy', {})
            excess = bt.get('excess', {})

            sr = strat.get('sharpe', 0.0)
            ann_ret = strat.get('annualized_return', 0.0)
            mdd = strat.get('max_drawdown', 0.0)
            win_rate = strat.get('win_rate', 0.0)
            calmar = strat.get('calmar', 0.0)
            excess_ann = excess.get('annualized_return', 0.0)

            record = {
                'k': k,
                'slippage_bps': bps,
                'slippage_rate': slippage_rate,
                'annualized_return': round(ann_ret, 4),
                'sharpe': round(sr, 4),
                'max_drawdown': round(mdd, 4),
                'win_rate': round(win_rate, 4),
                'calmar': round(calmar, 4),
                'excess_annualized_return': round(excess_ann, 4),
            }
            grid_results.append(record)
            sharpe_matrix[str(k)][str(bps)] = round(sr, 4)

    # 计算鲁棒性比例: 夏普 > 0 的比例
    sharpes = np.array([r['sharpe'] for r in grid_results])
    robustness_ratio = float(np.mean(sharpes > 0.0))
    mean_sharpe = float(np.mean(sharpes))
    std_sharpe = float(np.std(sharpes))

    # 断崖检测 (Cliff Detection)
    cliffs = []
    # 检查随 K 变化的梯度
    for bps in slippage_bps_list:
        sub_k = [r for r in grid_results if r['slippage_bps'] == bps]
        sub_k.sort(key=lambda x: x['k'])
        for i in range(len(sub_k) - 1):
            diff = abs(sub_k[i+1]['sharpe'] - sub_k[i]['sharpe'])
            if std_sharpe > 1e-4 and diff > 2.0 * std_sharpe:
                cliffs.append({
                    'param': 'k',
                    'transition': f"K={sub_k[i]['k']} -> K={sub_k[i+1]['k']} (滑点{bps}bps)",
                    'delta_sharpe': round(diff, 4),
                    'severity': 'HIGH' if diff > 3.0 * std_sharpe else 'MEDIUM'
                })

    is_robust = robustness_ratio >= 0.85 and len(cliffs) == 0

    if is_robust:
        assessment = '✅ 策略在多维参数空间展现出高平原性与优异鲁棒性，未发现过拟合断崖。'
    elif robustness_ratio >= 0.70:
        assessment = '⚠️ 策略在不同参数邻域存在一定收益波动，需持续关注高摩擦场景下的抗压能力。'
    else:
        assessment = '🚨 策略对参数变动极度敏感，存在过拟合尖峰风险。'

    report = {
        'updated_at': str(pd.Timestamp.now())[:19],
        'grid_size': len(grid_results),
        'k_range': k_list,
        'slippage_bps_range': slippage_bps_list,
        'robustness_ratio': round(robustness_ratio, 4),
        'mean_sharpe': round(mean_sharpe, 4),
        'std_sharpe': round(std_sharpe, 4),
        'is_robust': is_robust,
        'assessment': assessment,
        'cliff_count': len(cliffs),
        'cliffs': cliffs,
        'sharpe_matrix': sharpe_matrix,
        'grid_results': grid_results,
    }

    out_path = os.path.join(SAVED_MODELS_DIR, 'sensitivity_analysis.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print("Running parameter sensitivity analysis...")
    rep = run_parameter_sensitivity()
    print("Assessment:", rep.get('assessment'))
    print(f"Robustness: {rep.get('robustness_ratio')*100:.1f}%, Mean Sharpe: {rep.get('mean_sharpe'):.4f}")
    print("Sharpe Matrix (K vs Slippage BPS):")
    for k, row in rep.get('sharpe_matrix', {}).items():
        print(f"  K={k:>2s}: {row}")
