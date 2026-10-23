# -*- coding: utf-8 -*-
"""全局配置中心（单一事实源）

本模块是所有特征、标签、评级与路径定义的唯一来源。
修改特征集或标签口径只需改动此处，模型训练、归因、评测与回测会同步生效。

设计约定
--------
1. FEATURE_COLS 为模型实际使用的特征集合，跨模块必须引用同一常量。
2. 标签统一采用「截面超额收益」口径，而非绝对涨跌，避免模型退化为市场 beta。
3. 股票池按板块分层定义，主板/全板块的口径在此显式声明，不再分散到各模块。
"""

import os

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')
MODEL_DIR = os.path.join(DATA_DIR, 'stock_models')
PROCESSED_DIR = os.path.join(DATA_DIR, 'processed')
FACTOR_DIR = os.path.join(DATA_DIR, 'factors')
SAVED_MODELS_DIR = os.path.join(BASE_DIR, 'saved_models')

for _d in (DATA_DIR, CACHE_DIR, MODEL_DIR, PROCESSED_DIR, FACTOR_DIR, SAVED_MODELS_DIR):
    os.makedirs(_d, exist_ok=True)

# ---------------------------------------------------------------------------
# 特征定义
# ---------------------------------------------------------------------------
# 归一化后的量价与技术指标特征（10 维）。
# 注意：close / volume / OBV 的原始量级跨股票不可比，模型直接使用会退化为
# 「价格水平识别器」。因此这里一律使用无量纲化后的表达。
FEATURE_COLS = [
    'EMA20_ratio',   # 收盘价 / 20 日 EMA，衡量价格相对均线位置
    'RSI14',         # 14 日相对强弱指标
    'MACD_norm',     # MACD 除以收盘价，消除价格量级
    'OBV_zscore',    # OBV 的 60 日滚动 z-score，消除累计量级
    'CCI',           # 顺势指标
    'ATR_ratio',     # ATR / 收盘价，波动率相对水平
    'ADX',           # 平均趋向指标
    'pct_chg',       # 当日涨跌幅
    'vol_ratio',     # 成交量 / 20 日均量，量能放大倍数
    'ma_gap',        # (MA5 - MA20) / MA20，短期均线偏离度
]

# 候选因子池：所有可能入模的因子，供诊断模块逐一检验。
CANDIDATE_FACTORS = FEATURE_COLS + [
    'momentum_20d', 'momentum_60d', 'volatility_20d', 'turnover_proxy',
    'pe_ttm', 'pb', 'roe', 'roa', 'gross_margin', 'net_margin',
    'debt_ratio', 'revenue_growth', 'profit_growth',
]

# 入选因子的默认值（无诊断产物时的兜底）。
# 正常运行时会由 ml_pipeline/run_training.py 依据诊断结果覆盖此列表，
# 并写入 saved_models/selected_factors.json，保证「诊断选什么、模型用什么」。
DEFAULT_SELECTED_FACTORS = [
    'debt_ratio', 'roe', 'net_margin', 'pb', 'gross_margin', 'RSI14', 'momentum_20d',
]

# 诊断产物路径
SELECTED_FACTORS_PATH = os.path.join(SAVED_MODELS_DIR, 'selected_factors.json')


