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
import subprocess
import sys
from ml_pipeline.artifacts import artifact_dir, recommendation_path, experiment_status, live_dir
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
    get_pool,
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
        self.lock = threading.RLock()
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
            "enabled": False,
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
        realtime_csv = recommendation_path()
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
        market_model_file = os.path.join(artifact_dir(), "lgbm_market_classifier.pkl")
        model_exists = os.path.exists(market_model_file)
        report = recommend_service_instance.get_training_report()
        evaluation = recommend_service_instance.get_evaluation_metrics()
        test_metrics = report.get("model_metrics", {}).get("test", {})
        ranking = evaluation.get("comparison", {}).get("LightGBM (Ours)", {})
        model_info = {
            "exists": model_exists, "version": "LightGBM-CSI300",
            "file_size_kb": round(os.path.getsize(market_model_file) / 1024, 1) if model_exists else 0,
            "last_trained": datetime.datetime.fromtimestamp(os.path.getmtime(market_model_file)).isoformat(timespec="seconds") if model_exists else None,
            "best_params": report.get("best_params", {}),
            "metrics": {**test_metrics, "ndcg_at_10": ranking.get("NDCG@10")},
            "experiment": experiment_status(),
        }

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
                "latest_trade_date": latest_trade_date,
                "core_stocks_count": len(get_pool()),
                "market_scope_compliance": f"当前研究范围：沪深300成分股（{len(get_pool())} 只）",
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
            "schedule": self.schedule_config,
            "scheduler": getattr(self, 'scheduler_status', {'active': False, 'timezone': 'Asia/Shanghai'})
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
            self.task_state["current_step"] = "正在筛选沪深300成分股"
            self.task_state["progress"] = 5

            stock_list = get_pool()
            total_stocks = len(stock_list)
            self.add_log("INFO", f"沪深300研究池载入完成，共计 {total_stocks} 只标的。")

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
            self.add_log("SUCCESS", f"沪深300成分股行情更新完毕！成功处理 {success_count}/{total_stocks} 只标的。")

            # 2. 如果需要同步刷新推荐预测
            if sync_recommendations:
                self.task_state["current_step"] = "正在调用 LightGBM 预测引擎生成最新 Top-K 排序"
                self.add_log("INFO", "▶ 正在触发 LightGBM 推荐引擎进行最新截面信号预测...")

                df_res = self._refresh_recommendations(force_refresh=force_refresh)
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

    def _run_model_train_worker(self, force_retrain, use_optuna, n_trials, retrain_single_models):
        try:
            if retrain_single_models:
                self.add_log("WARNING", "主流程仅训练共享截面模型，不训练个股专属模型。")
            if not force_retrain and experiment_status().get("status") == "complete":
                self.add_log("INFO", "保留已验证的当前批次；需要重训时启用强制重训。")
            else:
                command = [sys.executable, "-m", "ml_pipeline.run_training",
                           "--trials", str(n_trials if use_optuna else 1)]
                self.add_log("TRAIN", "开始隔离训练，全部检查通过后才切换当前模型。")
                environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
                process = subprocess.Popen(
                    command, cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", env=environment,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                for line in process.stdout:
                    self.add_log("TRAIN", line.rstrip()[-1000:])
                    if line.startswith("["):
                        self.task_state["current_step"] = line.rstrip()[:160]
                if process.wait() != 0:
                    raise RuntimeError("训练失败，当前完整批次已保留；详情见训练日志")
                recommend_service_instance.reload()
            self.task_state.update(status="completed", progress=100,
                                   current_step="实验批次已校验并激活", end_time=datetime.datetime.now().isoformat())
            self.add_log("SUCCESS", "模型、归因和评测文件已作为同一批次加载。")
        except Exception as exc:
            self.task_state.update(status="failed", error_msg=str(exc), end_time=datetime.datetime.now().isoformat())
            self.add_log("ERROR", str(exc))

    def _refresh_recommendations(self, model=None, force_refresh=False) -> pd.DataFrame:
        """用当前模型为全池打分并持久化推荐表。模型不可用时返回空表。"""
        import joblib
        from config.config import FEATURE_NAMES_CN
        from ml_pipeline.dataset import build_inference_panel

        if model is None:
            bundle_path = os.path.join(artifact_dir(), "lgbm_market_classifier.pkl")
            if not os.path.exists(bundle_path):
                self.add_log("WARNING", "未找到已训练模型，跳过推荐刷新。")
                return pd.DataFrame()
            bundle = joblib.load(bundle_path)
            model = bundle.get("model") if isinstance(bundle, dict) else bundle
        if model is None:
            return pd.DataFrame()

        pool = get_pool()
        try:
            panel = build_inference_panel([stock["code"] for stock in pool], verbose=False, force_refresh=force_refresh)
        except Exception as exc:
            self.add_log("ERROR", f"构建推荐推理截面失败: {exc}")
            return pd.DataFrame()

        from ml_pipeline.run_training import generate_recommendations
        scoring_bundle = bundle if model is not None and 'bundle' in locals() and isinstance(bundle, dict) else {'model': model}
        df_res = generate_recommendations(model, [stock['code'] for stock in pool], panel, bundle=scoring_bundle)
        if df_res.empty:
            self.add_log("WARNING", "没有生成有效推荐，保留当前快照。")
            return df_res

        output_dir = live_dir()
        df_res["model_run_id"] = experiment_status().get("run_id")
        snapshot_path = os.path.join(output_dir, "realtime_recommendations.csv")
        temporary = snapshot_path + ".tmp"
        df_res.to_csv(temporary, index=False, encoding='utf-8-sig')
        os.replace(temporary, snapshot_path)

        today_tag = datetime.date.today().strftime("%Y%m%d")
        try:
            df_res.to_excel(os.path.join(output_dir, f"stock_recommend_{today_tag}.xlsx"),
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
