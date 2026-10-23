# -*- coding: utf-8 -*-
"""技术指标与特征工程模块

职责边界
--------
本模块只负责「单只股票时间序列」上的计算：
  - 原始技术指标（EMA/RSI/MACD/OBV/CCI/ATR/ADX），供前端展示与 SHAP 归因；
  - 无量纲化特征（FEATURE_COLS），供模型训练；
  - 前瞻收益 ret_5d_fwd，供训练层做截面超额收益标注。

注意：截面超额收益无法在单只股票内计算，必须跨股票聚合后去均值，
因此本模块只产出前瞻收益，标签的二值化在 model_trainer 中完成。

双引擎：优先 TA-Lib，缺失时回退到纯 NumPy/Pandas 向量化实现。
"""

import pandas as pd
import numpy as np

from config.config import TARGET_DAYS

try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False


def _calc_talib(df: pd.DataFrame) -> pd.DataFrame:
    """使用 TA-Lib 计算原始技术指标。"""
    close = df['close'].astype(float)
    high = df['high'].astype(float)
    low = df['low'].astype(float)

    df['EMA20'] = talib.EMA(close, timeperiod=20)
    df['RSI14'] = talib.RSI(close, timeperiod=14)
    macd, _signal, _hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    df['MACD'] = macd
    df['OBV'] = talib.OBV(close, df['volume'].astype(float))
    df['CCI'] = talib.CCI(high, low, close, timeperiod=14)
    df['ATR'] = talib.ATR(high, low, close, timeperiod=14)
    df['ADX'] = talib.ADX(high, low, close, timeperiod=14)
    return df


def _calc_pandas(df: pd.DataFrame) -> pd.DataFrame:
    """纯 NumPy/Pandas 向量化实现，结果与 TA-Lib 对齐。"""
    close = df['close'].astype(float)
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    volume = df['volume'].astype(float)

    df['EMA20'] = close.ewm(span=20, adjust=False).mean()

    delta = close.diff()
    avg_gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    df['RSI14'] = 100.0 - (100.0 / (1.0 + avg_gain / (avg_loss + 1e-9)))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26

    direction = np.sign(close.diff().fillna(0))
    df['OBV'] = (direction * volume).cumsum()

    tp = (high + low + close) / 3.0
    tp_sma = tp.rolling(14, min_periods=1).mean()
    mad = (tp - tp_sma).abs().rolling(14, min_periods=1).mean()
    df['CCI'] = (tp - tp_sma) / (0.015 * mad + 1e-9)

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.ewm(alpha=1.0 / 14.0, adjust=False).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr_safe = df['ATR'] + 1e-9
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / 14.0, adjust=False).mean() / atr_safe
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / 14.0, adjust=False).mean() / atr_safe
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    df['ADX'] = dx.ewm(alpha=1.0 / 14.0, adjust=False).mean()
    return df


def add_normalized_features(df: pd.DataFrame) -> pd.DataFrame:
    """在原始指标基础上派生模型使用的无量纲特征。

    原始 close / volume / OBV 的量级跨股票不可比，直接喂给树模型会让
    分裂点退化为「识别是哪只股票」而非「识别技术形态」，因此全部归一化。
    """
    close = df['close'].astype(float)
    volume = df['volume'].astype(float)
    eps = 1e-9

    df['EMA20_ratio'] = close / (df['EMA20'] + eps)
    df['MACD_norm'] = df['MACD'] / (close + eps)
    df['ATR_ratio'] = df['ATR'] / (close + eps)

    obv = df['OBV'].astype(float)
    obv_mean = obv.rolling(60, min_periods=10).mean()
    obv_std = obv.rolling(60, min_periods=10).std()
    df['OBV_zscore'] = (obv - obv_mean) / (obv_std + eps)

    vol_ma20 = volume.rolling(20, min_periods=5).mean()
    df['vol_ratio'] = volume / (vol_ma20 + eps)

    ma5 = close.rolling(5, min_periods=2).mean()
    ma20 = close.rolling(20, min_periods=5).mean()
    df['ma_gap'] = (ma5 - ma20) / (ma20 + eps)

    return df


def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算全套技术指标、归一化特征与前瞻收益。

    Args:
        df: 含 open/high/low/close/volume/pct_chg 列的 DataFrame

    Returns:
        追加了指标与 ret_5d_fwd 列的 DataFrame（索引保持原样）
    """
    if df is None or len(df) == 0:
        return df

    df = df.copy()

    if HAS_TALIB:
        try:
            df = _calc_talib(df)
        except Exception:
            df = _calc_pandas(df)
    else:
        df = _calc_pandas(df)

    df = add_normalized_features(df)

    # 可执行的 5 日持有收益：在信号日收盘后计算信号，下一交易日开盘买入，
    # 持有至第 TARGET_DAYS 个交易日收盘。末尾没有完整持有期的行保留 NaN，
    # 训练数据清理时不得对这个标签做前向填充。
    if 'close' in df.columns:
        if 'open' in df.columns:
            entry = df['open'].shift(-1)
            exit_ = df['close'].shift(-TARGET_DAYS)
            df['ret_5d_fwd'] = exit_ / entry - 1.0
        else:
            # 兼容不提供开盘价的数据源；回测报告会披露该近似口径。
            df['ret_5d_fwd'] = df['close'].shift(-TARGET_DAYS) / df['close'] - 1.0
        # 兼容旧字段名，避免历史脚本与缓存读取逻辑断裂
        df['pct_chg_5d'] = df['ret_5d_fwd']

    return df
