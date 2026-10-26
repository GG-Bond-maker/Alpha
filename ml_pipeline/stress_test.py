# -*- coding: utf-8 -*-
"""历史极端情景压力测试 (ML4T Crisis Scenario Stress Testing)

依照 ML4T 压力测试框架，将 Top-K 选股策略投射到 A 股历史上最严峻的
6 大典型危机时期与 3 种极端假设情景，检验模型在流动性休克、系统性暴跌、
风格逆转与关税冲击下的抗跌能力、Alpha 韧性与极端回撤表现。
"""

import json
import os
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from config.config import SAVED_MODELS_DIR, get_model_features
from ml_pipeline.backtest import run_backtest

REPORT_PATH = os.path.join(SAVED_MODELS_DIR, 'stress_test_report.json')

# A 股 6 大经典历史危机窗口定义
CRISIS_SCENARIOS = [
    {
        "id": "crisis_2015",
        "name": "2015 股灾与去杠杆踩踏",
        "start_date": "2015-06-12",
        "end_date": "2015-09-30",
        "description": "场外配资去杠杆引发千股跌停，流动性枯竭与恐慌抛售",
        "key_feature": "极端连续跌停潮与流动性踩踏",
        "market_regime": "流动性危机 / 恐慌熊市",
    },
    {
        "id": "circuit_2016",
        "name": "2016 熔断机制流动性休克",
        "start_date": "2016-01-04",
        "end_date": "2016-02-29",
        "description": "开年 4 个交易日触发 2 次提前收盘，流动性自强化枯竭",
        "key_feature": "磁吸效应导致的被动卖盘挤兑",
        "market_regime": "微观机制失灵 / 急速阴跌",
    },
    {
        "id": "trade_war_2018",
        "name": "2018 中美贸易战单边阴跌",
        "start_date": "2018-01-29",
        "end_date": "2018-12-28",
        "description": "关税升级与国内去杠杆共振，指数经历长达近一年的漫长估值压缩",
        "key_feature": "基本面预期压制与宏观熊市",
        "market_regime": "宏观逆风 / 慢熊持续阴跌",
    },
    {
        "id": "covid_2020",
        "name": "2020 疫情黑天鹅脉冲与修复",
        "start_date": "2020-01-20",
        "end_date": "2020-03-31",
        "description": "春节后开盘超 3000 只股票跌停，随后流动性宽松推动科技与医药 V 型反转",
        "key_feature": "突发外生事件冲击与极端剧烈波动",
        "market_regime": "突发黑天鹅 / V 型宽幅震荡",
    },
    {
        "id": "core_deflation_2021",
        "name": "2021 核心资产“抱团瓦解”",
        "start_date": "2021-02-18",
        "end_date": "2021-12-31",
        "description": "白酒、医药蓝筹高估值泡沫破裂，市场风格急剧转向新能源与周期资源股",
        "key_feature": "风格剧烈漂移与抱团赛道挤兑",
        "market_regime": "极致风格轮动 / 结构分化",
    },
    {
        "id": "microcap_squeeze_2024",
        "name": "2024 微盘股流动性挤兑",
        "start_date": "2024-01-02",
        "end_date": "2024-02-08",
        "description": "量化 DMA 降杠杆引发微盘股踩踏，大盘权重护盘，大小盘剪刀差拉大",
        "key_feature": "筹码集中与衍生品对冲平仓挤兑",
        "market_regime": "微盘踩踏 / 大小盘分化",
    },
]

# 未计算的情景保持空值，不用示例数字代替实验。
HYPOTHETICAL_SHOCKS = [
    {"id": "hypo_crash", "name": "市场冲击 -15%", "scenario_type": "历史 Beta 线性近似",
     "assumption": "历史样本外组合 Beta 保持不变；不包含非线性与无法成交风险",
     "max_tolerated_loss": -0.20},
    {"id": "hypo_liquidity", "name": "滑点提高至 50 bps", "scenario_type": "单周期成本冲击",
     "assumption": "比较每个已完成持有期的成本差异，其余成交假设不变；不模拟流动性冻结",
     "max_tolerated_loss": -0.02},
    {"id": "hypo_factor_reversal", "name": "因子风格反转", "scenario_type": "待定义的因子冲击",
     "assumption": "需要因子收益情景与持仓因子暴露；SHAP 不能代替因果收益敏感度",
     "max_tolerated_loss": None},
]


