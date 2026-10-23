# -*- coding: utf-8 -*-
"""沪深300 成分股池与行业映射

为什么改用沪深300
----------------
此前的 40 只样本分摊到 6 个行业，平均每组 6.4 只，34.4% 的股票在自己的
行业组里是唯一一只，导致行业中性化退化为「减去自身」，把因子抹成 0。
沪深300 覆盖 300 只大市值标的、行业分布完整，是解决这个问题的直接方式，
也是 A 股量化研究的标准基准池。

数据来源
--------
成分股：中证指数官方 index_stock_cons_csindex(000300)
行业：  新浪行业分类 stock_sector_spot + stock_sector_detail（逐行业展开）

结果本地缓存到 data/cache/csi300_pool.csv，避免重复拉取。
"""

import os
import time

import pandas as pd

from config.config import CACHE_DIR, get_stock_board

POOL_CACHE = os.path.join(CACHE_DIR, 'csi300_pool.csv')
CACHE_MAX_AGE_DAYS = 30


def _load_cached_pool():
    if not os.path.exists(POOL_CACHE):
        return None
    try:
        df = pd.read_csv(POOL_CACHE, dtype={'code': str})
        df['code'] = df['code'].str.zfill(6)
        age = (time.time() - os.path.getmtime(POOL_CACHE)) / 86400
        if age > CACHE_MAX_AGE_DAYS:
            print(f"[CSI300] 缓存已过期 ({age:.0f} 天)，将重新拉取")
            return None
        return df
    except Exception:
        return None


def fetch_csi300_constituents(force: bool = False) -> pd.DataFrame:
    """获取沪深300 成分股名单。"""
    cached = None if force else _load_cached_pool()
    if cached is not None and 250 <= len(cached) <= 310:
        return cached

    import akshare as ak

    try:
        raw = ak.index_stock_cons_csindex(symbol='000300')
    except Exception as e:
        print(f"[CSI300] 成分股拉取失败: {e}")
        if cached is not None:
            return cached
        return None

    if raw is None or len(raw) == 0:
        return None

    # 中证接口列名为中文，做一次健壮映射
    col_map = {}
    for c in raw.columns:
        s = str(c)
        if '成分券代码' in s:
            col_map[c] = 'code'
        elif '成分券名称' in s:
            col_map[c] = 'name'
    df = raw.rename(columns=col_map)

    if 'code' not in df.columns:
        print(f"[CSI300] 成分股字段解析失败，实际列: {list(raw.columns)}")
        return None

    df['code'] = df['code'].astype(str).str.zfill(6)
    df['name'] = df.get('name', df['code']).astype(str)
    df = df[['code', 'name']].drop_duplicates(subset='code').reset_index(drop=True)
    if not 250 <= len(df) <= 310:
        print(f"[CSI300] 成分股数量异常：{len(df)} 只，拒绝写入研究池")
        return cached if cached is not None and 250 <= len(cached) <= 310 else None
    df['board'] = df['code'].apply(get_stock_board)
    return df


def fetch_industry_map(force: bool = False) -> dict:
    """构建 code -> 行业 映射（新浪行业分类）。

    东方财富行业接口在当前网络环境被代理拦截，新浪接口可用。
    """
    map_cache = os.path.join(CACHE_DIR, 'csi300_industry.csv')
    if not force and os.path.exists(map_cache):
        try:
            d = pd.read_csv(map_cache, dtype={'code': str})
            d['code'] = d['code'].str.zfill(6)
            age = (time.time() - os.path.getmtime(map_cache)) / 86400
            if age <= CACHE_MAX_AGE_DAYS and len(d) > 100:
                return dict(zip(d['code'], d['industry']))
        except Exception:
            pass

    import akshare as ak

    mapping = {}
    try:
        sectors = ak.stock_sector_spot(indicator='新浪行业')
    except Exception as e:
        print(f"[CSI300] 行业列表拉取失败: {e}")
        return mapping

    label_col = 'label' if 'label' in sectors.columns else sectors.columns[0]
    name_col = '板块' if '板块' in sectors.columns else sectors.columns[1]

    for _, row in sectors.iterrows():
        label = row[label_col]
        ind_name = str(row[name_col])
        try:
            detail = ak.stock_sector_detail(sector=label)
            if detail is None or len(detail) == 0:
                continue
            for c in detail['code'].astype(str).str.zfill(6):
                mapping[c] = ind_name
        except Exception:
            continue

    if mapping:
        pd.DataFrame({'code': list(mapping), 'industry': list(mapping.values())}).to_csv(
            map_cache, index=False, encoding='utf-8-sig')
        print(f"[CSI300] 行业映射构建完成: {len(mapping)} 只 / {len(set(mapping.values()))} 个行业")

    return mapping


def build_csi300_pool(force: bool = False) -> list:
    """返回沪深300 股票池：[{code, name, industry, board}, ...]

    行业缺失的标的归入「未分类」，不阻断流程，但会削弱该截面的行业中性化。
    """
    cons = fetch_csi300_constituents(force=force)
    if cons is None or len(cons) == 0:
        print("[CSI300] 无法获取最新成分股，尝试沿用本地沪深300快照")
        try:
            cached = pd.read_csv(POOL_CACHE, dtype={'code': str})
            cached['code'] = cached['code'].str.zfill(6)
            cached = cached.drop_duplicates('code').reset_index(drop=True)
            if 250 <= len(cached) <= 310:
                print(f"[CSI300] 使用本地快照 {len(cached)} 只，不扩大到其他股票池")
                return [{
                    'code': row['code'],
                    'name': row.get('name', row['code']),
                    'industry': row.get('industry') or '未分类',
                    'board': row.get('board') or get_stock_board(row['code']),
                } for _, row in cached.iterrows()]
        except Exception:
            pass
        print("[CSI300] 无有效本地快照，返回空股票池；请恢复网络后重试")
        return []

    industry_map = fetch_industry_map(force=force)

    pool = []
    missing_industry = 0
    for _, row in cons.iterrows():
        code = row['code']
        ind = industry_map.get(code)
        if not ind:
            missing_industry += 1
            ind = '未分类'
        pool.append({
            'code': code,
            'name': row['name'],
            'industry': ind,
            'board': row['board'],
        })

    pool_df = pd.DataFrame(pool)
    pool_df.to_csv(POOL_CACHE, index=False, encoding='utf-8-sig')

    matched = len(pool) - missing_industry
    print(f"[CSI300] 股票池就绪: {len(pool)} 只，行业已匹配 {matched} 只"
          f"（{matched / len(pool):.1%}），缺行业 {missing_industry} 只")

    return pool


if __name__ == '__main__':
    p = build_csi300_pool(force=True)
    from collections import Counter
    print('行业分布 Top15:', Counter(x['industry'] for x in p).most_common(15))
