# -*- coding: utf-8 -*-
"""行情数据获取与本地缓存模块

数据质量约定
------------
早期版本对前复权产生的非正价格直接 clip 到 0.5，导致 600519 等标的
近三分之一的历史区间 OHLC 全为 0.5，技术指标完全失真。本版本改为
**剔除**异常行而非压平：任何 OHLC 非正或明显失真的交易日直接从样本中移除，
并在返回时附带质量报告，让上层能判断该标的是否仍可用。
"""

import os
import datetime

import pandas as pd
import numpy as np
import akshare as ak

from config.config import (
    CACHE_DIR,
    FACTOR_DIR,
    get_pool,
    is_main_board_stock,
    get_stock_board,
    is_valid_a_stock,
)
from features.feature_engineering import calculate_technical_indicators

# 单只标的最少可用交易日数，低于此值不参与训练
MIN_VALID_ROWS = 120

# 价格下限：低于此值的行视为复权异常，直接剔除
MIN_VALID_PRICE = 0.01


def _has_new_features(df: pd.DataFrame) -> bool:
    """判断缓存是否已包含当前特征集（含归一化特征）。"""
    from config.config import FEATURE_COLS
    return all(c in df.columns for c in FEATURE_COLS)


def _clean_price_rows(df: pd.DataFrame) -> tuple:
    """剔除复权异常行，返回 (清洗后数据, 质量报告)。

    判定规则：OHLC 任一列非正、或四价完全相等且等于某个固定常数
    （典型的 clip 残留特征），均视为不可用。
    """
    price_cols = [c for c in ('open', 'close', 'high', 'low') if c in df.columns]
    if not price_cols:
        return df, {"removed": 0, "reason": "no_price_columns"}

    before = len(df)
    valid = (df[price_cols] > MIN_VALID_PRICE).all(axis=1)

    # 四价完全相等在真实行情中几乎不可能出现，视为填充残留
    if len(price_cols) == 4:
        degenerate = (df[price_cols].nunique(axis=1) == 1)
        valid &= ~degenerate

    cleaned = df[valid].copy()
    removed = before - len(cleaned)

    report = {
        "removed": int(removed),
        "removed_ratio": round(removed / before, 4) if before else 0.0,
        "remaining": int(len(cleaned)),
    }
    return cleaned, report


def _load_recent_factor_price_cache(code: str, cache_file: str,
                                    use_cache: bool = True) -> pd.DataFrame:
    """读取因子流水线保存的真实 OHLCV，作为主行情接口不可用时的本地数据源。"""
    path = os.path.join(FACTOR_DIR, f"price_{code}.csv")
    if not os.path.exists(path):
        return None

    try:
        # 只用近期更新、且最后交易日不陈旧的因子行情缓存。
        if (datetime.datetime.now().timestamp() - os.path.getmtime(path)) > 7 * 86400:
            return None
        df = pd.read_csv(path)
        required = {'date', 'open', 'high', 'low', 'close', 'volume'}
        if not required.issubset(df.columns):
            return None

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        for column in required - {'date'}:
            df[column] = pd.to_numeric(df[column], errors='coerce')
        df = (df.dropna(subset=list(required))
                .sort_values('date')
                .drop_duplicates('date', keep='last')
                .reset_index(drop=True))
        if df.empty or (datetime.date.today() - df['date'].iloc[-1].date()).days > 7:
            return None

        if 'pct_chg' not in df.columns:
            df['pct_chg'] = df['close'].pct_change() * 100.0
        else:
            df['pct_chg'] = pd.to_numeric(df['pct_chg'], errors='coerce')

        df, report = _clean_price_rows(df)
        if len(df) < MIN_VALID_ROWS:
            return None
        if report.get('removed', 0):
            print(f"[DataFetcher] {code} 因子行情缓存剔除 {report['removed']} 行异常价格")

        df = calculate_technical_indicators(df)
        if use_cache:
            try:
                df.to_csv(cache_file, index=False, encoding='utf-8-sig')
            except OSError:
                pass
        print(f"[DataFetcher] {code} 使用真实因子行情缓存，共 {len(df)} 个交易日")
        return df.set_index('date')
    except Exception as exc:
        print(f"[DataFetcher] 读取 {code} 因子行情缓存失败: {exc}")
        return None


