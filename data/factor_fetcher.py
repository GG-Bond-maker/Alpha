# -*- coding: utf-8 -*-
"""基本面与行情因子获取

数据源分工
----------
东方财富接口在当前网络环境下被代理拦截，因此本模块采用可用源：

  行情（OHLCV）  akshare.stock_zh_a_daily      (新浪)
  估值（PE/PB）  akshare.stock_zh_valuation_baidu (百度)
  财务（ROE等）  akshare.stock_financial_abstract (按报告期)

关键设计：财务数据必须做「公告滞后对齐」
--------------------------------------
财报按报告期发布，但投资者实际看到的是公告日。若把 2024Q1 的 ROE
直接对齐到 2024-03-31，就使用了当时尚未公开的信息，构成前视泄漏。

本模块按法定披露截止日做保守滞后：
  Q1 (03-31) -> 04-30 可用
  半年 (06-30) -> 08-31 可用
  Q3 (09-30) -> 10-31 可用
  年报 (12-31) -> 次年 04-30 可用
"""

import os
import time
import datetime

import numpy as np
import pandas as pd
import akshare as ak

from config.config import CACHE_DIR, FACTOR_DIR

os.makedirs(FACTOR_DIR, exist_ok=True)

# 财务指标中文名 -> 内部字段名
FINANCIAL_FIELDS = {
    '净资产收益率(ROE)': 'roe',
    '总资产收益率(ROA)': 'roa',
    '毛利率': 'gross_margin',
    '销售净利率': 'net_margin',
    '资产负债率': 'debt_ratio',
    '营业总收入增长率': 'revenue_growth',
    '归属母公司股东的净利润增长率': 'profit_growth',
}

# 报告期 -> 实际可用日期（保守滞后，避免前视）
def _report_to_available(report_date: str) -> pd.Timestamp:
    """把报告期转换为信息可用的最早日期。"""
    dt = pd.to_datetime(report_date, format='%Y%m%d', errors='coerce')
    if pd.isna(dt):
        return pd.NaT
    m, y = dt.month, dt.year
    if m == 3:
        return pd.Timestamp(year=y, month=4, day=30)
    if m == 6:
        return pd.Timestamp(year=y, month=8, day=31)
    if m == 9:
        return pd.Timestamp(year=y, month=10, day=31)
    if m == 12:
        return pd.Timestamp(year=y + 1, month=4, day=30)
    return dt + pd.Timedelta(days=90)


def _cache_path(kind: str, code: str) -> str:
    return os.path.join(FACTOR_DIR, f"{kind}_{code}.csv")


def _read_cache(kind: str, code: str, max_age_days: int = 7):
    path = _cache_path(kind, code)
    if not os.path.exists(path):
        return None
    if os.environ.get('ALPHA_OFFLINE') != '1' and (time.time() - os.path.getmtime(path)) > max_age_days * 86400:
        return None
    try:
        df = pd.read_csv(path)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        return df
    except Exception:
        return None


def _write_cache(kind: str, code: str, df: pd.DataFrame):
    try:
        df.to_csv(_cache_path(kind, code), index=False, encoding='utf-8-sig')
    except Exception:
        pass


def fetch_price_history(code: str, start: str = '20150101', force: bool = False) -> pd.DataFrame:
    """获取前复权日线行情（新浪源）。"""
    cached = None if force else _read_cache('price', code)
    if cached is not None and len(cached) > 100:
        cached['date'] = pd.to_datetime(cached['date'])
        return cached
    if os.environ.get('ALPHA_OFFLINE') == '1':
        return None

    clean = str(code).zfill(6)
    prefix = 'sh' if clean.startswith(('6', '9')) else ('bj' if clean.startswith(('4', '8')) else 'sz')
    symbol = f"{prefix}{clean}"

    end = datetime.date.today().strftime('%Y%m%d')
    for source in ('sina', 'tx'):
        try:
            if source == 'sina':
                df = ak.stock_zh_a_daily(symbol=symbol, start_date=start, end_date=end, adjust='qfq')
            else:
                df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start, end_date=end, adjust='qfq')
            if df is None or len(df) == 0:
                continue
            df = df.rename(columns={'日期': 'date'})
            df['date'] = pd.to_datetime(df['date'])
            for c in ('open', 'close', 'high', 'low', 'volume'):
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
            df = df.sort_values('date').reset_index(drop=True)
            # 新浪源无涨跌幅字段，此处补算
            if 'pct_chg' not in df.columns:
                df['pct_chg'] = df['close'].pct_change() * 100.0
            _write_cache('price', clean, df)
            return df
        except Exception:
            continue
    return None


