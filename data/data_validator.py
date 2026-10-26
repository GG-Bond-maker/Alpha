# -*- coding: utf-8 -*-
"""金融时序数据质量检验门禁 (ML4T Data Validation Gate)

依照 ML4T 数据工程准则，在模型训练、因子计算与实盘推断前
对日线数据与特征面板进行系统性检验，防止脏数据、未复权拆分、时间戳重复
与极端异常值无感渗入模型。
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def validate_ohlcv(df: pd.DataFrame, symbol: str = "") -> Dict[str, Any]:
    """系统性检验单只股票或资产的 OHLCV 日线质量。

    Checks:
      1. OHLC 几何一致性：High >= Low, High >= Open, High >= Close, Low <= Open, Low <= Close
      2. 价格非负性：Close > 0, Open > 0, High > 0, Low > 0
      3. 成交量非负：Volume >= 0
      4. 极端日收益率（可能存在未除权拆股）：|ret| > 50%
      5. 时间戳重复：Duplicate dates
      6. 缺失值：NaN 计数
      7. 价格僵死（Stale Prices）：连续 5 日及以上收盘价完全相同且成交量不为 0

    Returns:
        包含各项异常计数与整体通过状态 (passed) 的审计字典。
    """
    if df is None or df.empty:
        return {
            "symbol": symbol,
            "total_rows": 0,
            "passed": False,
            "issues": {"empty_dataframe": 1},
            "summary": "数据为空",
        }

    work = df.copy()
    issues: Dict[str, int] = {}

    # 统一日期字段
    if "date" in work.columns:
        date_series = pd.to_datetime(work["date"])
    elif isinstance(work.index, pd.DatetimeIndex):
        date_series = pd.Series(work.index)
    else:
        date_series = None

    # 1. 时间戳重复检验
    if date_series is not None:
        issues["duplicate_dates"] = int(date_series.duplicated().sum())
    else:
        issues["duplicate_dates"] = 0

    # 2. OHLC 几何一致性检验
    needed_cols = {"open", "high", "low", "close"}
    if needed_cols.issubset(work.columns):
        high = pd.to_numeric(work["high"], errors="coerce")
        low = pd.to_numeric(work["low"], errors="coerce")
        open_ = pd.to_numeric(work["open"], errors="coerce")
        close = pd.to_numeric(work["close"], errors="coerce")

        issues["high_lt_low"] = int((high < low).sum())
        issues["close_outside_hl"] = int(((close > high) | (close < low)).sum())
        issues["open_outside_hl"] = int(((open_ > high) | (open_ < low)).sum())
        issues["negative_or_zero_price"] = int(((close <= 0) | (open_ <= 0) | (high <= 0) | (low <= 0)).sum())

        # 3. 极端未复权跳空收益检验 (|ret| > 50%)
        daily_ret = close.pct_change()
        issues["extreme_returns"] = int((daily_ret.abs() > 0.50).sum())

        # 4. 价格僵死检验（连续 5 天价格不变）
        consecutive_same = (close.diff() == 0).astype(int)
        flat_runs = consecutive_same.groupby((consecutive_same != consecutive_same.shift()).cumsum()).cumsum()
        issues["stale_price_runs"] = int((flat_runs >= 5).sum())
    else:
        for c in needed_cols:
            if c not in work.columns:
                issues[f"missing_column_{c}"] = 1

    # 5. 成交量非负检验
    if "volume" in work.columns:
        vol = pd.to_numeric(work["volume"], errors="coerce")
        issues["negative_volume"] = int((vol < 0).sum())
        issues["null_volume"] = int(vol.isna().sum())

    # 缺失值统计
    issues["null_close"] = int(work["close"].isna().sum()) if "close" in work.columns else 0

    # 判定是否通过门禁：严重几何违背或极端收益视为阻断级不合格
    critical_errors = (
        issues.get("high_lt_low", 0)
        + issues.get("negative_or_zero_price", 0)
        + issues.get("duplicate_dates", 0)
        + issues.get("extreme_returns", 0)
    )
    passed = critical_errors == 0

    return {
        "symbol": symbol,
        "total_rows": len(work),
        "passed": passed,
        "critical_errors": critical_errors,
        "issues": {k: v for k, v in issues.items() if v > 0},
        "summary": "数据检验合格" if passed else f"发现 {critical_errors} 处阻断级数据质量问题",
    }


def validate_panel_dataset(panel: pd.DataFrame, feature_cols: Optional[List[str]] = None) -> Dict[str, Any]:
    """系统性检验多标的横截面/时间序列面板数据集。"""
    if panel is None or panel.empty:
        return {"passed": False, "error": "面板为空"}

    report: Dict[str, Any] = {
        "total_rows": len(panel),
        "unique_dates": int(panel["date"].nunique()) if "date" in panel.columns else 0,
        "unique_stocks": int(panel["stock_code"].nunique()) if "stock_code" in panel.columns else 0,
        "issues": {},
    }

    # 检查主键唯一性 (date, stock_code)
    if "date" in panel.columns and "stock_code" in panel.columns:
        dups = int(panel.duplicated(subset=["date", "stock_code"]).sum())
        if dups > 0:
            report["issues"]["duplicate_records"] = dups

    # 检查前瞻标签
    if "ret_5d_fwd" in panel.columns:
        ret = panel["ret_5d_fwd"]
        report["issues"]["ret_5d_nan"] = int(ret.isna().sum())
        report["issues"]["ret_5d_inf"] = int(np.isinf(ret).sum())
        # 极端 5 日前瞻收益率（超出 300% 视为数据异常）
        report["issues"]["extreme_5d_ret"] = int((ret.abs() > 3.0).sum())

    # 检查特征列中的 Inf 异常
    if feature_cols:
        inf_counts = {}
        for col in feature_cols:
            if col in panel.columns:
                infs = int(np.isinf(panel[col]).sum())
                if infs > 0:
                    inf_counts[col] = infs
        if inf_counts:
            report["issues"]["feature_infinities"] = inf_counts

    report["passed"] = len(report["issues"]) == 0
    report["summary"] = "面板检验通过" if report["passed"] else f"发现 {len(report['issues'])} 项需修正的数据问题"
    return report
