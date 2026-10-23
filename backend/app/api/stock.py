# -*- coding: utf-8 -*-
"""股票行情与股票池管理 API 路由"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from config.config import STOCK_BOARDS, get_pool, get_stock_board, is_valid_a_stock
from data.data_fetcher import get_stock_kline_data
from backend.app.services.recommend_service import service_instance

router = APIRouter(prefix="/stock", tags=["股票行情与股票池"])

# 内存自选集合（进程级，重启后重置）
favorite_stocks = {"600519", "600030", "300750", "688981"}


class ToggleFavoriteRequest(BaseModel):
    code: str


def _market_suffix(code: str) -> str:
    clean = str(code).zfill(6)
    if clean.startswith(("600", "601", "603", "605", "688", "689")):
        return "SH"
    if clean.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZ"
    return "BJ"


@router.get("/boards", summary="板块分类列表")
def get_boards() -> List[str]:
    return STOCK_BOARDS


@router.get("/pool", summary="可选股票池列表")
def get_pool_list(
    board: Optional[str] = Query(None, description="板块筛选"),
) -> List[Dict[str, str]]:
    items = []
    for s in get_pool():
        b = s.get("board", get_stock_board(s["code"]))
        if board and board != "全部" and b != board:
            continue
        code = s["code"]
        items.append({
            "code": code,
            "full_code": f"{code}.{_market_suffix(code)}",
            "name": s["name"],
            "industry": s.get("industry", "未分类"),
            "board": b,
        })
    return items


@router.get("/kline/{code}", summary="日 K 线与均线数据")
def get_kline(
    code: str,
    limit: int = Query(800, ge=30, le=6000, description="最大 K 线根数"),
) -> Dict[str, Any]:
    pure = code.split(".")[0].strip()
    if not is_valid_a_stock(pure):
        raise HTTPException(status_code=400, detail=f"{pure} 不是有效的 A 股代码")

    data = get_stock_kline_data(pure, limit=limit)
    if not data:
        raise HTTPException(status_code=404, detail=f"未找到 {pure} 的 K 线数据")
    return data


@router.get("/manage/list", summary="股票池与推荐状态管理列表")
def get_manage_list(
    keyword: Optional[str] = Query(None, description="代码或名称搜索"),
    board: Optional[str] = Query(None, description="板块筛选"),
    industry: Optional[str] = Query(None, description="行业筛选"),
    rating: Optional[str] = Query(None, description="评级筛选 A/B/C"),
    only_favorite: bool = Query(False, description="仅看自选"),
) -> Dict[str, Any]:
    # 取全量推荐作为关联数据；未匹配到的标的不编造概率，字段留空
    rec = service_instance.get_topk(k=len(get_pool()))
    rec_map = {item["stock_code"]: item for item in rec.get("recommendations", [])}

    items = []
    for s in get_pool():
        code = s["code"]
        name = s["name"]
        ind = s.get("industry", "未分类")
        b = s.get("board", get_stock_board(code))

        if keyword:
            kw = keyword.strip().upper()
            if kw not in code and kw not in name.upper():
                continue
        if board and board != "全部" and b != board:
            continue
        if industry and industry != "全部" and ind != industry:
            continue

        pred = rec_map.get(code)
        prob = pred["probability"] if pred else None
        r_val = pred["recommend_rating"] if pred else None

        if rating and rating != "全部" and r_val != rating:
            continue

        is_fav = code in favorite_stocks
        if only_favorite and not is_fav:
            continue

        items.append({
            "code": code,
            "full_code": f"{code}.{_market_suffix(code)}",
            "name": name,
            "industry": ind,
            "board": b,
            "price": pred["close_price"] if pred else None,
            "change_pct": pred["pct_chg"] if pred else None,
            "probability": prob,
            "rating": r_val,
            "is_limit_up": pred["is_limit_up"] if pred else None,
            "rsi14": pred["rsi14"] if pred else None,
            "predicted_rank": pred["predicted_rank"] if pred else None,
            "has_prediction": pred is not None,
            "is_favorite": is_fav,
        })

    return {
        "total": len(items),
        "total_pool_size": len(get_pool()),
        "favorite_count": len(favorite_stocks),
        "stocks": items,
    }


@router.post("/manage/toggle_favorite", summary="切换自选状态")
def toggle_favorite(req: ToggleFavoriteRequest = Body(...)) -> Dict[str, Any]:
    code = req.code.split(".")[0].strip()
    if code in favorite_stocks:
        favorite_stocks.remove(code)
        active = False
    else:
        favorite_stocks.add(code)
        active = True
    return {"code": code, "is_favorite": active, "favorite_count": len(favorite_stocks)}


@router.get("/overview/stats", summary="首页概览统计")
def get_overview_stats() -> Dict[str, Any]:
    report = service_instance.get_training_report()
    metrics = service_instance.get_evaluation_metrics()
    rec = service_instance.get_topk(k=10)

    panel = report.get("panel", {})
    model_metrics = report.get("model_metrics", {})
    test_m = model_metrics.get("test", {})
    bt = report.get("backtest", {})

    return {
        "pool_size": len(get_pool()),
        "panel": {
            "stocks": panel.get("stocks", 0),
            "dates": panel.get("dates", 0),
            "rows": panel.get("rows", 0),
            "date_range": panel.get("date_range", []),
            "label": panel.get("label", ""),
        },
        "model": {
            "test_auc": test_m.get("auc"),
            "test_rows": test_m.get("n_rows"),
            "test_dates": test_m.get("n_dates"),
            "features": len(panel.get("features", [])),
        },
        "backtest": {
            "strategy_annual": bt.get("strategy", {}).get("annualized_return"),
            "benchmark_annual": bt.get("benchmark", {}).get("annualized_return"),
            "excess_annual": bt.get("excess", {}).get("annualized_return"),
            "max_drawdown": bt.get("strategy", {}).get("max_drawdown"),
            "sharpe": bt.get("strategy", {}).get("sharpe"),
        },
        "latest_date": rec.get("date", ""),
        "latest_count": len(rec.get("recommendations", [])),
        "metrics_available": bool(metrics.get("comparison")),
    }
