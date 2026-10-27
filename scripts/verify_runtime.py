"""Validate the active experiment and API using persisted, real artifacts."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
from ml_pipeline.artifacts import artifact_dir, recommendation_path
from ml_pipeline.train_explainer import verify_additivity


async def request(app, path, query=''):
    messages = []
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        messages.append(message)
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'GET',
             'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'query_string': query.encode(),
             'root_path': '', 'headers': [], 'server': ('127.0.0.1', 8008), 'client': ('127.0.0.1', 1)}
    await asyncio.wait_for(app(scope, receive, send), timeout=30)
    status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
    body = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return status, json.loads(body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'docs/review/2026-10-27/runtime-checks.json')
    args = parser.parse_args()
    directory = Path(artifact_dir())
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    mismatches = []
    for name, expected in manifest['files'].items():
        with (directory / name).open('rb') as handle:
            actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        if actual != expected:
            mismatches.append(name)
    assert not mismatches, mismatches
    bundle = joblib.load(directory / 'lgbm_market_classifier.pkl')
    explainer = joblib.load(directory / 'shap_explainer.pkl')
    check = verify_additivity(bundle['model'], explainer, bundle['test'][bundle['feature_cols']].head(200))
    assert check['passed']
    recommendations = pd.read_csv(recommendation_path(), dtype={'代码': str})
    latest_date = str(recommendations['更新日期'].max())
    refresh_report_path = ROOT / 'docs' / 'review' / latest_date / 'price-refresh.json'
    if refresh_report_path.exists():
        refresh_report = json.loads(refresh_report_path.read_text(encoding='utf-8'))
        assert refresh_report['latest_trade_date'] == latest_date
        assert refresh_report['successful'] == 300 and not refresh_report['failures']
        assert refresh_report['on_latest'] >= 270
    probability = bundle['model'].predict_proba(recommendations[bundle['feature_cols']])[:, 1]
    difference = float(np.max(np.abs(probability - recommendations['跑赢候选池均值概率'])))
    assert difference <= 0.000051, difference
    report = json.loads((directory / 'training_report.json').read_text(encoding='utf-8'))
    market_dates = pd.to_datetime(pd.read_csv(ROOT / 'data/factors/price_000001.csv', usecols=['date'])['date'])
    assert latest_date == str(market_dates.iloc[-1].date())
    mature_signal_date = str(market_dates.iloc[-6].date())
    assert report['panel']['date_range'][-1][:10] <= mature_signal_date
    assert pd.to_datetime(bundle['test']['label_end_date']).max() <= pd.Timestamp(latest_date)
    backtest = json.loads((directory / 'backtest_result.json').read_text(encoding='utf-8'))
    assert report['backtest']['strategy']['periods'] == backtest['strategy']['periods']
    assert len(backtest['strategy']['nav']) == len(backtest['dates'])
    assert backtest['strategy']['dsr'] is None
    assert bundle['params']['subsample_freq'] == 1
    selection_checks = None
    if bundle.get('model_selection'):
        plan = bundle['model_selection']
        protocol = json.loads((directory / 'model_selection_protocol.json').read_text(encoding='utf-8'))
        protocol.pop('run_id', None)  # finalize_run stamps all JSON artifacts.
        encoded = json.dumps(protocol, ensure_ascii=False, sort_keys=True, indent=2).encode()
        assert hashlib.sha256(encoded).hexdigest() == plan['protocol_sha256']
        assert len(plan['candidates']) == protocol['trials_total'] == 7
        development_end = pd.Timestamp(plan['fit_end'] if plan.get('frozen_training')
                                       else protocol['development_end'])
        for candidate in plan['candidates']:
            for fold in candidate['folds']:
                assert pd.Timestamp(fold['label_end']) < pd.Timestamp(fold['validation_start'])
                assert pd.Timestamp(fold['validation_end']) <= development_end
        eligible = [c for c in plan['candidates'] if not c['profile'].get('legacy')
                    and not c['profile'].get('diagnostic_only')]
        assert max(eligible, key=lambda c: c['selection_score'])['profile'] == plan['selected_profile']
        assert bundle['feature_cols'] == plan['features']
        assert bundle['params'] == plan['params']
        if plan.get('frozen_training'):
            source = ROOT / 'saved_models' / 'runs' / plan['frozen_from_run']
            old = joblib.load(source / 'lgbm_market_classifier.pkl')
            assert old['feature_cols'] == bundle['feature_cols']
            assert old['params'] == bundle['params']
            assert pd.Timestamp(plan['training_label_end']) < pd.Timestamp(bundle['calibration']['fit_period'][0])
        assert pd.Timestamp(bundle['calibration']['fit_period'][0]) > development_end
        comparison_path = directory / 'reference_comparison.json'
        comparison = (json.loads(comparison_path.read_text(encoding='utf-8')) if comparison_path.exists()
                      else {'status': 'no_reference', 'splits': {}})
        comparable = comparison['status'] == 'retrospective_previously_observed_holdout'
        if comparable:
            assert comparison['splits']['test']['rows'] == len(bundle['test'])
        walk_forward = json.loads((directory / 'walk_forward.json').read_text(encoding='utf-8'))
        for window in walk_forward['windows']:
            assert pd.Timestamp(window['val_start']) > development_end
            assert pd.Timestamp(window['train_label_end']) < pd.Timestamp(window['val_start'])
        selection_checks = {'profile': plan['selected_profile']['name'], 'protocol_hash_valid': True,
                            'candidates': len(plan['candidates']), 'outer_windows': len(walk_forward['windows']),
                            'test_population_unchanged': comparable, 'reference_status': comparison['status'],
                            'comparison': comparison['splits']}
    from ml_pipeline.calibration import calibrate_margin
    calibrated = calibrate_margin(bundle['model'].predict(recommendations[bundle['feature_cols']], raw_score=True), bundle.get('calibration'))
    assert calibrated is not None
    np.testing.assert_allclose(calibrated, recommendations['calibrated_probability'], atol=1e-10)
    assert pd.Timestamp(bundle['calibration']['fit_period'][1]) < bundle['test']['date'].min()
    assert bundle['factor_ranker']['fit_source'] == 'training_only'
    assert sum(r['weight'] for r in bundle['factor_ranker']['factors']) > 0.99999
    from backend.app.main import app
    async def smoke():
        paths = ['/api/health', '/api/v1/recommend/topk', '/api/v1/recommend/dates',
                 '/api/v1/explain/global', '/api/v1/explain/global-summary',
                 '/api/v1/evaluation/metrics', '/api/v1/evaluation/backtest',
                 '/api/v1/evaluation/report', '/api/v1/evaluation/experiment',
                 '/api/v1/evaluation/diagnostics', '/api/v1/evaluation/walk-forward',
                 '/api/v1/evaluation/attribution', '/api/v1/evaluation/stress_test',
                 '/api/v1/engineering/status', '/api/v1/engineering/drift_status']
        out = {}
        for path in paths:
            status, body = await request(app, path)
            assert status == 200, (path, status)
            if path == '/api/v1/recommend/topk':
                assert body['date'] == latest_date
                assert body['recommendations']
                assert all(item['update_date'] == latest_date for item in body['recommendations'])
                for item in body['recommendations']:
                    row = recommendations.loc[recommendations['代码'] == item['stock_code']].iloc[0]
                    assert abs(item['close_price'] - float(row['最新收盘价'])) < 0.0001
                    assert abs(item['pct_chg'] - float(row['当日涨幅(%)'])) < 0.0001
            if path == '/api/v1/recommend/dates':
                assert body[-1] == latest_date
            if path.endswith('/drift_status') and body.get('overall_status') == 'HEALTHY':
                assert '不能证明预测有效' in body['summary_desc']
            out[path] = status
        status, diagnosis = await request(app, '/api/v1/evaluation/factors')
        assert status == 200
        assert {f + '_neu' for f in diagnosis['model_factors']} == set(bundle['feature_cols'])
        assert {r['factor'] + '_neu' for r in diagnosis['results'] if r['in_model']} == set(bundle['feature_cols'])
        out['factor_diagnosis_matches_model'] = status
        code = recommendations.iloc[0]['代码']
        status, kline = await request(app, '/api/v1/stock/kline/' + code, 'limit=30')
        assert status == 200 and not kline['is_synthetic']
        assert kline['dates'][-1].replace('/', '-') == latest_date
        out['latest_kline_matches_recommendation'] = status
        status, body = await request(app, '/api/v1/explain/local/' + code)
        assert status == 200
        assert abs(body['base_value'] + sum(r['shap_value'] for r in body['features']) - body['predicted_margin']) < 0.001
        out['local_explanation'] = status
        status, body = await request(app, '/api/v1/recommend/topk', 'date=invalid')
        assert status == 422
        out['invalid_date'] = status
        status, body = await request(app, '/api/v1/recommend/topk', 'rank_by=factor&k=10')
        assert status == 200 and len(body['recommendations']) == 10
        scores = [r['factor_score'] for r in body['recommendations']]
        assert scores == sorted(scores, reverse=True)
        out['factor_ranking'] = status
        status, body = await request(app, '/api/v1/recommend/topk', 'min_amount=1000000000000')
        assert status == 200 and not body['recommendations']
        assert body['screening']['excluded_count'] == body['screening']['input_count']
        out['empty_rule_screen'] = status
        status, body = await request(app, '/api/v1/recommend/topk', 'rank_by=invalid')
        assert status == 422
        out['invalid_rank_mode'] = status
        return out
    output = {'run_id': manifest['run_id'], 'hash_mismatches': mismatches,
              'latest_recommendation_date': latest_date,
              'latest_mature_signal_date': mature_signal_date,
              'shap': check, 'recommendation_count': len(recommendations),
              'max_score_feature_error': difference, 'test_metrics': report['model_metrics']['test'],
              'calibration': bundle['calibration'], 'factor_ranker': bundle['factor_ranker'],
              'backtest_periods': backtest['strategy']['periods'], 'api': asyncio.run(smoke())}
    output['model_selection_checks'] = selection_checks
    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
