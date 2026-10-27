import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from ml_pipeline.backtest import BUY_COST, SELL_COST, max_drawdown_duration, run_backtest
from ml_pipeline.dataset import align_forward_returns, time_split, neutralize_and_standardize
from ml_pipeline.factor_diagnosis import compute_ic_series, layered_returns
from ml_pipeline.risk_guard import RiskKillSwitch


def frame(returns):
    return pd.DataFrame({'date': pd.bdate_range('2020-01-01', periods=len(returns)),
                         'stock_code': '000001', 'ret_5d_fwd': returns,
                         'score_lgb': 1.0, 'pct_chg': 0.0})


class BacktestTests(unittest.TestCase):
    def test_initial_capital_is_included_in_drawdown(self):
        result = run_backtest(frame([-0.5] * 5 + [0.0] * 5), k=1)
        expected = 0.5 * (1 - SELL_COST) / (1 + BUY_COST) - 1
        self.assertAlmostEqual(result['strategy']['drawdown'][0], expected, places=6)
        self.assertLessEqual(result['strategy']['max_drawdown'], round(expected, 4))
        self.assertEqual(max_drawdown_duration(np.array([0.5])), 1)

    def test_repeated_selection_is_closed_and_reopened_with_both_costs(self):
        result = run_backtest(frame([0.0] * 10), k=1)
        period = (1 - SELL_COST) / (1 + BUY_COST) - 1
        self.assertAlmostEqual(result['strategy']['total_return'], round((1 + period) ** 2 - 1, 4))
        self.assertEqual([r['holdings'][0]['action'] for r in result['rebalance_ledger']], ['BUY', 'BUY'])
        self.assertTrue(all(r['cost'] > 0 for r in result['rebalance_ledger']))
        self.assertEqual(result['final_holdings'], [])
        self.assertIsNone(result['strategy']['dsr'])
        self.assertEqual(result['strategy']['nav'], result['benchmark']['nav'])

    def test_labels_use_market_calendar_across_missing_stock_sessions(self):
        dates = pd.bdate_range('2020-01-01', periods=10)
        normal = pd.DataFrame({'date': dates, 'stock_code': 'normal', 'open': 100.0, 'close': np.arange(100., 110.)})
        suspended = normal.copy()
        suspended['stock_code'] = 'suspended'
        suspended = suspended.drop(index=[3, 4])
        result = align_forward_returns(pd.concat([normal, suspended], ignore_index=True))
        first = result[(result.stock_code == 'suspended') & (result.date == dates[0])].iloc[0]
        self.assertEqual(first.label_end_date, dates[5])
        self.assertAlmostEqual(first.ret_5d_fwd, 0.05)
        before_gap = result[(result.stock_code == 'suspended') & (result.date == dates[2])].iloc[0]
        self.assertTrue(pd.isna(before_gap.ret_5d_fwd))


