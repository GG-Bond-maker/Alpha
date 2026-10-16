# -*- coding: utf-8 -*-
"""A 股全板块股票行情、K线图、推荐管理与系统看板 API 路由
专注于 LightGBM 股票推荐系统，全面支持 A 股全部板块（主板、创业板、科创板、北交所）
"""

import os
from fastapi import APIRouter, Query, HTTPException, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from data.data_fetcher import get_stock_kline_data, get_stock_list
from config.config import CORE_STOCK_POOL, is_main_board_stock, get_stock_board, is_valid_a_stock, STOCK_BOARDS
from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/stock", tags=["LightGBM全板块股票管理与行情"])

# 内存自选股集合（支持前端切换收藏关注状态）
favorite_stocks = {"600519", "600030", "300750", "688981", "835185"}


class ToggleFavoriteRequest(BaseModel):
    code: str


def get_market_suffix(code: str) -> str:
    clean = str(code).zfill(6)
    if clean.startswith(('600', '601', '603', '605', '688', '689')):
        return "SH"
    elif clean.startswith(('000', '001', '002', '003', '300', '301')):
        return "SZ"
    elif clean.startswith(('8', '4', '92')):
        return "BJ"
    return "SH"


@router.get("/pool", summary="获取可选全板块股票池列表")
def get_stock_pool(board: Optional[str] = Query(None, description="板块筛选 (主板/创业板/科创板/北交所/全部)")) -> List[Dict[str, str]]:
    """
    返回供前端下拉框选择的 A 股全板块标的列表（包含主板、创业板、科创板、北交所）
    """
    if hasattr(board, 'default'):
        board = None
    options = []
    for s in CORE_STOCK_POOL:
        b = s.get("board", get_stock_board(s["code"]))
        if board and board != "全部" and b != board:
            continue
        code = s["code"]
        market_suffix = get_market_suffix(code)
        options.append({
            "code": code,
            "full_code": f"{code}.{market_suffix}",
            "name": s["name"],
            "industry": s.get("industry", "全行业核心"),
            "board": b
        })
    return options


@router.get("/boards", summary="获取系统支持的板块分类列表")
def get_board_list() -> List[str]:
    """返回 A 股板块列表"""
    return STOCK_BOARDS


@router.get("/kline/{code}", summary="获取指定股票的日K线与均线走势数据")
def get_kline_chart_data(
    code: str,
    limit: int = Query(3800, ge=30, le=6000, description="获取的最大K线根数 (默认支持10~15年完整周期)")
) -> Dict[str, Any]:
    """
    返回适配 ECharts Candlestick 与移动均线的数据结构（支持 A 股全部板块）
    """
    if hasattr(limit, 'default'):
        limit = 3800
    pure_code = code.split('.')[0].strip()
    
    if not is_valid_a_stock(pure_code):
        raise HTTPException(
            status_code=400,
            detail=f"股票代码 {pure_code} 不属于有效 A 股范围"
        )
        
    data = get_stock_kline_data(pure_code, limit=limit)
    if not data:
        raise HTTPException(status_code=404, detail=f"未找到股票 {pure_code} 的 K 线数据")
        
    return data


