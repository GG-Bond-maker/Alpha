# -*- coding: utf-8 -*-
"""推荐 API 路由模块
提供 Top-K 推荐查询、日期列表及 Excel 报表导出下载
"""

import os
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from typing import Optional, List
from backend.app.schemas.recommend import RecommendTopKResponse
from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/recommend", tags=["Top-K 智能选股推荐"])


@router.get("/dates", summary="获取所有可推荐的交易截面日期")
def list_available_dates() -> List[str]:
    return service_instance.get_available_dates()


@router.get("/topk", response_model=RecommendTopKResponse, summary="获取指定日期的 Top-K 推荐股票列表")
def get_topk_recommendations(
    date: Optional[str] = Query(None, description="截面日期 (格式: YYYY-MM-DD)，缺省为最新"),
    k: int = Query(10, ge=1, le=50, description="推荐数量 K (默认 10)"),
    industry: Optional[str] = Query(None, description="按申万行业筛选，默认全部"),
    board: Optional[str] = Query(None, description="按板块筛选 (主板/创业板/科创板/北交所/全部)")
):
    result = service_instance.get_topk_recommendations(date=date, k=k, industry=industry, board=board)
    return result


@router.get("/export_excel", summary="导出并下载当前选股推荐结果为 Excel 文件")
def export_recommendations_excel():
    excel_path = service_instance.export_excel()
    if not os.path.exists(excel_path):
        raise HTTPException(status_code=500, detail="生成 Excel 报表失败")
    
    filename = os.path.basename(excel_path)
    return FileResponse(
        path=excel_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
