"""Bounded, training-only temporal model comparison for weak financial signals.

The previous test period has already been observed. This protocol provides a
retrospective audit, not a claim of a fresh, untouched holdout.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from config.config import CANDIDATE_FACTORS, FEATURE_COLS, SHORT_HORIZON_FACTORS, TARGET_DAYS
from ml_pipeline.factor_diagnosis import compute_ic_series, diagnose_all, factors_for_model

REGULARIZED_PARAMS = dict(
    n_estimators=200, learning_rate=0.025, max_depth=3, num_leaves=7,
    min_child_samples=500, reg_alpha=1.0, reg_lambda=20.0,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.9,
    max_bin=63, n_jobs=4, random_state=42, verbose=-1,
)
LEGACY_PARAMS = dict(
    n_estimators=212, learning_rate=0.17254716573280354, max_depth=7,
    num_leaves=41, subsample=0.6624074561769746, subsample_freq=1,
    colsample_bytree=0.662397808134481, reg_alpha=0.00018747059221802545,
    reg_lambda=1.1752647960576206, n_jobs=4, random_state=42, verbose=-1,
)
EXISTING_PRICE = FEATURE_COLS + ['momentum_20d', 'momentum_60d', 'volatility_20d']
# turnover_proxy duplicates vol_ratio after its warm-up; do not count it twice.
ENRICHED_PRICE = EXISTING_PRICE + SHORT_HORIZON_FACTORS
PROFILES = [
    dict(name='legacy_control', features='legacy_ic', window=None, legacy=True),
    dict(name='consistent_ic', features='neutralized_ic', window=None),
    dict(name='existing_price', features='existing_price', window=None),
    dict(name='enriched_price', features='enriched_price', window=None),
    dict(name='enriched_rolling', features='enriched_price', window=756),
    dict(name='quality_all', features='quality_all', window=None, diagnostic_only=True),
    dict(name='enriched_stumps', features='enriched_price', window=None, depth=2),
]


def date_weights(frame: pd.DataFrame) -> np.ndarray:
    """Each date has equal total weight; normalize mean row weight to one."""
    counts = frame.groupby('date')['date'].transform('size').to_numpy(dtype=float)
    weights = 1.0 / counts
    return weights / weights.mean()


def fit_frame(frame: pd.DataFrame, profile: dict) -> pd.DataFrame:
    window = profile.get('window')
    if window:
        dates = np.sort(frame.date.unique())[-int(window):]
        return frame.loc[frame.date.isin(dates)]
    return frame


def quality_features(train: pd.DataFrame, factors: list[str]) -> list[str]:
    """Coverage/variation only; fitted independently within each training fold."""
    selected = []
    for factor in factors:
        col = factor + '_neu'
        if col not in train:
            continue
        values = train[col].replace([np.inf, -np.inf], np.nan)
        quarterly = values.notna().groupby(train.date.dt.to_period('Q')).mean()
        if (values.notna().mean() >= 0.90 and quarterly.min() >= 0.70
                and values.nunique() >= 10 and values.std() > 1e-9):
            selected.append(col)
    if not selected:
        raise ValueError('No features pass training-only quality gates')
    return selected


def features_for_profile(train: pd.DataFrame, profile: dict) -> list[str]:
    mode = profile['features']
    if mode in ('legacy_ic', 'neutralized_ic'):
        factors = ([f for f in CANDIDATE_FACTORS if f not in SHORT_HORIZON_FACTORS]
                   if mode == 'legacy_ic' else EXISTING_PRICE)
        report = diagnose_all(train, factors, representation=('raw' if mode == 'legacy_ic' else 'neutralized'))
        selected, _ = factors_for_model(report)
        return [f + '_neu' for f in selected]
    factors = {'existing_price': EXISTING_PRICE, 'enriched_price': ENRICHED_PRICE,
               'quality_all': [f for f in CANDIDATE_FACTORS if f != 'turnover_proxy']}[mode]
    return quality_features(train, factors)


def params_for_profile(profile: dict) -> dict:
    params = dict(LEGACY_PARAMS if profile.get('legacy') else REGULARIZED_PARAMS)
    if profile.get('depth'):
        params.update(max_depth=profile['depth'], num_leaves=2 ** profile['depth'] - 1)
    return params


def temporal_folds(train: pd.DataFrame, n_splits: int = 3, val_days: int = 252):
    """Full-date expanding folds with a gap and actual label-maturity purge."""
    dates = np.sort(train.date.unique())
    val_days = min(val_days, (len(dates) - 126 - TARGET_DAYS) // n_splits)
    if val_days < 20:
        raise ValueError('Insufficient trading dates for temporal comparison')
    for start in range(len(dates) - n_splits * val_days, len(dates), val_days):
        tr = train.loc[train.date.isin(dates[:start - TARGET_DAYS])]
        va = train.loc[train.date.isin(dates[start:start + val_days])]
        tr = tr.loc[pd.to_datetime(tr.label_end_date) < va.date.min()]
        if tr.empty or tr.label_end_date.max() >= va.date.min():
            raise ValueError('Unmatured labels entered a training fold')
        yield tr, va


def daily_auc(frame: pd.DataFrame, probability: np.ndarray) -> pd.Series:
    scores = frame[['date', 'target_up']].copy()
    scores['probability'] = np.asarray(probability)
    return pd.Series({date: roc_auc_score(group.target_up, group.probability)
                      for date, group in scores.groupby('date')
                      if len(group) >= 8 and group.target_up.nunique() == 2}).sort_index()


def select_model(train: pd.DataFrame, output_dir: str | Path) -> dict:
    """Freeze protocol before scores; choose once without validation/test labels."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    protocol = dict(version=1, profiles=PROFILES, regularized_params=REGULARIZED_PARAMS,
                    legacy_params=LEGACY_PARAMS, seed=42, cv_folds=3, cv_val_days=252,
                    selection_metric='mean_daily_auc_minus_0.25_fold_std',
                    weighting='equal_date_total_weight_except_legacy_control',
                    development_end=str(train.date.max()),
                    holdout_status='previously_observed_retrospective_recheck',
                    trials_total=len(PROFILES),
                    note='No early stopping or selection uses outer validation/test labels.')
    serialized = json.dumps(protocol, ensure_ascii=False, sort_keys=True, indent=2)
    protocol_hash = hashlib.sha256(serialized.encode()).hexdigest()
    (destination / 'model_selection_protocol.json').write_text(serialized, encoding='utf-8')
    folds = list(temporal_folds(train))
    results = []
    for profile in PROFILES:
        observations = []
        for fold, (past, future) in enumerate(folds, 1):
            past = fit_frame(past, profile)
            features = features_for_profile(past, profile)
            model = lgb.LGBMClassifier(**params_for_profile(profile))
            model.fit(past[features], past.target_up,
                      sample_weight=None if profile.get('legacy') else date_weights(past))
            pred = model.predict_proba(future[features])[:, 1]
            score = float(daily_auc(future, pred).mean())
            observations.append(dict(fold=fold, train_start=str(past.date.min()),
                                     train_end=str(past.date.max()),
                                     label_end=str(past.label_end_date.max()),
                                     validation_start=str(future.date.min()),
                                     validation_end=str(future.date.max()), features=features,
                                     section_auc=score,
                                     auc=float(roc_auc_score(future.target_up, pred))))
            print(f"[Selection] {profile['name']} fold={fold} daily_AUC={score:.6f}", flush=True)
        scores = np.array([r['section_auc'] for r in observations])
        results.append(dict(profile=profile, folds=observations, mean=float(scores.mean()),
                            std=float(scores.std(ddof=1)),
                            selection_score=float(scores.mean() - 0.25 * scores.std(ddof=1))))
    # The legacy control is diagnostic, not an extra opportunity to change policy.
    eligible = [r for r in results if not r['profile'].get('legacy')
                and not r['profile'].get('diagnostic_only')]
    best = max(eligible, key=lambda r: r['selection_score'])
    profile = best['profile']
    final_train = fit_frame(train, profile)
    features = features_for_profile(final_train, profile)
    plan = dict(protocol_sha256=protocol_hash, protocol=protocol, candidates=results,
                selected_profile=profile, params=params_for_profile(profile), features=features,
                selection_score=best['selection_score'], fit_start=str(final_train.date.min()),
                fit_end=str(final_train.date.max()), fit_rows=len(final_train),
                improvement_proven=False,
                warning='Selection scores are optimistic; outer rechecks were previously observed. '
                        'Prospective confirmation and point-in-time universe/fundamentals remain required.')
    (destination / 'model_selection.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[Selection] FROZEN winner={profile['name']} features={features}", flush=True)
    return plan


def freeze_training_plan(source: dict, train: pd.DataFrame,
                         source_run: str, output_dir: str | Path) -> dict:
    """Reuse the active feature set and parameters without a new model search."""
    if not source or not source.get('selected_profile') or not source.get('features') or not source.get('params'):
        raise ValueError('The active batch has no complete training plan to freeze')
    plan = deepcopy(source)
    canonical = json.dumps(plan['protocol'], ensure_ascii=False, sort_keys=True, indent=2)
    if hashlib.sha256(canonical.encode()).hexdigest() != plan['protocol_sha256']:
        raise ValueError('Active selection protocol hash mismatch')
    fitted = fit_frame(train, plan['selected_profile'])
    if not set(plan['features']).issubset(fitted.columns):
        raise ValueError('Current panel is missing frozen model features')
    plan.update(frozen_from_run=source_run, frozen_training=True,
                source_fit_start=source['fit_start'], source_fit_end=source['fit_end'],
                candidates_source_run=source_run,
                fit_start=str(fitted.date.min()), fit_end=str(fitted.date.max()),
                fit_rows=int(len(fitted)),
                training_label_end=str(pd.to_datetime(fitted.label_end_date).max()),
                warning='Feature list, LightGBM parameters and protocol frozen from the previous batch. '
                        'Recorded candidates belong to the source batch and were not re-evaluated. '
                        'The new holdout is not a fresh blind test after earlier historical inspection.')
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'model_selection_protocol.json').write_text(canonical, encoding='utf-8')
    (destination / 'model_selection.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[Selection] FROZEN from {source_run}: {plan['selected_profile']['name']} "
          f"features={len(plan['features'])} fit_end={plan['fit_end']}", flush=True)
    return plan


