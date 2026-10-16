# -*- coding: utf-8 -*-
"""A 股智能选股与推荐系统 v2.0 - 主程序入口 (CLI)
参考 AShare-AI-Stock-Picker 打造，全面支持 Optuna 超参数优化、A/B/C 评级、涨停过滤及 Excel 导出
"""

import os
import sys
import glob
import argparse
from datetime import datetime
import pandas as pd
import numpy as np
from tqdm import tqdm

# 兼容 Windows 控制台 UTF-8 输出
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
        sys.stderr.reconfigure(encoding='utf-8', errors='ignore')
    except Exception:
        pass

from config.config import MODEL_DIR, FEATURE_COLS, CORE_STOCK_POOL, SAVED_MODELS_DIR, PROCESSED_DIR, get_stock_board
from data.data_fetcher import get_stock_data, get_stock_list
from models.model_trainer import (
    train_and_save_model,
    train_market_joint_model,
    predict_stock_signal
)


def print_banner():
    """打印系统 ASCII 艺术启动横幅"""
    print(r"""
 █████╗       ███████╗██╗  ██╗ █████╗ ██████╗ ███████╗
██╔══██╗      ██╔════╝██║  ██║██╔══██╗██╔══██╗██╔════╝
███████║█████╗███████╗███████║███████║██████╔╝█████╗  
██╔══██║╚════╝╚════██║██╔══██║██╔══██║██╔══██╗██╔══╝  
██║  ██║      ███████║██║  ██║██║  ██║██║  ██║███████╗
╚═╝  ╚═╝      ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
      🚀 启动 A 股智能选股与可解释推荐系统 v2.0
   [LightGBM + Optuna 优化 + TreeSHAP 归因 + Excel 导出]
    """)


def parse_arguments():
    """解析命令行参数，支持灵活配置与自动化运行"""
    parser = argparse.ArgumentParser(description="A-shares Intelligent Stock Picker")
    parser.add_argument("--no-cache", action="store_true", help="强制重新训练模型，忽略缓存")
    parser.add_argument("--optuna", action="store_true", help="开启 Optuna 贝叶斯超参数优化")
    parser.add_argument("--limit", type=int, default=None, help="限制处理的股票数量（便于快速测试）")
    parser.add_argument("--filter-st", type=bool, default=True, help="过滤 ST 及退市股票")
    parser.add_argument("--main-board-only", action="store_true", default=False, help="仅限定为主板股票")
    parser.add_argument("--board", type=str, default=None, help="指定分析板块 (主板/创业板/科创板/北交所/全部)")
    return parser.parse_args()


def main():
    print_banner()
    args = parse_arguments()

    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(SAVED_MODELS_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # 1. 缓存处理检查
    use_cache = not args.no_cache
    cached_models = glob.glob(os.path.join(MODEL_DIR, '*_model.txt'))
    market_model_path = os.path.join(SAVED_MODELS_DIR, "lgbm_market_classifier.pkl")

    if use_cache:
        if cached_models or os.path.exists(market_model_path):
            latest_time = 0
            if cached_models:
                latest_time = max(os.path.getmtime(f) for f in cached_models)
            if os.path.exists(market_model_path):
                latest_time = max(latest_time, os.path.getmtime(market_model_path))
            print(f"📦 已发现本地模型缓存，最新更新时间: {datetime.fromtimestamp(latest_time).strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("⚠️ 未找到历史模型缓存，将启动模型训练...")
            use_cache = False

    # 2. 预备市场通用基准模型（用于快速赋能全市场主板股票预测）
    print("\n🔍 初始化推荐预测引擎与主板市场模型...")
    market_model = None
    try:
        market_model, _ = train_market_joint_model(force_retrain=not use_cache, n_trials=15 if args.optuna else 1)
    except Exception as e:
        print(f"⚠️ 市场通用模型加载/训练提示: {e}")

    # 3. 获取目标股票列表 (覆盖 A 股全板块：主板、创业板、科创板、北交所)
    board_hint = f"【{args.board}】" if args.board else "全板块"
    print(f"\n📊 正在拉取目标 A 股{board_hint}股票池行情清单...")
    stock_list = get_stock_list(
        filter_st=args.filter_st,
        main_board_only=args.main_board_only,
        board=args.board,
        limit=args.limit
    )

    if stock_list is None or stock_list.empty:
        print("❌ 未获取到股票列表，程序退出")
        return

    print(f"✅ 成功筛选出 {len(stock_list)} 只待分析股票标的")

    # 4. 循环预测与评级打分
    results = []
    pbar = tqdm(stock_list.iterrows(), total=len(stock_list), desc="⚡ 正在进行 AI 选股预测", ncols=100)

    for _, row in pbar:
        code = str(row['code']).zfill(6)
        name = str(row['name'])
        b_name = str(row.get('board', get_stock_board(code)))
        pbar.set_postfix_str(f"标的: {code} {name[:4]}")

        try:
            # 优先使用单股专属模型，如无则使用市场通用大模型
            booster = None
            if os.path.exists(os.path.join(MODEL_DIR, f"{code}_model.txt")):
                booster = train_and_save_model(code, force_retrain=False)
            elif market_model is not None:
                booster = market_model

            # 执行预测
            sig = predict_stock_signal(code, booster_or_model=booster)
            if not sig:
                continue

            results.append({
                '代码': sig['code'],
                '名称': name,
                '板块': b_name,
                '是否涨停': sig['is_limit_up'],
                '预测看涨概率': sig['probability'],
                '推荐评级': sig['rating'],
                '最新收盘价': sig['close'],
                '当日涨幅(%)': sig['pct_chg'],
                '更新日期': sig['update_date'],
                'RSI14': sig['features'].get('RSI14', 0.0),
                'MACD': sig['features'].get('MACD', 0.0),
                'EMA20比率': sig['features'].get('EMA20_ratio', 1.0)
            })

        except Exception as e:
            continue

    # 5. 输出推荐结果与导出 Excel
    if results:
        df_res = pd.DataFrame(results)
        # 按看涨概率降序排序
        df_res = df_res.sort_values('预测看涨概率', ascending=False).reset_index(drop=True)
        df_res.index = df_res.index + 1
        df_res.index.name = "推荐排名"

        # 导出 Excel 文件
        today_tag = datetime.today().strftime("%Y%m%d")
        excel_filename = f"stock_recommend_{today_tag}.xlsx"
        df_res.reset_index().to_excel(excel_filename, index=False, engine='openpyxl')

        # 同时也保存一份到 data/processed/ 作为 Web 后端数据源
        web_cache_file = os.path.join(PROCESSED_DIR, "realtime_recommendations.csv")
        df_res.reset_index().to_csv(web_cache_file, index=False, encoding='utf-8-sig')

        print(f"\n🎉 选股分析完成！共处理 {len(results)} 只股票标的")
        print(f"📁 推荐结果已成功导出至 Excel: 【{excel_filename}】")
        print("\n🏆 Top 10 重点推荐股票清单：")
        print("=" * 80)
        show_cols = ['代码', '名称', '板块', '推荐评级', '预测看涨概率', '是否涨停', '最新收盘价', '当日涨幅(%)', 'RSI14']
        print(df_res[show_cols].head(10).to_string())
        print("=" * 80)
    else:
        print("\n⚠️ 未生成有效预测结果，请检查数据网络连接")


if __name__ == '__main__':
    main()
