from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from backend.app.schemas.recommend import StockExplainResponse, GlobalFeatureImportance
from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/explain", tags=["特征归因与可解释性"])


@router.get("/local/{stock_code}", response_model=StockExplainResponse, summary="获取个股推荐理由与 SHAP 局部归因")
def explain_single_stock(
    stock_code: str,
    date: Optional[str] = Query(None, description="截面日期，缺省为最新")
):
    result = service_instance.explain_stock(stock_code=stock_code, date=date)
    if not result:
        raise HTTPException(status_code=404, detail=f"未找到股票代码 {stock_code} 在日期 {date} 的归因数据")
    return result


@router.get("/global", response_model=List[GlobalFeatureImportance], summary="获取全局特征重要性排序 (Mean |SHAP|)")
def get_global_importance():
    return service_instance.get_global_importance()
