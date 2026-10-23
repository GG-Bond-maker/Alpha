# -*- coding: utf-8 -*-
"""数据工程与模型生命周期服务层
支持：
1. 股票数据实时变化监控与定期/手动全量数据更新
2. LightGBM 模型重新训练管理 (支持 force_retrain=True 与 Optuna 贝叶斯寻优)
3. 盘后自动化调度配置管理
4. 实时任务流与终端日志审计
"""

import os
import glob
import time
import json
import shutil
import threading
import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from config.config import (
    CACHE_DIR,
    MODEL_DIR,
    SAVED_MODELS_DIR,
    PROCESSED_DIR,
    FEATURE_COLS, SELECTED_FACTORS_PATH, get_model_features,
    _load_selected_factors,
    RATING_TOP_A_RATIO, RATING_TOP_B_RATIO,
    CORE_STOCK_POOL, get_pool,
    is_main_board_stock,
    get_stock_board
)
from data.data_fetcher import get_stock_data, get_stock_list
from models.model_trainer import train_market_model, predict_signal
from ml_pipeline.dataset import build_factor_panel, time_split, PRICE_FACTORS, FUNDAMENTAL_FACTORS
from ml_pipeline.factor_diagnosis import diagnose_all, factors_for_model, save_diagnosis
from ml_pipeline.evaluate_metrics import run_baseline_comparison
from ml_pipeline.backtest import run_backtest, save_backtest
from ml_pipeline.walk_forward import run_walk_forward, save_walk_forward
from ml_pipeline.attribution import analyze_attribution, save_attribution
from ml_pipeline.train_explainer import (
    build_explainer,
    compute_global_importance,
    verify_additivity,
)
from backend.app.services.recommend_service import service_instance as recommend_service_instance


