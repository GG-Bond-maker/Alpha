# -*- coding: utf-8 -*-
"""评测与回测 API 路由"""

from typing import Any, Dict

from fastapi import APIRouter

from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/evaluation", tags=["评测与回测"])


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
