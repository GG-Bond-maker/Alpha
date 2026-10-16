# -*- coding: utf-8 -*-
"""全局系统配置参数模块
融合 AShare-AI-Stock-Picker 技术指标体系与 Alpha 全栈架构配置
严格限定股票池与扫描范围为 A 股主板（沪市主板 600/601/603/605，深市主板 000/001/002/003）
"""

import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 核心技术指标特征列配置（与 AShare-AI-Stock-Picker 保持一致并扩充）
FEATURE_COLS = [
    'close', 'volume', 'pct_chg',
    'EMA20_ratio', 'RSI14', 'MACD',
    'OBV', 'CCI', 'ATR', 'ADX'
]

# 核心特征中英文映射对照表（用于前端可视化大屏与 TreeSHAP 归因解释）
FEATURE_NAMES_CN = {
    'close': '收盘价',
    'volume': '成交量',
    'pct_chg': '当日涨跌幅(%)',
    'EMA20_ratio': '价格/20日均线比率',
    'RSI14': '14日相对强弱指标(RSI)',
    'MACD': '异同移动平均线(MACD)',
    'OBV': '能量潮指标(OBV)',
    'CCI': '顺势指标(CCI)',
    'ATR': '真实波幅(ATR)',
    'ADX': '平均趋向指标(ADX)'
}

# 预测目标参数：未来 N 日收益率
TARGET_DAYS = 5

# 推荐评级划分阈值
RATING_BINS = [0.0, 0.60, 0.75, 1.0]
RATING_LABELS = ['C', 'B', 'A']

# 数据存储与缓存路径
DATA_DIR = os.path.join(BASE_DIR, 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')
MODEL_DIR = os.path.join(DATA_DIR, 'stock_models')
PROCESSED_DIR = os.path.join(DATA_DIR, 'processed')
SAVED_MODELS_DIR = os.path.join(BASE_DIR, 'saved_models')

# 确保核心目录已创建
for d in [DATA_DIR, CACHE_DIR, MODEL_DIR, PROCESSED_DIR, SAVED_MODELS_DIR]:
    os.makedirs(d, exist_ok=True)


def get_stock_board(code: str) -> str:
    """
    判断 A 股股票所属板块：
    - 主板：沪市主板 (600, 601, 603, 605) 及 深市主板 (000, 001, 002, 003)
    - 创业板：深市创业板 (300, 301)
    - 科创板：沪市科创板 (688, 689)
    - 北交所：北京证券交易所 (82, 83, 87, 88, 43, 92)
    """
    clean = str(code).zfill(6)
    if clean.startswith(('600', '601', '603', '605', '000', '001', '002', '003')):
        return "主板"
    elif clean.startswith(('300', '301')):
        return "创业板"
    elif clean.startswith(('688', '689')):
        return "科创板"
    elif clean.startswith(('8', '4', '92')):
        return "北交所"
    return "主板"


def is_valid_a_stock(code: str) -> bool:
    """判断是否为中国 A 股全市场有效股票代码（覆盖全市场全部板块）"""
    clean = str(code).zfill(6)
    return clean.startswith((
        '600', '601', '603', '605', '000', '001', '002', '003',
        '300', '301',
        '688', '689',
        '8', '4', '92'
    ))


def is_main_board_stock(code: str) -> bool:
    """
    判断股票是否属于中国 A 股主板标的
    """
    clean = str(code).zfill(6)
    return clean.startswith(('600', '601', '603', '605', '000', '001', '002', '003'))


# A 股全板块板块分类定义表
STOCK_BOARDS = ["全部", "主板", "创业板", "科创板", "北交所"]

# 代表性核心资产股票池（全面覆盖 A 股全板块：主板、创业板、科创板、北交所，共 500 支）
from config.stock_pool import CORE_STOCK_POOL_500 as CORE_STOCK_POOL