def get_stock_data(code: str, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    """获取单只股票历史日线并计算技术指标。

    Args:
        code: 6 位股票代码
        use_cache: 是否使用本地磁盘缓存
        force_refresh: 是否强制从数据源重新拉取

    Returns:
        以 date 为索引的 DataFrame，含指标与 ret_5d_fwd；
        数据不可用时返回 None。
    """
    clean_code = str(code).zfill(6)
    cache_file = os.path.join(CACHE_DIR, f"{clean_code}_hist.csv")
    cached_df = None

    # 1. 本地缓存优先
    if use_cache and not force_refresh and os.path.exists(cache_file):
        try:
            raw = pd.read_csv(cache_file)
            if len(raw) > 20 and 'close' in raw.columns:
                raw['date'] = pd.to_datetime(raw['date'])
                raw = raw.sort_values('date')
                cached_df = raw.set_index('date')

                # 缓存已含新特征：直接复用
                if _has_new_features(cached_df):
                    return cached_df

                # 缓存只有 OHLCV：本地重算指标，避免依赖网络
                if {'open', 'high', 'low', 'volume'}.issubset(raw.columns):
                    clean, report = _clean_price_rows(raw.copy())
                    if report.get('removed', 0) > 0:
                        print(f"[DataFetcher] {clean_code} 缓存中剔除 {report['removed']} 行"
                              f"异常价格（占比 {report['removed_ratio']:.1%}）")
                    if len(clean) < MIN_VALID_ROWS:
                        print(f"[DataFetcher] {clean_code} 清洗后仅 {len(clean)} 行，数据不可用")
                        return None
                    recalc = calculate_technical_indicators(clean)
                    if use_cache:
                        try:
                            recalc.to_csv(cache_file, index=False, encoding='utf-8-sig')
                        except Exception:
                            pass
                    return recalc.set_index('date')
        except Exception as e:
            print(f"[DataFetcher] 读取 {clean_code} 缓存失败，转为网络拉取: {e}")

    # 1.5 复用近期的真实因子 OHLCV，避免主行情源失效时落到模拟曲线。
    if cached_df is None and not force_refresh:
        factor_cached = _load_recent_factor_price_cache(clean_code, cache_file, use_cache)
        if factor_cached is not None:
            return factor_cached

    # 2. 从数据源拉取前复权日线（约 15 年）
    try:
        start_date = (datetime.date.today() - datetime.timedelta(days=15 * 365 + 60)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=clean_code, period="daily", start_date=start_date, adjust="qfq")

        if df is None or len(df) == 0:
            print(f"[DataFetcher] {clean_code} 无网络数据，回退本地缓存")
            return cached_df

        df = df.rename(columns={
            '日期': 'date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume', '涨跌幅': 'pct_chg',
        })

        df['date'] = pd.to_datetime(df['date'])
        for col in ('open', 'close', 'high', 'low', 'volume', 'pct_chg'):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.sort_values('date').reset_index(drop=True)

        # 关键改动：剔除异常行，而不是把价格压成常数
        df, report = _clean_price_rows(df)
        if report.get("removed_ratio", 0) > 0.2:
            print(f"[DataFetcher] {clean_code} 剔除 {report['removed']} 行异常价格"
                  f"（占比 {report['removed_ratio']:.1%}），数据质量偏低")

        if len(df) < MIN_VALID_ROWS:
            print(f"[DataFetcher] {clean_code} 有效样本仅 {len(df)} 行，低于阈值 {MIN_VALID_ROWS}")
            return cached_df

        df = calculate_technical_indicators(df)

        if use_cache:
            try:
                df.to_csv(cache_file, index=False, encoding='utf-8-sig')
            except Exception:
                pass

        return df.set_index('date')

    except Exception as e:
        print(f"[DataFetcher] 拉取 {clean_code} 行情异常: {e}")
        if cached_df is not None:
            return cached_df
        if os.path.exists(cache_file):
            try:
                fb = pd.read_csv(cache_file)
                fb['date'] = pd.to_datetime(fb['date'])
                return fb.set_index('date')
            except Exception:
                pass
        return None


def get_stock_list(filter_st: bool = True, main_board_only: bool = False,
                   board: str = None, limit: int = None) -> pd.DataFrame:
    """获取沪深300研究池股票列表，支持板块筛选。"""
    cache_list_file = os.path.join(CACHE_DIR, "stock_market_list.csv")
    pool = get_pool()
    pool_map = {s['code']: s for s in pool}
    pool_codes = set(pool_map)
    if not pool_codes:
        return pd.DataFrame(columns=['code', 'name', 'price', 'change_pct', 'board'])
    df = None

    if os.path.exists(cache_list_file):
        try:
            df = pd.read_csv(cache_list_file, dtype={'code': str})
            df['code'] = df['code'].apply(lambda x: str(x).zfill(6))
            df = df[df['code'].isin(pool_codes)].copy()
        except Exception:
            df = None

    if df is None or df.empty:
        try:
            print("[DataFetcher] 拉取沪深300研究池行情列表...")
            raw_df = ak.stock_zh_a_spot_em()
            if raw_df is not None and len(raw_df) > 0:
                df = raw_df.rename(columns={
                    '代码': 'code', '名称': 'name',
                    '最新价': 'price', '涨跌幅': 'change_pct',
                })[['code', 'name', 'price', 'change_pct']]
                df['code'] = df['code'].apply(lambda x: str(x).zfill(6))
                df = df[df['code'].isin(pool_codes)].copy()
                df['board'] = df['code'].map({
                    code: stock.get('board', get_stock_board(code))
                    for code, stock in pool_map.items()
                })
                df.to_csv(cache_list_file, index=False, encoding='utf-8-sig')
        except Exception as e:
            print(f"[DataFetcher] 行情列表获取失败，使用沪深300成分股名单: {e}")

    if df is None or df.empty:
        df = pd.DataFrame([{
            'code': s['code'],
            'name': s['name'],
            'price': 0.0,
            'change_pct': 0.0,
            'board': s.get('board', get_stock_board(s['code'])),
        } for s in pool])

    # 即便旧行情缓存存在，也只保留当前研究池内的股票。
    if 'code' in df.columns:
        df['code'] = df['code'].astype(str).str.zfill(6)
        df = df[df['code'].isin(pool_codes)].copy()
        try:
            df.to_csv(cache_list_file, index=False, encoding='utf-8-sig')
        except OSError:
            pass

    if 'board' not in df.columns and 'code' in df.columns:
        df['board'] = df['code'].map({
            code: stock.get('board', get_stock_board(code))
            for code, stock in pool_map.items()
        })

    if filter_st and 'name' in df.columns:
        df = df[~df['name'].str.contains('ST|退', na=False)]

    if main_board_only and 'code' in df.columns:
        df = df[df['code'].apply(is_main_board_stock)]

    if board and board != "全部" and 'board' in df.columns:
        df = df[df['board'] == board]

    if limit and limit > 0:
        df = df.head(limit)

    return df.reset_index(drop=True)


def _fallback_kline(clean_code: str, stock_name: str, limit: int) -> dict:
    """网络与缓存均不可用时的 K 线占位数据。

    明确标记 is_synthetic=True，前端必须据此提示用户，
    避免把占位曲线误认为真实行情。
    """
    periods = min(limit, 2500)
    dates = pd.date_range(end=datetime.date.today(), periods=periods, freq='B').strftime('%Y/%m/%d').tolist()
    k_values, volumes = [], []
    for i in range(len(dates)):
        p = 20.0 + np.sin(i / 15) * 4.5 + np.cos(i / 40) * 3.0 + i * 0.03
        o = round(p + np.random.uniform(-0.3, 0.3), 2)
        c = round(p + np.random.uniform(-0.3, 0.3), 2)
        l = round(min(o, c) - np.random.uniform(0.1, 0.4), 2)
        h = round(max(o, c) + np.random.uniform(0.1, 0.4), 2)
        k_values.append([o, c, l, h])
        volumes.append(int(100000 + np.random.randint(10000, 50000)))

    c_series = pd.Series([x[1] for x in k_values])
    return {
        "stock_code": clean_code,
        "stock_name": stock_name,
        "is_synthetic": True,
        "dates": dates,
        "kline_values": k_values,
        "volumes": volumes,
        "ma5": c_series.rolling(5, min_periods=1).mean().round(3).tolist(),
        "ma10": c_series.rolling(10, min_periods=1).mean().round(3).tolist(),
        "ma20": c_series.rolling(20, min_periods=1).mean().round(3).tolist(),
        "ma30": c_series.rolling(30, min_periods=1).mean().round(3).tolist(),
        "highest": round(max(x[3] for x in k_values), 2),
        "highest_date": dates[int(np.argmax([x[3] for x in k_values]))],
        "lowest": round(min(x[2] for x in k_values), 2),
        "lowest_date": dates[int(np.argmin([x[2] for x in k_values]))],
        "latest_close": k_values[-1][1],
        "change_pct": 0.0,
        "start_date": dates[0] if dates else "",
        "end_date": dates[-1] if dates else "",
        "total_count": len(dates),
        "years_span": round(len(dates) / 242, 1),
    }


def get_stock_kline_data(code: str, limit: int = 3800) -> dict:
    """返回适配 ECharts 的日 K 线、均线与成交量数据。"""
    clean_code = str(code).zfill(6)
    df = get_stock_data(clean_code)

    stock_name = clean_code
    for s in get_pool():
        if s['code'] == clean_code:
            stock_name = s['name']
            break

    if df is None or len(df) == 0:
        return _fallback_kline(clean_code, stock_name, limit)

    df_sub = df.tail(limit).copy() if limit and limit > 0 else df.copy()
    dates = [d.strftime('%Y/%m/%d') if hasattr(d, 'strftime') else str(d).replace('-', '/')
             for d in df_sub.index]

    k_values = [
        [round(float(r['open']), 2), round(float(r['close']), 2),
         round(float(r['low']), 2), round(float(r['high']), 2)]
        for _, r in df_sub.iterrows()
    ]

    close_series = df_sub['close'].astype(float)
    ma = {n: close_series.rolling(n, min_periods=1).mean().round(3).tolist() for n in (5, 10, 20, 30)}

    volumes = df_sub['volume'].astype(float).fillna(0).astype(int).tolist()
    high_idx = int(np.argmax([x[3] for x in k_values]))
    low_idx = int(np.argmin([x[2] for x in k_values]))

    return {
        "stock_code": clean_code,
        "stock_name": stock_name,
        "is_synthetic": False,
        "dates": dates,
        "kline_values": k_values,
        "volumes": volumes,
        "ma5": ma[5], "ma10": ma[10], "ma20": ma[20], "ma30": ma[30],
        "highest": round(k_values[high_idx][3], 2),
        "highest_date": dates[high_idx],
        "lowest": round(k_values[low_idx][2], 2),
        "lowest_date": dates[low_idx],
        "latest_close": k_values[-1][1] if k_values else 0.0,
        "change_pct": round(float(df_sub['pct_chg'].iloc[-1]), 2) if 'pct_chg' in df_sub.columns else 0.0,
        "start_date": dates[0] if dates else "",
        "end_date": dates[-1] if dates else "",
        "total_count": len(dates),
        "years_span": round(len(dates) / 242, 1),
    }
