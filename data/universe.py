# -*- coding: utf-8 -*-
"""按生效日期管理股票池；历史回测优先使用历史成分股文件。"""

import os

import pandas as pd

from config.config import DATA_DIR

MEMBERSHIP_HISTORY_PATH = os.path.join(DATA_DIR, 'csi300_membership_history.csv')
REQUIRED_HISTORY_COLUMNS = {
    'code', 'name', 'industry', 'board', 'start_date', 'end_date',
}


def load_membership_history(path: str = MEMBERSHIP_HISTORY_PATH) -> pd.DataFrame | None:
    """读取成分股历史。end_date 为空表示仍在指数内，起止日均包含。"""
    if not os.path.exists(path):
        return None
    history = pd.read_csv(path, dtype={'code': str})
    missing = REQUIRED_HISTORY_COLUMNS - set(history.columns)
    if missing:
        raise ValueError(f'成分股历史缺少字段: {sorted(missing)}')
    history['code'] = history['code'].str.zfill(6)
    history['start_date'] = pd.to_datetime(history['start_date'], errors='coerce')
    history['end_date'] = pd.to_datetime(history['end_date'], errors='coerce')
    if history['start_date'].isna().any():
        raise ValueError('成分股历史 start_date 存在无效日期')
    history = history.sort_values(['code', 'start_date']).reset_index(drop=True)
    for code, group in history.groupby('code'):
        rows = group.to_dict('records')
        for previous, current in zip(rows, rows[1:]):
            previous_end = previous['end_date']
            if pd.isna(previous_end) or current['start_date'] <= previous_end:
                raise ValueError(f'成分股历史存在重叠有效期: {code}')
    return history


def historical_codes(path: str = MEMBERSHIP_HISTORY_PATH) -> list[str] | None:
    history = load_membership_history(path)
    return sorted(history['code'].unique().tolist()) if history is not None else None


def apply_point_in_time_universe(panel: pd.DataFrame,
                                 path: str = MEMBERSHIP_HISTORY_PATH) -> tuple[pd.DataFrame, bool]:
    """按每行日期过滤非成分股，并附加当时有效的名称、行业和板块。"""
    history = load_membership_history(path)
    if history is None:
        return panel, False
    hist = history.rename(columns={
        'code': 'stock_code', 'name': '_pit_name',
        'industry': '_pit_industry', 'board': '_pit_board',
        'start_date': '_pit_start', 'end_date': '_pit_end',
    })
    merged = panel.copy()
    merged['date'] = pd.to_datetime(merged['date'])
    merged = merged.merge(hist, on='stock_code', how='inner')
    active = (merged['date'] >= merged['_pit_start']) & (
        merged['_pit_end'].isna() | (merged['date'] <= merged['_pit_end'])
    )
    merged = merged.loc[active].copy()
    for column, pit_column in (('industry', '_pit_industry'),
                               ('board', '_pit_board')):
        merged[column] = merged[pit_column].fillna(merged[column])
    merged['stock_name'] = merged['_pit_name']
    merged = merged.drop(columns=[c for c in merged.columns if c.startswith('_pit_')])
    return merged.reset_index(drop=True), True
