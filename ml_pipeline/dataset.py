# -*- coding: utf-8 -*-
"""面板数据集构建、因子中性化与防泄漏切分

三层职责
--------
1. 单股票特征清洗：只用 ffill，绝不 bfill（bfill 会把未来值搬到过去）；
2. 截面处理：计算超额收益标签、行业中性化、因子标准化；
3. 时序切分：训练/验证/测试严格按时间，测试集完全不参与任何决策。

为什么需要行业中性化
--------------------
银行 PE 天然 6 倍、白酒 30 倍。不做行业去均值，模型学到的是
「这是银行」而不是「这个估值相对同业便宜」，因子有效性会被行业结构淹没。
"""

import numpy as np
import pandas as pd

from config.config import FEATURE_COLS, TARGET_DAYS, get_stock_board, get_pool

MIN_FEATURE_COVERAGE = 0.8


def align_forward_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """按全市场交易日对齐可执行标签；缺失入场/出场价格不伪造成交。"""
    panel = panel.copy()
    panel['date'] = pd.to_datetime(panel['date'])
    dates = pd.Series(sorted(panel['date'].unique()))
    calendar = pd.DataFrame({'date': dates, 'entry_date': dates.shift(-1),
                             'label_end_date': dates.shift(-TARGET_DAYS)})
    panel = panel.drop(columns=['entry_date', 'label_end_date'], errors='ignore').merge(calendar, on='date', how='left')
    prices = panel[['stock_code', 'date', 'open', 'close']].drop_duplicates(['stock_code', 'date'])
    entry = prices[['stock_code', 'date', 'open']].rename(columns={'date': 'entry_date', 'open': '_entry_open'})
    exit_ = prices[['stock_code', 'date', 'close']].rename(columns={'date': 'label_end_date', 'close': '_exit_close'})
    panel = panel.merge(entry, on=['stock_code', 'entry_date'], how='left')
    panel = panel.merge(exit_, on=['stock_code', 'label_end_date'], how='left')
    valid = (panel['_entry_open'] > 0) & (panel['_exit_close'] > 0)
    panel['ret_5d_fwd'] = (panel['_exit_close'] / panel['_entry_open'] - 1).where(valid)
    return panel.drop(columns=['_entry_open', '_exit_close'])

# 估值与财务因子（来自 data/factor_fetcher.py）
FUNDAMENTAL_FACTORS = [
    'pe_ttm', 'pb', 'roe', 'gross_margin', 'debt_ratio',
    'revenue_growth', 'profit_growth', 'roa', 'net_margin',
]

# 量价派生因子（由日线直接计算，无需外部数据）
PRICE_FACTORS = [
    'momentum_20d', 'momentum_60d', 'volatility_20d', 'turnover_proxy',
]


def _add_price_factors(df: pd.DataFrame) -> pd.DataFrame:
    """从日线派生动量、波动因子与技术指标，并计算前瞻收益。"""
    from features.feature_engineering import calculate_technical_indicators

    close = df['close'].astype(float)
    df['momentum_20d'] = close.pct_change(20)
    df['momentum_60d'] = close.pct_change(60)
    df['volatility_20d'] = close.pct_change().rolling(20).std() * np.sqrt(242)
    # 成交量相对水平作为换手活跃度代理（无流通股本数据时的替代）
    if 'volume' in df.columns:
        vol = df['volume'].astype(float)
        df['turnover_proxy'] = vol / (vol.rolling(20).mean() + 1e-9)

    # 技术特征与前瞻收益：若数据源未提供，则就地计算
    if not all(c in df.columns for c in FEATURE_COLS) or 'ret_5d_fwd' not in df.columns:
        needed = {'open', 'high', 'low', 'close', 'volume'}
        if needed.issubset(df.columns):
            # calculate_technical_indicators 需要 date 作为普通列，计算后恢复为索引
            work = df.reset_index(drop=False)
            if 'date' not in work.columns:
                work['date'] = df.index
            work = calculate_technical_indicators(work)
            work['date'] = pd.to_datetime(work['date'])
            df = work.set_index('date')

    return df


