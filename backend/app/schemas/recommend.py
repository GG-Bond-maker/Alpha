# -*- coding: utf-8 -*-
"""Pydantic 数据契约

仅声明服务层实际返回的字段，避免默认值掩盖真实数据缺失。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class StockRecommendItem(BaseModel):
    stock_code: str
    stock_name: str
    industry: Optional[str] = None
    board: Optional[str] = None
    predicted_rank: int
    predicted_score: float
    probability: Optional[float] = None
    recommend_rating: Optional[str] = None
    is_limit_up: Optional[str] = None
    close_price: Optional[float] = None
    pct_chg: Optional[float] = None
    ema20_ratio: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    obv: Optional[float] = None
    cci: Optional[float] = None
    atr: Optional[float] = None
    adx: Optional[float] = None
    update_date: Optional[str] = None


class RecommendTopKResponse(BaseModel):
    date: str
    k: int
    total_candidates: int
    recommendations: List[StockRecommendItem]
    message: Optional[str] = None


class FeatureContribution(BaseModel):
    feature_key: str
    name_cn: str
    feature_value: Optional[float] = None
    shap_value: float


class StockExplainResponse(BaseModel):
    stock_code: str
    stock_name: str
    industry: Optional[str] = None
    date: Optional[str] = None
    predicted_score: float
    predicted_margin: Optional[float] = None
    output_space: Optional[str] = None
    predicted_rank: int
    base_value: float
    natural_language_reason: str
    features: List[FeatureContribution]
    top_positive: List[FeatureContribution]
    top_negative: List[FeatureContribution]


class GlobalFeatureImportance(BaseModel):
    feature_key: str
    name_cn: str
    importance: float
    mean_abs_shap: Optional[float] = None