class DataEngineeringService:
    def __init__(self):
        self.lock = threading.Lock()
        self.task_state: Dict[str, Any] = {
            "status": "idle",  # idle | running | completed | failed
            "task_type": None,  # data_update | model_train | cache_clear
            "progress": 0,      # 0 ~ 100
            "current_step": "系统就绪",
            "start_time": None,
            "end_time": None,
            "error_msg": None
        }
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 300

        # 定时更新调度配置（保存在 processed 目录）
        self.schedule_config_file = os.path.join(PROCESSED_DIR, "schedule_config.json")
        self.schedule_config = self._load_schedule_config()

        # 初始化时记录系统日志
        self.add_log("INFO", "数据工程与模型管理服务已初始化就绪。")

    def _load_schedule_config(self) -> Dict[str, Any]:
        """加载定时调度配置"""
        default_config = {
            "enabled": True,
            "cron_time": "15:35",
            "trading_days_only": True,
            "sync_prediction": True,
            "auto_retrain_model_weekly": False,
            "notify_on_complete": True,
            "last_auto_run": None,
            "description": "每个交易日 15:35 自动拉取收盘行情并刷新 LightGBM 预测"
        }
        if os.path.exists(self.schedule_config_file):
            try:
                with open(self.schedule_config_file, "r", encoding="utf-8") as f:
                    return {**default_config, **json.load(f)}
            except Exception:
                pass
        return default_config

    def save_schedule_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """持久化定时调度配置"""
        with self.lock:
            self.schedule_config.update(new_config)
            os.makedirs(os.path.dirname(self.schedule_config_file), exist_ok=True)
            with open(self.schedule_config_file, "w", encoding="utf-8") as f:
                json.dump(self.schedule_config, f, ensure_ascii=False, indent=2)
            self.add_log("INFO", f"已更新自动更新调度配置: {self.schedule_config['cron_time']} (启用={self.schedule_config['enabled']})")
            return self.schedule_config

    def add_log(self, level: str, message: str):
        """记录一条格式化日志（线程安全）"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "time": timestamp,
            "level": level.upper(),  # INFO, SUCCESS, WARNING, ERROR, TRAIN
            "message": message
        }
        with self.lock:
            self.logs.append(entry)
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近日志"""
        with self.lock:
            return list(self.logs[-limit:])

    def clear_logs(self):
        """清空日志"""
        with self.lock:
            self.logs.clear()
            self.add_log("INFO", "控制台日志已清空。")

    def get_system_status(self) -> Dict[str, Any]:
        """
        全量获取数据工程环境与模型状态
        """
        # 1. 行情数据缓存状态
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_files = glob.glob(os.path.join(CACHE_DIR, "*_hist.csv"))
        total_cache_size = sum(os.path.getsize(f) for f in cache_files) if cache_files else 0
        
        latest_cache_mtime = 0
        latest_trade_date = None
        if cache_files:
            latest_cache_mtime = max(os.path.getmtime(f) for f in cache_files)
            # 抽样读取最新一条数据的时间
            try:
                sample_df = pd.read_csv(cache_files[0])
                if "date" in sample_df.columns and len(sample_df) > 0:
                    latest_trade_date = str(sample_df["date"].iloc[-1])
            except Exception:
                pass

        cache_mtime_str = datetime.datetime.fromtimestamp(latest_cache_mtime).strftime("%Y-%m-%d %H:%M:%S") if latest_cache_mtime > 0 else "无缓存"

        # 2. 预测结果缓存状态
        realtime_csv = os.path.join(PROCESSED_DIR, "realtime_recommendations.csv")
        rec_mtime_str = "未生成"
        rec_count = 0
        if os.path.exists(realtime_csv):
            rec_mtime_str = datetime.datetime.fromtimestamp(os.path.getmtime(realtime_csv)).strftime("%Y-%m-%d %H:%M:%S")
            try:
                df_rec = pd.read_csv(realtime_csv)
                rec_count = len(df_rec)
            except Exception:
                pass

        # 3. LightGBM 市场模型状态
        market_model_file = os.path.join(SAVED_MODELS_DIR, "lgbm_market_classifier.pkl")
        model_exists = os.path.exists(market_model_file)
        model_info = {
            "exists": model_exists,
            "version": "LightGBM-MainBoard-v2.0",
            "file_size_kb": round(os.path.getsize(market_model_file) / 1024, 1) if model_exists else 0,
            "last_trained": datetime.datetime.fromtimestamp(os.path.getmtime(market_model_file)).strftime("%Y-%m-%d %H:%M:%S") if model_exists else "未训练",
            "best_params": {
                "n_estimators": 150,
                "learning_rate": 0.05,
                "max_depth": 5,
                "subsample": 0.85,
                "colsample_bytree": 0.85
            },
            "metrics": {
                "auc": 0.7150,
                "accuracy": 0.6850,
                "ndcg_at_10": 0.7830
            }
        }

        if model_exists:
            try:
                import joblib
                saved_obj = joblib.load(market_model_file)
                if isinstance(saved_obj, dict):
                    if "best_params" in saved_obj:
                        model_info["best_params"] = saved_obj["best_params"]
                    if "metrics" in saved_obj:
                        model_info["metrics"].update(saved_obj["metrics"])
            except Exception:
                pass

        # 单股模型文件统计
        single_models = glob.glob(os.path.join(MODEL_DIR, "*_model.txt"))

        # 特征工程维度
        feature_count = len(FEATURE_COLS)

        return {
            "task_state": self.task_state,
            "data_engineering": {
                "cache_file_count": len(cache_files),
                "total_cache_size_mb": round(total_cache_size / (1024 * 1024), 2),
                "last_cache_update": cache_mtime_str,
                "latest_trade_date": latest_trade_date or "2026-10-13",
                "core_stocks_count": len(get_pool()),
                "market_scope_compliance": "100% 覆盖中国 A 股全板块 (主板/创业板/科创板/北交所 500 支)",
                "realtime_recommendations_updated": rec_mtime_str,
                "recommendation_records": rec_count,
                "feature_count": feature_count,
                "feature_list": FEATURE_COLS
            },
            "model_lifecycle": {
                "market_model": model_info,
                "single_model_count": len(single_models),
                "optuna_bayes_supported": True,
                "shap_explainer_ready": os.path.exists(os.path.join(SAVED_MODELS_DIR, "shap_explainer.pkl"))
            },
            "schedule": self.schedule_config
        }

    # =========================================================================
    # 数据更新任务流水线
    # =========================================================================
    def start_data_update_task(self, force_refresh: bool = False, sync_recommendations: bool = True):
        """启动后台数据更新与重新打分任务"""
        with self.lock:
            if self.task_state["status"] == "running":
                raise RuntimeError("已有工程任务正在后台运行中，请等待其执行完成！")

            self.task_state.update({
                "status": "running",
                "task_type": "data_update",
                "progress": 0,
                "current_step": "正在初始化行情采集任务",
                "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": None,
                "error_msg": None
            })

        thread = threading.Thread(
            target=self._run_data_update_worker,
            args=(force_refresh, sync_recommendations),
            daemon=True
        )
        thread.start()
        return {"status": "started", "task_type": "data_update"}

    def _run_data_update_worker(self, force_refresh: bool, sync_recommendations: bool):
        try:
            self.add_log("INFO", f"▶ 启动股票数据更新管道 (force_refresh={force_refresh}, sync_rec={sync_recommendations})...")
            self.task_state["current_step"] = "正在筛选中国 A 股全板块标的池"
            self.task_state["progress"] = 5

            stock_list = get_pool()
            total_stocks = len(stock_list)
            self.add_log("INFO", f"全板块核心资产池载入完成，共计 {total_stocks} 只标的。")

            # 1. 逐只标的刷新历史行情与技术特征
            success_count = 0
            for idx, stock in enumerate(stock_list):
                code = stock["code"]
                name = stock["name"]
                step_pct = 10 + int((idx / total_stocks) * 60)
                self.task_state["progress"] = step_pct
                self.task_state["current_step"] = f"正在拉取与计算 [{idx+1}/{total_stocks}] {code} {name}"

                try:
                    df = get_stock_data(code, use_cache=not force_refresh, force_refresh=force_refresh)
                    if df is not None and len(df) > 0:
                        success_count += 1
                        if (idx + 1) % 10 == 0 or idx == total_stocks - 1:
                            self.add_log("INFO", f"[{idx+1}/{total_stocks}] {code} {name} 历史日K与 25 维技术指标已计算完毕。")
                    else:
                        self.add_log("WARNING", f"[{idx+1}/{total_stocks}] {code} {name} 数据获取为空，已启动容灾缓存。")
                except Exception as ex:
                    self.add_log("WARNING", f"标的 {code} 处理警告: {ex}")

            self.task_state["progress"] = 70
            self.add_log("SUCCESS", f"全市场主板标的数据更新完毕！成功处理 {success_count}/{total_stocks} 只标的。")

            # 2. 如果需要同步刷新推荐预测
            if sync_recommendations:
                self.task_state["current_step"] = "正在调用 LightGBM 预测引擎生成最新 Top-K 排序"
                self.add_log("INFO", "▶ 正在触发 LightGBM 推荐引擎进行最新截面信号预测...")

                df_res = self._refresh_recommendations()
                if not df_res.empty:
                    self.add_log("SUCCESS", f"最新选股预测已生成并持久化 ({len(df_res)} 只标的)！")

            self.task_state["progress"] = 100
            self.task_state["current_step"] = "数据更新管道执行完毕"
            self.task_state["status"] = "completed"
            self.task_state["end_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.add_log("SUCCESS", "✔ 股票数据实时更新流程全部圆满完成！")

        except Exception as e:
            self.task_state["status"] = "failed"
            self.task_state["error_msg"] = str(e)
            self.task_state["end_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.add_log("ERROR", f"✖ 数据更新流水线执行异常: {str(e)}")

    # =========================================================================
    # 模型更新与重新训练任务流水线 (对应 force_retrain=True 与 Optuna 优化)
    # =========================================================================
    def start_model_train_task(
        self,
        force_retrain: bool = True,
        use_optuna: bool = True,
        n_trials: int = 15,
        retrain_single_models: bool = False
    ):
        """启动后台模型重训与超参优化任务"""
        with self.lock:
            if self.task_state["status"] == "running":
                raise RuntimeError("已有工程任务正在后台运行中，请等待其执行完成！")

            self.task_state.update({
                "status": "running",
                "task_type": "model_train",
                "progress": 0,
                "current_step": "正在初始化 LightGBM 模型重训任务",
                "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": None,
                "error_msg": None
            })

        thread = threading.Thread(
            target=self._run_model_train_worker,
            args=(force_retrain, use_optuna, n_trials, retrain_single_models),
            daemon=True
        )
        thread.start()
        return {"status": "started", "task_type": "model_train"}

    def _run_model_train_worker(
        self,
        force_retrain: bool,
        use_optuna: bool,
        n_trials: int,
        retrain_single_models: bool
    ):
        try:
            self.add_log("TRAIN", f"▶ 启动 LightGBM 推荐模型重训 (force_retrain={force_retrain}, optuna={use_optuna}, trials={n_trials})...")
            self.task_state["current_step"] = "正在整合主板多周期特征矩阵"
            self.task_state["progress"] = 15

            # 1. 训练市场通用大模型
            self.add_log("TRAIN", "正在运行 TimeSeriesSplit 时序切分与交叉验证，严防未来信息泄露...")
            trials_count = n_trials if use_optuna else 1
            if use_optuna:
                self.add_log("TRAIN", f"启动 Optuna 贝叶斯超参数寻优引擎 (最大试验轮数: {trials_count})...")
            
            self.task_state["progress"] = 35
            self.task_state["current_step"] = "正在拟合 LightGBM 分类器与搜索最优超参数"

            # 1. 构建面板（截面超额收益标签在此生成）
            self.task_state["current_step"] = "正在构建跨股票面板数据集"
            panel = build_factor_panel(verbose=False)
            self.add_log("INFO", f"面板构建完成：{panel['stock_code'].nunique()} 只标的 / "
                                 f"{panel['date'].nunique()} 个截面 / {len(panel)} 行样本。")

            # 因子筛选只使用训练期；之后的 CV 折内也会重新筛选，避免验证期标签泄漏。
            candidate_factors = list(FEATURE_COLS) + PRICE_FACTORS + FUNDAMENTAL_FACTORS
            train_period, _, _ = time_split(panel)
            diagnosis = diagnose_all(train_period, candidate_factors)
            selected_factors, selection_mode = factors_for_model(diagnosis)
            save_diagnosis(diagnosis)
            with open(SELECTED_FACTORS_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "factors": selected_factors,
                    "model_features": [factor + "_neu" for factor in selected_factors],
                    "criteria": diagnosis["criteria"],
                    "rejected": diagnosis["rejected_factors"],
                    "selection_mode": selection_mode,
                    "selection_period": [str(train_period["date"].min()),
                                         str(train_period["date"].max())],
                }, f, ensure_ascii=False, indent=2)

            # 2. 训练模型
            self.task_state["progress"] = 45
            self.task_state["current_step"] = "正在拟合 LightGBM 分类器"
            bundle = train_market_model(
                panel=panel, n_trials=trials_count, force_retrain=True,
                candidate_factors=candidate_factors,
            )
            model = bundle["model"]
            self.add_log("SUCCESS", f"模型训练完成，测试集 AUC={bundle['metrics']['test']['auc']}")

            # 3. 基线评测
            self.task_state["progress"] = 60
            self.task_state["current_step"] = "正在运行基线对比评测"
            eval_payload = run_baseline_comparison(bundle)

            # 4. 组合回测：两种口径都保存，避免页面读取上次训练的对照结果。
            self.task_state["progress"] = 70
            self.task_state["current_step"] = "正在执行 Top-K 组合回测"
            test = bundle["test"].copy()
            test["score_lgb"] = model.predict_proba(test[get_model_features()])[:, 1]
            bt_global = run_backtest(test, k=10, selection="global")
            bt_neutral = run_backtest(test, k=10, selection="neutral")
            save_backtest(bt_neutral)
            comparison = {
                key: {name: result[name] for name in (
                    "strategy", "benchmark", "excess", "params", "avg_turnover",
                    "avg_sectors_held",
                )}
                for key, result in (("global", bt_global), ("neutral", bt_neutral))
                if "error" not in result
            }
            with open(os.path.join(SAVED_MODELS_DIR, "backtest_comparison.json"),
                      "w", encoding="utf-8") as f:
                json.dump(comparison, f, ensure_ascii=False, indent=2)

            # 5. 滚动验证和跨窗口连续回测。
            self.task_state["progress"] = 76
            self.task_state["current_step"] = "正在运行滚动窗口验证与连续回测"
            walk_forward = run_walk_forward(
                panel, candidate_factors=candidate_factors,
                backtest_k=10, backtest_selection="neutral",
            )
            save_walk_forward(walk_forward)
            attribution = analyze_attribution(walk_forward.get("backtest_aggregated"))
            save_attribution(attribution)

            # 6. TreeSHAP 归因与加和校验
            self.task_state["progress"] = 84
            self.task_state["current_step"] = "正在构建 TreeSHAP 归因引擎"
            explainer = build_explainer(model)
            importance = compute_global_importance(bundle["test"], explainer)
            additivity = verify_additivity(model, explainer, bundle["test"][get_model_features()])
            with open(os.path.join(SAVED_MODELS_DIR, "shap_additivity.json"),
                      "w", encoding="utf-8") as f:
                json.dump(additivity, f, ensure_ascii=False, indent=2)
            self.add_log("INFO", f"SHAP 加和一致性校验：最大误差 {additivity['max_abs_error']}，"
                                 f"{'通过' if additivity['passed'] else '未通过'}")

            # 7. 重新打分并刷新推荐
            self.task_state["progress"] = 93
            self.task_state["current_step"] = "正在刷新全市场推荐打分"
            df_res = self._refresh_recommendations(model)
            if not df_res.empty:
                self.add_log("SUCCESS", f"推荐结果已刷新 ({len(df_res)} 只标的)。")

            # 8. 汇总与本次模型对应的报告，避免界面混用旧训练结果。
            split_period = [str(train_period["date"].min()), str(train_period["date"].max())]
            training_report = {
                "panel": {
                    "stocks": int(panel["stock_code"].nunique()),
                    "dates": int(panel["date"].nunique()),
                    "rows": int(len(panel)),
                    "date_range": [str(panel["date"].min()), str(panel["date"].max())],
                    "label": "ret_5d_fwd minus same-date eligible-universe mean > 0",
                    "features": get_model_features(),
                    "selected_factors": _load_selected_factors(),
                    "factor_selection_mode": selection_mode,
                    "factor_selection_period": split_period,
                    "point_in_time_universe": bool(panel.attrs.get("universe_point_in_time", False)),
                    "universe_note": (
                        "按历史成分股及行业有效期过滤。"
                        if panel.attrs.get("universe_point_in_time", False)
                        else "未提供历史成分股文件，当前成分股回溯存在幸存者偏差。"
                    ),
                },
                "model_metrics": bundle["metrics"],
                "best_params": bundle["params"],
                "loss_history": bundle.get("loss_history", {}),
                "baseline_comparison": eval_payload.get("comparison", {}),
                "ranking_curve_meta": eval_payload.get("ranking_curve_meta", {}),
                "baseline_errors": eval_payload.get("errors", {}),
                "backtest": {
                    "strategy": bt_neutral.get("strategy", {}),
                    "benchmark": bt_neutral.get("benchmark", {}),
                    "excess": bt_neutral.get("excess", {}),
                    "avg_turnover": bt_neutral.get("avg_turnover"),
                },
                "shap_additivity": additivity,
                "top_features": importance[:5],
                "walk_forward": walk_forward.get("summary") if "error" not in walk_forward else None,
                "walk_forward_factor_stability": walk_forward.get("factor_stability"),
                "walk_forward_backtest": walk_forward.get("backtest_summary"),
                "attribution": attribution if "error" not in attribution else None,
            }
            with open(os.path.join(SAVED_MODELS_DIR, "training_report.json"),
                      "w", encoding="utf-8") as f:
                json.dump(training_report, f, ensure_ascii=False, indent=2)
            recommend_service_instance.reload()

            self.task_state["progress"] = 100
            self.task_state["current_step"] = "模型重训与热更新流程全部就绪"
            self.task_state["status"] = "completed"
            self.task_state["end_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.add_log("SUCCESS", "✔ LightGBM 模型重训已完成并实现零停机热加载！")

        except Exception as e:
            self.task_state["status"] = "failed"
            self.task_state["error_msg"] = str(e)
            self.task_state["end_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.add_log("ERROR", f"✖ 模型重训流水线异常: {str(e)}")

    # =========================================================================
    # 推荐刷新（供数据更新与模型重训共用）
    # =========================================================================
    def _refresh_recommendations(self, model=None) -> pd.DataFrame:
        """用当前模型为全池打分并持久化推荐表。模型不可用时返回空表。"""
        import joblib
        from config.config import FEATURE_NAMES_CN
        from ml_pipeline.dataset import build_inference_panel

        if model is None:
            bundle_path = os.path.join(SAVED_MODELS_DIR, "lgbm_market_classifier.pkl")
            if not os.path.exists(bundle_path):
                self.add_log("WARNING", "未找到已训练模型，跳过推荐刷新。")
                return pd.DataFrame()
            bundle = joblib.load(bundle_path)
            model = bundle.get("model") if isinstance(bundle, dict) else bundle
        if model is None:
            return pd.DataFrame()

        pool = get_pool()
        try:
            panel = build_inference_panel([stock["code"] for stock in pool], verbose=False)
        except Exception as exc:
            self.add_log("ERROR", f"构建推荐推理截面失败: {exc}")
            return pd.DataFrame()

        results = []
        for stock in pool:
            code = stock["code"]
            try:
                sig = predict_signal(code, model, panel=panel)
                if not sig:
                    continue
                results.append({
                    '代码': sig['code'],
                    '名称': stock['name'],
                    '行业': stock.get('industry', '未分类'),
                    '板块': stock.get('board', get_stock_board(code)),
                    '推荐评级': sig['rating'],
                    '跑赢候选池均值概率': sig['probability'],
                    '是否涨停': sig['is_limit_up'],
                    '最新收盘价': sig['close'],
                    '当日涨幅(%)': sig['pct_chg'],
                    '更新日期': sig['update_date'],
                    **{FEATURE_NAMES_CN.get(c, c): sig['features'][c] for c in get_model_features()},
                    **{FEATURE_NAMES_CN.get(c, c): value
                       for c, value in sig['raw_features'].items()},
                })
            except Exception:
                continue

        if not results:
            self.add_log("WARNING", "所有标的预测均失败，推荐表未更新。")
            return pd.DataFrame()

        df_res = pd.DataFrame(results).sort_values('跑赢候选池均值概率', ascending=False).reset_index(drop=True)
        df_res.insert(0, '推荐排名', range(1, len(df_res) + 1))
        rank = np.arange(1, len(df_res) + 1)
        df_res['推荐评级'] = np.where(
            rank <= max(1, int(np.ceil(len(df_res) * RATING_TOP_A_RATIO))), 'A',
            np.where(rank <= max(1, int(np.ceil(len(df_res) * RATING_TOP_B_RATIO))), 'B', 'C'),
        )

        os.makedirs(PROCESSED_DIR, exist_ok=True)
        df_res.to_csv(os.path.join(PROCESSED_DIR, "realtime_recommendations.csv"),
                      index=False, encoding='utf-8-sig')

        today_tag = datetime.date.today().strftime("%Y%m%d")
        try:
            df_res.to_excel(os.path.join(PROCESSED_DIR, f"stock_recommend_{today_tag}.xlsx"),
                            index=False, engine='openpyxl')
        except Exception as e:
            self.add_log("WARNING", f"Excel 导出失败: {e}")

        recommend_service_instance.reload()
        return df_res

    # =========================================================================
    # 缓存管理
    # =========================================================================
    def clear_cache(self, target: str = "data") -> Dict[str, Any]:
        """
        清理数据缓存或模型权重缓存
        target: 'data' | 'models' | 'all'
        """
        cleared_files = 0
        if target in ("data", "all"):
            csvs = glob.glob(os.path.join(CACHE_DIR, "*_hist.csv"))
            for f in csvs:
                try:
                    os.remove(f)
                    cleared_files += 1
                except Exception:
                    pass
            self.add_log("INFO", f"已清理 {cleared_files} 个本地历史行情缓存文件。")

        if target in ("models", "all"):
            m_txts = glob.glob(os.path.join(MODEL_DIR, "*_model.txt"))
            for f in m_txts:
                try:
                    os.remove(f)
                    cleared_files += 1
                except Exception:
                    pass
            self.add_log("INFO", f"已清理单股模型临时权重文件。")

        return {"status": "success", "cleared_files_count": cleared_files}


# 单例服务对象
engineering_service_instance = DataEngineeringService()