def _prepare_single(df: pd.DataFrame, code: str, factor_cols: list,
                    require_target: bool = True) -> pd.DataFrame:
    """清理单股时间序列；只填补特征，不触碰未来收益标签。"""
    if df is None or len(df) == 0:
        return None

    needed = [c for c in factor_cols if c in df.columns]
    if len(needed) < len(factor_cols) * 0.5:
        return None

    market_cols = [c for c in ('open', 'close', 'high', 'low', 'volume', 'pct_chg')
                   if c in df.columns]
    keep = list(dict.fromkeys(needed + market_cols + ['ret_5d_fwd']))
    sub = df[keep].copy().replace([np.inf, -np.inf], np.nan)

    # 只对特征做 ffill。ret_5d_fwd 是未来标签，绝不能填充；
    # 价格字段也保留原值，避免把停牌日伪装成有成交的交易日。
    sub[needed] = sub[needed].ffill()

    coverage = sub[needed].notna().mean(axis=1) >= MIN_FEATURE_COVERAGE
    sub = sub[coverage]
    if len(sub) == 0:
        return None

    # 不用整段样本的中位数填补历史缺失，避免把未来分布带入过去。
    # LightGBM 可原生处理剩余 NaN；逻辑回归基线会在训练折内单独拟合填补器。

    for c in factor_cols:
        if c not in sub.columns:
            sub[c] = np.nan

    sub['stock_code'] = code
    # 索引来自日线，可能是 DatetimeIndex 或整数索引，统一转为时间戳
    if isinstance(sub.index, pd.DatetimeIndex):
        sub['date'] = sub.index
    elif 'date' in sub.columns:
        sub['date'] = pd.to_datetime(sub['date'])
    else:
        return None
    return sub.reset_index(drop=True)


def _winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """截面缩尾，抑制极端值对标准化的干扰。"""
    if s.notna().sum() < 10:
        return s
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lo, hi)


# 行业组内的最少股票数。低于此值说明该行业在当日样本中过于稀疏，
# 对其去均值等于减去自身（把因子抹成 0），因此退回截面中性化。
MIN_STOCKS_PER_INDUSTRY = 3

# 行业缺失时的占位标签。该组不参与组内去均值。
UNCLASSIFIED_INDUSTRY = '未分类'


def neutralize_and_standardize(panel: pd.DataFrame, factor_cols: list,
                               industry_col: str = 'industry') -> pd.DataFrame:
    """截面内行业中性化 + z-score 标准化。

    对每个交易日的每个因子：
      1. 缩尾至 1%/99% 分位；
      2. 减去同行业均值；若该行业当日样本不足 MIN_STOCKS_PER_INDUSTRY，
         则退回「减去全截面均值」，避免把因子抹成 0；
      3. 除以截面标准差（标准化）。

    结果列名为 <factor>_neu。
    """
    panel = panel.copy()

    dates = panel['date']
    for f in factor_cols:
        if f not in panel:
            panel[f + '_neu'] = np.nan
            continue
        values = panel[f]
        grouped = values.groupby(dates)
        count = grouped.transform('count')
        lower = dates.map(grouped.quantile(0.01))
        upper = dates.map(grouped.quantile(0.99))
        x = values.clip(lower=lower, upper=upper).where(count >= 10, values)
        demeaned = x - x.groupby(dates).transform('mean')
        if industry_col in panel:
            industry = panel[industry_col].fillna(UNCLASSIFIED_INDUSTRY)
            sizes = industry.groupby([dates, industry]).transform('size')
            rich = (sizes >= MIN_STOCKS_PER_INDUSTRY) & (industry != UNCLASSIFIED_INDUSTRY)
            mean = x.groupby([dates, industry]).transform('mean')
            demeaned = demeaned.where(~rich, x - mean)
        std = demeaned.groupby(dates).transform('std')
        valid = std.notna() & np.isfinite(std) & (std > 1e-9)
        panel[f + '_neu'] = (demeaned / std.where(valid)).where(valid, demeaned * 0.0)

    return panel