class PipelineTests(unittest.TestCase):
    def test_neutralization_matches_per_date_reference_with_missing_values(self):
        rng = np.random.default_rng(31)
        panel = pd.DataFrame({'date': np.repeat(pd.date_range('2020-01-01', periods=3), 30),
                              'industry': np.tile(['a'] * 14 + ['b'] * 14 + ['未分类'] * 2, 3),
                              'factor': rng.normal(size=90)})
        panel.loc[[2, 8, 21, 40], 'factor'] = np.nan
        expected = pd.Series(index=panel.index, dtype=float)
        for _, g in panel.groupby('date'):
            values = g.factor.clip(g.factor.quantile(0.01), g.factor.quantile(0.99))
            centered = values - values.mean()
            counts = g.industry.value_counts()
            rich = (g.industry.map(counts) >= 3) & (g.industry != '未分类')
            mean = values.groupby(g.industry).transform('mean')
            centered = centered.where(~rich, values - mean)
            expected.loc[g.index] = centered / centered.std()
        actual = neutralize_and_standardize(panel, ['factor']).factor_neu
        np.testing.assert_allclose(actual, expected, equal_nan=True, atol=1e-12)

    def test_split_purges_actual_label_end_dates(self):
        panel = frame([0.0] * 100)
        panel['label_end_date'] = panel['date'] + pd.offsets.BDay(5)
        panel.loc[20, 'label_end_date'] = panel.loc[75, 'date']
        train, val, test = time_split(panel)
        self.assertTrue((train.label_end_date < val.date.min()).all())
        self.assertTrue((val.label_end_date < test.date.min()).all())
        self.assertNotIn(20, train.index)

    def test_vectorized_ic_and_quantile_returns_match_reference(self):
        rng = np.random.default_rng(17)
        panel = pd.DataFrame({'date': np.repeat(pd.date_range('2020-01-01', periods=5), 31),
                              'factor': rng.normal(size=155), 'ret_5d_fwd': rng.normal(size=155)})
        expected = panel.groupby('date').apply(lambda g: g.factor.corr(g.ret_5d_fwd, method='spearman'))
        np.testing.assert_allclose(compute_ic_series(panel, 'factor'), expected)
        reference = []
        for _, group in panel.groupby('date'):
            group = group.copy()
            group['layer'] = pd.qcut(group.factor.rank(method='first'), 5, labels=False)
            reference.append(group.groupby('layer').ret_5d_fwd.mean())
        np.testing.assert_allclose(layered_returns(panel, 'factor'), pd.concat(reference, axis=1).mean(axis=1), atol=1e-6)

    def test_training_accepts_missing_candidate_argument(self):
        import models.model_trainer as trainer
        from config.config import get_model_features
        columns = get_model_features()
        rng = np.random.default_rng(11)
        panel = pd.DataFrame(rng.normal(size=(600, len(columns))), columns=columns)
        panel['date'] = np.repeat(pd.bdate_range('2020-01-01', periods=60), 10)
        panel['target_up'] = np.tile([0, 1], 300)
        with tempfile.TemporaryDirectory() as temp:
            params = {**trainer.DEFAULT_PARAMS, 'n_estimators': 3, 'n_jobs': 2}
            with patch.object(trainer, 'SAVED_MODELS_DIR', temp), patch.object(trainer, 'DEFAULT_PARAMS', params), contextlib.redirect_stdout(io.StringIO()):
                result = trainer.train_market_model(panel=panel, n_trials=1, force_retrain=True)
            self.assertTrue(Path(temp, 'lgbm_market_classifier.pkl').exists())
            self.assertTrue(result['loss_history']['iterations'])
            import joblib
            saved = joblib.load(Path(temp) / 'lgbm_market_classifier.pkl')
            np.testing.assert_array_equal(saved['train'][columns].to_numpy(), result['train'][columns].to_numpy())


class ServiceTests(unittest.TestCase):
    def test_scheduler_runs_once_and_fails_closed_without_calendar(self):
        from datetime import datetime
        from backend.app.services.scheduler import DailyScheduler
        from unittest.mock import Mock
        service = Mock()
        service.schedule_config = {'enabled': True, 'cron_time': '15:35', 'trading_days_only': True}
        service.task_state = {'status': 'idle'}
        scheduler = DailyScheduler(service, calendar_check=lambda day: True)
        self.assertFalse(scheduler.tick(datetime(2026, 10, 27, 15, 34)))
        self.assertTrue(scheduler.tick(datetime(2026, 10, 27, 15, 35)))
        self.assertFalse(scheduler.tick(datetime(2026, 10, 27, 15, 36)))
        service.start_data_update_task.assert_called_once()
        service.start_data_update_task.reset_mock()
        def unavailable(day):
            raise RuntimeError('offline')
        scheduler = DailyScheduler(service, calendar_check=unavailable)
        self.assertFalse(scheduler.tick(datetime(2026, 10, 27, 15, 35)))
        service.start_data_update_task.assert_not_called()

    def test_schedule_and_logging_remain_available_after_mutation(self):
        from backend.app.services.data_engineering_service import DataEngineeringService
        service = DataEngineeringService()
        with tempfile.TemporaryDirectory() as temp:
            service.schedule_config_file = str(Path(temp) / 'schedule.json')
            worker = threading.Thread(target=lambda: (service.save_schedule_config({'enabled': False}), service.clear_logs()), daemon=True)
            worker.start()
            worker.join(3)
            self.assertFalse(worker.is_alive(), 'mutations must not deadlock')
            service.add_log('INFO', 'still works')
            self.assertEqual(service.get_logs()[-1]['message'], 'still works')

    def test_recommendation_dates_never_fall_back_or_mix(self):
        from backend.app.services.recommend_service import RecommendationService
        service = RecommendationService.__new__(RecommendationService)
        service.data_df = pd.DataFrame({'代码': ['000001', '600519'], '更新日期': ['2020-01-01', '2020-01-02'],
                                        '跑赢候选池均值概率': [0.9, 0.1]})
        service.reload = lambda: None
        service._get_market_indicator_cache = lambda: {}
        latest = service.get_topk()
        self.assertEqual([r['stock_code'] for r in latest['recommendations']], ['600519'])
        self.assertEqual(service.get_topk('1900-01-01')['recommendations'], [])
        with self.assertRaises(ValueError):
            service.get_topk('wrong-date')

    def test_unobserved_risks_are_unknown_and_concentration_is_screened(self):
        guard = RiskKillSwitch('test-token')
        self.assertIsNone(guard.status_report['gauges']['daily_loss'])
        rows = guard.filter_recommendations([{'industry': 'same'}, {'industry': 'same'}])
        self.assertEqual([r['risk_status'] for r in rows], ['WARNING', 'WARNING'])
        self.assertIsNone(guard.status_report['gauges']['drawdown'])
        self.assertFalse(guard.check_portfolio_risk(daily_loss=-0.10))
        self.assertFalse(guard.reset('wrong'))
        self.assertTrue(guard.reset('test-token'))

    def test_engineering_metrics_come_from_saved_results(self):
        from backend.app.services.data_engineering_service import DataEngineeringService
        from backend.app.services.recommend_service import service_instance
        info = DataEngineeringService().get_system_status()['model_lifecycle']['market_model']
        report = service_instance.get_training_report()
        self.assertEqual(info['metrics']['auc'], report['model_metrics']['test']['auc'])
        self.assertEqual(info['best_params'], report['best_params'])