def audit_training_data(train: pd.DataFrame, output_dir: str | Path) -> dict:
    """Inspect development data only; no target-informed repairs on holdout."""
    rows = []
    for factor in CANDIDATE_FACTORS:
        col = factor + '_neu'
        if factor not in train or col not in train:
            continue
        raw_ic = compute_ic_series(train, factor)
        input_ic = compute_ic_series(train, col)
        values = train[col]
        rows.append(dict(factor=factor, missing_rate=float(values.isna().mean()),
                         raw_ic=float(raw_ic.mean()) if len(raw_ic) else None,
                         model_input_ic=float(input_ic.mean()) if len(input_ic) else None,
                         distinct_values=int(values.nunique()),
                         quarterly_coverage={str(k): float(v) for k, v in
                                             values.notna().groupby(train.date.dt.to_period('Q')).mean().items()}))
    ohlc = train[['open', 'high', 'low', 'close']]
    report = dict(rows=len(train), stocks=int(train.stock_code.nunique()),
                  start=str(train.date.min()), end=str(train.date.max()),
                  duplicate_keys=int(train.duplicated(['date', 'stock_code']).sum()),
                  invalid_ohlc_rows=int(((ohlc <= 0).any(axis=1) | (train.high < train.low)
                                        | (train.close > train.high + 1e-6)
                                        | (train.close < train.low - 1e-6)).sum()),
                  unclassified_industry_fraction=float((train.industry == '未分类').mean()),
                  positive_rate=float(train.target_up.mean()),
                  return_quantiles={str(k): float(v) for k, v in train.ret_5d_fwd.quantile([0, .001, .01, .5, .99, .999, 1]).items()},
                  features=rows,
                  limitations=['current-universe survivorship bias',
                               'fundamental revisions/actual announcements not fully point-in-time',
                               'qfq vendor adjustments can revise historical prices'])
    if report['duplicate_keys'] or report['invalid_ohlc_rows']:
        raise ValueError(f"Invalid training data: duplicates={report['duplicate_keys']}, OHLC={report['invalid_ohlc_rows']}")
    Path(output_dir, 'training_data_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def paired_block_interval(values: np.ndarray, block_days: int = 20,
                          repetitions: int = 2000) -> dict:
    """Moving-block bootstrap, preserving overlapping-label serial dependence."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2 * block_days:
        return dict(mean=float(values.mean()) if len(values) else None, ci95=None)
    rng = np.random.default_rng(42)
    means = np.empty(repetitions)
    blocks = int(np.ceil(len(values) / block_days))
    offsets = np.arange(block_days)
    for i in range(repetitions):
        starts = rng.integers(0, len(values) - block_days + 1, size=blocks)
        indices = (starts[:, None] + offsets).ravel()[:len(values)]
        means[i] = values[indices].mean()
    return dict(mean=float(values.mean()), ci95=np.quantile(means, [.025, .975]).tolist(),
                block_days=block_days, repetitions=repetitions,
                inference_scope='conditional retrospective uncertainty, not correction for all historical trials')


def compare_reference(result: dict, reference: dict, reference_run: str,
                      output_dir: str | Path) -> dict:
    """Evaluate the already frozen winner once; never feed these scores back."""
    report = dict(reference_run=reference_run, protocol_sha256=result['model_selection']['protocol_sha256'],
                  status='retrospective_previously_observed_holdout', splits={})
    original = reference['test'][['date', 'stock_code', 'target_up']].rename(columns={'target_up': '_original_label'})
    common = result['test'].merge(original, on=['date', 'stock_code'], how='inner', validate='one_to_one')
    if (len(common) != len(reference['test']) or len(common) != len(result['test'])
            or not (common.target_up == common._original_label).all()):
        # A later refresh may legitimately extend dates or revise prices/labels.
        # Do not block training or silently compare different prediction tasks.
        report.update(status='not_comparable_changed_population_or_labels',
                      reference_rows=len(reference['test']), selected_rows=len(result['test']),
                      common_keys=len(common))
        Path(output_dir, 'reference_comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return report
    for name in ('val', 'test'):
        frame = result[name]
        if name == 'test':
            frame = common
        old = reference['model'].predict_proba(frame[reference['feature_cols']])[:, 1]
        new = result['model'].predict_proba(frame[result['feature_cols']])[:, 1]
        old_daily, new_daily = daily_auc(frame, old), daily_auc(frame, new)
        difference = new_daily - old_daily
        report['splits'][name] = dict(
            rows=len(frame), dates=int(frame.date.nunique()),
            start=str(frame.date.min()), end=str(frame.date.max()),
            reference_auc=float(roc_auc_score(frame.target_up, old)),
            selected_auc=float(roc_auc_score(frame.target_up, new)),
            reference_daily_auc=float(old_daily.mean()), selected_daily_auc=float(new_daily.mean()),
            paired_daily_auc_difference=paired_block_interval(difference.to_numpy()),
            selected_daily_auc_minus_random=paired_block_interval((new_daily - .5).to_numpy()),
        )
    Path(output_dir, 'reference_comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[Selection] Outer retrospective recheck: ' + json.dumps(report['splits'], ensure_ascii=False), flush=True)
    return report
