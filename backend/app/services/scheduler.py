"""Daily China-time scheduler with an explicit exchange trading calendar."""
import asyncio
import io
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
from config.config import CACHE_DIR

CHINA_TIME = timezone(timedelta(hours=8))


def is_trading_day(day) -> bool:
    path = Path(CACHE_DIR) / 'trading_calendar.csv'
    calendar = pd.read_csv(path) if path.exists() else pd.DataFrame()
    dates = pd.to_datetime(calendar.get('trade_date', pd.Series(dtype=str)))
    if dates.empty or pd.Timestamp(day) > dates.max():
        # Bound external retrieval; an unavailable calendar must not become a weekday guess.
        code = "import akshare as a; print(a.tool_trade_date_hist_sina().to_csv(index=False), end='')"
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                                encoding='utf-8', timeout=25, check=True,
                                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        calendar = pd.read_csv(io.StringIO(result.stdout))
        dates = pd.to_datetime(calendar['trade_date'], errors='raise')
        if dates.empty or pd.Timestamp(day) > dates.max():
            raise RuntimeError('交易日历尚未覆盖计划日期，已跳过自动任务')
        temporary = path.with_suffix('.tmp')
        calendar.to_csv(temporary, index=False)
        os.replace(temporary, path)
    return pd.Timestamp(day) in set(dates)


class DailyScheduler:
    def __init__(self, service, calendar_check=is_trading_day):
        self.service = service
        self.calendar_check = calendar_check
        self.last_attempt = None
        self.weekly_pending = False
        self.status = {'active': False, 'timezone': 'Asia/Shanghai', 'last_check': None, 'error': None}
        service.scheduler_status = self.status

    def tick(self, now=None):
        now = now or datetime.now(CHINA_TIME)
        config = dict(self.service.schedule_config)
        today = now.date().isoformat()
        self.status['last_check'] = now.isoformat(timespec='seconds')
        if self.weekly_pending and self.service.task_state['status'] != 'running':
            self.weekly_pending = False
            if self.service.task_state['status'] == 'completed':
                self.service.start_model_train_task(force_retrain=True, use_optuna=True, n_trials=5)
        if not config.get('enabled') or now.strftime('%H:%M') < config.get('cron_time', '15:35'):
            return False
        if str(config.get('last_auto_run') or '').startswith(today) or self.last_attempt == today:
            return False
        if self.service.task_state['status'] == 'running':
            return False
        self.last_attempt = today
        try:
            if config.get('trading_days_only', True) and not self.calendar_check(now.date()):
                self.service.add_log('INFO', f'{today} 非交易日，跳过自动更新。')
                return False
            self.service.start_data_update_task(force_refresh=True, sync_recommendations=config.get('sync_prediction', True))
            self.service.save_schedule_config({'last_auto_run': now.isoformat(timespec='seconds')})
            self.weekly_pending = bool(config.get('auto_retrain_model_weekly')) and now.weekday() == 4
            self.status['error'] = None
            return True
        except Exception as exc:
            self.status['error'] = str(exc)
            self.service.add_log('ERROR', f'自动调度未执行：{exc}')
            return False

    async def run(self):
        self.status['active'] = True
        try:
            while True:
                await asyncio.to_thread(self.tick)
                await asyncio.sleep(15)
        finally:
            self.status['active'] = False
