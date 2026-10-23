# -*- coding: utf-8 -*-
"""推荐 API 路由"""

import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/recommend", tags=["Top-K 选股推荐"])


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
