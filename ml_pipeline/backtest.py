# -*- coding: utf-8 -*-
"""Top-K 周期回测，支持池内排序和行业配额筛选。

每期在下一交易日开盘买入，第五个交易日收盘全额卖出；
两期之间持有现金，重复入选也重新承担双边费用。策略与等权基准
使用相同费率。回撤包含初始本金；净值仅在周期末估值。
信号日涨停仅为候选筛选，不保证下一开盘成交。
DSR 需要真实可比试验的数量与 Sharpe 分布，缺失时不计算。
"""

import json
import os

import numpy as np
import pandas as pd
from scipy import stats

from config.config import CACHE_DIR, SAVED_MODELS_DIR, TARGET_DAYS

COMMISSION_RATE = 0.00025
STAMP_DUTY_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
DEFAULT_SLIPPAGE_RATE = 0.0005

BUY_COST = COMMISSION_RATE + TRANSFER_FEE_RATE + DEFAULT_SLIPPAGE_RATE
SELL_COST = COMMISSION_RATE + TRANSFER_FEE_RATE + STAMP_DUTY_RATE + DEFAULT_SLIPPAGE_RATE

TRADING_DAYS_PER_YEAR = 242
PERIODS_PER_YEAR = TRADING_DAYS_PER_YEAR / TARGET_DAYS

# 参与组内选股所需的最少股票数，低于此值降级到剩余池
MIN_STOCKS_PER_SECTOR = 5

UNCLASSIFIED = '未分类'


def _load_stock_name_map() -> dict:
    """加载沪深300股票代码到名称的映射。"""
    pool_cache = os.path.join(CACHE_DIR, 'csi300_pool.csv')
    if os.path.exists(pool_cache):
        try:
            df = pd.read_csv(pool_cache, encoding='utf-8-sig', dtype={'code': str})
            return dict(zip(df['code'].astype(str).str.zfill(6), df['name']))
        except Exception:
            pass
    return {}


def is_limit_up(code: str, pct_chg: float) -> bool:
    """判断当日是否封涨停板（若非已持仓标的，次日开盘无法正常买入）。"""
    if pd.isna(pct_chg):
        return False
    code_str = str(code).zfill(6)
    limit = 19.85 if code_str.startswith(('300', '301', '688')) else 9.85
    return pct_chg >= limit


def _filter_unbuyable(df: pd.DataFrame, prev_holdings: set,
                      filter_limit_up: bool) -> pd.DataFrame:
    """过滤无法买入的涨停标的。已持有标的不受买入限制（允许继续持有）。"""
    if not filter_limit_up or 'pct_chg' not in df.columns or df.empty:
        return df
    codes = df['stock_code'].astype(str).str.zfill(6)
    is_held = codes.isin(prev_holdings)
    is_chinext_star = codes.str.startswith(('300', '301', '688'))
    limit_threshold = np.where(is_chinext_star, 19.85, 9.85)
    limit_up = df['pct_chg'] >= limit_threshold
    can_trade = is_held | (~limit_up)
    return df[can_trade]


def max_drawdown_duration(nav: np.ndarray) -> int:
    """计算最长水下持续周期数（从净值峰值回落至创出新高所经历的最长周期）。"""
    if len(nav) == 0:
        return 0
    peak = np.maximum.accumulate(np.r_[1.0, nav])[1:]
    in_dd = nav < peak
    max_duration = 0
    current_duration = 0
    for is_dd in in_dd:
        if is_dd:
            current_duration += 1
            if current_duration > max_duration:
                max_duration = current_duration
        else:
            current_duration = 0
    return int(max_duration)


def deflated_sharpe_ratio(observed_sr: float, n_trials: int,
                          sr_std: float, n_obs: int,
                          skew: float = 0.0, kurtosis: float = 3.0) -> float | None:
    """Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR).

    对多次试验/超参搜索下的选择偏差进行统计惩罚，检验夏普比率是否反映真实 Alpha。

    Args:
        observed_sr: 单期（非年化）夏普比率 mean(r) / std(r)
        n_trials: 试验次数（如 Optuna 搜索次数）
        sr_std: 试验间单期夏普的标准差，默认经验值约 0.5 / sqrt(periods_per_year)
        n_obs: 样本观测期数
        skew: 收益序列偏度
        kurtosis: 收益序列 Pearson 峰度（正态分布为 3.0）

    Returns:
        DSR 概率值 [0, 1]：>0.95 表示具备高度统计显著性的真实技能。
    """
    if n_trials <= 1 or n_obs <= 2 or sr_std <= 1e-9:
        return None

    euler_mascheroni = 0.57721566490153286
    # 零假设下 N 次独立试验期望最大单期夏普
    e_max_sr = sr_std * (
        (1.0 - euler_mascheroni) * stats.norm.ppf(1.0 - 1.0 / n_trials)
        + euler_mascheroni * stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    )
    # 考虑偏度与厚尾的单期夏普标准误差
    variance_term = (
        1.0 - skew * observed_sr + ((kurtosis - 1.0) / 4.0) * (observed_sr ** 2)
    ) / (n_obs - 1.0)
    sr_se = np.sqrt(max(1e-8, variance_term))

    test_stat = (observed_sr - e_max_sr) / sr_se
    return float(stats.norm.cdf(test_stat))


