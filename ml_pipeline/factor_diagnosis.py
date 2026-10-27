# -*- coding: utf-8 -*-
"""因子有效性诊断

为什么先诊断再入模
------------------
直接把十几个因子塞进模型，很可能得到与只用技术指标时相近的 AUC，
却说不清原因。先做单因子检验，才能回答三个问题：
  1. 这个因子在截面上到底有没有区分能力（IC 均值与 t 值）；
  2. 它的区分能力是否稳定（ICIR，即 IC 均值 / IC 标准差）；
  3. 排序是否单调（分层回测，Top 组是否真的优于 Bottom 组）。

指标口径
--------
IC     ：每个截面内，因子值与未来收益的 Spearman 秩相关
ICIR   ：IC 均值 / IC 标准差，衡量稳定性，> 0.3 视为可用
t 值    ：ICIR × sqrt(截面数)，> 2 视为统计显著
分层收益：按因子值分 5 组，看 Top 组与 Bottom 组的平均前瞻收益差
"""

import json
import os

import numpy as np
import pandas as pd

from config.config import FEATURE_NAMES_CN, SAVED_MODELS_DIR, TARGET_DAYS

# 单截面最少股票数。截面股票越多，秩相关的统计意义越强；
# 低于此值的截面直接跳过，避免噪声主导 IC 估计。
MIN_STOCKS_PER_SECTION = 8
N_QUANTILES = 5

# 因子入选门槛
MIN_ABS_IC = 0.015
MIN_T_STAT = 2.0


def hac_t_stat(values: np.ndarray, max_lag: int = TARGET_DAYS - 1) -> float:
    """Newey-West t 统计量，校正相邻 5 日前瞻收益造成的 IC 序列相关。"""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = arr.size
    if n < 2:
        return 0.0
    centered = arr - arr.mean()
    long_run_var = float(np.dot(centered, centered) / n)
    for lag in range(1, min(max_lag, n - 1) + 1):
        weight = 1.0 - lag / (max_lag + 1.0)
        covariance = float(np.dot(centered[lag:], centered[:-lag]) / n)
        long_run_var += 2.0 * weight * covariance
    if not np.isfinite(long_run_var) or long_run_var <= 0:
        return 0.0
    return float(arr.mean() / np.sqrt(long_run_var / n))


def compute_ic_series(panel: pd.DataFrame, factor: str,
                      ret_col: str = 'ret_5d_fwd') -> pd.Series:
    """逐截面计算因子与前瞻收益的 Spearman 相关。"""
    sub = panel[['date', factor, ret_col]].dropna().copy()
    grouped = sub.groupby('date', sort=True)
    ranks = grouped[[factor, ret_col]].rank(method='average')
    centered = ranks - ranks.groupby(sub['date']).transform('mean')
    cross = (centered[factor] * centered[ret_col]).groupby(sub['date']).sum()
    variance = centered.pow(2).groupby(sub['date']).sum()
    denominator = np.sqrt(variance[factor] * variance[ret_col])
    valid = (grouped.size() >= MIN_STOCKS_PER_SECTION) & (grouped[factor].nunique() >= 3)
    return (cross / denominator.where(denominator > 0)).where(valid).dropna()



def layered_returns(panel: pd.DataFrame, factor: str,
                    ret_col: str = 'ret_5d_fwd', n_groups: int = N_QUANTILES) -> list:
    """按因子值分层，返回各层平均前瞻收益（从低到高）。"""
    sub = panel[['date', factor, ret_col]].dropna().copy()
    grouped = sub.groupby('date')
    counts = grouped[factor].transform('size')
    sub = sub[counts >= MIN_STOCKS_PER_SECTION].copy()
    if sub.empty:
        return [None] * n_groups
    counts = sub.groupby('date')[factor].transform('size')
    rank = sub.groupby('date')[factor].rank(method='first')
    sub['_layer'] = (np.ceil((rank - 1) / (counts - 1) * n_groups).clip(lower=1) - 1).astype(int)
    means = sub.groupby(['date', '_layer'])[ret_col].mean().groupby('_layer').mean()
    return [round(float(means[i]), 6) if i in means else None for i in range(n_groups)]



def diagnose_factor(panel: pd.DataFrame, factor: str,
                    ret_col: str = 'ret_5d_fwd') -> dict:
    """对单个因子做完整诊断。"""
    ic = compute_ic_series(panel, factor, ret_col)
    if len(ic) < 20:
        return {
            'factor': factor,
            'usable': False,
            'reason': f'有效截面仅 {len(ic)} 个，样本不足',
        }

    ic_mean = float(ic.mean())
    ic_std = float(ic.std())
    icir = ic_mean / ic_std if ic_std > 0 else 0.0
    t_stat = hac_t_stat(ic.to_numpy())

    layers = layered_returns(panel, factor, ret_col)
    valid_layers = [x for x in layers if x is not None]
    monotonic = False
    spread = None
    if len(valid_layers) >= 3:
        diffs = np.diff(valid_layers)
        monotonic = bool(np.all(diffs > 0) or np.all(diffs < 0))
        spread = round(valid_layers[-1] - valid_layers[0], 6)

    return {
        'factor': factor,
        'name_cn': FEATURE_NAMES_CN.get(factor, factor),
        'n_sections': int(len(ic)),
        'ic_mean': round(ic_mean, 4),
        'ic_std': round(ic_std, 4),
        'icir': round(float(icir), 4),
        't_stat': round(float(t_stat), 2),
        't_stat_method': f'Newey-West HAC, max_lag={TARGET_DAYS - 1}',
        'ic_positive_ratio': round(float((ic > 0).mean()), 4),
        'layered_returns': layers,
        'top_minus_bottom': spread,
        'monotonic': monotonic,
        # 筛选标准：IC 有实际幅度 且 t 值统计显著。
        # 不使用 ICIR 硬门槛：IC 序列的日间波动本身很大，ICIR 普遍偏低，
        # 用它筛选会把 t 值已达 3~4 的有效因子误杀。
        'usable': bool(abs(ic_mean) >= MIN_ABS_IC and abs(t_stat) >= MIN_T_STAT),
    }


