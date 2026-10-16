# -*- coding: utf-8 -*-
"""Pydantic 数据契约规范模块
适配 AShare-AI-Stock-Picker 评级体系与 Alpha 推荐可解释性服务
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class StockRecommendItem(BaseModel):
    stock_code: str
    stock_name: str
    industry: Optional[str] = "全市场A股"
    board: Optional[str] = "主板"
    predicted_rank: int
    predicted_score: float
    probability: Optional[float] = None
    recommend_rating: Optional[str] = "B"     # 推荐评级: 'A' | 'B' | 'C'
    is_limit_up: Optional[str] = "否"        # 是否涨停: '是' | '否'
    close_price: Optional[float] = None     # 最新收盘价
    pct_chg: Optional[float] = None         # 当日涨幅(%)
    
    # 核心技术指标
    ema20_ratio: Optional[float] = 1.0
    rsi14: Optional[float] = 50.0
    macd: Optional[float] = 0.0
    obv: Optional[float] = 0.0
    cci: Optional[float] = 0.0
    atr: Optional[float] = 0.0
    adx: Optional[float] = 0.0

    # 历史兼容字段
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    roe: Optional[float] = None
    net_profit_growth: Optional[float] = None
    momentum_20d: Optional[float] = None
    net_inflow_ratio: Optional[float] = None
    relevance_label: Optional[int] = 1


class RecommendTopKResponse(BaseModel):
    date: str
    k: int
    total_candidates: int
    recommendations: List[StockRecommendItem]


class FeatureContribution(BaseModel):
    feature_key: str
    name_cn: str
    feature_value: float
    shap_value: float


class StockExplainResponse(BaseModel):
    stock_code: str
    stock_name: str
    date: str
    industry: str
    predicted_score: float
    predicted_rank: int
    base_value: float
    natural_language_reason: str
    features: List[FeatureContribution]
    top_positive: List[FeatureContribution]
    top_negative: List[FeatureContribution]
    waterfall_data: Optional[List[FeatureContribution]] = None


class GlobalFeatureImportance(BaseModel):
    feature_key: str
    name_cn: str
    importance: float


class ModelMetricValues(BaseModel):
    NDCG_at_5: Optional[float] = Field(default=0.74, alias="NDCG@5")
    NDCG_at_10: Optional[float] = Field(default=0.78, alias="NDCG@10")
    Precision_at_5: Optional[float] = Field(default=0.73, alias="Precision@5")
    Precision_at_10: Optional[float] = Field(default=0.66, alias="Precision@10")
    Recall_at_5: Optional[float] = Field(default=0.60, alias="Recall@5")
    Recall_at_10: Optional[float] = Field(default=0.75, alias="Recall@10")
    HitRate_at_5: Optional[float] = Field(default=1.00, alias="HitRate@5")
    HitRate_at_10: Optional[float] = Field(default=1.00, alias="HitRate@10")
    AUC: Optional[float] = Field(default=0.71, alias="AUC")

    class Config:
        populate_by_name = True