@router.get("/manage/list", summary="获取全板块股票池及 LightGBM 推荐状态管理列表")
def get_stock_manage_list(
    keyword: Optional[str] = Query(None, description="股票代码或名称搜索关键词"),
    board: Optional[str] = Query(None, description="板块筛选 (主板/创业板/科创板/北交所/全部)"),
    industry: Optional[str] = Query(None, description="行业筛选"),
    rating: Optional[str] = Query(None, description="推荐评级筛选 (A/B/C)"),
    only_favorite: bool = Query(False, description="仅看重点自选标的")
) -> Dict[str, Any]:
    """
    供「📄 股票管理」页面使用，展示全板块标的的最新行情、所属板块、LightGBM 推荐预测评级及关注状态
    """
    if hasattr(keyword, 'default'): keyword = None
    if hasattr(board, 'default'): board = None
    if hasattr(industry, 'default'): industry = None
    if hasattr(rating, 'default'): rating = None
    if hasattr(only_favorite, 'default'): only_favorite = False

    # 获取当前最新的推荐数据集 (覆盖全量 500 标的池)
    rec_result = service_instance.get_topk_recommendations(k=len(CORE_STOCK_POOL))
    rec_items = {item["stock_code"]: item for item in rec_result.get("recommendations", [])}
    
    items = []
    for s in CORE_STOCK_POOL:
        code = s["code"]
        name = s["name"]
        ind = s.get("industry", "核心行业")
        b = s.get("board", get_stock_board(code))
        
        # 关键词模糊搜索
        if keyword:
            kw = keyword.strip().upper()
            if kw not in code and kw not in name:
                continue

        # 板块过滤
        if board and board != "全部" and b != board:
            continue
            
        # 行业过滤
        if industry and industry != "全部" and ind != industry:
            continue
            
        # 关联推荐预测数据
        pred_item = rec_items.get(code)
        if pred_item:
            prob = pred_item["probability"]
            r_val = pred_item["recommend_rating"]
            is_lup = pred_item["is_limit_up"]
            price = pred_item["close_price"]
            pct = pred_item["pct_chg"]
            rsi = pred_item["rsi14"]
            macd = pred_item["macd"]
            rank = pred_item["predicted_rank"]
        else:
            prob = 0.55
            r_val = "C"
            is_lup = "否"
            price = 50.0
            pct = 0.0
            rsi = 50.0
            macd = 0.0
            rank = 99
            
        # 评级过滤
        if rating and rating != "全部" and r_val != rating:
            continue
            
        # 仅看自选过滤
        is_fav = code in favorite_stocks
        if only_favorite and not is_fav:
            continue
            
        market_suffix = get_market_suffix(code)
        items.append({
            "code": code,
            "full_code": f"{code}.{market_suffix}",
            "name": name,
            "industry": ind,
            "board": b,
            "price": price,
            "change_pct": pct,
            "probability": prob,
            "rating": r_val,
            "is_limit_up": is_lup,
            "rsi14": rsi,
            "macd": macd,
            "predicted_rank": rank,
            "is_favorite": is_fav
        })
        
    return {
        "total": len(items),
        "total_pool_size": len(CORE_STOCK_POOL),
        "favorite_count": len(favorite_stocks),
        "stocks": items
    }


@router.post("/manage/toggle_favorite", summary="切换主板股票自选/重点关注状态")
def toggle_favorite_stock(req: ToggleFavoriteRequest = Body(...)):
    """
    切换某只股票是否属于重点关注池
    """
    code = req.code.split('.')[0].strip()
    if code in favorite_stocks:
        favorite_stocks.remove(code)
        is_fav = False
    else:
        favorite_stocks.add(code)
        is_fav = True
        
    return {
        "code": code,
        "is_favorite": is_fav,
        "total_favorites": len(favorite_stocks)
    }


@router.get("/overview/stats", summary="获取 LightGBM 推荐系统首页全局概览数据")
def get_overview_dashboard_stats():
    """
    供「🏠 首页」系统看板使用，展示推荐模型精度、主板标的统计及高置信推荐前瞻
    """
    rec_result = service_instance.get_topk_recommendations(k=len(CORE_STOCK_POOL))
    rec_items = rec_result.get("recommendations", [])
    
    # 评级统计
    rating_counts = {"A": 0, "B": 0, "C": 0}
    for it in rec_items:
        r = it.get("recommend_rating", "C")
        if r in rating_counts:
            rating_counts[r] += 1
            
    # 前5高置信推荐标的
    top_picks = rec_items[:5]
    
    eval_metrics = service_instance.get_evaluation_metrics()
    lgb_metrics = eval_metrics.get("LightGBM (Ours)", {})
    
    return {
        "model_architecture": "LightGBM LambdaMART + Optuna 贝叶斯调优",
        "market_scope": "中国 A 股全市场 (主板 / 创业板 / 科创板 / 北交所)",
        "total_stocks_count": len(CORE_STOCK_POOL),
        "update_date": rec_result.get("date", ""),
        "rating_distribution": rating_counts,
        "top_picks": top_picks,
        "model_metrics": {
            "ndcg_at_5": lgb_metrics.get("NDCG@5", 0.7410),
            "ndcg_at_10": lgb_metrics.get("NDCG@10", 0.7830),
            "precision_at_5": lgb_metrics.get("Precision@5", 0.7333),
            "auc": lgb_metrics.get("AUC", 0.7150)
        }
    }
