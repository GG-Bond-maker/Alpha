# -*- coding: utf-8 -*-
"""推荐服务层：聚合模型产物、归因与回测结果

数据来源原则
------------
早期版本在数据缺失时会用公式凭空生成 500 只股票的概率与价格
（prob = 0.91 - idx/500*0.38 ...），前端展示时无法与真实结果区分。
本版本移除该路径：没有数据就返回空集并附带原因，由前端显示空状态。
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd

from config.config import (
    PROCESSED_DIR, SAVED_MODELS_DIR, get_stock_board,
)


class RecommendationService:
    def __init__(self):
        self.realtime_path = os.path.join(PROCESSED_DIR, "realtime_recommendations.csv")
        self.model_path = os.path.join(SAVED_MODELS_DIR, "lgbm_market_classifier.pkl")
        self.explainer_path = os.path.join(SAVED_MODELS_DIR, "shap_explainer.pkl")
        self.importance_path = os.path.join(SAVED_MODELS_DIR, "global_importance.json")
        self.shap_summary_path = os.path.join(SAVED_MODELS_DIR, "shap_summary.json")
        self.metrics_path = os.path.join(SAVED_MODELS_DIR, "evaluation_metrics.json")
        self.backtest_path = os.path.join(SAVED_MODELS_DIR, "backtest_result.json")
        self.report_path = os.path.join(SAVED_MODELS_DIR, "training_report.json")
        self.factor_path = os.path.join(SAVED_MODELS_DIR, "factor_diagnosis.json")
        self.backtest_cmp_path = os.path.join(SAVED_MODELS_DIR, "backtest_comparison.json")
        self.walk_forward_path = os.path.join(SAVED_MODELS_DIR, "walk_forward.json")
        self.attribution_path = os.path.join(SAVED_MODELS_DIR, "attribution.json")
        self._load()

    # ------------------------------------------------------------------
    # 资源加载
    # ------------------------------------------------------------------
    def _load(self):
        self.data_df = self._read_csv(self.realtime_path)
        self.explainer = self._read_pickle(self.explainer_path)
        self.model_bundle = self._read_pickle(self.model_path)
        self.global_importance = self._read_json(self.importance_path, [])
        self.shap_summary = self._read_json(self.shap_summary_path, {})
        self.metrics = self._read_json(self.metrics_path, {})
        self.backtest = self._read_json(self.backtest_path, {})
        self.report = self._read_json(self.report_path, {})
        self.factor_diagnosis = self._read_json(self.factor_path, {})
        self.backtest_cmp = self._read_json(self.backtest_cmp_path, {})
        self.walk_forward = self._read_json(self.walk_forward_path, {})
        self.attribution = self._read_json(self.attribution_path, {})

    @staticmethod
    def _read_csv(path: str):
        if not os.path.exists(path):
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _read_pickle(path: str):
        if not os.path.exists(path):
            return None
        try:
            return joblib.load(path)
        except Exception:
            return None

    @staticmethod
    def _read_json(path: str, default):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def reload(self):
        self._load()

    # ------------------------------------------------------------------
    # 推荐查询
    # ------------------------------------------------------------------
    def get_available_dates(self) -> List[str]:
        self.reload()
        if self.data_df.empty:
            return []
        col = "更新日期" if "更新日期" in self.data_df.columns else None
        if col is None:
            return []
        return sorted(self.data_df[col].dropna().astype(str).unique().tolist())

    def get_topk(self, date: Optional[str] = None, k: int = 10,
                 industry: Optional[str] = None, board: Optional[str] = None) -> Dict[str, Any]:
        self.reload()
        if self.data_df.empty:
            return {
                "date": date or "",
                "k": k,
                "total_candidates": 0,
                "recommendations": [],
                "message": "尚未生成推荐结果，请先运行 python -m ml_pipeline.run_training",
            }

        df = self.data_df.copy()

        date_col = "更新日期" if "更新日期" in df.columns else None
        if date and date_col and date in df[date_col].astype(str).values:
            df = df[df[date_col].astype(str) == date]
            current_date = date
        else:
            current_date = str(df[date_col].iloc[-1]) if date_col else datetime.today().strftime("%Y-%m-%d")

        if board and board != "全部" and "板块" in df.columns:
            df = df[df["板块"] == board]
        if industry and industry != "全部" and "行业" in df.columns:
            df = df[df["行业"] == industry]

        score_col = next((c for c in ("跑赢候选池均值概率", "预测超额概率", "预测看涨概率")
                          if c in df.columns), None)
        if score_col:
            df = df.sort_values(score_col, ascending=False)

        total = len(df)
        items = [self._to_item(row, idx + 1, current_date)
                 for idx, (_, row) in enumerate(df.head(k).iterrows())]

        return {
            "date": current_date,
            "k": k,
            "total_candidates": total,
            "recommendations": items,
        }

    def _to_item(self, row: pd.Series, rank: int, date: str) -> Dict[str, Any]:
        code = str(row.get("代码", "")).zfill(6)
        score = self._row_score(row)
        rating = row.get("推荐评级")
        if not isinstance(rating, str):
            rating = "A" if score >= 0.75 else ("B" if score >= 0.60 else "C")

        return {
            "stock_code": code,
            "stock_name": str(row.get("名称", code)),
            "industry": str(row.get("行业", "未分类")),
            "board": str(row.get("板块", get_stock_board(code))),
            "predicted_rank": rank,
            "predicted_score": round(score, 4),
            "probability": round(score, 4),
            "recommend_rating": rating,
            "is_limit_up": str(row.get("是否涨停", "否")),
            "close_price": self._num(row.get("最新收盘价"), 0.0),
            "pct_chg": self._num(row.get("当日涨幅(%)"), 0.0),
            "ema20_ratio": self._num(row.get("价格/20日均线比率"), None),
            "rsi14": self._num(row.get("14日相对强弱指标(RSI)"), None),
            "macd": self._num(row.get("归一化异同移动平均线(MACD)"), None),
            "obv": self._num(row.get("能量潮标准分(OBV-Z)"), None),
            "cci": self._num(row.get("顺势指标(CCI)"), None),
            "atr": self._num(row.get("相对真实波幅(ATR/价格)"), None),
            "adx": self._num(row.get("平均趋向指标(ADX)"), None),
            "update_date": date,
        }

    @staticmethod
    def _num(value, default):
        try:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return default
            return round(float(value), 4)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _row_score(row: pd.Series) -> float:
        for column in ("跑赢候选池均值概率", "预测超额概率", "预测看涨概率"):
            if column in row.index:
                return RecommendationService._num(row.get(column), 0.5)
        return 0.5

    # ------------------------------------------------------------------
    # 归因
    # ------------------------------------------------------------------
    def get_global_importance(self) -> List[Dict[str, Any]]:
        self.reload()
        return [
            {
                "feature_key": r.get("feature", ""),
                "name_cn": r.get("name_cn", r.get("feature", "")),
                "importance": r.get("importance_ratio", 0.0),
                "mean_abs_shap": r.get("mean_abs_shap", 0.0),
            }
            for r in (self.global_importance or [])
        ]

    def get_shap_summary(self) -> Dict[str, Any]:
        self.reload()
        importance = [
            {
                "feature_key": r.get("feature", ""),
                "name_cn": r.get("name_cn", r.get("feature", "")),
                "importance": r.get("importance_ratio", 0.0),
                "mean_abs_shap": r.get("mean_abs_shap", 0.0),
            }
            for r in (self.global_importance or [])
        ]
        return {"summary": self.shap_summary or {}, "importance": importance}

    def explain_stock(self, stock_code: str, date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """基于真实模型与解释器生成归因；不可用时返回 None，不伪造数据。"""
        from ml_pipeline.train_explainer import explain_stock as build_explanation

        clean = str(stock_code).zfill(6)

        if self.explainer is None or self.model_bundle is None:
            return None

        model = self.model_bundle.get("model") if isinstance(self.model_bundle, dict) else None
        if model is None:
            return None

        if self.data_df.empty or "代码" not in self.data_df.columns:
            return None
        feature_cols = self.model_bundle.get("feature_cols") or []
        if not feature_cols:
            return None
        recs = self.data_df[self.data_df["代码"].astype(str).str.zfill(6) == clean].copy()
        if date is not None and "更新日期" in recs.columns:
            recs = recs[recs["更新日期"].astype(str) == str(date)]
        elif "更新日期" in recs.columns and not recs.empty:
            recs = recs.sort_values("更新日期")
        if recs.empty or any(c not in recs.columns for c in feature_cols):
            return None
        row = recs.iloc[-1]
        feats = {c: row[c] for c in feature_cols}
        name = str(row.get("名称", clean))
        score = self._row_score(row)
        rank = int(self._num(row.get("推荐排名"), 1))
        try:
            result = build_explanation(
                self.explainer, model, clean, name, feats, score, rank,
                feature_cols=feature_cols,
            )
        except (ValueError, TypeError):
            return None
        result["industry"] = str(row.get("行业", "未分类"))
        result["date"] = str(row.get("更新日期", date or ""))
        return result

    # ------------------------------------------------------------------
    # 评测与回测
    # ------------------------------------------------------------------
    def get_evaluation_metrics(self) -> Dict[str, Any]:
        self.reload()
        if not self.metrics:
            return {"comparison": {}, "errors": {}, "meta": {},
                    "message": "尚未生成评测结果，请先运行 python -m ml_pipeline.run_training"}
        return self.metrics

    def get_backtest(self) -> Dict[str, Any]:
        self.reload()
        if not self.backtest:
            return {"error": "尚未生成回测结果，请先运行 python -m ml_pipeline.run_training"}
        return self.backtest

    def get_training_report(self) -> Dict[str, Any]:
        self.reload()
        return self.report or {}

    def get_attribution(self) -> Dict[str, Any]:
        self.reload()
        if not self.attribution:
            return {"error": "尚未生成归因结果，请先运行训练脚本"}
        return self.attribution

    def get_walk_forward(self) -> Dict[str, Any]:
        self.reload()
        if not self.walk_forward:
            return {"error": "尚未生成滚动窗口验证结果，请先运行训练脚本",
                    "windows": []}
        return self.walk_forward

    def get_backtest_comparison(self) -> Dict[str, Any]:
        self.reload()
        if not self.backtest_cmp:
            return {"error": "尚未生成回测对比，请先运行训练脚本"}
        return self.backtest_cmp

    def get_factor_diagnosis(self) -> Dict[str, Any]:
        self.reload()
        if not self.factor_diagnosis:
            return {"results": [], "usable_factors": [],
                    "message": "尚未生成因子诊断，请先运行 python -m ml_pipeline.run_training"}
        return self.factor_diagnosis

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def export_excel(self) -> str:
        if self.data_df.empty:
            return ""
        self.reload()
        tag = datetime.today().strftime("%Y%m%d")
        path = os.path.join(PROCESSED_DIR, f"stock_recommend_{tag}.xlsx")
        self.data_df.to_excel(path, index=False, engine="openpyxl")
        return path


service_instance = RecommendationService()