def run_stress_test(panel=None, model=None, train_end=None, scored_panel=None, backtest=None):
    """Historical evaluation uses only predictions made after their model's training end."""
    from ml_pipeline.artifacts import artifact_dir
    from ml_pipeline.backtest import COMMISSION_RATE, TRANSFER_FEE_RATE, STAMP_DUTY_RATE
    if scored_panel is not None:
        work = scored_panel.copy()
        if not {'model_train_end', 'pred'}.issubset(work.columns):
            raise ValueError('滚动预测缺少模型训练截止日期，不能验证样本外性')
        work = work[pd.to_datetime(work['date']) > pd.to_datetime(work['model_train_end'])].copy()
        work['score_lgb'] = work['pred']
    elif panel is not None and model is not None and train_end is not None:
        work = panel[pd.to_datetime(panel['date']) > pd.Timestamp(train_end)].copy()
        if not work.empty:
            work['score_lgb'] = model.predict_proba(work[get_model_features()])[:, 1]
    else:
        work = pd.DataFrame()
    if not work.empty:
        work['date'] = pd.to_datetime(work['date'])
    history = []
    for scenario in CRISIS_SCENARIOS:
        row = {**scenario, 'evaluation_type': 'out_of_sample', 'status': 'NOT_EVALUATED',
               'trading_days': 0, 'strategy_return': None, 'benchmark_return': None,
               'excess_return': None, 'max_drawdown': None,
               'resilience': '样本外预测未覆盖', 'badge_type': 'is-neutral'}
        if not work.empty:
            sub = work[(work['date'] >= scenario['start_date']) & (work['date'] <= scenario['end_date'])]
            if 'label_end_date' in sub:
                sub = sub[pd.to_datetime(sub['label_end_date']) <= pd.Timestamp(scenario['end_date'])]
            if not sub.empty:
                bt = run_backtest(sub, k=10, selection='neutral')
                if 'error' not in bt:
                    excess = bt['strategy']['total_return'] - bt['benchmark']['total_return']
                    row.update(status='COMPUTED', trading_days=int(sub['date'].nunique()),
                               strategy_return=bt['strategy']['total_return'],
                               benchmark_return=bt['benchmark']['total_return'],
                               excess_return=round(excess, 4), max_drawdown=bt['strategy']['max_drawdown'],
                               resilience='跑赢同期基准' if excess > 0 else '未跑赢同期基准')
        history.append(row)

    shocks = [{**s, 'estimated_impact': None, 'pass_status': 'NOT_EVALUATED',
               'verdict': '缺少本批次可比收益或因子情景数据'} for s in HYPOTHETICAL_SHOCKS]
    if backtest and backtest.get('strategy', {}).get('returns'):
        rp = np.asarray(backtest['strategy']['returns'], dtype=float)
        rb = np.asarray(backtest['benchmark']['returns'], dtype=float)
        if len(rp) > 2 and np.std(rb) > 1e-9:
            beta = float(np.cov(rp, rb, ddof=1)[0, 1] / np.var(rb, ddof=1))
            shocks[0].update(estimated_impact=round(beta * -0.15, 6),
                             verdict=f'使用本批次样本外周期收益估计 Beta={beta:.4f}；线性情景估计，非实际成交结果')
        gross = np.array([r['period_gross_return'] for r in backtest.get('rebalance_ledger', [])])
        if len(gross):
            buy = COMMISSION_RATE + TRANSFER_FEE_RATE + 0.005
            sell = COMMISSION_RATE + TRANSFER_FEE_RATE + STAMP_DUTY_RATE + 0.005
            change = ((1 + gross) * (1 - sell) / (1 + buy) - 1) - rp
            shocks[1].update(estimated_impact=round(float(change.mean()), 6),
                             verdict='根据本批次逐期毛收益重算；数值为平均每个持有期的净收益变化')
        for row in shocks:
            if row['estimated_impact'] is not None:
                row['pass_status'] = 'PASS' if row['estimated_impact'] >= row['max_tolerated_loss'] else 'FAIL'
    computed = [r for r in history if r['status'] == 'COMPUTED']
    wins = sum(r['excess_return'] > 0 for r in computed)
    report = {
        'generated_at': pd.Timestamp.now().isoformat(), 'historical_crises': history,
        'hypothetical_shocks': shocks,
        'summary': {'total_tested_crises': len(computed), 'win_crises': wins,
                    'win_rate': wins / len(computed) if computed else None,
                    'avg_crisis_excess': float(np.mean([r['excess_return'] for r in computed])) if computed else None,
                    'overall_assessment': f'样本外预测覆盖 {len(computed)}/{len(CRISIS_SCENARIOS)} 个历史情景；未覆盖区间不计入胜率。'},
    }
    path = os.path.join(artifact_dir(), 'stress_test_report.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return report


def load_stress_test_report():
    from ml_pipeline.artifacts import artifact_dir
    path = os.path.join(artifact_dir(), 'stress_test_report.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    return {'error': '本批次未生成压力情景分析', 'historical_crises': [], 'hypothetical_shocks': []}
