# -*- coding: utf-8 -*-
"""特征归因 API 路由"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/explain", tags=["特征归因"])


@router.get("/local/{stock_code}", summary="个股 SHAP 局部归因与诊断理由")
def explain_single_stock(
    stock_code: str,
    date: Optional[str] = Query(None, description="截面日期，缺省为最新"),
) -> Dict[str, Any]:
    result = service_instance.explain_stock(stock_code=stock_code, date=date)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"股票 {stock_code} 暂无归因数据（模型或解释器未就绪，请先运行训练脚本）",
        )
    return result


@router.get("/global", summary="全局特征重要性排序 (Mean |SHAP|)")
def get_global_importance() -> List[Dict[str, Any]]:
    return service_instance.get_global_importance()


@router.get("/global-summary", summary="全局 SHAP summary beeswarm 样本")
def get_global_shap_summary() -> Dict[str, Any]:
    return service_instance.get_shap_summary()
