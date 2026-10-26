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
        self.stress_test_path = os.path.join(SAVED_MODELS_DIR, "stress_test_report.json")
        self.sensitivity_path = os.path.join(SAVED_MODELS_DIR, "sensitivity_analysis.json")
        self._asset_signatures = {}
        self._model_file_signature = None
        self._model_loaded_signature = None
        self.model_bundle = None
        self._load()

    # ------------------------------------------------------------------
    # 资源加载
    # ------------------------------------------------------------------
    def _load(self):
        # API 查询会频繁调用 reload。按文件签名刷新缓存，避免每次请求都重读模型和结果文件。
        self._load_asset_if_changed("data_df", self.realtime_path, self._read_csv, pd.DataFrame)
        self._load_asset_if_changed("explainer", self.explainer_path, self._read_pickle, lambda: None)
        self._load_asset_if_changed("global_importance", self.importance_path,
                                    lambda path: self._read_json(path, []), list)
        self._load_asset_if_changed("shap_summary", self.shap_summary_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("metrics", self.metrics_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("backtest", self.backtest_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("report", self.report_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("factor_diagnosis", self.factor_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("backtest_cmp", self.backtest_cmp_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("walk_forward", self.walk_forward_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("attribution", self.attribution_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("stress_test", self.stress_test_path,
                                    lambda path: self._read_json(path, {}), dict)
        self._load_asset_if_changed("sensitivity", self.sensitivity_path,
                                    lambda path: self._read_json(path, {}), dict)

        # 首页、评测和推荐接口不需要模型对象。模型包含训练面板数据，体积很大，延迟到局部解释时加载。
        signature = self._file_signature(self.model_path)
        if signature != self._model_file_signature:
            self._model_file_signature = signature
            self._model_loaded_signature = None
            self.model_bundle = None

    @staticmethod
    def _file_signature(path: str):
        try:
            stat = os.stat(path)
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _load_asset_if_changed(self, attribute, path, loader, default_factory):
        signature = self._file_signature(path)
        if path in self._asset_signatures and self._asset_signatures[path] == signature:
            return
        value = loader(path) if signature is not None else default_factory()
        setattr(self, attribute, value)
        self._asset_signatures[path] = signature

    def _get_model_bundle(self):
        self._load()
        if self._model_file_signature is None:
            return None
        if self._model_loaded_signature != self._model_file_signature:
            self.model_bundle = self._read_pickle(self.model_path)
            self._model_loaded_signature = self._model_file_signature
        return self.model_bundle

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

        from ml_pipeline.risk_guard import risk_guard_instance
        guarded_items = risk_guard_instance.filter_recommendations(items)

        return {
            "date": current_date,
            "k": k,
            "total_candidates": total,
            "risk_guard": risk_guard_instance.status_report,
            "recommendations": guarded_items,
        }

    def get_risk_status(self) -> Dict[str, Any]:
        from ml_pipeline.risk_guard import risk_guard_instance
        return risk_guard_instance.status_report

    def _get_market_indicator_cache(self) -> Dict[str, Any]:
        if hasattr(self, "_market_indicator_cache") and self._market_indicator_cache:
            return self._market_indicator_cache

        cache = {}
        import glob
        cache_dir = os.path.join(os.path.dirname(self.realtime_path), "..", "cache")
        for p in glob.glob(os.path.join(cache_dir, "*_hist.csv")):
            code = os.path.basename(p).split("_")[0].zfill(6)
            try:
                df = pd.read_csv(p)
                if not df.empty:
                    last = df.iloc[-1]
                    cache[code] = {
                        "close": round(float(last.get("close", 0.0)), 2),
                        "pct_chg": round(float(last.get("pct_chg", 0.0)), 2),
                        "macd": round(float(last.get("MACD", 0.0)), 3) if pd.notna(last.get("MACD")) else None,
                        "rsi14": round(float(last.get("RSI14", 0.0)), 2) if pd.notna(last.get("RSI14")) else None,
                    }
            except Exception:
                pass

        panel_path = os.path.join(os.path.dirname(self.realtime_path), "panel_dataset.csv")
        if os.path.exists(panel_path):
            try:
                panel_df = pd.read_csv(panel_path)
                latest_date = panel_df["date"].max()
                panel_sub = panel_df[panel_df["date"] == latest_date]
                for _, p_row in panel_sub.iterrows():
                    c = str(p_row["stock_code"]).zfill(6)
                    if c not in cache:
                        cache[c] = {
                            "close": None,
                            "pct_chg": round(float(p_row.get("pct_chg", 0.0)), 2) if pd.notna(p_row.get("pct_chg")) else None,
                            "macd": round(float(p_row.get("MACD_norm", 0.0)), 3) if pd.notna(p_row.get("MACD_norm")) else None,
                            "rsi14": round(float(p_row.get("RSI14", 0.0)), 2) if pd.notna(p_row.get("RSI14")) else None,
                        }
            except Exception:
                pass

        self._market_indicator_cache = cache
        return cache

    def _to_item(self, row: pd.Series, rank: int, date: str) -> Dict[str, Any]:
        code = str(row.get("代码", "")).zfill(6)
        score = self._row_score(row)
        rating = row.get("推荐评级")
        if not isinstance(rating, str) or rating not in ("A", "B", "C"):
            # 依据全市场截面相对百分位排名 (前 10% A 级，随后 20% B 级，其余 C 级)
            if rank <= 30:
                rating = "A"
            elif rank <= 90:
                rating = "B"
            else:
                rating = "C"

        try:
            from backend.app.api.stock import favorite_stocks
            is_fav = code in favorite_stocks
        except Exception:
            is_fav = False

        mkt = self._get_market_indicator_cache().get(code, {})

        close_price = self._num(row.get("最新收盘价"), None)
        if (close_price is None or close_price == 0.0) and mkt.get("close"):
            close_price = mkt["close"]
        if close_price is None:
            close_price = 0.0

        pct_chg = self._num(row.get("当日涨幅(%)"), None)
        if (pct_chg is None or pct_chg == 0.0) and mkt.get("pct_chg") is not None:
            pct_chg = mkt["pct_chg"]
        if pct_chg is None:
            pct_chg = 0.0

        macd_val = self._num(
            row.get("归一化异同移动平均线(MACD)")
            or row.get("MACD_norm_neu")
            or row.get("MACD_norm")
            or row.get("MACD")
            or row.get("macd"),
            None
        )
        if macd_val is None and mkt.get("macd") is not None:
            macd_val = mkt["macd"]

        rsi_val = self._num(
            row.get("14日相对强弱指标(RSI)")
            or row.get("RSI14_neu")
            or row.get("RSI14")
            or row.get("rsi14")
            or row.get("RSI"),
            None
        )
        if rsi_val is None and mkt.get("rsi14") is not None:
            rsi_val = mkt["rsi14"]

        return {
            "stock_code": code,
            "stock_name": str(row.get("名称", code)),
            "industry": str(row.get("行业", "未分类")),
            "board": str(row.get("板块", get_stock_board(code))),
            "predicted_rank": rank,
            "predicted_score": round(score, 4),
            "probability": round(score, 4),
            "recommend_rating": rating,
            "is_favorite": is_fav,
            "is_limit_up": str(row.get("是否涨停", "否")),
            "close_price": close_price,
            "pct_chg": pct_chg,
            "ema20_ratio": self._num(row.get("价格/20日均线比率"), None),
            "rsi14": rsi_val,
            "macd": macd_val,
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
        model_bundle = self._get_model_bundle()

        if self.explainer is None or model_bundle is None:
            return None

        model = model_bundle.get("model") if isinstance(model_bundle, dict) else None
        if model is None:
            return None

        if self.data_df.empty or "代码" not in self.data_df.columns:
            return None
        feature_cols = model_bundle.get("feature_cols") or []
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

    def get_stress_test(self) -> Dict[str, Any]:
        self.reload()
        if not getattr(self, "stress_test", None):
            from ml_pipeline.stress_test import load_stress_test_report
            return load_stress_test_report()
        return self.stress_test

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

    def get_sensitivity_analysis(self) -> Dict[str, Any]:
        self.reload()
        if not getattr(self, "sensitivity", None):
            return {"error": "尚未生成策略敏感性分析，请先运行 python -m ml_pipeline.sensitivity_analysis"}
        return self.sensitivity

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
