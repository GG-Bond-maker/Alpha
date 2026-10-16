# -*- coding: utf-8 -*-
"""模型训练与 Optuna 贝叶斯超参数优化模块
融合 AShare-AI-Stock-Picker 贝叶斯超参调优、单股建模，与 Alpha 市场联合模型及 TreeSHAP 归因
"""

import os
import glob
import logging
import warnings
import joblib
import optuna
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, accuracy_score
from sklearn.model_selection import TimeSeriesSplit

from config.config import MODEL_DIR, SAVED_MODELS_DIR, FEATURE_COLS, CORE_STOCK_POOL, RATING_BINS, RATING_LABELS
from data.data_fetcher import get_stock_data

warnings.filterwarnings("ignore")


def optimize_hyperparameters(X: pd.DataFrame, y: pd.Series, n_trials: int = 25) -> dict:
    """
    使用 Optuna 进行贝叶斯超参数自动寻优
    采用 TimeSeriesSplit 时间序列交叉验证，严防未来信息泄露
    
    Args:
        X (pd.DataFrame): 特征矩阵
        y (pd.Series): 二分类目标标签 (0 或 1)
        n_trials (int): Optuna 试验轮数
        
    Returns:
        dict: 最佳超参数配置字典
    """
    logging.getLogger('optuna').setLevel(logging.ERROR)
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # 兜底默认参数（当数据量较小或快速运行）
    default_params = {
        'n_estimators': 150,
        'learning_rate': 0.05,
        'max_depth': 5,
        'subsample': 0.85,
        'colsample_bytree': 0.85,
        'reg_alpha': 0.1,
        'reg_lambda': 0.1,
        'random_state': 42,
        'verbose': -1
    }

    if len(X) < 100 or y.nunique() < 2:
        return default_params

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 80, 300),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2, log=True),
            'max_depth': trial.suggest_int('max_depth', 3, 7),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-4, 5.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-4, 5.0, log=True),
            'random_state': 42,
            'verbose': -1
        }

        n_splits = min(3, max(2, len(X) // 80))
        tscv = TimeSeriesSplit(n_splits=n_splits)
        scores = []

        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            if y_val.nunique() < 2 or y_train.nunique() < 2:
                continue

            model = lgb.LGBMClassifier(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(stopping_rounds=15, verbose=False)]
            )

            y_pred = model.predict_proba(X_val)[:, 1]
            try:
                score = roc_auc_score(y_val, y_pred)
                scores.append(score)
            except Exception:
                pass

        return np.mean(scores) if scores else 0.5

    try:
        study = optuna.create_study(direction='maximize')
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        best = study.best_params
        best['random_state'] = 42
        best['verbose'] = -1
        return best
    except Exception as e:
        print(f"[Optuna] 优化过程发生异常: {e}，使用默认参数")
        return default_params


def train_and_save_model(code: str, force_retrain: bool = False, n_trials: int = 15) -> lgb.Booster:
    """
    单股 LightGBM 模型训练与保存 (参考 AShare-AI-Stock-Picker)
    
    Args:
        code (str): 6位股票代码
        force_retrain (bool): 是否强制重训
        n_trials (int): Optuna 轮数
        
    Returns:
        lgb.Booster: 训练好的模型实例
    """
    clean_code = str(code).zfill(6)
    model_path = os.path.join(MODEL_DIR, f'{clean_code}_model.txt')

    # 1. 优先加载本地已有模型缓存
    if not force_retrain and os.path.exists(model_path):
        try:
            return lgb.Booster(model_file=model_path)
        except Exception as e:
            print(f"[ModelTrainer] 加载股票 {clean_code} 缓存模型失败: {e}，准备重新训练")

    # 2. 获取股票真实历史数据与技术指标
    df = get_stock_data(clean_code)
    if df is None or len(df) < 100:
        return None

    try:
        # 清洗数据与对齐目标
        valid_df = df.dropna(subset=['pct_chg_5d']).copy()
        if len(valid_df) < 60:
            return None

        X = valid_df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0)
        y = (valid_df['pct_chg_5d'] > 0).astype(int)

        if y.nunique() < 2:
            return None

        # 时序切分
        split_idx = int(len(X) * 0.8)
        X_train, X_valid = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_valid = y.iloc[:split_idx], y.iloc[split_idx:]

        # Optuna 超参数优化
        best_params = optimize_hyperparameters(X_train, y_train, n_trials=n_trials)

        # 全量数据拟合
        model = lgb.LGBMClassifier(**best_params)
        model.fit(X, y, callbacks=[])

        # 持久化存储模型
        os.makedirs(MODEL_DIR, exist_ok=True)
        model.booster_.save_model(model_path)
        return model.booster_

    except Exception as e:
        print(f"[ModelTrainer] 训练股票 {clean_code} 模型发生异常: {e}")
        return None


