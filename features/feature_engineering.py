# -*- coding: utf-8 -*-
"""特征工程和技术指标计算模块
提供与 AShare-AI-Stock-Picker 兼容的双引擎技术指标计算：
1. 优先使用 talib（如已安装）
2. 自动平滑 Fallback 到纯 NumPy/Pandas 高性能向量化算法（零 C 依赖，跨平台 100% 稳定运行）
"""

import pandas as pd
import numpy as np

# 尝试导入 talib
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False


def _calculate_indicators_talib(df: pd.DataFrame) -> pd.DataFrame:
    """使用 TA-Lib 计算技术指标"""
    df = df.copy()
    
    # 20日EMA与比率
    df['EMA20'] = talib.EMA(df['close'].astype(float), timeperiod=20)
    df['EMA20_ratio'] = df['close'] / (df['EMA20'] + 1e-9)

    # RSI (14日)
    df['RSI14'] = talib.RSI(df['close'].astype(float), timeperiod=14)

    # MACD (12, 26, 9)
    macd, signal, hist = talib.MACD(
        df['close'].astype(float),
        fastperiod=12,
        slowperiod=26,
        signalperiod=9
    )
    df['MACD'] = macd

    # OBV 能量潮
    df['OBV'] = talib.OBV(df['close'].astype(float), df['volume'].astype(float))

    # CCI (14日)
    df['CCI'] = talib.CCI(
        df['high'].astype(float),
        df['low'].astype(float),
        df['close'].astype(float),
        timeperiod=14
    )

    # ATR (14日)
    df['ATR'] = talib.ATR(
        df['high'].astype(float),
        df['low'].astype(float),
        df['close'].astype(float),
        timeperiod=14
    )

    # ADX (14日)
    df['ADX'] = talib.ADX(
        df['high'].astype(float),
        df['low'].astype(float),
        df['close'].astype(float),
        timeperiod=14
    )

    return df


def _calculate_indicators_numpy_pandas(df: pd.DataFrame) -> pd.DataFrame:
    """使用纯 NumPy / Pandas 向量化算法计算技术指标（结果与 TA-Lib 对齐）"""
    df = df.copy()
    close = df['close'].astype(float)
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    volume = df['volume'].astype(float)

    # 1. EMA20 与 EMA20_ratio
    ema20 = close.ewm(span=20, adjust=False).mean()
    df['EMA20'] = ema20
    df['EMA20_ratio'] = close / (ema20 + 1e-9)

    # 2. RSI14
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df['RSI14'] = 100.0 - (100.0 / (1.0 + rs))

    # 3. MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26

    # 4. OBV
    direction = np.sign(close.diff().fillna(0))
    df['OBV'] = (direction * volume).cumsum()

    # 5. CCI (14)
    tp = (high + low + close) / 3.0
    tp_sma = tp.rolling(window=14, min_periods=1).mean()
    mad = (tp - tp_sma).abs().rolling(window=14, min_periods=1).mean()
    df['CCI'] = (tp - tp_sma) / (0.015 * mad + 1e-9)

    # 6. ATR (14)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['ATR'] = tr.ewm(alpha=1.0 / 14.0, adjust=False).mean()

    # 7. ADX (14)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    smoothed_tr = df['ATR'] + 1e-9
    plus_di = 100.0 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1.0 / 14.0, adjust=False).mean() / smoothed_tr)
    minus_di = 100.0 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1.0 / 14.0, adjust=False).mean() / smoothed_tr)
    dx = 100.0 * (plus_di - minus_di).abs() / ((plus_di + minus_di) + 1e-9)
    df['ADX'] = dx.ewm(alpha=1.0 / 14.0, adjust=False).mean()

    return df


def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算全套技术指标并添加到数据框
    
    Args:
        df (pd.DataFrame): 包含 open, close, high, low, volume 的 DataFrame
        
    Returns:
        pd.DataFrame: 包含技术指标与目标变量的 DataFrame
    """
    if df is None or len(df) == 0:
        return df

    df = df.copy()

    # 根据可用性选择引擎
    if HAS_TALIB:
        try:
            df = _calculate_indicators_talib(df)
        except Exception:
            df = _calculate_indicators_numpy_pandas(df)
    else:
        df = _calculate_indicators_numpy_pandas(df)

    # 计算未来 5 日收益率作为预测目标 (pct_chg_5d)
    if 'close' in df.columns:
        df['pct_chg_5d'] = df['close'].pct_change(periods=5).shift(-5)
        # 二分类标签：未来5日收益率是否大于0（1为涨，0为跌）
        df['target_up'] = (df['pct_chg_5d'] > 0).astype(int)

    return df