def _period_return(df: pd.DataFrame, codes: list, ret_col: str) -> float:
    """等权组合在单个调仓周期的收益。"""
    sub = df[df['stock_code'].isin(codes)]
    if sub.empty:
        return 0.0
    return float(sub[ret_col].mean())


def _sector_neutral_pick(current: pd.DataFrame, k: int, score_col: str,
                         industry_col: str = 'industry',
                         prev_holdings: set = None,
                         filter_limit_up: bool = True) -> tuple:
    """行业中性选股：行业组内取 Top-N，剩余名额由剩余池按打分补足。
    支持涨停不可买入过滤。

    Returns:
        (选中代码列表, 各行业入选数统计)
    """
    prev_holdings = prev_holdings or set()
    current = _filter_unbuyable(current, prev_holdings, filter_limit_up)

    if industry_col not in current.columns:
        return current.nlargest(k, score_col)['stock_code'].tolist(), {}

    # 剔除未分类与小组：它们不参与组内选股
    sizes = current[industry_col].value_counts()
    eligible = current[
        (current[industry_col] != UNCLASSIFIED) &
        (current[industry_col].map(sizes) >= MIN_STOCKS_PER_SECTOR)
    ]
    sector_pool = current[~current.index.isin(eligible.index)]

    sectors = eligible[industry_col].unique()
    n_sectors = len(sectors)
    if n_sectors == 0:
        # 无可用行业组，退化为全市场排序
        return current.nlargest(k, score_col)['stock_code'].tolist(), {}

    # 配额按行业等权分配：每个行业分得 k / n_sectors 个名额。
    quota_float = k / n_sectors
    base_quota = int(np.floor(quota_float))
    remainder = k - base_quota * n_sectors

    sector_sizes = eligible[industry_col].value_counts()
    ranked_eligible = eligible.sort_values(score_col, ascending=False)

    picks, counts = [], {}
    sector_order = list(sector_sizes.index)

    for idx, sector in enumerate(sector_order):
        quota = base_quota + (1 if idx < remainder else 0)
        if quota <= 0:
            continue
        grp = ranked_eligible[ranked_eligible[industry_col] == sector].head(quota)
        if len(grp) == 0:
            continue
        picks.extend(grp['stock_code'].tolist())
        counts[sector] = len(grp)

    # 名额不足时，从剩余池（含未分类股票与小组股票的全体），
    # 以及已用行业组中未入选的高分标的里补足
    if len(picks) < k:
        used = set(picks)
        remaining = current[~current['stock_code'].isin(used)]
        remaining = pd.concat([remaining, sector_pool]).drop_duplicates(subset='stock_code')
        remaining = remaining.sort_values(score_col, ascending=False)
        picks.extend(remaining['stock_code'].head(k - len(picks)).tolist())

    # 超额（超配）时按全局打分截断
    if len(picks) > k:
        score_map = dict(zip(current['stock_code'], current[score_col]))
        picks = sorted(picks, key=lambda c: score_map.get(c, -np.inf), reverse=True)[:k]

    return picks, counts


def _global_pick(current: pd.DataFrame, k: int, score_col: str,
                 prev_holdings: set = None,
                 filter_limit_up: bool = True) -> tuple:
    """全市场排序取 Top-K（支持涨停不可买入过滤）。"""
    prev_holdings = prev_holdings or set()
    pool = _filter_unbuyable(current, prev_holdings, filter_limit_up)
    return pool.nlargest(k, score_col)['stock_code'].tolist(), {}


