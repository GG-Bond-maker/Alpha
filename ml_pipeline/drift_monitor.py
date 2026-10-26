# -*- coding: utf-8 -*-
"""特征与模型漂移监控 (Feature Drift & Model Degradation Monitor)

依据《Machine Learning for Algorithmic Trading》第 9、26 章规范构建：
1. 群体稳定性指数 (Population Stability Index, PSI) 评估特征分布时序漂移；
2. 双样本 Kolmogorov-Smirnov 检验 (KS-Test) 验证连续变量累积分布函数的一致性；
3. 预测概率分布漂移与目标市场收益分布检验；
4. 设立制度化漂移警戒阈值：
   - PSI < 0.10: 稳定 (No significant drift) - 继续部署运行
   - 0.10 <= PSI < 0.20: 温和漂移 (Moderate drift) - 提高监控频次与提示
   - PSI >= 0.20: 显著漂移 (Significant drift) - 触发告警并建议模型重训
"""

import json
import os
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from config.config import SAVED_MODELS_DIR


def calculate_psi(reference: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    """计算两组样本分布间的群体稳定性指数 (Population Stability Index, PSI)。

    标准 ML4T 实现：
    - 基于基准分布 (Reference) 的分位数划分子区间；
    - 外侧箱子边界扩展到 [-inf, +inf]，完整捕获尾部极端移动；
    - 裁剪概率值至 1e-4，防止除以零或对数无穷大异常。
    """
    ref = np.asarray(reference).flatten()
    cur = np.asarray(current).flatten()
    ref = ref[~np.isnan(ref)]
    cur = cur[~np.isnan(cur)]

    if len(ref) < 20 or len(cur) < 20:
        return 0.0

    try:
        breakpoints = np.percentile(ref, np.linspace(0, 100, n_bins + 1))
        # 扩展外边界
        breakpoints[0], breakpoints[-1] = -np.inf, np.inf
        # 去除重复分位点（针对离散特征）
        breakpoints = np.unique(breakpoints)
        if len(breakpoints) < 2:
            return 0.0

        ref_counts = np.histogram(ref, bins=breakpoints)[0]
        cur_counts = np.histogram(cur, bins=breakpoints)[0]

        ref_pct = ref_counts / len(ref)
        cur_pct = cur_counts / len(cur)

        # 概率裁剪防溢出
        ref_pct = np.clip(ref_pct, 1e-4, None)
        cur_pct = np.clip(cur_pct, 1e-4, None)

        psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
        return round(max(0.0, psi), 4)
    except Exception:
        return 0.0


def evaluate_feature_drift(ref_series: pd.Series, cur_series: pd.Series, n_bins: int = 10) -> Dict[str, Any]:
    """对单个特征计算 PSI、KS 统计量与 p-value，并给出状态评级。"""
    ref_clean = ref_series.dropna().values
    cur_clean = cur_series.dropna().values

    if len(ref_clean) == 0 or len(cur_clean) == 0:
        return {
            'psi': 0.0,
            'ks_stat': 0.0,
            'ks_pvalue': 1.0,
            'ks_pvalue_fmt': '1.0000',
            'ref_mean': 0.0,
            'cur_mean': 0.0,
            'ref_std': 0.0,
            'cur_std': 0.0,
            'status': 'UNKNOWN',
            'status_label': '无有效数据',
            'action': '数据缺失'
        }

    psi = calculate_psi(ref_clean, cur_clean, n_bins=n_bins)
    ks_res = ks_2samp(ref_clean, cur_clean)
    ks_stat = float(round(ks_res.statistic, 4))
    ks_pval = float(ks_res.pvalue)

    if psi < 0.10:
        status = 'STABLE'
        label = '分布稳定'
        action = '正常生产运行'
    elif psi < 0.20:
        status = 'MODERATE'
        label = '轻度漂移'
        action = '建议关注并提高监控频次'
    else:
        status = 'SIGNIFICANT'
        label = '显著漂移'
        action = '建议触发特征重整与模型重训'

    return {
        'psi': psi,
        'ks_stat': ks_stat,
        'ks_pvalue': ks_pval,
        'ks_pvalue_fmt': f'{ks_pval:.2e}' if ks_pval < 1e-4 else f'{ks_pval:.4f}',
        'ref_mean': float(round(np.mean(ref_clean), 4)),
        'cur_mean': float(round(np.mean(cur_clean), 4)),
        'ref_std': float(round(np.std(ref_clean), 4)),
        'cur_std': float(round(np.std(cur_clean), 4)),
        'status': status,
        'status_label': label,
        'action': action,
    }


def generate_drift_report(model_path: str = None) -> Dict[str, Any]:
    """生成全套特征与模型预测稳定性检测报告并持久化。"""
    if model_path is None:
        model_path = os.path.join(SAVED_MODELS_DIR, 'lgbm_market_classifier.pkl')

    if not os.path.exists(model_path):
        return {'error': '未找到模型权重与训练集快照'}

    bundle = joblib.load(model_path)
    train_df = bundle.get('train')
    test_df = bundle.get('test')
    model = bundle.get('model')
    model_features = bundle.get('feature_cols', [])

    if train_df is None or test_df is None:
        return {'error': '模型对象内缺少 train / test 分割集'}

    feature_candidates = [
        ('ATR_ratio_neu', '真实波幅比 (ATR中性化)', '波动率'),
        ('MACD_norm_neu', '异同移动平均线 (MACD中性化)', '动量/均线'),
        ('momentum_60d_neu', '60日动量 (中性化)', '动量'),
        ('OBV_zscore_neu', '能量潮指标 (OBV中性化)', '量价'),
        ('RSI14', '14日相对强弱指标 (RSI14)', '超买超卖'),
        ('momentum_20d', '20日中短期动量', '动量'),
        ('volatility_20d', '20日历史波动率', '波动率'),
        ('pe_ttm', '滚动市盈率 (PE-TTM)', '基本面估值'),
        ('debt_ratio', '资产负债率', '基本面财务'),
        ('turnover_proxy', '换手率代理指标', '流动性'),
    ]

    features_report = []
    max_psi = 0.0

    for col, name_cn, category in feature_candidates:
        if col in train_df.columns and col in test_df.columns:
            res = evaluate_feature_drift(train_df[col], test_df[col])
            res['feature'] = col
            res['name_cn'] = name_cn
            res['category'] = category
            res['is_model_input'] = col in model_features
            features_report.append(res)
            if res['psi'] > max_psi:
                max_psi = res['psi']

    # 模型预测值漂移检验 (Prediction Score Drift)
    prediction_drift = None
    if model is not None and model_features:
        try:
            train_preds = model.predict_proba(train_df[model_features])[:, 1]
            test_preds = model.predict_proba(test_df[model_features])[:, 1]
            pred_res = evaluate_feature_drift(pd.Series(train_preds), pd.Series(test_preds))
            pred_res['name'] = 'LightGBM 预测看涨概率分布'
            prediction_drift = pred_res
        except Exception:
            pass

    # 目标变量（市场未来收益）漂移检验 (Target Drift)
    target_drift = None
    target_col = 'ret_5d_fwd'
    if target_col in train_df.columns and target_col in test_df.columns:
        t_res = evaluate_feature_drift(train_df[target_col], test_df[target_col])
        t_res['name'] = '5日持仓未来收益分布 (Target)'
        target_drift = t_res

    # 总体健康评估
    if max_psi < 0.10:
        overall_status = 'HEALTHY'
        overall_label = '✅ 特征与模型高度稳定 (Healthy)'
        summary_desc = '核心特征 PSI 均低于 0.10，未发生显著统计漂移。当前训练集提取的特征规律对测试区间保持有效。'
    elif max_psi < 0.20:
        overall_status = 'WARNING'
        overall_label = '⚠️ 存在温和分布漂移 (Moderate Drift)'
        summary_desc = '个别特征分布在测试集发生温和漂移 (0.10 <= PSI < 0.20)，模型目前仍具备预测效力，建议缩短调仓重训周期。'
    else:
        overall_status = 'CRITICAL'
        overall_label = '🚨 检测到显著特征漂移 (Significant Drift)'
        summary_desc = '至少有一个核心特征 PSI 突破 0.20 临界线，时序分布发生结构性位移，强烈建议立即触发重训流程。'

    report = {
        'updated_at': str(pd.Timestamp.now())[:19],
        'train_samples': len(train_df),
        'test_samples': len(test_df),
        'overall_status': overall_status,
        'overall_label': overall_label,
        'summary_desc': summary_desc,
        'max_feature_psi': round(max_psi, 4),
        'features': features_report,
        'prediction_drift': prediction_drift,
        'target_drift': target_drift,
        'thresholds': {
            'stable': '< 0.10',
            'moderate': '0.10 ~ 0.20',
            'significant': '>= 0.20'
        }
    }

    out_path = os.path.join(SAVED_MODELS_DIR, 'feature_drift_report.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


if __name__ == '__main__':
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    r = generate_drift_report()
    print("Feature Drift Report Generated:")
    print("Overall Status:", r.get('overall_label'))
    print("Max PSI:", r.get('max_feature_psi'))
    for item in r.get('features', []):
        print(f"  {item['feature']:20s} PSI={item['psi']:.4f} KS_p={item['ks_pvalue_fmt']} [{item['status_label']}]")