def _load_selected_factors() -> list:
    """优先读取诊断产出的因子列表，缺失时用默认值。"""
    try:
        import json
        if os.path.exists(SELECTED_FACTORS_PATH):
            with open(SELECTED_FACTORS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            factors = data.get('factors') or []
            if factors:
                return factors
    except Exception:
        pass
    return list(DEFAULT_SELECTED_FACTORS)


SELECTED_FACTORS = _load_selected_factors()


def get_model_features() -> list:
    """模型实际输入的列名：入选因子经行业中性化与标准化后的版本。

    用函数而非常量，确保 run_training 写入新的 selected_factors.json 后，
    同一进程内后续步骤（训练、评测、归因）能读到一致的口径。
    """
    return [f + '_neu' for f in _load_selected_factors()]


MODEL_FEATURES = get_model_features()

FEATURE_NAMES_CN = {
    'EMA20_ratio': '价格/20日均线比率',
    'RSI14': '14日相对强弱指标(RSI)',
    'MACD_norm': '归一化异同移动平均线(MACD)',
    'OBV_zscore': '能量潮标准分(OBV-Z)',
    'CCI': '顺势指标(CCI)',
    'ATR_ratio': '相对真实波幅(ATR/价格)',
    'ADX': '平均趋向指标(ADX)',
    'pct_chg': '当日涨跌幅(%)',
    'vol_ratio': '成交量放大倍数',
    'ma_gap': '短期均线偏离度',
    'pe_ttm': '市盈率(TTM)',
    'pb': '市净率(PB)',
    'roe': '净资产收益率(ROE)',
    'roa': '总资产收益率(ROA)',
    'gross_margin': '销售毛利率',
    'net_margin': '销售净利率',
    'debt_ratio': '资产负债率',
    'revenue_growth': '营业收入增长率',
    'profit_growth': '净利润增长率',
    'momentum_20d': '20日动量',
    'momentum_60d': '60日动量',
    'volatility_20d': '20日波动率',
    'turnover_proxy': '换手活跃度',
}

# ---------------------------------------------------------------------------
# 标签定义
# ---------------------------------------------------------------------------
# 预测周期（交易日）
TARGET_DAYS = 5

# 标签口径：截面超额收益 = 个股 N 日收益 - 同一截面全样本 N 日收益均值
# 使用绝对涨跌会让模型在牛市中全部预测为上涨，学到的只是市场 beta。
LABEL_MODE = 'excess'          # 'excess' | 'absolute'
LABEL_COL = 'excess_ret_5d'    # 超额收益列名
TARGET_COL = 'target_up'       # 二分类标签列名

# 截面评级比例：A 为分数前 10%，B 为随后 20%，其余为 C。
# 概率未校准，因此评级按当日候选池内的相对名次生成。
RATING_TOP_A_RATIO = 0.10
RATING_TOP_B_RATIO = 0.30

# ---------------------------------------------------------------------------
# 股票池与板块
# ---------------------------------------------------------------------------
STOCK_BOARDS = ["全部", "主板", "创业板", "科创板", "北交所"]

_MAIN_BOARD_PREFIXES = ('600', '601', '603', '605', '000', '001', '002', '003')
_CHINEXT_PREFIXES = ('300', '301')
_STAR_PREFIXES = ('688', '689')
_BSE_PREFIXES = ('8', '4', '92')


def get_stock_board(code: str) -> str:
    """按代码前缀判定 A 股所属板块。"""
    clean = str(code).zfill(6)
    if clean.startswith(_MAIN_BOARD_PREFIXES):
        return "主板"
    if clean.startswith(_CHINEXT_PREFIXES):
        return "创业板"
    if clean.startswith(_STAR_PREFIXES):
        return "科创板"
    if clean.startswith(_BSE_PREFIXES):
        return "北交所"
    return "主板"


def is_valid_a_stock(code: str) -> bool:
    """是否为可识别的 A 股代码。"""
    clean = str(code).zfill(6)
    return clean.startswith(
        _MAIN_BOARD_PREFIXES + _CHINEXT_PREFIXES + _STAR_PREFIXES + _BSE_PREFIXES
    )


def is_main_board_stock(code: str) -> bool:
    """是否属于沪深主板。"""
    return str(code).zfill(6).startswith(_MAIN_BOARD_PREFIXES)


# ---------------------------------------------------------------------------
# 股票池
# ---------------------------------------------------------------------------
# 建模范畴锁定为沪深300 成分股。
#
# 为什么不用 500 只全板块池：早前 40 只样本分摊到 6 个行业，平均每组 6.4 只，
# 34.4% 的股票在自己的行业组里是唯一一只，行业中性化退化为「减去自身」，
# 把因子抹成 0。沪深300 覆盖 300 只大市值标的、行业分布完整，是直接解法，
# 也是 A 股量化研究的标准基准池。
POOL_SCOPE = "csi300"

# 沪深300 池由 data/csi300_pool.py 构建并缓存到 data/cache/csi300_pool.csv。
# 池缺失或损坏时返回空列表，避免静默扩展到其他股票。
_CSI300_CACHE = None


def _load_csi300_pool() -> list:
    """加载沪深300 股票池；缓存缺失或不完整时拒绝扩大研究范围。"""
    global _CSI300_CACHE
    if _CSI300_CACHE is not None:
        return _CSI300_CACHE

    import pandas as pd
    path = os.path.join(CACHE_DIR, 'csi300_pool.csv')
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, dtype={'code': str})
            df['code'] = df['code'].str.zfill(6)
            df = df.drop_duplicates('code').reset_index(drop=True)
            if not 250 <= len(df) <= 310:
                raise ValueError(f'沪深300 成分股缓存数量异常：{len(df)} 只')
            _CSI300_CACHE = [
                {
                    'code': r['code'],
                    'name': r['name'],
                    'industry': r.get('industry') or '未分类',
                    'board': r.get('board') or get_stock_board(r['code']),
                }
                for _, r in df.iterrows()
            ]
            return _CSI300_CACHE
        except Exception:
            pass

    print('[Config] 未找到有效的沪深300 成分股缓存，当前研究池为空。'
          '请运行 python -m data.csi300_pool 重新构建')
    return []


def get_pool(scope: str = None) -> list:
    """返回建模股票池。scope 缺省为 POOL_SCOPE（沪深300）。"""
    scope = scope or POOL_SCOPE
    if scope in ("csi300", "全部"):
        return _load_csi300_pool()
    pool = _load_csi300_pool()
    return [s for s in pool if s.get('board', get_stock_board(s['code'])) == scope]


# 兼容仍导入 CORE_STOCK_POOL 的旧模块；此变量也严格指向当前 CSI300 缓存。
CORE_STOCK_POOL = _load_csi300_pool()