def _build_panel(codes: list = None, include_fundamental: bool = True,
                 require_target: bool = True, verbose: bool = True,
                 force_refresh: bool = False) -> pd.DataFrame:
    """构建训练面板或最新推理面板。

    Args:
        codes: 股票代码列表，缺省用全池
        include_fundamental: 是否纳入估值与财务因子（需联网）

    Returns:
        含技术特征、基本面因子与中性化列的面板；训练模式另含标签
    """
    from data.factor_fetcher import build_factor_panel as build_single

    point_in_time_universe = False
    if codes is None and require_target:
        from data.universe import historical_codes
        codes = historical_codes()
        point_in_time_universe = codes is not None
    if codes is None:
        codes = [s['code'] for s in get_pool()]

    pool_map = {s['code']: s for s in get_pool()}
    factor_cols = list(FEATURE_COLS) + PRICE_FACTORS
    if include_fundamental:
        factor_cols += FUNDAMENTAL_FACTORS

    frames, skipped = [], 0
    for i, code in enumerate(codes, 1):
        clean = str(code).zfill(6)
        df = build_single(clean, force=force_refresh) if include_fundamental else _fallback_local(clean)
        if df is None:
            skipped += 1
            continue

        price_columns = [c for c in ('open', 'high', 'low', 'close') if c in df]
        if price_columns:
            valid_prices = df[price_columns].apply(pd.to_numeric, errors='coerce').gt(0).all(axis=1)
            df = df.loc[valid_prices].copy()

        df = df.set_index('date') if 'date' in df.columns else df
        df = _add_price_factors(df)
        prep = _prepare_single(df, clean, factor_cols, require_target=require_target)
        if prep is None:
            skipped += 1
            continue

        info = pool_map.get(clean, {})
        prep['industry'] = info.get('industry', '未分类')
        prep['board'] = info.get('board', get_stock_board(clean))
        frames.append(prep)

        if verbose and i % 25 == 0:
            print(f"[Panel] {i}/{len(codes)} 已处理，有效 {len(frames)} 只")

    if not frames:
        raise RuntimeError("未能构建任何有效样本，请检查数据源连通性")

    panel = pd.concat(frames, ignore_index=True)
    panel = align_forward_returns(panel)

    if require_target:
        from data.universe import apply_point_in_time_universe
        panel, point_in_time_universe = apply_point_in_time_universe(panel)
        if panel.empty:
            raise RuntimeError('按历史成分股过滤后没有有效样本，请检查 membership history 文件')

    if require_target:
        # 先按当日可用特征构建完整截面；再对有已实现前瞻收益的样本计算标签。
        # 缺少未来收益的股票仍参与特征中性化，但不被误标为负样本。
        panel['excess_ret_5d'] = (panel['ret_5d_fwd']
                                  - panel.groupby('date')['ret_5d_fwd'].transform('mean'))
        has_return = panel['ret_5d_fwd'].notna()
        panel['target_up'] = np.where(
            has_return, (panel['excess_ret_5d'] > 0).astype(float), np.nan,
        )

    # 因子中性化与标准化
    panel = neutralize_and_standardize(panel, factor_cols)

    if require_target:
        panel = panel.dropna(subset=['target_up']).copy()
        panel['target_up'] = panel['target_up'].astype(int)

    panel = panel.sort_values(['date', 'stock_code']).reset_index(drop=True)
    panel.attrs['universe_point_in_time'] = point_in_time_universe

    if verbose:
        print(f"[Panel] {len(frames)} 只标的 / {panel['date'].nunique()} 个截面 / {len(panel)} 行"
              f"（跳过 {skipped} 只）")

    return panel


def build_factor_panel(codes: list = None, include_fundamental: bool = True,
                       verbose: bool = True) -> pd.DataFrame:
    """构建有完整未来标签的训练面板。"""
    return _build_panel(codes, include_fundamental, require_target=True, verbose=verbose)


def build_inference_panel(codes: list = None, include_fundamental: bool = True,
                           verbose: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    """构建不依赖未来收益标签的推理面板，包含最新可用行情与收盘价。"""
    return _build_panel(codes, include_fundamental, require_target=False, verbose=verbose, force_refresh=force_refresh)


def _fallback_local(code: str) -> pd.DataFrame:
    """不联网时退化为本地缓存行情（无基本面因子）。"""
    from data.data_fetcher import get_stock_data
    df = get_stock_data(code)
    if df is None:
        return None
    return df.reset_index()


def time_split(panel: pd.DataFrame, train_ratio: float = 0.7, val_ratio: float = 0.15,
               embargo_days: int = TARGET_DAYS):
    """按日期切分，并在训练/验证边界清除尚未成熟的前瞻标签。"""
    dates = np.sort(panel['date'].unique())
    if len(dates) < 10:
        raise RuntimeError(f"有效截面仅 {len(dates)} 个，不足以做时序切分")

    train_start = int(len(dates) * train_ratio)
    val_start = int(len(dates) * (train_ratio + val_ratio))
    train_end = max(1, train_start - embargo_days)
    val_end = max(train_start + 1, val_start - embargo_days)
    if train_end >= train_start or val_end >= val_start:
        raise RuntimeError("切分边界与标签隔离期冲突，请增加样本长度或缩短隔离期")

    train = panel[panel['date'] < dates[train_end]]
    val = panel[(panel['date'] >= dates[train_start]) & (panel['date'] < dates[val_end])]
    test = panel[panel['date'] >= dates[val_start]]
    if 'label_end_date' in panel:
        train = train[pd.to_datetime(train['label_end_date']) < pd.Timestamp(dates[train_start])]
        val = val[pd.to_datetime(val['label_end_date']) < pd.Timestamp(dates[val_start])]

    if len(train) == 0 or len(val) == 0 or len(test) == 0:
        raise RuntimeError("时序切分后存在空集合")

    return train, val, test
