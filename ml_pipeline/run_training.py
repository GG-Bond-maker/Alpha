# -*- coding: utf-8 -*-
"""离线重训与产物生成（论文实验数据的一键来源）

用法
----
    python -m ml_pipeline.run_training --trials 20

产出（全部为真实计算结果，无任何硬编码兜底）
  saved_models/lgbm_market_classifier.pkl  模型与切分数据
  saved_models/shap_explainer.pkl          TreeSHAP 解释器
  saved_models/global_importance.json      全局特征重要性
  saved_models/shap_summary.json           测试集 beeswarm 样本归因
  saved_models/evaluation_metrics.json     基线对比与逐轮训练/验证 Binary Logloss
  saved_models/backtest_result.json        组合回测
  saved_models/shap_additivity.json        加和一致性校验
  saved_models/training_report.json        汇总报告
  data/processed/realtime_recommendations.csv  最新截面推荐（前端数据源）
"""

import argparse
import json
import os
import sys

if __name__ == '__main__' and os.environ.get('ALPHA_TRAIN_WORKER') != '1':
    from ml_pipeline.artifacts import launch_training
    raise SystemExit(launch_training(sys.argv[1:]))

import numpy as np
import pandas as pd

from config.config import (
    FEATURE_COLS, FEATURE_NAMES_CN, SELECTED_FACTORS_PATH, DEFAULT_SELECTED_FACTORS,
    get_model_features, _load_selected_factors,
    PROCESSED_DIR, SAVED_MODELS_DIR, get_pool, get_stock_board,
    RATING_TOP_A_RATIO, RATING_TOP_B_RATIO,
)
from ml_pipeline.dataset import (
    build_factor_panel, build_inference_panel, time_split,
    FUNDAMENTAL_FACTORS, PRICE_FACTORS,
)
from ml_pipeline.factor_diagnosis import diagnose_all, factors_for_model, save_diagnosis
from ml_pipeline.evaluate_metrics import run_baseline_comparison
from ml_pipeline.backtest import run_backtest, save_backtest
from ml_pipeline.walk_forward import run_walk_forward, save_walk_forward
from ml_pipeline.attribution import analyze_attribution, save_attribution
from ml_pipeline.train_explainer import (
    build_explainer, compute_global_importance, verify_additivity,
)


