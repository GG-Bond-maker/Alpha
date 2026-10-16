"""
Stock Panel Data Generator & Loader
Simulates or loads multi-period cross-sectional panel data for Chinese A-share stocks.
Covers Valuation, Profitability, Growth, Quality, Momentum, and Sentiment features.
"""

import os
import json
import numpy as np
import pandas as pd

from config.config import CORE_STOCK_POOL, get_stock_board

def get_market_suffix(code: str) -> str:
    clean = str(code).zfill(6)
    if clean.startswith(('600', '601', '603', '605', '688', '689')):
        return "SH"
    elif clean.startswith(('000', '001', '002', '003', '300', '301')):
        return "SZ"
    elif clean.startswith(('8', '4', '92')):
        return "BJ"
    return "SH"


FEATURE_COLUMNS = [
    "pe_ratio",            # 市盈率 (TTM)
    "pb_ratio",            # 市净率 (PB)
    "roe",                 # 净资产收益率 (%)
    "gross_margin",        # 销售毛利率 (%)
    "net_profit_growth",   # 净利润同比增长率 (%)
    "revenue_growth",      # 营业收入同比增长率 (%)
    "debt_to_asset",       # 资产负债率 (%)
    "momentum_20d",        # 近20日价格动量 (%)
    "momentum_60d",        # 近60日价格动量 (%)
    "volatility_20d",      # 近20日年化波动率 (%)
    "turnover_rate",       # 近20日平均换手率 (%)
    "net_inflow_ratio",    # 主力资金净流入占比 (%)
]

FEATURE_NAMES_CN = {
    "pe_ratio": "市盈率(PE)",
    "pb_ratio": "市净率(PB)",
    "roe": "净资产收益率(ROE)",
    "gross_margin": "销售毛利率",
    "net_profit_growth": "净利润增长率",
    "revenue_growth": "营业收入增长率",
    "debt_to_asset": "资产负债率",
    "momentum_20d": "近20日价格动量",
    "momentum_60d": "近60日价格动量",
    "volatility_20d": "近20日价格波动率",
    "turnover_rate": "换手率水平",
    "net_inflow_ratio": "主力资金净流入率",
}