class SelectionLayerTests(unittest.TestCase):
    def test_signal_limit_indicator_uses_board_specific_threshold(self):
        from ml_pipeline.backtest import is_limit_up
        self.assertTrue(is_limit_up('000001', 10.0))
        self.assertFalse(is_limit_up('300502', 10.0))
        self.assertTrue(is_limit_up('688981', 20.0))

    def test_inverted_validation_signal_never_reverses_model_ordering(self):
        from ml_pipeline.calibration import fit_calibrator, calibrate_margin
        class Model:
            def predict(self, x, raw_score=False):
                return x['margin'].to_numpy()
        val = pd.DataFrame({'margin': np.tile(np.linspace(-2, 2, 30), 4),
                            'target_up': np.tile([1] * 15 + [0] * 15, 4),
                            'date': np.repeat(pd.date_range('2020-01-01', periods=4), 30)})
        spec = fit_calibrator(Model(), val, ['margin'])
        self.assertTrue(spec['weak_validation_signal'])
        np.testing.assert_allclose(calibrate_margin([-5, 0, 5], spec), 0.5, atol=1e-5)

    def test_calibration_is_monotone_and_validation_only(self):
        from ml_pipeline.calibration import fit_calibrator, calibrate_margin
        class Model:
            def predict(self, features, raw_score=False):
                return features['margin'].to_numpy()
        validation = pd.DataFrame({'margin': np.tile(np.linspace(-3, 3, 40), 3),
                                   'target_up': np.tile(([0] * 15 + [1] * 25), 3),
                                   'date': np.repeat(pd.date_range('2020-01-01', periods=3), 40)})
        spec = fit_calibrator(Model(), validation, ['margin'])
        prediction = calibrate_margin(np.linspace(-10, 10, 100), spec)
        self.assertTrue((np.diff(prediction) >= 0).all())
        self.assertTrue(((prediction >= 0) & (prediction <= 1)).all())
        self.assertEqual(spec['fit_source'], 'validation_only')
        self.assertEqual(spec['fit_period'], ['2020-01-01', '2020-01-03'])

    def test_rules_explain_rejections_without_future_inputs(self):
        from ml_pipeline.selection import screen_candidates
        candidates = pd.DataFrame({'更新日期': ['2020-01-01'] * 4, '最新收盘价': [10] * 4,
                                    'volume': [100, 0, 100, 100], 'history_days': [200, 200, 10, 200],
                                    '名称': ['正常', '停牌', '新股', 'ST公司'], '是否涨停': ['否'] * 4})
        result, audit = screen_candidates(candidates, '2020-01-01')
        self.assertEqual(result.rule_eligible.tolist(), [True, False, False, False])
        self.assertEqual(audit['eligible_count'], 1)
        self.assertEqual(audit['excluded_count'], 3)

    def test_factor_comparator_directions_weights_and_missing_values(self):
        from ml_pipeline.selection import enrich_recommendations
        panel = pd.DataFrame({'stock_code': ['000001', '000002', '000003'],
                              'date': pd.to_datetime(['2020-01-01'] * 3),
                              'volume': [100] * 3, 'history_days': [200] * 3})
        rows = pd.DataFrame({'代码': panel.stock_code, '更新日期': ['2020-01-01'] * 3,
                             '最新收盘价': [10] * 3, '名称': ['a', 'b', 'c'],
                             'value_neu': [1.0, 2.0, np.nan]})
        bundle = {'factor_ranker': {'factors': [{'feature': 'value_neu', 'direction': -1, 'weight': 1}]}}
        result = enrich_recommendations(rows, panel, bundle)
        self.assertGreater(result.factor_score[0], result.factor_score[1])
        self.assertTrue(pd.isna(result.factor_score[2]))
        self.assertTrue(result.calibrated_probability.isna().all())


if __name__ == '__main__':
    unittest.main()