def generate_recommendations(model, codes: list, panel=None, bundle=None) -> pd.DataFrame:
    """用训练好的模型为最新截面打分，生成前端使用的推荐表。"""
    from models.model_trainer import predict_signal

    pool_map = {s['code']: s for s in get_pool()}
    rows = []
    for code in codes:
        sig = predict_signal(code, model, panel=panel)
        if not sig:
            continue
        info = pool_map.get(code, {})
        rows.append({
            '代码': sig['code'],
            '名称': info.get('name', code),
            '行业': info.get('industry', '未分类'),
            '板块': info.get('board', get_stock_board(code)),
            '推荐评级': sig['rating'],
            '跑赢候选池均值概率': sig['probability'],
            '是否涨停': sig['is_limit_up'],
            '最新收盘价': sig['close'],
            '当日涨幅(%)': sig['pct_chg'],
            '更新日期': sig['update_date'],
            **{FEATURE_NAMES_CN.get(c, c): sig['features'][c] for c in get_model_features()},
            **{FEATURE_NAMES_CN.get(c, c): value
               for c, value in sig['raw_features'].items()},
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values('跑赢候选池均值概率', ascending=False).reset_index(drop=True)
    df.insert(0, '推荐排名', range(1, len(df) + 1))
    rank = np.arange(1, len(df) + 1)
    df['推荐评级'] = np.where(
        rank <= max(1, int(np.ceil(len(df) * RATING_TOP_A_RATIO))), 'A',
        np.where(rank <= max(1, int(np.ceil(len(df) * RATING_TOP_B_RATIO))), 'B', 'C'),
    )
    from ml_pipeline.selection import enrich_recommendations
    return enrich_recommendations(df, panel, bundle or {'model': model})


def main():
    parser = argparse.ArgumentParser(description="离线重训 LightGBM 推荐模型并生成全部实验产物")
    parser.add_argument('--trials', type=int, default=20, help='Optuna 试验轮数')
    parser.add_argument('--limit', type=int, default=None, help='限制标的数量（快速验证用）')
    parser.add_argument('--k', type=int, default=10, help='回测持仓数量')
    parser.add_argument('--selection', type=str, default='neutral',
                        choices=['global', 'neutral'],
                        help='默认回测口径：global 全市场排序 / neutral 行业中性')
    parser.add_argument('--no-walk-forward', action='store_true',
                        help='跳过滚动窗口验证（默认执行，约增加 3-5 分钟）')
    parser.add_argument('--wf-step', type=int, default=120,
                        help='滚动窗口每次前进的交易日数（默认 120，约半年）')
    parser.add_argument('--wf-no-backtest', action='store_true',
                        help='滚动窗口内跳过回测（仅算 AUC 与因子稳定性）')
    parser.add_argument('--cached', action='store_true', help='仅使用本地原始因子缓存，离线重建标签与特征')
    args = parser.parse_args()
    if args.trials < 1 or args.k < 1:
        parser.error('trials 和 k 必须大于 0')
    if args.cached:
        os.environ['ALPHA_OFFLINE'] = '1'
    run_id = os.environ['ALPHA_RUN_ID']
    print(f'[Experiment] 开始批次 {run_id}', flush=True)

    print("=" * 70)
    print(" LightGBM 推荐系统 · 离线重训")
    print("=" * 70)

    # 1. 构建面板
    pool = get_pool()
    codes = [s['code'] for s in pool]
    if args.limit:
        codes = codes[:args.limit]

    print(f"\n[1/7] 构建面板数据集（{len(codes)} 只标的，含基本面因子）...")
    panel = build_factor_panel(codes if args.limit else None, include_fundamental=True)
    panel.to_pickle(os.path.join(PROCESSED_DIR, 'panel_dataset.pkl'), compression='gzip')

    # 因子诊断：产出论文所需的因子有效性检验表
    print("\n[2/7] 因子有效性诊断（IC / ICIR / t 值）...")
    all_factors = list(FEATURE_COLS) + PRICE_FACTORS + FUNDAMENTAL_FACTORS
    train_for_selection, _, _ = time_split(panel)
    diagnosis = diagnose_all(train_for_selection, all_factors)
    selected_factors, selection_mode = factors_for_model(diagnosis)
    save_diagnosis(diagnosis)

    # 关键：把诊断结论固化为模型实际使用的因子列表，
    # 避免「诊断选出一套、模型训练另一套」的口径断裂。
    usable = selected_factors or DEFAULT_SELECTED_FACTORS
    with open(SELECTED_FACTORS_PATH, 'w', encoding='utf-8') as f:
        json.dump({
            'factors': usable,
            'model_features': [x + '_neu' for x in usable],
            'criteria': diagnosis['criteria'],
            'rejected': diagnosis['rejected_factors'],
            'selection_mode': selection_mode,
            'selection_period': [str(train_for_selection['date'].min()),
                                 str(train_for_selection['date'].max())],
        }, f, ensure_ascii=False, indent=2)
    print(f"[Factor] 入选 {len(usable)} 个因子并写入模型口径: {usable}")

    # 2. 训练
    print(f"\n[3/7] 训练模型（Optuna {args.trials} 轮，{len(get_model_features())} 维因子）...")
    from models.model_trainer import train_market_model
    result = train_market_model(
        panel=panel, n_trials=args.trials, force_retrain=True,
        candidate_factors=all_factors,
    )
    model = result['model']

    # 3. 基线对比
    print("\n[4/7] 基线对比评测...")
    eval_payload = run_baseline_comparison(result)

    # 4. 回测：全市场排序 vs 行业中性，两种模式都跑并对比
    print("\n[5/7] 组合回测（全市场 vs 行业中性）...")
    test = result['test'].copy()
    test['score_lgb'] = model.predict_proba(test[get_model_features()])[:, 1]

    bt_global = run_backtest(test, k=args.k, selection='global')
    bt_neutral = run_backtest(test, k=args.k, selection='neutral')

    for tag, r_ in (('全市场排序', bt_global), ('行业中性  ', bt_neutral)):
        s = r_['strategy']
        print(f"  {tag} k={args.k} 年化={s['annualized_return']:.2%} 夏普={s['sharpe']} "
              f"回撤={s['max_drawdown']:.2%} 超额={r_['excess']['annualized_return']:.2%} "
              f"行业数={r_.get('avg_sectors_held')}")

    # 默认口径可切换；两份结果都落盘便于论文中对比
    bt = bt_neutral if args.selection == 'neutral' else bt_global
    save_backtest(bt)
    with open(os.path.join(SAVED_MODELS_DIR, 'backtest_comparison.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'global': {k: bt_global[k] for k in ('strategy', 'benchmark', 'excess',
                                                 'params', 'avg_turnover', 'avg_sectors_held')},
            'neutral': {k: bt_neutral[k] for k in ('strategy', 'benchmark', 'excess',
                                                   'params', 'avg_turnover', 'avg_sectors_held')},
        }, f, ensure_ascii=False, indent=2)

    # 4.5 滚动窗口验证：给出比单次切分更可靠的口径
    wf = None
    attribution_result = None
    if not args.no_walk_forward:
        print("\n[5.5/7] 滚动窗口验证（walk-forward）...")
        wf = run_walk_forward(
            panel,
            step_days=args.wf_step,
            backtest_k=0 if args.wf_no_backtest else args.k,
            backtest_selection=args.selection,
            candidate_factors=all_factors,
        )
        if 'error' in wf:
            print(f"  [警告] {wf['error']}")
            wf = None
        else:
            s = wf['summary']
            print(f"  窗口数={s['n_windows']}  AUC均值={s['auc_mean']} "
                  f"中位数={s['auc_median']} 标准差={s['auc_std']} "
                  f"低于随机的窗口占比={s['pct_below_random']:.1%}")

            bts = wf.get('backtest_summary') or {}
            if bts:
                print(f"  回测跨窗口: 超额年化均值={bts['excess_ann_mean']:.2%} "
                      f"中位数={bts['excess_ann_median']:.2%} "
                      f"正超额窗口占比={bts['excess_positive_ratio']:.1%} "
                      f"最差回撤={bts['strategy_mdd_worst']:.2%}")
                agg = wf.get('backtest_aggregated') or {}
                if agg.get('strategy'):
                    st = agg['strategy']
                    print(f"  拼接净值: 年化={st['annualized_return']:.2%} "
                          f"夏普={st['sharpe']} 最大回撤={st['max_drawdown']:.2%}")
            save_walk_forward(wf)

            # Alpha / Beta 归因：判断超额收益是选股能力还是市场暴露
            print("  正在做 Alpha/Beta 归因...")
            attr = analyze_attribution(wf.get('backtest_aggregated'))
            attribution_result = None if 'error' in attr else attr
            if 'error' not in attr:
                reg = attr['regression']
                print(f"  Alpha 年化={reg['alpha_annual']:.2%} (t={reg['alpha_t']}, "
                      f"p={reg['alpha_p']})  Beta={reg['beta']:.4f}  R2={reg['r_squared']:.4f}")
                print(f"  结论: {attr['conclusion']['verdict']}")
                save_attribution(attr)
            else:
                print(f"  [警告] 归因失败: {attr['error']}")

    # 5. SHAP 归因
    print("\n[6/7] TreeSHAP 归因...")
    explainer = build_explainer(model)
    importance = compute_global_importance(result['test'], explainer)
    additivity = verify_additivity(model, explainer, result['test'][get_model_features()])
    print(f"[SHAP] 加和一致性: max_err={additivity['max_abs_error']}, "
          f"通过={additivity['passed']}")
    with open(os.path.join(SAVED_MODELS_DIR, 'shap_additivity.json'), 'w', encoding='utf-8') as f:
        json.dump(additivity, f, ensure_ascii=False, indent=2)

    # 6. 生成推荐表
    print("\n[7/7] 生成最新截面推荐...")
    # 推理不应依赖已经成熟的训练标签：重新构造含最新行情的横截面，
    # 否则模型会停留在最新行情之前 TARGET_DAYS 个交易日。
    inference_panel = build_inference_panel(codes, include_fundamental=True)
    rec_df = generate_recommendations(model, codes, inference_panel, bundle=result)
    if not rec_df.empty:
        rec_path = os.path.join(PROCESSED_DIR, 'realtime_recommendations.csv')
        rec_df.to_csv(rec_path, index=False, encoding='utf-8-sig')
        print(f"[Rec] {len(rec_df)} 条推荐已写入 {rec_path}")
        print(rec_df[['推荐排名', '代码', '名称', '推荐评级', '跑赢候选池均值概率']].head(10).to_string(index=False))
    else:
        print("[Rec] 未能生成推荐（可能所有标的预测均失败）")

    # 7. 汇总报告
    report = {
        'run_id': run_id,
        'panel': {
            'cached_only': args.cached,
            'feature_engine': 'pandas',
            'label_calendar': 'union_of_observed_market_sessions',
            'stocks': int(panel['stock_code'].nunique()),
            'dates': int(panel['date'].nunique()),
            'rows': int(len(panel)),
            'date_range': [str(panel['date'].min()), str(panel['date'].max())],
            'label': 'excess_ret_5d > 0',
            'features': get_model_features(),
            'selected_factors': _load_selected_factors(),
            'factor_selection_mode': selection_mode,
            'factor_selection_period': [str(train_for_selection['date'].min()),
                                        str(train_for_selection['date'].max())],
            'point_in_time_universe': bool(panel.attrs.get('universe_point_in_time', False)),
            'universe_note': (
                '按历史沪深300成分股及历史行业分类过滤。'
                if panel.attrs.get('universe_point_in_time', False)
                else '未提供 data/csi300_membership_history.csv，训练仍使用当前成分股回溯，'
                     '存在幸存者偏差；不能把该回测作为无偏历史成分股结果。'
            ),
            'return_definition': (
                'signal date close to next session open, held through close after '
                f'{5} sessions'
            ),
            'backtest_rebalance_every_sessions': 5,
        },
        'model_metrics': result['metrics'],
        'selection_layer': {'calibration': result['calibration'], 'factor_ranker': result['factor_ranker']},
        'best_params': result['params'],
        'loss_history': result.get('loss_history', {}),
        'baseline_comparison': eval_payload['comparison'],
        'ranking_curve_meta': eval_payload.get('ranking_curve_meta', {}),
        'baseline_errors': eval_payload['errors'],
        'backtest': {
            'strategy': bt.get('strategy', {}),
            'benchmark': bt.get('benchmark', {}),
            'excess': bt.get('excess', {}),
            'avg_turnover': bt.get('avg_turnover'),
        },
        'shap_additivity': additivity,
        'top_features': importance[:5],
        'walk_forward': (wf['summary'] if wf else None),
        'walk_forward_factor_stability': (wf['factor_stability'] if wf else None),
        'walk_forward_backtest': (wf.get('backtest_summary') if wf else None),
        'attribution': attribution_result,
    }
    from ml_pipeline.diagnostics import build_diagnostics
    build_diagnostics(test, bt)
    from ml_pipeline.stress_test import run_stress_test
    prediction_path = os.path.join(PROCESSED_DIR, 'walk_forward_predictions.csv')
    scored = pd.read_csv(prediction_path, dtype={'stock_code': str}) if os.path.exists(prediction_path) else None
    run_stress_test(panel=test, model=model, train_end=result['train']['date'].max(), scored_panel=scored, backtest=bt)
    from ml_pipeline.sensitivity_analysis import run_parameter_sensitivity
    run_parameter_sensitivity()
    from ml_pipeline.drift_monitor import generate_drift_report
    generate_drift_report()
    if rec_df.empty:
        raise RuntimeError('推荐截面为空，不能激活本批次')
    with open(os.path.join(SAVED_MODELS_DIR, 'training_report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    from ml_pipeline.artifacts import finalize_run
    finalize_run(report)

    print("\n" + "=" * 70)
    print(" 完成。训练集/验证集/测试集指标：")
    for split in ('train', 'val', 'test'):
        m = result['metrics'][split]
        print(f"   {split:5s}  AUC={m['auc']}  n={m['n_rows']}  dates={m['n_dates']}")
    print(f" 回测超额年化: {bt.get('excess', {}).get('annualized_return')}")
    if wf:
        s = wf['summary']
        print(f" 滚动窗口 AUC: 均值={s['auc_mean']} 中位数={s['auc_median']} "
              f"低于随机={s['pct_below_random']:.1%}（{s['n_windows']} 个窗口）")
        bts = wf.get('backtest_summary') or {}
        if bts:
            print(f" 滚动窗口超额年化: 均值={bts['excess_ann_mean']:.2%} "
                  f"正超额窗口占比={bts['excess_positive_ratio']:.1%}")
    print("=" * 70)


if __name__ == '__main__':
    main()
