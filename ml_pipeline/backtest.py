# -*- coding: utf-8 -*-
"""Top-K 组合回测（支持全市场排序与行业中性两种选股模式）

两种选股模式的差异
------------------
global    全市场按打分排序取 Top-K。简单，但容易把仓位集中在当期最热的
          少数行业上，行业暴露失控会放大回撤。

neutral   行业中性：每个行业内按打分取 Top-N，再合并。行业暴露被限制在
          可控范围内，代价是可能选入得分并非全市场最高的标的。

行业稀疏时的处理
----------------
沪深300 中有部分标的在现有行业分类里查不到（标记为「未分类」）。若把
「未分类」当成一个行业，它会在组内选股时占用大量名额，但组内成分来自
互不相关的真实行业，等于没有中性化。因此：
  - 「未分类」不参与组内选股，而是并入「剩余候选池」，按打分补位；
  - 行业内股票数不足时同样降级到剩余池，保证每期持仓数量稳定。

净值口径
--------
每个调仓周期等权持有选中标的，周期内收益取该组下一期实际收益均值，
扣除换手成本。基准为同期全样本等权（市场平均）。

交易成本（A 股）
----------------
  买入：佣金 0.025% + 过户费 0.001%
  卖出：佣金 0.025% + 过户费 0.001% + 印花税 0.05%
"""

import json
import os

import numpy as np
import pandas as pd

from config.config import SAVED_MODELS_DIR, TARGET_DAYS

COMMISSION_RATE = 0.00025
STAMP_DUTY_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
BUY_COST = COMMISSION_RATE + TRANSFER_FEE_RATE
SELL_COST = COMMISSION_RATE + TRANSFER_FEE_RATE + STAMP_DUTY_RATE

TRADING_DAYS_PER_YEAR = 242
PERIODS_PER_YEAR = TRADING_DAYS_PER_YEAR / TARGET_DAYS

# 参与组内选股所需的最少股票数，低于此值降级到剩余池
MIN_STOCKS_PER_SECTOR = 5

UNCLASSIFIED = '未分类'


def _period_return(df: pd.DataFrame, codes: list, ret_col: str) -> float:
    """等权组合在单个调仓周期的收益。"""
    sub = df[df['stock_code'].isin(codes)]
    if sub.empty:
        return 0.0
    return float(sub[ret_col].mean())


def _sector_neutral_pick(current: pd.DataFrame, k: int, score_col: str,
                         industry_col: str = 'industry') -> tuple:
    """行业中性选股：行业组内取 Top-N，剩余名额由剩余池按打分补足。

    Returns:
        (选中代码列表, 各行业入选数统计)
    """
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
    # 关键：不使用「每行业至少 1 只」的规则——当行业数多于持仓数时，
    # 那等于强制分散到 k 个不同行业，把全市场头部的高分标的全部打散，
    # 既不是中性化也损害收益。这里改为按配额取整后由剩余池补足。
    quota_float = k / n_sectors
    base_quota = int(np.floor(quota_float))
    # 有小数部分的行业，按行业规模从大到小各多给 1 个名额
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


def _global_pick(current: pd.DataFrame, k: int, score_col: str) -> tuple:
    """全市场排序取 Top-K。"""
    return current.nlargest(k, score_col)['stock_code'].tolist(), {}


def run_backtest(panel: pd.DataFrame, k: int = 10, ret_col: str = 'ret_5d_fwd',
                 score_col: str = 'score_lgb', periods_per_year: float = PERIODS_PER_YEAR,
                 selection: str = 'global',
                 industry_col: str = 'industry') -> dict:
    """执行 Top-K 组合回测。

    Args:
        panel: 含 date / stock_code / ret_col / score_col 的测试集
        k: 每期持仓数量
        ret_col: 信号日之后、可执行且未去均值的 5 日持有收益
        score_col: 模型打分数值列
        periods_per_year: 每年调仓次数，默认 242 / TARGET_DAYS
        selection: 'global' 全市场排序 | 'neutral' 行业中性
        industry_col: 行业列名

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

    strategy_returns, benchmark_returns, turnovers = [], [], []
    sector_counts = []
    prev_holdings = set()

    rebalance_dates = []
    for i in range(0, len(dates), TARGET_DAYS):
        date = dates[i]
        current = panel[panel['date'] == date]
        current = current[current[ret_col].notna() & current[score_col].notna()]
        if len(current) < k:
            continue

        if selection == 'neutral':
            holdings, counts = _sector_neutral_pick(current, k, score_col, industry_col)
        else:
            holdings, counts = _global_pick(current, k, score_col)

        if not holdings:
            continue

        holdings_set = set(holdings)
        buy_turnover = len(holdings_set - prev_holdings) / len(holdings)
        sell_turnover = len(prev_holdings - holdings_set) / len(holdings) if prev_holdings else 0.0
        turnovers.append(max(buy_turnover, sell_turnover))
        if counts:
            sector_counts.append(counts)

        # ret_5d_fwd 从下一交易日开盘买入至第 5 个交易日收盘，
        # 每隔 5 个交易日才生成下一组收益，避免重叠持有期被重复复利。
        strategy_ret = _period_return(current, holdings, ret_col)
        benchmark_ret = float(current[ret_col].mean())

        cost = buy_turnover * BUY_COST + sell_turnover * SELL_COST
        strategy_returns.append(strategy_ret - cost)
        benchmark_returns.append(benchmark_ret)
        prev_holdings = holdings_set
        rebalance_dates.append(str(date)[:10])

    if not strategy_returns:
        return {'error': '没有足够的有效调仓周期'}

    strat = np.array(strategy_returns)
    bench = np.array(benchmark_returns)

    def _metrics(returns: np.ndarray) -> dict:
        nav = np.cumprod(1.0 + returns)
        total = float(nav[-1] - 1.0)
        n = len(returns)
        ann = float((1.0 + total) ** (periods_per_year / n) - 1.0) if n > 0 else 0.0
        vol = float(np.std(returns, ddof=1) * np.sqrt(periods_per_year)) if n > 1 else 0.0
        sharpe = float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(periods_per_year)) \
            if n > 1 and np.std(returns, ddof=1) > 0 else 0.0
        peak = np.maximum.accumulate(nav)
        drawdown = (nav - peak) / peak
        return {
            'total_return': round(total, 4),
            'annualized_return': round(ann, 4),
            'annualized_volatility': round(vol, 4),
            'sharpe': round(sharpe, 4),
            'max_drawdown': round(float(drawdown.min()), 4),
            'win_rate': round(float(np.mean(returns > 0)), 4),
            'periods': int(n),
            'nav': [round(float(x), 6) for x in nav],
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
            'return_column': ret_col,
            'buy_cost': BUY_COST,
            'sell_cost': SELL_COST,
            'score_col': score_col,
            'min_stocks_per_sector': MIN_STOCKS_PER_SECTOR,
        },
        'strategy': strat_m,
        'benchmark': bench_m,
        'excess': {
            'total_return': relative_m['total_return'],
            'annualized_return': relative_m['annualized_return'],
            'sharpe': round(information_ratio, 4),
            'information_ratio': round(information_ratio, 4),
            'tracking_error': round(tracking_error * np.sqrt(periods_per_year), 4),
            'max_drawdown': relative_m['max_drawdown'],
            'win_rate': round(float(np.mean(active > 0)), 4),
        },
        'avg_turnover': round(float(np.mean(turnovers)), 4) if turnovers else 0.0,
        'avg_sectors_held': avg_sectors,
        'final_holdings': sorted(prev_holdings),
        'dates': rebalance_dates,
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
