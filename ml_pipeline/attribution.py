# -*- coding: utf-8 -*-
"""业绩归因：Alpha / Beta 分解与显著性检验

为什么需要这一层
----------------
回测报出的「超额年化」回答不了最要紧的问题：这个超额是选股能力（alpha），
还是仅仅因为承担了更多市场风险（beta）？

本项目实测：策略 beta = 1.1431、R² = 0.7396。也就是说策略收益约四分之三
可由市场收益解释。若不拆开，把 beta 暴露带来的收益记成「模型有效」，是
典型的业绩归因错误。

检验内容
--------
1. OLS 回归：r_p = alpha + beta * r_b + e
   - beta 是否显著大于 1（是否承担了超额市场风险）
   - alpha 是否显著异于 0（是否存在真实选股能力）
2. 信息比率 IR = 超额均值 / 跟踪误差，衡量相对基准的稳定性
3. 分市场状态：按基准涨跌分组，观察超额是否随市场方向漂移
   —— 若下跌市超额为负、上涨市超额为正，说明超额同样来自 beta
4. Beta 中性化模拟：剥离 beta 后剩下的收益，是纯选股能力的上界估计
"""

import json
import os

import numpy as np
import pandas as pd

from config.config import SAVED_MODELS_DIR, TARGET_DAYS

PERIODS_PER_YEAR = 242 / TARGET_DAYS


def _nav_to_returns(nav: list) -> np.ndarray:
    """由净值序列反推每期收益。"""
    arr = np.asarray(nav, dtype=float)
    if arr.size < 2:
        return np.array([])
    prev = np.concatenate(([1.0], arr[:-1]))
    return arr / prev - 1.0


def _ols(rs: np.ndarray, rb: np.ndarray, periods_per_year: float) -> dict:
    """OLS 回归并用 Newey-West 协方差估计标准误。"""
    from scipy import stats

    X = np.column_stack([np.ones(len(rb)), rb])
    coef, _, _, _ = np.linalg.lstsq(X, rs, rcond=None)
    alpha, beta = float(coef[0]), float(coef[1])

    resid = rs - X @ coef
    dof = len(rs) - 2
    sigma2 = float(resid @ resid / dof) if dof > 0 else 0.0
    try:
        bread = np.linalg.inv(X.T @ X)
        scores = X * resid[:, None]
        meat = scores.T @ scores
        max_lag = min(TARGET_DAYS - 1, max(0, len(rs) - 1))
        for lag in range(1, max_lag + 1):
            weight = 1.0 - lag / (max_lag + 1.0)
            cross = scores[lag:].T @ scores[:-lag]
            meat += weight * (cross + cross.T)
        cov = bread @ meat @ bread
        se_alpha, se_beta = float(np.sqrt(max(cov[0, 0], 0))), float(np.sqrt(max(cov[1, 1], 0)))
    except np.linalg.LinAlgError:
        se_alpha = se_beta = float('nan')

    t_alpha = alpha / se_alpha if se_alpha else 0.0
    t_beta = (beta - 1.0) / se_beta if se_beta else 0.0

    p_alpha = 2 * (1 - stats.t.cdf(abs(t_alpha), dof)) if dof > 0 else 1.0
    p_beta_gt1 = 1 - stats.t.cdf(t_beta, dof) if dof > 0 else 1.0

    ss_tot = float((rs - rs.mean()) @ (rs - rs.mean()))
    r2 = 1 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0

    return {
        'alpha_period': round(alpha, 6),
        'alpha_annual': round(alpha * periods_per_year, 4),
        'alpha_se_period': round(se_alpha, 6),
        'alpha_t': round(t_alpha, 3),
        'alpha_p': round(p_alpha, 4),
        'alpha_ci95_annual': [
            round((alpha - 1.96 * se_alpha) * periods_per_year, 4),
            round((alpha + 1.96 * se_alpha) * periods_per_year, 4),
        ],
        'beta': round(beta, 4),
        'beta_se': round(se_beta, 4),
        'beta_t_vs_1': round(t_beta, 2),
        'beta_p_gt1': round(p_beta_gt1, 4),
        'r_squared': round(r2, 4),
        'dof': int(dof),
        'alpha_significant': bool(p_alpha < 0.05),
        'beta_above_one': bool(p_beta_gt1 < 0.05),
    }


