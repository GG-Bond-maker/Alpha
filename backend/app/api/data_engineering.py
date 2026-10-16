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

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.app.services.data_engineering_service import engineering_service_instance

router = APIRouter(prefix="/engineering", tags=["数据工程与模型生命周期管理"])


class DataUpdateRequest(BaseModel):
    force_refresh: bool = Field(False, description="是否强制跳过本地缓存，重新从网络拉取全量行情")
    sync_recommendations: bool = Field(True, description="更新数据后是否同步调用 LightGBM 生成最新推荐")


class ModelTrainRequest(BaseModel):
    force_retrain: bool = Field(True, description="是否强制重新训练模型 (忽略本地已有权重缓存)")
    use_optuna: bool = Field(True, description="是否启用 Optuna 贝叶斯超参数寻优")
    n_trials: int = Field(15, ge=1, le=50, description="Optuna 试验轮数")
    retrain_single_models: bool = Field(False, description="是否同步微调核心主板个股专属模型")


class ScheduleConfigRequest(BaseModel):
    enabled: bool = Field(True, description="是否启用自动定时更新任务")
    cron_time: str = Field("15:35", description="每日执行时间 (HH:MM)")
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
            retrain_single_models=req.retrain_single_models
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
