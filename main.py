# -*- coding: utf-8 -*-
"""使用已训练 LightGBM 模型生成当前截面股票推荐。"""

import argparse
import os
import sys
from datetime import datetime

import joblib
import pandas as pd

from config.config import PROCESSED_DIR, SAVED_MODELS_DIR, get_pool
from ml_pipeline.dataset import build_inference_panel
from ml_pipeline.run_training import generate_recommendations

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_arguments():
    parser = argparse.ArgumentParser(description="生成 LightGBM 截面 Top-K 股票推荐")
    parser.add_argument("--limit", type=int, default=None,
                        help="限制候选数量，仅用于快速演示")
    parser.add_argument("--board", type=str, default=None,
                        choices=["主板", "创业板", "科创板", "北交所"],
                        help="只导出指定板块；分数仍按完整候选池截面计算")
    parser.add_argument("--k", type=int, default=10, help="终端展示 Top-K 数量")
    return parser.parse_args()


def main():
    args = parse_arguments()
    bundle_path = os.path.join(SAVED_MODELS_DIR, "lgbm_market_classifier.pkl")
    if not os.path.exists(bundle_path):
        print("未找到已训练模型，请先运行 python -m ml_pipeline.run_training")
        return

    bundle = joblib.load(bundle_path)
    model = bundle.get("model") if isinstance(bundle, dict) else bundle
    if model is None:
        print("模型文件中没有可用的 LightGBM 分类器，请重新训练")
        return

    pool = get_pool()
    codes = [stock["code"] for stock in pool]
    if args.limit:
        codes = codes[:args.limit]

    print(f"构建 {len(codes)} 只候选股票的最新推理截面...")
    panel = build_inference_panel(codes, include_fundamental=True)
    all_recommendations = generate_recommendations(model, codes, panel)
    if all_recommendations.empty:
        print("没有生成有效推荐，请检查行情、因子和模型输入是否齐全")
        return

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    today = datetime.today().strftime("%Y%m%d")
    if args.limit:
        csv_path = os.path.join(PROCESSED_DIR, f"recommendation_preview_{today}.csv")
    else:
        csv_path = os.path.join(PROCESSED_DIR, "realtime_recommendations.csv")
        all_recommendations.to_csv(csv_path, index=False, encoding="utf-8-sig")

    recommendations = all_recommendations.copy()
    if args.board:
        recommendations = recommendations[recommendations["板块"] == args.board]
    if recommendations.empty:
        print(f"当前候选池没有可展示的 {args.board} 标的")
        return

    xlsx_path = os.path.join(PROCESSED_DIR, f"stock_recommend_{today}.xlsx")
    recommendations.to_excel(xlsx_path, index=False, engine="openpyxl")

    display_col = "跑赢候选池均值概率"
    display = recommendations[["推荐排名", "代码", "名称", "推荐评级", display_col,
                               "最新收盘价", "当日涨幅(%)"]].head(args.k)
    print(display.to_string(index=False))
    if args.limit:
        recommendations.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"推荐表：{csv_path}")
    print(f"Excel：{xlsx_path}")


if __name__ == "__main__":
    main()
