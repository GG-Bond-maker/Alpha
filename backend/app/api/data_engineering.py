# -*- coding: utf-8 -*-
"""数据工程与模型管理 API 路由模块
提供：
1. GET /api/v1/engineering/status: 数据缓存与模型版本状态查看
2. POST /api/v1/engineering/data/update: 一键触发数据更新（实时变化获取与最新预测）
3. POST /api/v1/engineering/model/train: 一键触发模型重训（支持 force_retrain=True 与 Optuna）
4. GET /api/v1/engineering/logs: 实时工程执行控制台日志流
5. POST /api/v1/engineering/logs/clear: 清空控制台日志
6. GET /api/v1/engineering/schedule: 获取自动运行调度配置
7. POST /api/v1/engineering/schedule: 保存自动运行调度配置
8. POST /api/v1/engineering/cache/clear: 清理本地缓存
"""

import json
import os
from typing import Optional, Dict, Any, List, Literal

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

from config.config import SAVED_MODELS_DIR
from ml_pipeline.artifacts import artifact_dir, live_dir
from backend.app.services.data_engineering_service import engineering_service_instance

router = APIRouter(prefix="/engineering", tags=["数据工程与模型生命周期管理"])


class DataUpdateRequest(BaseModel):
    force_refresh: bool = Field(False, description="是否强制跳过本地缓存，重新从网络拉取全量行情")
    sync_recommendations: bool = Field(True, description="更新数据后是否同步调用 LightGBM 生成最新推荐")


class ModelTrainRequest(BaseModel):
    scheme: Literal['robust', 'legacy'] = Field('robust', description='默认固定候选时序比较；legacy 保留旧搜索')
    force_retrain: bool = Field(True, description="是否强制重新训练模型 (忽略本地已有权重缓存)")
    use_optuna: bool = Field(True, description="是否启用 Optuna 贝叶斯超参数寻优")
    n_trials: int = Field(15, ge=1, le=50, description="Optuna 试验轮数")
    retrain_single_models: bool = Field(False, description="是否同步微调核心主板个股专属模型")


class ScheduleConfigRequest(BaseModel):
    enabled: bool = Field(True, description="是否启用自动定时更新任务")
    cron_time: str = Field("15:35", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="每日执行时间 (HH:MM)，Asia/Shanghai")
    trading_days_only: bool = Field(True, description="是否仅在交易日执行")
    sync_prediction: bool = Field(True, description="是否在更新后自动运行选股打分")
    auto_retrain_model_weekly: bool = Field(False, description="每周是否自动重训模型")


class ClearCacheRequest(BaseModel):
    target: str = Field("data", description="清理目标: 'data'(历史行情数据) | 'models'(单股模型缓存) | 'all'")


@router.get("/status", summary="获取数据工程与模型生命周期全景状态")
def get_engineering_status():
    """
    返回当前行情数据缓存状态、最新交易日、主板股票池合规性、LightGBM 模型参数及后台任务进度
    """
    return engineering_service_instance.get_system_status()


@router.post("/data/update", summary="触发数据更新与最新预测")
def trigger_data_update(req: DataUpdateRequest = Body(...)):
    """
    股票数据实时变化，定期运行以拉取最新日K线数据、计算25维技术指标并刷新预测排行榜
    """
    try:
        res = engineering_service_instance.start_data_update_task(
            force_refresh=req.force_refresh,
            sync_recommendations=req.sync_recommendations
        )
        return {
            "status": "success",
            "message": "数据更新任务已在后台启动",
            "details": res
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/model/train", summary="触发 LightGBM 模型重新训练")
def trigger_model_train(req: ModelTrainRequest = Body(...)):
    """
    模型更新：如需强制重新训练模型，设置 force_retrain=True，支持 Optuna 贝叶斯超参数优化
    """
    try:
        res = engineering_service_instance.start_model_train_task(
            force_retrain=req.force_retrain,
            use_optuna=req.use_optuna,
            n_trials=req.n_trials,
            retrain_single_models=req.retrain_single_models,
            scheme=req.scheme,
        )
        return {
            "status": "success",
            "message": "LightGBM 模型重训任务已在后台启动",
            "details": res
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/logs", summary="获取实时工程执行控制台日志")
def get_engineering_logs(limit: int = 100):
    return {
        "status": "success",
        "logs": engineering_service_instance.get_logs(limit=limit)
    }


@router.post("/logs/clear", summary="清空工程控制台日志")
def clear_engineering_logs():
    engineering_service_instance.clear_logs()
    return {"status": "success", "message": "控制台日志已清空"}


@router.get("/schedule", summary="获取自动更新调度配置")
def get_schedule_config():
    return {
        "status": "success",
        "config": engineering_service_instance.schedule_config
    }


@router.post("/schedule", summary="更新自动更新调度配置")
def update_schedule_config(req: ScheduleConfigRequest = Body(...)):
    saved = engineering_service_instance.save_schedule_config(req.model_dump())
    return {
        "status": "success",
        "message": "调度配置已成功更新并持久化",
        "config": saved
    }


@router.post("/cache/clear", summary="清理本地历史行情或模型缓存")
def clear_cache(req: ClearCacheRequest = Body(...)):
    res = engineering_service_instance.clear_cache(target=req.target)
    return {
        "status": "success",
        "message": f"成功清理 {res['cleared_files_count']} 个缓存文件",
        "details": res
    }


@router.get("/drift_status", summary="获取特征分布与模型预测稳定性监控报告 (ML4T PSI Drift)")
def get_drift_status():
    """基于《Machine Learning for Algorithmic Trading》规范：
    监控核心特征、预测概率与目标收益在训练集与测试集间的群体稳定性指数 (PSI) 与双样本 KS 检验
    """
    report_path = os.path.join(live_dir(), "feature_drift_report.json")
    if not os.path.exists(report_path):
        report_path = os.path.join(artifact_dir(), "feature_drift_report.json")
    if not os.path.exists(report_path):
        from ml_pipeline.drift_monitor import generate_drift_report
        return generate_drift_report()
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            from ml_pipeline.drift_monitor import interpret_drift_report
            return interpret_drift_report(json.load(f))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取漂移监控报告失败: {e}")


@router.post("/drift/refresh", summary="重新执行特征与模型漂移检测")
def refresh_drift_status():
    """重新计算并刷新 PSI 漂移指标"""
    try:
        from ml_pipeline.drift_monitor import generate_drift_report
        res = generate_drift_report()
        return {"status": "success", "message": "特征与预测稳定性监控已刷新", "report": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刷新漂移报告失败: {e}")