def fetch_valuation(code: str, force: bool = False) -> pd.DataFrame:
    """获取 PE(TTM) 与 PB 时间序列（百度源，5 日频）。"""
    cached = None if force else _read_cache('valuation', code)
    if cached is not None and len(cached) > 20:
        cached['date'] = pd.to_datetime(cached['date'])
        return cached
    if os.environ.get('ALPHA_OFFLINE') == '1':
        return None

    clean = str(code).zfill(6)
    frames = []
    for indicator, col in (('市盈率(TTM)', 'pe_ttm'), ('市净率', 'pb')):
        try:
            d = ak.stock_zh_valuation_baidu(symbol=clean, indicator=indicator, period='全部')
            if d is None or len(d) == 0:
                continue
            d = d.rename(columns={'value': col})
            d['date'] = pd.to_datetime(d['date'])
            d[col] = pd.to_numeric(d[col], errors='coerce')
            frames.append(d[['date', col]])
        except Exception:
            continue

    if not frames:
        return None

    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on='date', how='outer')
    out = out.sort_values('date').reset_index(drop=True)
    _write_cache('valuation', clean, out)
    return out


def fetch_financials(code: str, force: bool = False) -> pd.DataFrame:
    """获取财务指标并按公告滞后转换为可用日期。"""
    cached = None if force else _read_cache('financial', code)
    if cached is not None and len(cached) > 0:
        cached['available_date'] = pd.to_datetime(cached['available_date'])
        return cached
    if os.environ.get('ALPHA_OFFLINE') == '1':
        return None

    clean = str(code).zfill(6)
    try:
        raw = ak.stock_financial_abstract(symbol=clean)
    except Exception:
        return None
    if raw is None or len(raw) == 0:
        return None

    name_col = raw.columns[1]
    period_cols = [c for c in raw.columns[2:] if str(c).isdigit() and len(str(c)) == 8]
    if not period_cols:
        return None

    rows = []
    for cn_name, field in FINANCIAL_FIELDS.items():
        matched = raw[raw[name_col].astype(str).str.strip() == cn_name]
        if matched.empty:
            continue
        for p in period_cols:
            try:
                val = float(matched.iloc[0][p])
            except (TypeError, ValueError):
                continue
            if not np.isfinite(val):
                continue
            rows.append({
                'report_date': p,
                'available_date': _report_to_available(p),
                'field': field,
                'value': val,
            })

    if not rows:
        return None

    long_df = pd.DataFrame(rows)
    wide = long_df.pivot_table(index=['report_date', 'available_date'],
                               columns='field', values='value').reset_index()
    wide = wide.dropna(subset=['available_date']).sort_values('available_date').reset_index(drop=True)
    _write_cache('financial', clean, wide)
    return wide


def build_factor_panel(code: str, force: bool = False) -> pd.DataFrame:
    """把行情、估值、财务对齐成日频因子表。

    Returns:
        以 date 为索引，含价格、估值、财务因子与前瞻收益的 DataFrame
    """
    clean = str(code).zfill(6)

    price = fetch_price_history(clean, force=force)
    if price is None or len(price) < 120:
        return None

    df = price.set_index('date').sort_index()
    df.index = pd.to_datetime(df.index)

    # 估值：5 日频，前向填充到日频（只用历史值，无前视）
    val = fetch_valuation(clean, force=force)
    if val is not None and len(val) > 0:
        v = val.set_index('date').sort_index()
        v.index = pd.to_datetime(v.index)
        v = v[~v.index.duplicated(keep='last')]
        df = df.join(v.reindex(df.index, method='ffill'))

    # 财务：按「可用日期」合并，确保只用当时已公告的数据
    fin = fetch_financials(clean, force=force)
    if fin is not None and len(fin) > 0:
        f = fin.drop(columns=['report_date'], errors='ignore')
        # 同一可用日期可能对应多份报告（如年报与快报），保留最后一份
        f = f.sort_values('available_date').drop_duplicates(subset='available_date', keep='last')
        f = f.set_index('available_date').sort_index()
        f.index = pd.to_datetime(f.index)
        f = f[~f.index.duplicated(keep='last')]
        df = df.join(f.reindex(df.index, method='ffill'))

    df['stock_code'] = clean
    return df.reset_index()
