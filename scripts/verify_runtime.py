"""Validate the active experiment and API using persisted, real artifacts."""
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
    probability = bundle['model'].predict_proba(recommendations[bundle['feature_cols']])[:, 1]
    difference = float(np.max(np.abs(probability - recommendations['跑赢候选池均值概率'])))
    assert difference <= 0.000051, difference
    report = json.loads((directory / 'training_report.json').read_text(encoding='utf-8'))
    backtest = json.loads((directory / 'backtest_result.json').read_text(encoding='utf-8'))
    assert report['backtest']['strategy']['periods'] == backtest['strategy']['periods']
    assert len(backtest['strategy']['nav']) == len(backtest['dates'])
    assert backtest['strategy']['dsr'] is None
    assert bundle['params']['subsample_freq'] == 1
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
            out[path] = status
        code = recommendations.iloc[0]['代码']
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
              'shap': check, 'recommendation_count': len(recommendations),
              'max_score_feature_error': difference, 'test_metrics': report['model_metrics']['test'],
              'calibration': bundle['calibration'], 'factor_ranker': bundle['factor_ranker'],
              'backtest_periods': backtest['strategy']['periods'], 'api': asyncio.run(smoke())}
    destination = ROOT / 'docs/review/2026-10-27/runtime-checks.json'
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