def _beta_neutral(rp: np.ndarray, rb: np.ndarray, beta: float,
                  periods_per_year: float) -> dict:
    """剥离 beta 暴露后的残余收益表现。"""
    adj = rp - beta * rb
    nav = np.cumprod(1.0 + adj)
    total = float(nav[-1] - 1.0)
    n = len(adj)
    ann = float((1.0 + total) ** (periods_per_year / n) - 1.0) if n else 0.0
    std = float(np.std(adj, ddof=1)) if n > 1 else 0.0
    sharpe = float(np.mean(adj) / std * np.sqrt(periods_per_year)) if std > 0 else 0.0
    peak = np.maximum.accumulate(np.r_[1.0, nav])[1:]
    dd = (nav - peak) / peak
    return {
        'annualized_return': round(float(ann), 4),
        'annualized_volatility': round(float(std * np.sqrt(periods_per_year)), 4),
        'sharpe': round(float(sharpe), 4),
        'max_drawdown': round(float(dd.min()), 4),
    }


def _regime_analysis(rs: np.ndarray, rb: np.ndarray, n_bins: int = 5) -> list:
    """按基准收益分组，观察策略超额是否随市场方向变化。"""
    df = pd.DataFrame({'rp': rs, 'rb': rb})
    try:
        df['regime'] = pd.qcut(df['rb'], n_bins, labels=False)
    except ValueError:
        return []

    labels = ['最差 20%', '较差', '中等', '较好', '最好 20%']
    out = []
    for g, sub in df.groupby('regime'):
        gi = int(g)
        out.append({
            'regime': labels[gi] if gi < len(labels) else f'Q{gi + 1}',
            'n_periods': int(len(sub)),
            'benchmark_mean': round(float(sub['rb'].mean()), 6),
            'strategy_mean': round(float(sub['rp'].mean()), 6),
            'excess_mean': round(float(sub['rp'].mean() - sub['rb'].mean()), 6),
        })
    return out


def analyze_attribution(backtest_aggregated: dict = None) -> dict:
    """对拼接净值做完整的 Alpha/Beta 归因。

    Args:
        backtest_aggregated: walk_forward 的 backtest_aggregated 字段；
                             缺省时从磁盘读取 walk_forward.json

    Returns:
        归因结果字典
    """
    if backtest_aggregated is None:
        wf_path = os.path.join(SAVED_MODELS_DIR, 'walk_forward.json')
        if not os.path.exists(wf_path):
            return {'error': '缺少 walk_forward.json，请先运行训练脚本'}
        with open(wf_path, 'r', encoding='utf-8') as f:
            wf = json.load(f)
        backtest_aggregated = wf.get('backtest_aggregated') or {}

    if not backtest_aggregated.get('strategy'):
        return {'error': '缺少拼接净值数据'}

    periods_per_year = float(backtest_aggregated.get('params', {}).get('periods_per_year', PERIODS_PER_YEAR))

    rs = _nav_to_returns(backtest_aggregated['strategy']['nav'])
    rb = _nav_to_returns(backtest_aggregated['benchmark']['nav'])
    n = min(len(rs), len(rb))
    if n < 30:
        return {'error': f'有效周期仅 {n} 个，不足以做归因'}

    rs, rb = rs[:n], rb[:n]

    ols = _ols(rs, rb, periods_per_year)

    # 超额序列
    excess = rs - rb
    te = float(np.std(excess, ddof=1))
    ir = float(np.mean(excess) / te * np.sqrt(periods_per_year)) if te > 0 else 0.0
    from scipy import stats
    from ml_pipeline.factor_diagnosis import hac_t_stat
    t_excess = hac_t_stat(excess)
    p_excess = float(2 * (1 - stats.t.cdf(abs(t_excess), max(1, n - TARGET_DAYS))))

    neutral = _beta_neutral(rs, rb, ols['beta'], periods_per_year)
    regimes = _regime_analysis(rs, rb)

    # 超额是否随市场方向单调变化——若是，说明超额同样来自 beta
    excess_by_regime = [r['excess_mean'] for r in regimes]
    monotonic_with_market = bool(
        len(excess_by_regime) >= 3 and
        all(np.diff(excess_by_regime) > 0) or all(np.diff(excess_by_regime) < 0)
    ) if len(excess_by_regime) >= 3 else False

    return {
        'periods': int(n),
        'periods_per_year': periods_per_year,
        'regression': ols,
        'relative': {
            'excess_mean_period': round(float(np.mean(excess)), 6),
            'tracking_error_annual': round(te * np.sqrt(PERIODS_PER_YEAR), 4),
            'information_ratio': round(ir, 4),
            'excess_t': round(t_excess, 3),
            'excess_p': round(p_excess, 4),
            'excess_significant': bool(p_excess < 0.05),
        },
        'beta_neutralized': neutral,
        'regime': regimes,
        'excess_monotonic_with_market': monotonic_with_market,
        'conclusion': _build_conclusion(ols, ir, p_excess, neutral,
                                        monotonic_with_market, t_excess,
                                        te * np.sqrt(PERIODS_PER_YEAR)),
        'note': ('Beta 衡量策略对市场整体涨跌的敏感度；Alpha 是剥离市场影响后的'
                 '选股能力。R² 表示策略收益中被市场解释的比例。'),
    }


