"""Isolated experiment outputs and atomic activation of a complete run."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / 'saved_models'
POINTER = STORE / 'current.json'


def artifact_dir() -> str:
    override = os.environ.get('ALPHA_ARTIFACT_DIR')
    if override:
        return str(Path(override).resolve())
    if POINTER.exists():
        pointer = json.loads(POINTER.read_text(encoding='utf-8'))
        path = (STORE / 'runs' / pointer['run_id']).resolve()
        path.relative_to((STORE / 'runs').resolve())
        if not (path / 'manifest.json').is_file():
            raise RuntimeError('当前实验批次不完整，请重新训练或恢复 current.json')
        return str(path)
    return str(STORE)


def processed_dir() -> str:
    active = Path(artifact_dir())
    return str(active / 'processed') if active != STORE else str(ROOT / 'data' / 'processed')


def live_dir(active=None) -> str:
    active = Path(active or artifact_dir())
    path = ROOT / 'data' / 'processed' / 'live' / (active.name if active != STORE else 'legacy')
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def recommendation_path(active=None) -> str:
    active = Path(active or artifact_dir())
    candidate = Path(live_dir(str(active))) / 'realtime_recommendations.csv'
    fallback = active / 'processed' if active != STORE else ROOT / 'data' / 'processed'
    return str(candidate if candidate.exists() else fallback / candidate.name)


def experiment_status() -> dict:
    path = Path(artifact_dir()) / 'manifest.json'
    if not path.exists():
        return {'status': 'legacy', 'run_id': None,
                'message': '历史产物未验证为同一实验批次，请重新训练后再引用指标。'}
    return json.loads(path.read_text(encoding='utf-8'))


def launch_training(arguments: list[str]) -> int:
    run_id = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-') + uuid4().hex[:8]
    destination = STORE / 'runs' / run_id
    destination.mkdir(parents=True)
    env = {**os.environ, 'ALPHA_RUN_ID': run_id, 'ALPHA_ARTIFACT_DIR': str(destination),
           'ALPHA_TRAIN_WORKER': '1', 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1'}
    if any(arg == '--limit' or arg.startswith('--limit=') for arg in arguments):
        env['ALPHA_PREVIEW_RUN'] = '1'
    command = [sys.executable, '-m', 'ml_pipeline.run_training', *arguments]
    try:
        return subprocess.call(command, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 130


def finalize_run(report: dict) -> dict:
    """Publish only after every required artifact and consistency check passes."""
    directory = Path(artifact_dir())
    run_id = os.environ.get('ALPHA_RUN_ID')
    if not run_id:
        raise RuntimeError('训练必须通过隔离的实验批次入口执行')
    required = ['lgbm_market_classifier.pkl', 'shap_explainer.pkl', 'selected_factors.json',
                'evaluation_metrics.json', 'backtest_result.json', 'training_report.json',
                'shap_additivity.json', 'processed/realtime_recommendations.csv']
    for name in required:
        if not (directory / name).is_file():
            raise RuntimeError(f'实验批次缺少产物: {name}')
    if not report['shap_additivity']['passed']:
        raise RuntimeError('SHAP 加和校验失败，保留当前正式模型')
    import joblib
    import numpy as np
    import pandas as pd
    bundle = joblib.load(directory / 'lgbm_market_classifier.pkl')
    recommendations = pd.read_csv(directory / 'processed/realtime_recommendations.csv')
    probability = bundle['model'].predict_proba(recommendations[bundle['feature_cols']])[:, 1]
    if np.max(np.abs(probability - recommendations['跑赢候选池均值概率'])) > 0.000051:
        raise RuntimeError('推荐分数与保存特征不一致，不能发布本批次')
    backtest = json.loads((directory / 'backtest_result.json').read_text(encoding='utf-8'))
    if backtest['strategy']['periods'] != report['backtest']['strategy']['periods']:
        raise RuntimeError('汇总报告与回测周期数不一致')
    hashes = {}
    for file in sorted(directory.rglob('*')):
        if not file.is_file() or file.name == 'manifest.json':
            continue
        if file.suffix == '.json':
            value = json.loads(file.read_text(encoding='utf-8'))
            if isinstance(value, dict):
                value['run_id'] = run_id
                file.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        with file.open('rb') as handle:
            hashes[str(file.relative_to(directory)).replace('\\', '/')] = hashlib.file_digest(handle, 'sha256').hexdigest()
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        diff = subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT)
    except subprocess.CalledProcessError:
        commit, diff = None, b''
    import importlib.metadata as metadata
    manifest = {'status': 'complete', 'run_id': run_id,
                'completed_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                'git_commit': commit, 'source_diff_sha256': hashlib.sha256(diff).hexdigest(),
                'python': sys.version.split()[0],
                'versions': {p: metadata.version(p) for p in ['lightgbm', 'pandas', 'numpy', 'shap', 'scikit-learn', 'optuna']},
                'panel': report['panel'], 'files': hashes,
                'message': '同一实验批次；历史股票池和成交假设限制见数据说明。'}
    manifest['source_files'] = {
        str(file.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(file.read_bytes()).hexdigest()
        for folder in ['config', 'data', 'features', 'models', 'ml_pipeline', 'backend']
        for file in (ROOT / folder).rglob('*.py') if '__pycache__' not in file.parts
    }
    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if os.environ.get('ALPHA_PREVIEW_RUN') == '1':
        manifest['status'] = 'preview'
        (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[Experiment] 小样本预览已保存，保留原正式批次：{run_id}', flush=True)
        return manifest
    temporary = POINTER.with_suffix('.tmp')
    temporary.write_text(json.dumps({'run_id': run_id}), encoding='utf-8')
    os.replace(temporary, POINTER)
    print(f'[Experiment] 已激活完整实验批次 {run_id}', flush=True)
    return manifest
