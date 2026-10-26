# -*- coding: utf-8 -*-
"""评测与回测 API 路由"""

from typing import Any, Dict

from fastapi import APIRouter

from backend.app.services.recommend_service import service_instance
from ml_pipeline.artifacts import artifact_dir, experiment_status
import json
import os

router = APIRouter(prefix="/evaluation", tags=["评测与回测"])


@router.get('/experiment', summary='当前实验批次及数据口径')
def get_experiment():
    return experiment_status()


@router.get('/diagnostics', summary='样本外校准、Rank IC 与平仓月收益')
def get_diagnostics():
    path = os.path.join(artifact_dir(), 'diagnostics.json')
    if not os.path.exists(path):
        return {'error': '当前批次没有实验诊断，请完成一次训练'}
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


@router.get("/metrics", summary="获取各模型推荐评估指标对比表")
def get_evaluation_metrics() -> Dict[str, Any]:
    return service_instance.get_evaluation_metrics()


@router.get("/backtest", summary="获取 Top-K 组合回测结果")
def get_backtest() -> Dict[str, Any]:
    return service_instance.get_backtest()


@router.get("/report", summary="获取训练与实验汇总报告")
def get_report() -> Dict[str, Any]:
    return service_instance.get_training_report()


@router.get("/factors", summary="获取因子有效性诊断结果 (IC / ICIR / 分层收益)")
def get_factor_diagnosis() -> Dict[str, Any]:
    return service_instance.get_factor_diagnosis()


@router.get("/backtest/comparison", summary="沪深300池内排序与行业中性两种回测口径对比")
def get_backtest_comparison() -> Dict[str, Any]:
    return service_instance.get_backtest_comparison()


@router.get("/walk-forward", summary="滚动窗口验证结果（各窗口 AUC 与因子稳定性）")
def get_walk_forward() -> Dict[str, Any]:
    return service_instance.get_walk_forward()


@router.get("/attribution", summary="Alpha/Beta 业绩归因与显著性检验")
def get_attribution() -> Dict[str, Any]:
    return service_instance.get_attribution()


@router.get("/stress_test", summary="历史极端危机情景与假设压力测试 (ML4T Crisis Stress Testing)")
def get_stress_test() -> Dict[str, Any]:
    return service_instance.get_stress_test()


@router.get("/sensitivity", summary="策略多维参数敏感性与断崖检测 (ML4T Sensitivity Analysis)")
def get_sensitivity() -> Dict[str, Any]:
    return service_instance.get_sensitivity_analysis()

