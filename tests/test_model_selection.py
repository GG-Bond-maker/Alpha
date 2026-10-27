"""Temporal causality and experiment isolation, without relying on live data."""
import unittest
from unittest.mock import patch
import tempfile
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config.config import SHORT_HORIZON_FACTORS
from ml_pipeline.dataset import _add_price_factors, _prepare_single
from ml_pipeline.factor_diagnosis import diagnose_all
from ml_pipeline.model_selection import (
    date_weights, fit_frame, temporal_folds, quality_features, paired_block_interval,
    freeze_training_plan,
)


class ModelSelectionTests(unittest.TestCase):
    def test_refit_freezes_prior_features_and_parameters_without_search(self):
        protocol = {'development_end': '2022-12-30', 'trials_total': 7}
        canonical = json.dumps(protocol, ensure_ascii=False, sort_keys=True, indent=2)
        source = {'protocol': protocol,
                  'protocol_sha256': hashlib.sha256(canonical.encode()).hexdigest(),
                  'selected_profile': {'name': 'enriched_price', 'window': None},
                  'features': ['signal_neu'], 'params': {'n_estimators': 200},
                  'fit_start': '2020-01-01', 'fit_end': '2022-12-30',
                  'candidates': [{'profile': {'name': 'enriched_price'}, 'selection_score': .51}]}
        dates = pd.bdate_range('2023-01-03', periods=8)
        train = pd.DataFrame({'date': dates, 'label_end_date': dates + pd.offsets.BDay(5),
                              'signal_neu': range(8)})
        with tempfile.TemporaryDirectory() as destination:
            with patch('ml_pipeline.model_selection.select_model', side_effect=AssertionError('search')):
                frozen = freeze_training_plan(source, train, 'source-run', destination)
            self.assertEqual(json.loads((Path(destination) /
                                         'model_selection_protocol.json').read_text()), protocol)
        self.assertEqual(frozen['features'], source['features'])
        self.assertEqual(frozen['params'], source['params'])
        self.assertEqual(frozen['frozen_from_run'], 'source-run')
        self.assertEqual(frozen['fit_end'], str(dates[-1]))
        self.assertEqual(frozen['training_label_end'], str(dates[-1] + pd.offsets.BDay(5)))
        self.assertEqual(source.get('frozen_training'), None)

    def test_new_features_are_invariant_to_future_prices(self):
        rng = np.random.default_rng(47)
        close = 100 * np.exp(np.cumsum(rng.normal(0, .01, 180)))
        prices = pd.DataFrame({'open': close * .998, 'close': close,
                               'high': close * 1.01, 'low': close * .99,
                               'volume': rng.uniform(1e6, 2e6, 180)},
                              index=pd.bdate_range('2020-01-01', periods=180))
        prices.index.name = 'date'
        full = _add_price_factors(prices.copy())
        prefix = _add_price_factors(prices.iloc[:120].copy())
        pd.testing.assert_frame_equal(full.loc[prefix.index, SHORT_HORIZON_FACTORS],
                                      prefix[SHORT_HORIZON_FACTORS])
        last = prefix.iloc[-1]
        self.assertAlmostEqual(last.momentum_5d, prices.close.iloc[119] / prices.close.iloc[114] - 1)
        self.assertAlmostEqual(last.overnight_gap, prices.open.iloc[119] / prices.close.iloc[118] - 1)
        self.assertTrue((prefix.illiquidity_20d.dropna() > 0).all())

    def test_new_feature_missingness_does_not_change_label_population(self):
        index = pd.bdate_range('2020-01-01', periods=30)
        data = pd.DataFrame({'a': 1., 'b': 2., 'close': 10., 'open': 10.,
                             'volume': 1., 'ret_5d_fwd': .01}, index=index)
        for factor in SHORT_HORIZON_FACTORS:
            data[factor] = np.nan
        old = _prepare_single(data, '000001', ['a', 'b'])
        new = _prepare_single(data, '000001', ['a', 'b'] + SHORT_HORIZON_FACTORS)
        pd.testing.assert_series_equal(old.date, new.date)
        pd.testing.assert_series_equal(old.ret_5d_fwd, new.ret_5d_fwd)

    def test_date_folds_purge_actual_maturity_and_rolling_caps_dates(self):
        dates = pd.bdate_range('2015-01-01', periods=400)
        data = pd.DataFrame({'date': np.repeat(dates, 4), 'stock_code': list('abcd') * 400})
        data['label_end_date'] = data.date + pd.offsets.BDay(12)
        for train, validation in temporal_folds(data, val_days=60):
            self.assertLess(train.label_end_date.max(), validation.date.min())
            self.assertFalse(set(train.date) & set(validation.date))
            self.assertTrue((validation.groupby('date').size() == 4).all())
            rolling = fit_frame(train, dict(window=126))
            self.assertEqual(rolling.date.nunique(), min(126, train.date.nunique()))

    def test_diagnosis_uses_actual_model_inputs(self):
        rng = np.random.default_rng(9)
        frame = pd.DataFrame({'date': np.repeat(pd.bdate_range('2020-01-01', periods=35), 30),
                              'stock_code': list(range(30)) * 35})
        frame['ret_5d_fwd'] = np.tile(np.arange(30), 35)
        frame['factor'] = frame.ret_5d_fwd
        frame['factor_neu'] = rng.normal(size=len(frame))
        neutral = diagnose_all(frame, ['factor'])
        raw = diagnose_all(frame, ['factor'], representation='raw')
        self.assertEqual(neutral['results'][0]['input_column'], 'factor_neu')
        self.assertAlmostEqual(raw['results'][0]['ic_mean'], 1.)
        self.assertLess(abs(neutral['results'][0]['ic_mean']), .1)

    def test_quality_and_date_weighting_handle_unbalanced_panels(self):
        frame = pd.DataFrame({'date': pd.to_datetime(['2020-01-01'] * 12 + ['2020-04-01'] * 24),
                              'valid_neu': np.arange(36, dtype=float),
                              'constant_neu': 1., 'missing_neu': np.nan})
        weights = pd.Series(date_weights(frame))
        self.assertAlmostEqual(weights.groupby(frame.date).sum().iloc[0],
                               weights.groupby(frame.date).sum().iloc[1])
        self.assertEqual(quality_features(frame, ['valid', 'constant', 'missing']), ['valid_neu'])

    def test_block_interval_reports_uncertainty_and_is_reproducible(self):
        values = np.tile([-.03, .01, .02, -.01, .04], 30)
        first = paired_block_interval(values, repetitions=100)
        self.assertEqual(first, paired_block_interval(values, repetitions=100))
        self.assertLessEqual(first['ci95'][0], first['mean'])
        self.assertGreaterEqual(first['ci95'][1], first['mean'])

    def test_outer_walk_forward_starts_after_profile_selection(self):
        from ml_pipeline.walk_forward import run_walk_forward
        rng = np.random.default_rng(50)
        dates = pd.bdate_range('2019-01-01', periods=460)
        frame = pd.DataFrame({'date': np.repeat(dates, 24),
                              'stock_code': list(range(24)) * len(dates)})
        frame['signal_neu'] = rng.normal(size=len(frame))
        frame['ret_5d_fwd'] = frame.signal_neu * .01 + rng.normal(0, .02, len(frame))
        frame['target_up'] = (frame.ret_5d_fwd > 0).astype(int)
        frame['label_end_date'] = frame.date + pd.offsets.BDay(8)
        plan = dict(protocol={'development_end': str(dates[300])},
                    params=dict(n_estimators=2, max_depth=1, num_leaves=2, n_jobs=1, verbose=-1),
                    selected_profile=dict(name='test', window=126))
        with patch('ml_pipeline.model_selection.features_for_profile', return_value=['signal_neu']):
            result = run_walk_forward(frame, step_days=60, val_days=60,
                                      backtest_k=0, verbose=False, training_plan=plan)
        self.assertTrue(result.get('windows'))
        for window in result['windows']:
            self.assertGreater(pd.Timestamp(window['val_start']), dates[300])
            self.assertLess(pd.Timestamp(window['train_label_end']), pd.Timestamp(window['val_start']))
            self.assertLessEqual(window['n_train'], 126 * 24)

    def test_training_api_defaults_to_bounded_protocol_and_keeps_legacy_explicit(self):
        from pydantic import ValidationError
        from backend.app.api.data_engineering import ModelTrainRequest, trigger_model_train
        self.assertEqual(ModelTrainRequest().scheme, 'robust')
        with self.assertRaises(ValidationError):
            ModelTrainRequest(scheme='unknown')
        with patch('backend.app.api.data_engineering.engineering_service_instance.start_model_train_task') as start:
            start.return_value = {'status': 'started'}
            trigger_model_train(ModelTrainRequest(scheme='legacy', use_optuna=False, n_trials=1))
            self.assertEqual(start.call_args.kwargs['scheme'], 'legacy')
            self.assertFalse(start.call_args.kwargs['use_optuna'])

    def test_changed_labels_are_not_reported_as_a_paired_improvement(self):
        from ml_pipeline.model_selection import compare_reference
        old = pd.DataFrame({'date': pd.to_datetime(['2020-01-01', '2020-01-01']),
                             'stock_code': ['a', 'b'], 'target_up': [0, 1]})
        new = old.copy()
        new['target_up'] = [1, 0]
        # Deliberately no models: a mismatched task must not be scored at all.
        with tempfile.TemporaryDirectory() as destination:
            report = compare_reference({'test': new, 'model_selection': {'protocol_sha256': 'frozen'}},
                                       {'test': old}, 'previous', destination)
        self.assertEqual(report['status'], 'not_comparable_changed_population_or_labels')
        self.assertEqual(report['splits'], {})

    def test_low_psi_never_claims_predictive_effectiveness(self):
        from ml_pipeline.drift_monitor import interpret_drift_report
        old = dict(overall_status='HEALTHY', max_feature_psi=.01,
                   summary_desc='当前规律保持有效', features=[dict(status='STABLE', psi=.01, action='正常生产运行')])
        result = interpret_drift_report(old)
        self.assertEqual(result['max_feature_psi'], old['max_feature_psi'])
        self.assertIn('不能证明预测有效', result['summary_desc'])
        self.assertNotIn('正常生产运行', result['features'][0]['action'])
        self.assertEqual(old['summary_desc'], '当前规律保持有效')


if __name__ == '__main__':
    unittest.main()
