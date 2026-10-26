# -*- coding: utf-8 -*-
"""滚动窗口（Walk-Forward）验证

为什么需要这一层
----------------
单次三段切分的验证结果高度依赖切分点落在哪个市场状态。本项目的实测表明：
同一套流程，验证集 AUC 可以是 0.4975（低于随机），滚动窗口均值却是 0.5105，
且 33% 的窗口低于 0.5。只报单一数字会同时高估稳定性、低估不确定性。

滚动窗口用「过去 N 年训练、随后 M 个月检验」逐段推进，产出：
  - 每个窗口的整体 AUC；
  - 每个窗口的截面 AUC 分布（衡量选股能力而非跨期漂移）；
  - 每个窗口内各因子的 IC 与 t 值（衡量信号是否在衰减）；
  - 汇总统计：均值 / 中位数 / 标准差 / 跑赢随机的窗口占比。

这些数字才是论文里该报告的口径。
"""

import json
import os

import numpy as np
import pandas as pd

from config.config import SAVED_MODELS_DIR, get_model_features, TARGET_DAYS
from ml_pipeline.factor_diagnosis import diagnose_all, factors_for_model, hac_t_stat

# 默认参数：每 120 个交易日（约半年）滚动一次，训练集取窗口起点往前全部历史
DEFAULT_STEP_DAYS = 120
MIN_TRAIN_DAYS = 252
MIN_VAL_DAYS = 20
MIN_STOCKS_PER_SECTION = 20

PARAMS = dict(
    n_estimators=300, learning_rate=0.013, max_depth=3, num_leaves=46,
    subsample=0.8, colsample_bytree=0.9, reg_alpha=5e-4, reg_lambda=0.009,
    subsample_freq=1, n_jobs=4,
    random_state=42, verbose=-1,
)


def _section_auc(df: pd.DataFrame, score_col: str, label_col: str = 'target_up') -> np.ndarray:
    """逐截面 AUC。"""
    from sklearn.metrics import roc_auc_score

    out = []
    for _date, g in df.groupby('date'):
        if len(g) >= MIN_STOCKS_PER_SECTION and g[label_col].nunique() > 1:
            out.append(roc_auc_score(g[label_col], g[score_col]))
    return np.array(out)


def _factor_ic(df: pd.DataFrame, factor: str, ret_col: str = 'ret_5d_fwd') -> dict:
    """窗口内因子的 IC 均值与 t 值。"""
    ics = []
    for _date, g in df.groupby('date'):
        if len(g) >= MIN_STOCKS_PER_SECTION and g[factor].nunique() > 3:
            ic = g[factor].corr(g[ret_col], method='spearman')
            if pd.notna(ic):
                ics.append(ic)
    if not ics:
        return {'ic': None, 't': None, 'n_sections': 0}
    arr = np.array(ics)
    t = hac_t_stat(arr)
    return {
        'ic': round(float(arr.mean()), 4),
        't': round(t, 2),
        'n_sections': int(len(arr)),
    }


def _window_backtest(va: pd.DataFrame, k: int, selection: str,
                     score_col: str = 'pred', ret_col: str = 'ret_5d_fwd') -> dict:
    """在单个窗口的验证段上执行回测。

    复用 ml_pipeline.backtest 的持仓构建与成本口径，保证与全样本回测一致。
    """
    from ml_pipeline.backtest import run_backtest

    return run_backtest(va, k=k, ret_col=ret_col, score_col=score_col,
                        selection=selection)