def run_backtest(panel: pd.DataFrame, k: int = 10, ret_col: str = 'ret_5d_fwd',
                 score_col: str = 'score_lgb', periods_per_year: float = PERIODS_PER_YEAR,
                 selection: str = 'global',
                 industry_col: str = 'industry',
                 slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
                 filter_limit_up: bool = True,
                 n_trials: int | None = None,
                 trial_sharpe_std: float | None = None) -> dict:
    """执行 Top-K 组合回测。

    Args:
        panel: 含 date / stock_code / ret_col / score_col 的测试集
        k: 每期持仓数量
        ret_col: 信号日之后、可执行且未去均值的 5 日持有收益
        score_col: 模型打分数值列
        periods_per_year: 每年调仓次数，默认 242 / TARGET_DAYS
        selection: 'global' 全市场排序 | 'neutral' 行业中性
        industry_col: 行业列名
        slippage_rate: 单边交易滑点摩擦率，默认 0.0005 (5 bps)
        filter_limit_up: 是否剔除当日涨停、次日无法买入的标的（已持有除外）
        n_trials: 模型搜索/超参优化试验次数（用于 DSR 检验）

    Returns:
        回测指标与净值曲线
    """
    if panel.empty or score_col not in panel.columns:
        return {'error': '测试集为空或缺少打分列'}

    if ret_col not in panel.columns:
        return {'error': f'面板缺少收益列 {ret_col}'}
    dates = sorted(panel['date'].dropna().unique())
    if len(dates) < TARGET_DAYS + 1:
        return {'error': f'有效交易日仅 {len(dates)} 个，不足以进行 {TARGET_DAYS} 日持有期回测'}

    if k < 1 or slippage_rate < 0:
        raise ValueError('持仓数量必须为正，滑点不能为负')
    panel = panel.copy()
    panel['stock_code'] = panel['stock_code'].astype(str).str.zfill(6)
    buy_cost = COMMISSION_RATE + TRANSFER_FEE_RATE + slippage_rate
    sell_cost = COMMISSION_RATE + TRANSFER_FEE_RATE + STAMP_DUTY_RATE + slippage_rate

    strategy_returns, benchmark_returns, turnovers = [], [], []
    sector_counts = []
    prev_holdings = set()
    name_map = _load_stock_name_map()
    rebalance_ledger = []

    rebalance_dates = []
    last_exit = None
    for i in range(0, len(dates), TARGET_DAYS):
        date = dates[i]
        if last_exit is not None and pd.Timestamp(date) < last_exit:
            continue
        current = panel[panel['date'] == date]
        current = current[current[ret_col].notna() & current[score_col].notna()]
        if len(current) < k:
            continue

        if selection == 'neutral':
            holdings, counts = _sector_neutral_pick(
                current, k, score_col, industry_col=industry_col,
                prev_holdings=set(), filter_limit_up=filter_limit_up,
            )
        else:
            holdings, counts = _global_pick(
                current, k, score_col,
                prev_holdings=set(), filter_limit_up=filter_limit_up,
            )

        if not holdings:
            continue

        holdings_set = set(str(c).zfill(6) for c in holdings)
        # 每期末全部平仓。相邻周期的隔夜资金为空仓，重复入选也必须重新买入。
        buy_turnover = sell_turnover = 1.0
        turnovers.append(max(buy_turnover, sell_turnover))
        if counts:
            sector_counts.append(counts)

        # ret_5d_fwd 从下一交易日开盘买入至第 5 个交易日收盘，
        # 每隔 5 个交易日才生成下一组收益，避免重叠持有期被重复复利。
        strategy_ret = _period_return(current, holdings, ret_col)
        benchmark_ret = float(current[ret_col].mean())

        net_return = (1.0 + strategy_ret) * (1.0 - sell_cost) / (1.0 + buy_cost) - 1.0
        benchmark_net = (1.0 + benchmark_ret) * (1.0 - sell_cost) / (1.0 + buy_cost) - 1.0
        cost = strategy_ret - net_return
        strategy_returns.append(net_return)
        benchmark_returns.append(benchmark_net)
        exit_date = (pd.to_datetime(current['label_end_date']).max()
                     if 'label_end_date' in current else None)
        if exit_date is not None and pd.notna(exit_date):
            last_exit = exit_date

        # 记录当期持仓标的明细与收益 (Rebalance Ledger)
        period_holdings = []
        weight_per_stock = round(1.0 / len(holdings), 4) if holdings else 0.0
        code_to_row = {}
        for _, row in current.iterrows():
            c_str = str(row['stock_code']).zfill(6)
            if c_str in holdings_set:
                code_to_row[c_str] = row

        for code in holdings:
            c_str = str(code).zfill(6)
            row = code_to_row.get(c_str)
            ret_val = float(row[ret_col]) if row is not None and pd.notna(row.get(ret_col)) else 0.0
            score_val = float(row[score_col]) if row is not None and pd.notna(row.get(score_col)) else 0.0
            ind_val = str(row.get(industry_col, UNCLASSIFIED)) if row is not None else UNCLASSIFIED
            is_new = c_str not in prev_holdings

            period_holdings.append({
                'code': c_str,
                'name': str(name_map.get(c_str, f"标的{c_str}")),
                'industry': ind_val,
                'weight': weight_per_stock,
                'score': round(score_val, 4),
                'return_5d': round(ret_val, 4),
                'action': 'BUY',
                'previously_selected': not is_new,
                'exit_action': 'SELL',
                'beat_benchmark': bool(ret_val > benchmark_ret),
            })

        exited_list = []
        if prev_holdings:
            exited_codes = prev_holdings
            for code in exited_codes:
                c_str = str(code).zfill(6)
                exited_list.append({
                    'code': c_str,
                    'name': str(name_map.get(c_str, f"标的{c_str}")),
                    'action': 'SELL',
                })

        win_count = sum(1 for h in period_holdings if h['return_5d'] > 0)
        rebalance_ledger.append({
            'period_index': len(rebalance_ledger) + 1,
            'date': str(date)[:10],
            'holdings_count': len(holdings),
            'exit_date': str(exit_date)[:10] if exit_date is not None else None,
            'period_net_return': round(net_return, 6),
            'period_gross_return': round(strategy_ret, 4),
            'benchmark_return': round(benchmark_net, 6),
            'excess_return': round(net_return - benchmark_net, 6),
            'turnover': round(max(buy_turnover, sell_turnover), 4),
            'cost': round(cost, 5),
            'win_rate': round(win_count / len(period_holdings), 4) if period_holdings else 0.0,
            'holdings': period_holdings,
            'exited': exited_list,
        })

        prev_holdings = holdings_set
        rebalance_dates.append(str(date)[:10])

    if not strategy_returns:
        return {'error': '没有足够的有效调仓周期'}

    strat = np.array(strategy_returns)
    bench = np.array(benchmark_returns)

    def _metrics(returns: np.ndarray, nav: np.ndarray = None) -> dict:
        if nav is None:
            nav = np.cumprod(1.0 + returns)
        total = float(nav[-1] - 1.0) if len(nav) > 0 else 0.0
        n = len(returns)
        ann = float((1.0 + total) ** (periods_per_year / n) - 1.0) if n > 0 and total > -1.0 else 0.0
        ret_std = float(np.std(returns, ddof=1)) if n > 1 else 0.0
        vol = float(ret_std * np.sqrt(periods_per_year)) if n > 1 else 0.0
        obs_sr = float(np.mean(returns) / ret_std) if n > 1 and ret_std > 0 else 0.0
        sharpe = float(obs_sr * np.sqrt(periods_per_year))

        # 下行波动率与 Sortino 比率
        downside = np.minimum(returns, 0.0)
        downside_dev = float(np.sqrt(np.mean(downside ** 2)))
        sortino = float((np.mean(returns) / downside_dev) * np.sqrt(periods_per_year)) if downside_dev > 1e-9 else 0.0

        # 最大回撤与 Calmar 比率
        peak = np.maximum.accumulate(np.r_[1.0, nav])[1:]
        drawdown = (nav - peak) / peak
        max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0
        calmar = float(ann / abs(max_dd)) if abs(max_dd) > 1e-6 else 0.0
        mdd_duration = max_drawdown_duration(nav)

        # 尾部风险指标: 95% 历史 VaR 与 CVaR (Expected Shortfall)
        var_95 = float(np.percentile(returns, 5)) if n > 0 else 0.0
        tail_returns = returns[returns <= var_95]
        cvar_95 = float(tail_returns.mean()) if len(tail_returns) > 0 else var_95

        # 偏度与峰度（Pearson 峰度，正态 = 3.0）
        skewness = float(stats.skew(returns)) if n > 2 else 0.0
        kurtosis = float(stats.kurtosis(returns, fisher=False)) if n > 3 else 3.0

        # Deflated Sharpe Ratio (DSR) 扣除多次测试偏差
        dsr = deflated_sharpe_ratio(
            observed_sr=obs_sr,
            n_trials=n_trials,
            sr_std=trial_sharpe_std,
            n_obs=n,
            skew=skewness,
            kurtosis=kurtosis,
        ) if n_trials is not None and n_trials > 1 and trial_sharpe_std is not None and trial_sharpe_std > 0 else None

        return {
            'total_return': round(total, 4),
            'annualized_return': round(ann, 4),
            'annualized_volatility': round(vol, 4),
            'sharpe': round(sharpe, 4),
            'sortino': round(sortino, 4),
            'calmar': round(calmar, 4),
            'max_drawdown': round(max_dd, 4),
            'max_drawdown_duration': int(mdd_duration),
            'var_95': round(var_95, 4),
            'cvar_95': round(cvar_95, 4),
            'win_rate': round(float(np.mean(returns > 0)), 4) if n > 0 else 0.0,
            'periods': int(n),
            'skewness': round(skewness, 4),
            'kurtosis': round(kurtosis, 4),
            'dsr': round(dsr, 4) if dsr is not None else None,
            'dsr_p_value': round(1.0 - dsr, 4) if dsr is not None else None,
            'dsr_status': 'computed' if dsr is not None else 'missing_comparable_trial_sharpes',
            'n_trials': n_trials,
            'nav': [round(float(x), 6) for x in nav],
            'drawdown': [round(float(x), 6) for x in drawdown],
            'returns': [round(float(x), 8) for x in returns],
        }

    strat_m = _metrics(strat)
    bench_m = _metrics(bench)
    active = strat - bench
    relative = (1.0 + strat) / (1.0 + bench) - 1.0
    relative_m = _metrics(relative)
    tracking_error = float(np.std(active, ddof=1)) if len(active) > 1 else 0.0
    information_ratio = (float(np.mean(active) / tracking_error * np.sqrt(periods_per_year))
                         if tracking_error > 0 else 0.0)

    # 行业集中度：每期入选标的覆盖的行业数
    avg_sectors = round(float(np.mean([len(c) for c in sector_counts])), 2) if sector_counts else None

    return {
        'params': {
            'k': k,
            'selection': selection,
            'periods_per_year': periods_per_year,
            'target_days': TARGET_DAYS,
            'entry': 'next_session_open',
            'exit': f'close_after_{TARGET_DAYS}_sessions',
            'rebalance_every_sessions': TARGET_DAYS,
            'position_policy': 'liquidate_at_period_close',
            'benchmark_cost_policy': 'same_round_trip_rates',
            'execution_note': '期末全额平仓，隔夜持有现金；信号日涨停仅作筛选，不保证下一开盘可成交。',
            'return_column': ret_col,
            'commission_rate': COMMISSION_RATE,
            'stamp_duty_rate': STAMP_DUTY_RATE,
            'transfer_fee_rate': TRANSFER_FEE_RATE,
            'slippage_rate': slippage_rate,
            'buy_cost': buy_cost,
            'sell_cost': sell_cost,
            'filter_limit_up': filter_limit_up,
            'n_trials': n_trials,
            'score_col': score_col,
            'min_stocks_per_sector': MIN_STOCKS_PER_SECTOR,
        },
        'strategy': strat_m,
        'benchmark': bench_m,
        'excess': {
            'total_return': relative_m['total_return'],
            'annualized_return': relative_m['annualized_return'],
            'annualized_volatility': relative_m['annualized_volatility'],
            'sharpe': round(information_ratio, 4),
            'information_ratio': round(information_ratio, 4),
            'sortino': relative_m['sortino'],
            'calmar': relative_m['calmar'],
            'tracking_error': round(tracking_error * np.sqrt(periods_per_year), 4),
            'max_drawdown': relative_m['max_drawdown'],
            'max_drawdown_duration': relative_m['max_drawdown_duration'],
            'var_95': relative_m['var_95'],
            'cvar_95': relative_m['cvar_95'],
            'win_rate': round(float(np.mean(active > 0)), 4),
            'dsr': relative_m['dsr'],
        },
        'avg_turnover': round(float(np.mean(turnovers)), 4) if turnovers else 0.0,
        'avg_sectors_held': avg_sectors,
        'final_holdings': [],
        'last_selected': sorted(prev_holdings),
        'dates': rebalance_dates,
        'rebalance_ledger': rebalance_ledger,
    }


def save_backtest(result: dict, path: str = None) -> str:
    """持久化回测结果供前端读取。"""
    if path is None:
        path = os.path.join(SAVED_MODELS_DIR, 'backtest_result.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[Backtest] 结果已保存: {path}")
    return path

