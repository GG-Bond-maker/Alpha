"""Stage and validate all Sina qfq OHLCV histories before publishing caches.

Usage: python scripts/refresh_factor_prices.py --as-of 2026-10-26
The staging directory remains local under ignored data/factors/ for audit.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import akshare as ak
import pandas as pd

from config.config import FACTOR_DIR, get_pool

REQUIRED = {'date', 'open', 'high', 'low', 'close', 'volume', 'amount'}


def fetch_one(code: str, as_of: date, stage: Path) -> dict:
    symbol = ('sh' if code.startswith(('6', '9')) else 'sz') + code
    end = (as_of + timedelta(days=1)).strftime('%Y%m%d')
    problem = None
    for attempt in range(3):
        try:
            frame = ak.stock_zh_a_daily(symbol=symbol, start_date='20150101',
                                        end_date=end, adjust='qfq')
            if frame is None or frame.empty:
                raise ValueError('provider returned no rows')
            if not REQUIRED.issubset(frame.columns):
                raise ValueError(f'missing columns: {sorted(REQUIRED - set(frame.columns))}')
            frame = frame.copy()
            frame['date'] = pd.to_datetime(frame['date'], errors='coerce')
            for col in REQUIRED - {'date'}:
                frame[col] = pd.to_numeric(frame[col], errors='coerce')
            frame = frame.loc[frame.date <= pd.Timestamp(as_of)].sort_values('date')
            if len(frame) < 120 or frame.date.isna().any() or frame.date.duplicated().any():
                raise ValueError('insufficient, invalid or duplicate trading dates')
            if frame[list(REQUIRED - {'date'})].isna().any().any():
                raise ValueError('missing required OHLCV/amount values')
            last = frame.iloc[-1]
            if not (last.open > 0 and last.high >= max(last.open, last.close)
                    and last.low <= min(last.open, last.close) and last.volume > 0):
                raise ValueError('latest bar has invalid price or volume')
            old_path = Path(FACTOR_DIR) / f'price_{code}.csv'
            if not old_path.is_file():
                raise ValueError('prior cache is missing')
            old = pd.read_csv(old_path, usecols=['date', 'close'])
            old.date = pd.to_datetime(old.date)
            if frame.date.min() > old.date.min() or frame.date.max() < old.date.max():
                raise ValueError('new history shrinks the cached date range')
            overlap = frame[['date', 'close']].merge(old, on='date', suffixes=('_new', '_old'))
            if len(overlap) < min(120, len(old)):
                raise ValueError('too little overlap with prior cache')
            frame['pct_chg'] = frame.close.pct_change() * 100.0
            path = stage / f'price_{code}.csv'
            temporary = path.with_suffix('.tmp')
            frame.to_csv(temporary, index=False, encoding='utf-8-sig')
            os.replace(temporary, path)
            return {'code': code, 'rows': len(frame), 'first': str(frame.date.min().date()),
                    'last': str(frame.date.max().date()), 'overlap_rows': len(overlap),
                    'revised_closes': int(((overlap.close_new - overlap.close_old).abs() > 1e-6).sum()),
                    'invalid_historical_prices': int((frame[['open', 'high', 'low', 'close']] <= 0).any(axis=1).sum()),
                    'source': 'akshare.stock_zh_a_daily:sina:qfq'}
        except Exception as exc:
            problem = str(exc)
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'{code}: {problem}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    if args.as_of > date.today() or not 1 <= args.workers <= 6:
        parser.error('as-of must not be in the future and workers must be in [1,6]')
    codes = [row['code'] for row in get_pool()]
    if len(codes) != 300 or len(set(codes)) != 300:
        raise RuntimeError('Expected exactly 300 unique pool codes')
    stage = Path(FACTOR_DIR) / f'.refresh-{args.as_of:%Y%m%d}-{uuid4().hex[:8]}'
    stage.mkdir(parents=True)
    print(f'[PriceRefresh] as_of={args.as_of} stocks={len(codes)} stage={stage}', flush=True)
    records, failures = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, code, args.as_of, stage): code for code in codes}
        for future in as_completed(futures):
            try:
                records.append(future.result())
            except Exception as exc:
                failures.append(str(exc))
            if (len(records) + len(failures)) % 25 == 0:
                print(f'[PriceRefresh] completed={len(records)+len(failures)}/300 ok={len(records)} failed={len(failures)}', flush=True)
    latest = max((r['last'] for r in records), default=None)
    on_latest = sum(r['last'] == latest for r in records)
    summary = {'as_of': str(args.as_of), 'latest_trade_date': latest, 'on_latest': on_latest,
               'stocks': len(codes), 'successful': len(records), 'failures': failures,
               'source': 'Sina qfq full-history snapshot via AKShare',
               'completed_at': datetime.now().isoformat(timespec='seconds'),
               'records': sorted(records, key=lambda row: row['code'])}
    (stage / 'refresh_report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    if failures or len(records) != len(codes) or latest != str(args.as_of) or on_latest < 270:
        raise RuntimeError(f'Price refresh incomplete: {len(failures)} failures; {on_latest}/300 on {latest}. Stage: {stage}')
    for row in summary['records']:
        code = row['code']
        os.replace(stage / f'price_{code}.csv', Path(FACTOR_DIR) / f'price_{code}.csv')
    destination = ROOT / 'docs' / 'review' / str(args.as_of) / 'price-refresh.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[PriceRefresh] published={len(records)} latest={latest} coverage={on_latest}/300 report={destination}', flush=True)


if __name__ == '__main__':
    main()