def run_walk_forward(panel: pd.DataFrame, step_days: int = DEFAULT_STEP_DAYS,
                     val_days: int = DEFAULT_STEP_DAYS,
                     start_ratio: float = 0.45,
                     factors: list = None,
                     candidate_factors: list = None,
                     backtest_k: int = 10,
                     backtest_selection: str = 'neutral',
                     verbose: bool = True) -> dict:
    """执行滚动窗口验证。

    Args:
        panel: 已完成中性化的面板数据
        step_days: 每次前进的交易日数
        val_days: 每个窗口的检验长度（交易日）
        start_ratio: 从时间轴的哪个位置开始滚动（保证首窗训练样本充足）
        factors: 需跟踪 IC 的因子列名（已中性化）

    Returns:
        窗口明细与汇总统计
    """
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score

    if factors is None and candidate_factors is None:
        factors = get_model_features()

    dates = np.sort(panel['date'].unique())
    start = int(len(dates) * start_ratio)

    windows = []
    scored_windows = []
    for i in range(start, len(dates), step_days):
        val_stop = min(i + val_days, len(dates))
        # 不在窗口末尾使用会跨入下一窗口的未完成 5 日收益。
        val_return_stop = val_stop - TARGET_DAYS
        train_stop = i - TARGET_DAYS
        if val_return_stop - i < MIN_VAL_DAYS or train_stop <= 0:
            continue
        train_dates = dates[:train_stop]
        val_dates = dates[i:val_return_stop]
        train_end = dates[train_stop - 1]
        val_start = dates[i]
        val_end = dates[val_return_stop - 1]
        tr = panel[panel['date'].isin(train_dates)]
        va = panel[panel['date'].isin(val_dates)]
        if 'label_end_date' in tr.columns:
            tr = tr[pd.to_datetime(tr['label_end_date']) < pd.Timestamp(val_start)]
            va = va[pd.to_datetime(va['label_end_date']) <= pd.Timestamp(dates[val_stop - 1])]

        if tr['date'].nunique() < MIN_TRAIN_DAYS or va['date'].nunique() < MIN_VAL_DAYS:
            continue
        if va['target_up'].nunique() < 2:
            continue

        if candidate_factors:
            diagnosis = diagnose_all(tr, candidate_factors)
            selected_raw, selection_mode = factors_for_model(diagnosis)
            fold_features = [f + '_neu' for f in selected_raw]
        else:
            selected_raw = [f[:-4] if f.endswith('_neu') else f for f in factors]
            fold_features = list(factors)
            selection_mode = 'fixed_training_selection'

        model = lgb.LGBMClassifier(**PARAMS)
        model.fit(tr[fold_features], tr['target_up'])

        va = va.copy()
        va['pred'] = model.predict_proba(va[fold_features])[:, 1]
        va['model_train_end'] = tr['date'].max()
        scored_windows.append(va)

        overall_auc = float(roc_auc_score(va['target_up'], va['pred']))
        sec_auc = _section_auc(va, 'pred')

        window = {
            'train_end': str(train_end)[:10],
            'val_start': str(val_start)[:10],
            'val_end': str(val_end)[:10],
            'n_train': int(len(tr)),
            'n_val': int(len(va)),
            'n_val_dates': int(va['date'].nunique()),
            'selected_factors': selected_raw,
            'factor_selection_mode': selection_mode,
            'auc': round(overall_auc, 4),
            'section_auc_mean': round(float(sec_auc.mean()), 4) if sec_auc.size else None,
            'section_auc_median': round(float(np.median(sec_auc)), 4) if sec_auc.size else None,
            'section_auc_below_half': round(float((sec_auc < 0.5).mean()), 4) if sec_auc.size else None,
            'factor_ic': {f: _factor_ic(va, f) for f in fold_features},
        }

        # 同一窗口内做回测：用本窗口训练的模型给本窗口打分，无未来信息
        bt = None
        if backtest_k and backtest_k > 0:
            bt = _window_backtest(va, backtest_k, backtest_selection)
            if bt and 'error' not in bt:
                window['bt_strategy_ann'] = bt['strategy']['annualized_return']
                window['bt_strategy_mdd'] = bt['strategy']['max_drawdown']
                window['bt_excess_ann'] = bt['excess']['annualized_return']
                window['bt_turnover'] = bt.get('avg_turnover')
            else:
                window['bt_strategy_ann'] = None
                window['bt_strategy_mdd'] = None
                window['bt_excess_ann'] = None
                window['bt_turnover'] = None

        windows.append(window)

        if verbose:
            bt_info = ''
            if window.get('bt_excess_ann') is not None:
                bt_info = f"  超额={window['bt_excess_ann']:.2%}"
            print(f"  {window['val_start']} ~ {window['val_end']}  "
                  f"AUC={window['auc']:.4f}  截面AUC均值={window['section_auc_mean']}"
                  f"{bt_info}")

    if not windows:
        return {'error': '没有产生任何有效窗口，请检查数据时间跨度或阈值设置',
                'windows': []}

    aucs = np.array([w['auc'] for w in windows])
    sec_means = np.array([w['section_auc_mean'] for w in windows
                          if w['section_auc_mean'] is not None])

    # 因子 IC 的跨窗口稳定性
    factor_summary = {}
    tracked = sorted({f for w in windows for f in w['factor_ic']})
    for f in tracked:
        items = [w['factor_ic'][f] for w in windows
                 if f in w['factor_ic'] and w['factor_ic'][f]['ic'] is not None]
        ics = [x['ic'] for x in items]
        ts = [x['t'] for x in items if x['t'] is not None]
        if not ics:
            continue
        ics_arr = np.array(ics)
        factor_summary[f] = {
            'ic_mean': round(float(ics_arr.mean()), 4),
            'ic_std': round(float(ics_arr.std(ddof=1)) if len(ics_arr) > 1 else 0.0, 4),
            'ic_positive_ratio': round(float((ics_arr > 0).mean()), 4),
            'sign_flips': int(np.sum(np.diff(np.sign(ics_arr)) != 0)) if len(ics_arr) > 1 else 0,
            't_mean': round(float(np.mean(ts)), 2) if ts else None,
            'n_significant': int(np.sum(np.abs(ts) >= 2.0)) if ts else 0,
            'n_windows': int(len(ics)),
        }

    # 回测跨窗口汇总
    bt_excess = np.array([w['bt_excess_ann'] for w in windows
                          if w.get('bt_excess_ann') is not None])
    bt_ann = np.array([w['bt_strategy_ann'] for w in windows
                       if w.get('bt_strategy_ann') is not None])
    bt_mdd = np.array([w['bt_strategy_mdd'] for w in windows
                       if w.get('bt_strategy_mdd') is not None])

    bt_summary = {}
    if bt_excess.size:
        bt_summary = {
            'n_windows': int(bt_excess.size),
            'excess_ann_mean': round(float(bt_excess.mean()), 4),
            'excess_ann_median': round(float(np.median(bt_excess)), 4),
            'excess_ann_std': round(float(bt_excess.std(ddof=1)) if bt_excess.size > 1 else 0.0, 4),
            'excess_positive_ratio': round(float((bt_excess > 0).mean()), 4),
            'strategy_ann_mean': round(float(bt_ann.mean()), 4) if bt_ann.size else None,
            'strategy_ann_min': round(float(bt_ann.min()), 4) if bt_ann.size else None,
            'strategy_ann_max': round(float(bt_ann.max()), 4) if bt_ann.size else None,
            'strategy_mdd_worst': round(float(bt_mdd.min()), 4) if bt_mdd.size else None,
            'strategy_mdd_mean': round(float(bt_mdd.mean()), 4) if bt_mdd.size else None,
        }

    # 把各窗口的样本拼回一条时间序列后统一回测，使持仓与换手成本
    # 在所有窗口使用一致的期末平仓与双边费用口径。
    aggregated = {}
    if backtest_k and backtest_k > 0 and scored_windows:
        from ml_pipeline.backtest import run_backtest
        scored_panel = pd.concat(scored_windows, ignore_index=True)
        scored_panel = scored_panel.sort_values(['date', 'model_train_end']).drop_duplicates(['date', 'stock_code'], keep='first')
        from config.config import PROCESSED_DIR
        keep = ['date', 'stock_code', 'pred', 'ret_5d_fwd', 'industry', 'pct_chg', 'model_train_end', 'label_end_date']
        scored_panel[[c for c in keep if c in scored_panel]].to_csv(os.path.join(PROCESSED_DIR, 'walk_forward_predictions.csv'), index=False)
        aggregated = run_backtest(
            scored_panel, k=backtest_k, ret_col='ret_5d_fwd',
            score_col='pred', selection=backtest_selection,
        )

    summary = {
        'n_windows': int(len(windows)),
        'auc_mean': round(float(aucs.mean()), 4),
        'auc_median': round(float(np.median(aucs)), 4),
        'auc_std': round(float(aucs.std(ddof=1)) if len(aucs) > 1 else 0.0, 4),
        'auc_min': round(float(aucs.min()), 4),
        'auc_max': round(float(aucs.max()), 4),
        'pct_below_random': round(float((aucs < 0.5).mean()), 4),
        'section_auc_mean': round(float(sec_means.mean()), 4) if sec_means.size else None,
        'step_days': step_days,
        'val_days': val_days,
        'backtest_k': backtest_k,
        'backtest_selection': backtest_selection,
        'params': PARAMS,
    }

    return {
        'summary': summary,
        'windows': windows,
        'factor_stability': factor_summary,
        'backtest_summary': bt_summary,
        'backtest_aggregated': aggregated,
        'note': ('滚动窗口结果比单次切分更可靠：单次验证集 AUC 受切分点所在市场状态影响，'
                 '滚动窗口给出的是分布的均值与离散度。连续回测把每个窗口模型在其验证段的'
                 '预测拼接后统一计算，每个持有期末平仓，窗口边界沿用相同收益与双边费用口径。'),
    }


def save_walk_forward(result: dict, path: str = None) -> str:
    if path is None:
        path = os.path.join(SAVED_MODELS_DIR, 'walk_forward.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[WalkForward] 结果已保存: {path}")
    return path