def _build_conclusion(ols: dict, ir: float, p_excess: float,
                      neutral: dict, monotonic: bool,
                      t_excess: float = 0.0, te_annual: float = 0.0) -> dict:
    """把统计结果翻译成明确、无歧义的结论陈述。"""
    points = []

    if ols['beta_above_one']:
        points.append(
            f"策略 beta = {ols['beta']:.4f}，显著大于 1（p = {ols['beta_p_gt1']:.4f}），"
            f"说明策略承担了高于市场的系统性风险。"
        )

    points.append(
        f"回归 R² = {ols['r_squared']:.4f}，即策略收益中约 "
        f"{ols['r_squared'] * 100:.1f}% 可由市场收益解释。"
    )

    if ols['alpha_significant']:
        points.append(
            f"Jensen alpha 年化 {ols['alpha_annual']:.2%}，统计显著"
            f"（t = {ols['alpha_t']:.2f}，p = {ols['alpha_p']:.4f}），存在真实选股能力。"
        )
    else:
        ci = ols['alpha_ci95_annual']
        points.append(
            f"Jensen alpha 年化 {ols['alpha_annual']:.2%}，但在统计上无法拒绝 alpha = 0"
            f"（t = {ols['alpha_t']:.2f}，p = {ols['alpha_p']:.4f}，"
            f"95% 置信区间 [{ci[0]:.2%}, {ci[1]:.2%}]）。"
        )

    # 这里必须用相对超额自身的 t 值，不能用 alpha 的 t 值：
    # 二者检验的是不同假设（alpha=0 与 超额均值=0），混用会得出错误结论。
    if p_excess < 0.05:
        points.append(
            f"相对基准的超额收益均值显著异于 0（t = {t_excess:.2f}，p = {p_excess:.4f}），"
            f"跟踪误差年化 {te_annual:.2%}，信息比率 IR = {ir:.4f}。"
        )
    else:
        points.append(
            f"相对基准的超额收益不显著（t = {t_excess:.2f}，p = {p_excess:.4f}），"
            f"信息比率 IR = {ir:.4f}。"
        )

    points.append(
        f"若完全对冲市场风险（beta 中性），策略年化仅 {neutral['annualized_return']:.2%}、"
        f"夏普 {neutral['sharpe']:.4f}、最大回撤 {neutral['max_drawdown']:.2%}，"
        f"说明策略的主要收益来源是市场暴露而非选股。"
    )

    if monotonic:
        points.append(
            "分市场状态看，超额收益随市场涨跌单调变化——上涨时跑赢、下跌时跑输，"
            "这进一步确认超额来自 beta 敞口，而非独立的选股能力。"
        )

    return {
        'points': points,
        'verdict': ('存在真实 alpha' if ols['alpha_significant']
                    else 'alpha 不显著，收益主要来自 beta 暴露'),
        'robust_alpha_annual': ols['alpha_annual'],
    }


def save_attribution(result: dict, path: str = None) -> str:
    if path is None:
        path = os.path.join(SAVED_MODELS_DIR, 'attribution.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[Attribution] 归因结果已保存: {path}")
    return path