def generate_simulated_dataset(
    start_date="2023-01-01",
    end_date="2024-12-31",
    freq="1MS", # 每月1日作为一个推荐决策截面
    seed=42
) -> pd.DataFrame:
    """
    生成高度真实的A股跨期截面多因子面板数据。
    包含内在经济学逻辑：如ROE与盈利增长对未来收益有正向驱动，高估值有回撤压力，资金流入带来短期动量等。
    """
    np.random.seed(seed)
    date_range = pd.date_range(start=start_date, end=end_date, freq=freq).strftime("%Y-%m-%d").tolist()
    
    rows = []
    
    # 为每只股票赋予基础风格底色（如茅台高ROE低负债，宁德高成长高波动，银行低PE低波动）
    base_profiles = {}
    for item in CORE_STOCK_POOL:
        ind = item["industry"]
        if ind == "食品饮料":
            base_profiles[item["code"]] = {"roe": 22.0, "pe": 28.0, "pb": 6.5, "margin": 60.0, "vol": 20.0, "growth": 15.0}
        elif ind in ["电力设备", "电子", "计算机"]:
            base_profiles[item["code"]] = {"roe": 18.0, "pe": 40.0, "pb": 4.5, "margin": 32.0, "vol": 38.0, "growth": 35.0}
        elif ind in ["银行", "公用事业"]:
            base_profiles[item["code"]] = {"roe": 11.0, "pe": 6.0, "pb": 0.6, "margin": 45.0, "vol": 14.0, "growth": 5.0}
        elif ind in ["医药生物"]:
            base_profiles[item["code"]] = {"roe": 19.0, "pe": 35.0, "pb": 5.0, "margin": 55.0, "vol": 28.0, "growth": 20.0}
        else:
            base_profiles[item["code"]] = {"roe": 14.0, "pe": 18.0, "pb": 2.2, "margin": 25.0, "vol": 26.0, "growth": 12.0}

    for dt in date_range:
        # 模拟全市场宏观周期冲击
        market_sentiment = np.random.normal(0, 1.0)
        
        for stock in CORE_STOCK_POOL:
            clean_code = str(stock["code"]).zfill(6)
            full_code = f"{clean_code}.{get_market_suffix(clean_code)}"
            name = stock["name"]
            ind = stock.get("industry", "全行业核心")
            b_val = stock.get("board", get_stock_board(clean_code))
            prof = base_profiles.get(stock["code"], {"roe": 14.0, "pe": 18.0, "pb": 2.2, "margin": 25.0, "vol": 26.0, "growth": 12.0})
            
            # 各特征按基准+随机扰动
            roe = max(1.0, prof["roe"] + np.random.normal(0, 3.5))
            pe_ratio = max(4.0, prof["pe"] * np.exp(np.random.normal(0, 0.2)))
            pb_ratio = max(0.4, prof["pb"] * np.exp(np.random.normal(0, 0.15)))
            gross_margin = max(5.0, prof["margin"] + np.random.normal(0, 4.0))
            net_profit_growth = prof["growth"] + np.random.normal(0, 15.0)
            revenue_growth = prof["growth"] * 0.8 + np.random.normal(0, 10.0)
            debt_to_asset = min(90.0, max(10.0, (80.0 if ind == "银行" else 42.0) + np.random.normal(0, 5.0)))
            
            momentum_20d = np.random.normal(1.0, 7.0) + market_sentiment * 3.0
            momentum_60d = momentum_20d * 1.5 + np.random.normal(0, 10.0)
            volatility_20d = max(10.0, prof["vol"] + np.random.normal(0, 5.0))
            turnover_rate = max(0.2, np.random.exponential(scale=2.5))
            net_inflow_ratio = np.random.normal(0, 4.0)
            
            # 内在真实收益率生成机制（潜变量）：由高ROE、高利润增长、适度动量、合理估值和资金流入驱动
            latent_quality_score = (
                0.35 * (roe - 15.0) / 8.0 +
                0.30 * (net_profit_growth - 15.0) / 20.0 +
                0.20 * (net_inflow_ratio) / 4.0 +
                0.15 * (momentum_20d) / 10.0 -
                0.20 * (pe_ratio - 30.0) / 25.0 -
                0.10 * (volatility_20d - 25.0) / 15.0
            )
            
            noise = np.random.normal(0, 0.6)
            forward_20d_return = latent_quality_score * 4.5 + noise * 3.0
            
            rows.append({
                "date": dt,
                "stock_code": full_code,
                "code": clean_code,
                "stock_name": name,
                "industry": ind,
                "board": b_val,
                "pe_ratio": round(pe_ratio, 2),
                "pb_ratio": round(pb_ratio, 2),
                "roe": round(roe, 2),
                "gross_margin": round(gross_margin, 2),
                "net_profit_growth": round(net_profit_growth, 2),
                "revenue_growth": round(revenue_growth, 2),
                "debt_to_asset": round(debt_to_asset, 2),
                "momentum_20d": round(momentum_20d, 2),
                "momentum_60d": round(momentum_60d, 2),
                "volatility_20d": round(volatility_20d, 2),
                "turnover_rate": round(turnover_rate, 2),
                "net_inflow_ratio": round(net_inflow_ratio, 2),
                "forward_20d_return": round(forward_20d_return, 4)
            })
            
    df = pd.DataFrame(rows)
    return df


if __name__ == "__main__":
    df = generate_simulated_dataset()
    os.makedirs("data/processed", exist_ok=True)
    df.to_csv("data/processed/stock_panel_dataset.csv", index=False, encoding="utf-8-sig")
    print(f"Generated panel dataset successfully: shape={df.shape}, dates={df['date'].nunique()}")