def _greedy_decorrelate(panel: pd.DataFrame, ordered: list,
                        max_corr: float = 0.7) -> tuple:
    """按重要性贪心选因子，剔除与已选因子高度相关的候选。

    为什么需要这一步：技术指标（EMA20_ratio、ma_gap、MACD_norm、momentum_20d）
    彼此高度相关，若只看 |IC| 门槛会把它们全部选入。这不仅让模型在少量
    重复信息上反复分裂，也会挤掉相关性低但独立信息量大的因子。

    返回 (保留列表, 被剔除的 {factor: 与谁冲突})。
    """
    cols = [f + '_neu' for f in ordered]
    available = [c for c in cols if c in panel.columns]
    if len(available) < 2:
        return ordered, {}

    corr = panel[available].corr().abs()

    kept, dropped = [], {}
    for f in ordered:
        col = f + '_neu'
        if col not in corr.columns:
            kept.append(f)
            continue
        conflict = None
        for k in kept:
            kc = k + '_neu'
            if kc in corr.columns and corr.loc[col, kc] > max_corr:
                conflict = k
                break
        if conflict:
            dropped[f] = {'conflicts_with': conflict,
                          'corr': round(float(corr.loc[col, conflict + '_neu']), 3)}
        else:
            kept.append(f)
    return kept, dropped


def diagnose_all(panel: pd.DataFrame, factors: list,
                 ret_col: str = 'ret_5d_fwd', representation: str = 'neutralized') -> dict:
    """批量诊断并输出汇总报告。"""
    if representation not in ('raw', 'neutralized'):
        raise ValueError('representation must be raw or neutralized')
    results = []
    for factor in factors:
        column = factor + '_neu' if representation == 'neutralized' else factor
        if column not in panel:
            continue
        result = diagnose_factor(panel, column, ret_col)
        result.update(factor=factor, input_column=column,
                      name_cn=FEATURE_NAMES_CN.get(factor, factor))
        results.append(result)
    results = [r for r in results if 'ic_mean' in r]
    results.sort(key=lambda x: abs(x['ic_mean']), reverse=True)

    # 第一层：统计显著性
    passed = [r['factor'] for r in results if r['usable']]

    # 第二层：相关性去冗余
    usable, dropped = _greedy_decorrelate(panel, passed)

    for r in results:
        if r['factor'] in dropped:
            r['rejected_reason'] = f"与 {dropped[r['factor']]['conflicts_with']} 高度相关" \
                                   f"（|r|={dropped[r['factor']]['corr']}）"
        elif r['factor'] in usable:
            r['rejected_reason'] = None
        elif r.get('usable'):
            r['rejected_reason'] = '被去冗余环节剔除'
        else:
            r['rejected_reason'] = 'IC 或 t 值未达门槛'
        r['in_model'] = r['factor'] in usable

    return {
        'results': results,
        'usable_factors': usable,
        'rejected_factors': [r['factor'] for r in results if r['factor'] not in usable],
        'decorrelation_dropped': dropped,
        'criteria': {
            'representation': representation,
            'min_abs_ic': MIN_ABS_IC,
            'min_abs_t': MIN_T_STAT,
            'max_pairwise_corr': 0.7,
            'min_sections': 20,
            't_stat_method': f'Newey-West HAC, max_lag={TARGET_DAYS - 1}',
        },
        'n_sections_total': int(panel['date'].nunique()),
        'n_stocks_total': int(panel['stock_code'].nunique()),
    }


def factors_for_model(report: dict, fallback_count: int = 5) -> tuple[list, str]:
    """返回训练期诊断出的因子；无因子通过门槛时仅按训练期 IC 选少量候选。"""
    selected = list(report.get('usable_factors') or [])
    if selected:
        return selected, 'ic_and_hac_t'
    ranked = [r['factor'] for r in sorted(
        report.get('results', []),
        key=lambda item: abs(item.get('ic_mean') or 0.0),
        reverse=True,
    ) if r.get('ic_mean') is not None]
    if not ranked:
        raise RuntimeError('训练期没有足够的有效截面来选择模型因子')
    return ranked[:fallback_count], 'training_period_top_ic_fallback'


def save_diagnosis(report: dict, path: str = None) -> str:
    if path is None:
        path = os.path.join(SAVED_MODELS_DIR, 'factor_diagnosis.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[Factor] 因子诊断结果已保存: {path}")
    return path