def train_market_joint_model(
    sample_codes: list = None,
    force_retrain: bool = False,
    n_trials: int = 20
) -> tuple:
    """
    训练全市场通用选股大模型（整合代表性标的多期真实技术指标样本）
    同时产出通用分类模型与用于全栈系统的评测和 SHAP 归因模型
    
    Args:
        sample_codes (list): 样本股票代码列表（默认采用核心蓝筹股池）
        force_retrain (bool): 是否强制重训
        n_trials (int): Optuna 轮数
        
    Returns:
        tuple: (lgb.LGBMClassifier, pd.DataFrame 验证测试集)
    """
    market_model_file = os.path.join(SAVED_MODELS_DIR, "lgbm_market_classifier.pkl")
    
    if not force_retrain and os.path.exists(market_model_file):
        try:
            saved = joblib.load(market_model_file)
            return saved['model'], saved.get('test_df', None)
        except Exception:
            pass

    if sample_codes is None:
        sample_codes = [s['code'] for s in CORE_STOCK_POOL]

    print(f"[ModelTrainer] 开始训练市场通用选股模型，采集 {len(sample_codes)} 只核心标的历史样本...")
    all_dfs = []
    for code in sample_codes:
        df = get_stock_data(code)
        if df is not None and len(df) > 80:
            df_sample = df.dropna(subset=['pct_chg_5d']).copy()
            df_sample['stock_code'] = str(code).zfill(6)
            all_dfs.append(df_sample)

    if not all_dfs:
        raise RuntimeError("未能获取到足够的股票历史数据，请检查网络或数据源！")

    joint_df = pd.concat(all_dfs).reset_index()
    joint_df = joint_df.sort_values('date').reset_index(drop=True)

    X = joint_df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0)
    y = (joint_df['pct_chg_5d'] > 0).astype(int)

    # 时序划分：前 80% 训练与调优，后 20% 测试
    split_idx = int(len(joint_df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    test_df = joint_df.iloc[split_idx:].copy()

    # Optuna 超参调优
    print(f"[ModelTrainer] 运行 Optuna 贝叶斯超参数调优 ({n_trials} 轮)...")
    best_params = optimize_hyperparameters(X_train, y_train, n_trials=n_trials)
    print(f"[ModelTrainer] 最佳超参搜索完毕: {best_params}")

    # 训练模型
    model = lgb.LGBMClassifier(**best_params)
    model.fit(X_train, y_train)

    # 在测试集上评估
    test_preds = model.predict_proba(X_test)[:, 1]
    test_df['predicted_prob'] = test_preds
    auc_score = roc_auc_score(y_test, test_preds)
    acc_score = accuracy_score(y_test, (test_preds >= 0.5).astype(int))
    print(f"[ModelTrainer] 市场通用模型测试集指标: AUC={auc_score:.4f}, Accuracy={acc_score:.4f}")

    # 保存模型
    os.makedirs(SAVED_MODELS_DIR, exist_ok=True)
    joblib.dump({
        'model': model,
        'best_params': best_params,
        'metrics': {'auc': auc_score, 'accuracy': acc_score},
        'test_df': test_df
    }, market_model_file)

    return model, test_df


def predict_stock_signal(code: str, booster_or_model=None) -> dict:
    """
    对指定股票预测未来 5 日上涨概率并输出推荐评级（A/B/C）与涨停预警
    
    Args:
        code (str): 股票代码
        booster_or_model: 预载的模型（单股 booster 或通用分类器）
        
    Returns:
        dict: 选股预测明细
    """
    clean_code = str(code).zfill(6)
    df = get_stock_data(clean_code)
    if df is None or len(df) == 0:
        return None

    # 获取最新一根 K 线的特征向量
    X = df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0)
    if len(X) == 0:
        return None

    latest_row = X.iloc[[-1]]
    latest_feature_vals = latest_row.values.astype(np.float32)

    # 预测概率
    prob = 0.5
    if booster_or_model is not None:
        try:
            if hasattr(booster_or_model, 'predict_proba'):
                prob = float(booster_or_model.predict_proba(latest_row)[0, 1])
            elif hasattr(booster_or_model, 'predict'):
                raw_pred = booster_or_model.predict(latest_feature_vals)[0]
                prob = float(raw_pred) if 0.0 <= raw_pred <= 1.0 else 1.0 / (1.0 + np.exp(-raw_pred))
        except Exception as e:
            print(f"[Predict] 预测计算异常: {e}")

    # 计算推荐评级
    rating = 'C'
    if prob >= 0.75:
        rating = 'A'
    elif prob >= 0.60:
        rating = 'B'

    # 是否涨停判断 (当日涨幅 >= 9.9%)
    latest_pct = float(df['pct_chg'].iloc[-1]) if 'pct_chg' in df.columns else 0.0
    is_limit_up = "是" if latest_pct >= 9.9 else "否"

    latest_close = float(df['close'].iloc[-1]) if 'close' in df.columns else 0.0
    latest_date = df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1])

    return {
        'code': clean_code,
        'probability': round(prob, 4),
        'rating': rating,
        'is_limit_up': is_limit_up,
        'close': latest_close,
        'pct_chg': round(latest_pct, 2),
        'update_date': latest_date,
        'features': {col: round(float(latest_row[col].iloc[0]), 4) for col in FEATURE_COLS}
    }
