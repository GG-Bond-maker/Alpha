# -*- coding: utf-8 -*-
"""推荐 API 路由"""

import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/recommend", tags=["Top-K 选股推荐"])


class ResetRiskRequest(BaseModel):
    auth_token: str


class TriggerRiskRequest(BaseModel):
    reason: Optional[str] = "管理员手动触发紧急避险熔断"


@router.get("/dates", summary="获取可选截面日期列表")
def list_available_dates() -> List[str]:
    return service_instance.get_available_dates()


@router.get("/topk", summary="获取指定截面的 Top-K 推荐列表")
def get_topk(
    date: Optional[str] = Query(None, description="截面日期 YYYY-MM-DD，缺省为最新"),
    k: int = Query(10, ge=1, le=50, description="推荐数量"),
    industry: Optional[str] = Query(None, description="行业筛选"),
    board: Optional[str] = Query(None, description="板块筛选"),
):
    return service_instance.get_topk(date=date, k=k, industry=industry, board=board)


@router.get("/risk_status", summary="获取风控熔断器状态 (ML4T Risk Guard)")
def get_risk_status():
    return service_instance.get_risk_status()


@router.post("/risk_trigger", summary="手动触发风控熔断 (ML4T Kill Switch)")
def trigger_risk(req: Optional[TriggerRiskRequest] = None):
    reason = req.reason if req and req.reason else "管理员手动触发紧急避险熔断"
    from ml_pipeline.risk_guard import risk_guard_instance
    return risk_guard_instance.manual_trigger(reason)


@router.post("/risk_reset", summary="重置解除风控熔断 (ML4T Kill Switch)")
def reset_risk(req: ResetRiskRequest):
    from ml_pipeline.risk_guard import risk_guard_instance
    success = risk_guard_instance.reset(req.auth_token)
    if not success:
        raise HTTPException(status_code=403, detail="口令鉴权失败，无法解除风控熔断（默认口令: ALPHA_SAFE_RESET_2026）")
    return risk_guard_instance.status_report


@router.get("/export_excel", summary="导出推荐结果为 Excel")
def export_excel():
    path = service_instance.export_excel()
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="暂无可导出的推荐数据")
    return FileResponse(
        path=path,
        filename=os.path.basename(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
