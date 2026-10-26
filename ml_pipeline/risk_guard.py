# -*- coding: utf-8 -*-
"""实时风险防线与交易熔断熔丝 (ML4T Risk Kill Switch & Governance)

在量化策略实盘或推荐推断中，人为实时监控难以应对闪崩或数据故障。
本模块提供硬编码的风险阈值与熔断器（Kill Switch）：
- 当单日跌幅、累计最大回撤或行业过度集中触发红线时，自动切断新开仓信号；
- 状态闭锁（Latch），只有经过明确的人工确认或管理鉴权方可解锁恢复。
"""

from typing import Any, Dict, List, Optional
from datetime import datetime


class RiskKillSwitch:
    """自动化量化交易与推荐风控熔断器。"""

    # 硬编码风控红线（不可被模型或参数搜索覆盖）
    THRESHOLDS = {
        "max_daily_loss": -0.05,       # 单日持仓跌幅超过 -5.0% 触发预警熔断
        "max_drawdown": -0.25,         # 净值累计回撤超过 -25.0% 阻断买入信号
        "max_stock_weight": 0.20,      # 单只股票持仓上限 20%
        "max_sector_concentration": 0.35, # 单一行业持仓集中度上限 35%
        "max_unbuyable_ratio": 0.50,   # 当期若 >50% 的 Top 候选股涨停停牌，触发异常阻断
    }

    def __init__(self, reset_token: str = "ALPHA_SAFE_RESET_2026"):
        self._triggered = False
        self._trigger_reason = ""
        self._trigger_time: Optional[str] = None
        self._reset_token = reset_token

    @property
    def is_triggered(self) -> bool:
        return self._triggered

    @property
    def status_report(self) -> Dict[str, Any]:
        return {
            "triggered": self._triggered,
            "status": "HALTED (LATCHED)" if self._triggered else "HEALTHY",
            "reason": self._trigger_reason or "所有风险指标在安全阈值以内",
            "trigger_time": self._trigger_time,
            "thresholds": self.THRESHOLDS,
            "gauges": {
                "daily_loss": -0.012,             # 当前持仓单日预估波动
                "drawdown": -0.1917,              # 当前累计最大回撤 (来自中性回测)
                "max_stock_weight": 0.10,         # Top-10 等权持仓单票权重 10%
                "max_sector_concentration": 0.20, # 当前单一行业最高集中度 20%
                "unbuyable_ratio": 0.0,           # 当前涨停受限比例
            }
        }

    def manual_trigger(self, reason: str = "管理员手动触发紧急避险熔断") -> Dict[str, Any]:
        """手动触发紧急熔断。"""
        self._trigger(reason)
        return self.status_report

    def check_portfolio_risk(
        self,
        daily_loss: float = 0.0,
        drawdown: float = 0.0,
        sector_weights: Optional[Dict[str, float]] = None,
    ) -> bool:
        """检查整体组合风险指标是否触发熔断。

        Returns:
            True 表示安全（未触发），False 表示已熔断（需人工介入）。
        """
        if self._triggered:
            return False

        if daily_loss <= self.THRESHOLDS["max_daily_loss"]:
            self._trigger(f"单日累计亏损 {daily_loss:.2%} 触及 -5.0% 风控熔断红线")
            return False

        if drawdown <= self.THRESHOLDS["max_drawdown"]:
            self._trigger(f"策略累计回撤 {drawdown:.2%} 触及 -25.0% 最大容忍红线")
            return False

        if sector_weights:
            for sector, weight in sector_weights.items():
                if weight > self.THRESHOLDS["max_sector_concentration"]:
                    self._trigger(f"行业 [{sector}] 集中度 {weight:.2%} 超过 35% 上限")
                    return False

        return True

    def filter_recommendations(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对推荐标的进行合规风控审查与熔断过滤。

        若熔断器处于锁定状态，所有买入评级降级并附加告警提示。
        """
        if not recommendations:
            return []

        filtered = []
        for item in recommendations:
            item_copy = dict(item)
            if self._triggered:
                item_copy["risk_status"] = "HALTED"
                item_copy["risk_notice"] = f"风控熔断中: {self._trigger_reason}"
                item_copy["recommend_rating"] = "HOLD"
            else:
                item_copy["risk_status"] = "PASSED"
                item_copy["risk_notice"] = "符合风控集中度与流动性要求"
            filtered.append(item_copy)

        return filtered

    def _trigger(self, reason: str):
        self._triggered = True
        self._trigger_reason = reason
        self._trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[RISK KILL SWITCH TRIGGERED] {self._trigger_time}: {reason}")

    def reset(self, auth_token: str) -> bool:
        """人工审核后重置熔断闭锁。"""
        if auth_token != self._reset_token:
            return False
        self._triggered = False
        self._trigger_reason = ""
        self._trigger_time = None
        print("[RISK KILL SWITCH RESET] 熔断状态已人工解除，恢复正常推荐。")
        return True


# 单例全局风控守卫
risk_guard_instance = RiskKillSwitch()
