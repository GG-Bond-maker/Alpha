"""Manual latch plus explicit candidate/portfolio risk assessment."""
import os
import threading
from collections import Counter
from datetime import datetime


class RiskKillSwitch:
    THRESHOLDS = {'max_daily_loss': -0.05, 'max_drawdown': -0.25,
                  'max_stock_weight': 0.20, 'max_sector_concentration': 0.35,
                  'max_unbuyable_ratio': 0.50}

    def __init__(self, reset_token=None):
        self._lock = threading.RLock()
        self._triggered = False
        self._trigger_reason = ''
        self._trigger_time = None
        self._reset_token = reset_token or os.environ.get('ALPHA_RISK_RESET_TOKEN')
        self._gauges = dict.fromkeys(['daily_loss', 'drawdown', 'max_stock_weight',
                                     'max_sector_concentration', 'unbuyable_ratio'])
        self._source = 'not_evaluated'
        self._as_of = None

    @property
    def is_triggered(self):
        return self._triggered

    @property
    def status_report(self):
        with self._lock:
            return {'triggered': self._triggered,
                    'status': 'HALTED (LATCHED)' if self._triggered else 'PARTIAL' if self._source != 'not_evaluated' else 'NOT_EVALUATED',
                    'reason': self._trigger_reason or '仅评估推荐等权假设的集中度；未接入真实持仓日亏损与回撤。',
                    'trigger_time': self._trigger_time, 'thresholds': self.THRESHOLDS,
                    'gauges': dict(self._gauges), 'source': self._source,
                    'as_of_date': self._as_of, 'reset_available': bool(self._reset_token),
                    'scope': '进程级手动熔断；推荐筛查不代表真实持仓风控'}

    def manual_trigger(self, reason='管理员手动触发紧急避险熔断'):
        self._trigger(reason)
        return self.status_report

    def _trigger(self, reason):
        with self._lock:
            self._triggered = True
            self._trigger_reason = reason
            self._trigger_time = datetime.now().isoformat(timespec='seconds')

    def check_portfolio_risk(self, daily_loss=None, drawdown=None, sector_weights=None):
        """Only call with observed portfolio data; absent inputs remain unknown."""
        with self._lock:
            self._source = 'observed_portfolio'
            self._gauges['daily_loss'] = daily_loss
            self._gauges['drawdown'] = drawdown
            if sector_weights:
                self._gauges['max_sector_concentration'] = max(sector_weights.values())
            if daily_loss is not None and daily_loss <= self.THRESHOLDS['max_daily_loss']:
                self._trigger(f'单日亏损 {daily_loss:.2%} 触及阈值')
            if drawdown is not None and drawdown <= self.THRESHOLDS['max_drawdown']:
                self._trigger(f'持仓回撤 {drawdown:.2%} 触及阈值')
            if sector_weights and max(sector_weights.values()) > self.THRESHOLDS['max_sector_concentration']:
                self._trigger('真实持仓行业集中度超限')
            return not self._triggered

    def filter_recommendations(self, recommendations):
        with self._lock:
            if not recommendations:
                return []
            n = len(recommendations)
            sectors = Counter(r.get('industry') or '未分类' for r in recommendations)
            max_weight, concentration = 1 / n, max(sectors.values()) / n
            self._gauges.update(max_stock_weight=max_weight, max_sector_concentration=concentration)
            self._source = 'recommendation_equal_weight_scenario'
            self._as_of = recommendations[0].get('update_date')
            warning = (max_weight > self.THRESHOLDS['max_stock_weight'] or
                       concentration > self.THRESHOLDS['max_sector_concentration'])
            status = 'HALTED' if self._triggered else 'WARNING' if warning else 'PARTIAL'
            notice = ('风控熔断中：' + self._trigger_reason if self._triggered else
                      '推荐等权假设下集中度超限；实际持仓风险未评估' if warning else
                      '推荐等权集中度已筛查；实际持仓日亏损、回撤和成交状态未评估')
            return [{**r, 'risk_status': status, 'risk_notice': notice,
                     **({'recommend_rating': 'HOLD'} if self._triggered else {})} for r in recommendations]

    def reset(self, auth_token):
        import hmac
        with self._lock:
            if not self._reset_token or not hmac.compare_digest(auth_token, self._reset_token):
                return False
            self._triggered, self._trigger_reason, self._trigger_time = False, '', None
            return True


risk_guard_instance = RiskKillSwitch()
