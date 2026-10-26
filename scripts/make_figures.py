# -*- coding: utf-8 -*-
"""用 Pillow 绘制论文用图表（运行环境无 matplotlib）

输出到 docs/figures/，供 Word 文档嵌入。
"""
import json
import os
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, BASE)
from ml_pipeline.artifacts import artifact_dir
SM = artifact_dir()
OUT = os.path.join(BASE, "docs", "figures")
os.makedirs(OUT, exist_ok=True)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]

W, H = 1200, 640
BG = (255, 255, 255)
AXIS = (203, 213, 225)
TEXT = (51, 65, 85)
TEXT_L = (100, 116, 139)
BLUE = (37, 99, 235)
GREEN = (16, 185, 129)
RED = (239, 68, 68)
GRAY = (148, 163, 184)
GOLD = (245, 158, 11)


def font(size, bold=False):
    for p in (FONT_CANDIDATES[1] if bold else FONT_CANDIDATES[0], *FONT_CANDIDATES):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def load(name):
    p = os.path.join(SM, name)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def new_canvas(title):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((60, 28), title, font=font(26, True), fill=(15, 23, 42))
    return img, d


def draw_axes(d, left, top, right, bottom, ymin, ymax, yticks, fmt="{:.2f}"):
    d.line([(left, top), (left, bottom)], fill=AXIS, width=2)
    d.line([(left, bottom), (right, bottom)], fill=AXIS, width=2)
    for v in yticks:
        y = bottom - (v - ymin) / (ymax - ymin) * (bottom - top)
        d.line([(left, y), (right, y)], fill=(241, 245, 249), width=1)
        d.text((left - 12 - len(fmt.format(v)) * 7, y - 9), fmt.format(v),
               font=font(15), fill=TEXT_L)


def save(img, name):
    path = os.path.join(OUT, name)
    img.save(path, "PNG", dpi=(200, 200))
    print("saved", name)


def _has_loss_history():
    payload = load("evaluation_metrics.json") or {}
    history = payload.get("meta", {}).get("loss_history", {})
    return len(history.get("train", [])) >= 2 and len(history.get("validation", [])) >= 2


def _post_loss_figure_number(number):
    return number if _has_loss_history() else number - 1


# ---------------------------------------------------------------- 图1 因子IC
def fig_factor_ic():
    fd = load("factor_diagnosis.json")
    if not fd:
        return None
    rows = fd.get("results", [])[:12]
    if not rows:
        return None
    img, d = new_canvas("图1  因子有效性检验（截面 IC 与 t 值）")
    left, top, right, bottom = 300, 110, 1140, 560
    vals = [r["ic_mean"] for r in rows]
    vmax = max(abs(v) for v in vals) * 1.25
    n = len(rows)
    step = (bottom - top) / n
    bar_h = step * 0.55
    zero_x = left + (right - left) * 0.5

    d.line([(zero_x, top - 10), (zero_x, bottom)], fill=(203, 213, 225), width=2)
    for i, r in enumerate(rows):
        y = top + i * step + (step - bar_h) / 2
        v = r["ic_mean"]
        w = abs(v) / vmax * (right - left) * 0.5
        color = BLUE if v >= 0 else RED
        x0 = zero_x if v >= 0 else zero_x - w
        d.rectangle([x0, y, x0 + w, y + bar_h], fill=color)
        name = r["factor"]
        d.text((left - 190, y + bar_h / 2 - 10), name, font=font(15), fill=TEXT)
        mark = "  [入选]" if r.get("in_model") else ""
        d.text((right - 130, y + bar_h / 2 - 10),
               "IC=%.4f  t=%.2f%s" % (v, r["t_stat"], mark),
               font=font(14), fill=TEXT_L)

    d.text((left, 78), "蓝色=正 IC  红色=负 IC  t 值使用 Newey–West HAC 校正",
           font=font(14), fill=TEXT_L)
    save(img, "fig1_factor_ic.png")
    return "fig1_factor_ic.png"


# ------------------------------------------------------- 图2 滚动窗口AUC
def fig_walk_forward():
    wf = load("walk_forward.json")
    if not wf:
        return None
    wins = wf["windows"]
    s = wf["summary"]
    img, d = new_canvas("图%d  滚动窗口验证（AUC）" % _post_loss_figure_number(5))
    left, top, right, bottom = 110, 120, 1150, 520
    auc_values = [float(w["auc"]) for w in wins if w.get("auc") is not None]
    if not auc_values:
        return None
    spread = max(max(auc_values) - min(auc_values), 0.02)
    ymin = min(0.5, min(auc_values)) - spread * 0.15
    ymax = max(0.5, max(auc_values)) + spread * 0.15
    tick_step = (ymax - ymin) / 4
    ticks = [ymin + tick_step * i for i in range(5)]
    draw_axes(d, left, top, right, bottom, ymin, ymax,
              ticks, "{:.3f}")

    y50 = bottom - (0.5 - ymin) / (ymax - ymin) * (bottom - top)
    d.line([(left, y50), (right, y50)], fill=RED, width=2)
    d.text((right - 130, y50 - 24), "随机基线 0.500", font=font(14), fill=RED)

    n = len(wins)
    step = (right - left) / (n + 0.5)
    pts = []
    for i, w in enumerate(wins):
        x = left + step * (i + 0.7)
        y = bottom - (w["auc"] - ymin) / (ymax - ymin) * (bottom - top)
        pts.append((x, y))
    if len(pts) > 1:
        d.line(pts, fill=BLUE, width=3)
    for (x, y), w in zip(pts, wins):
        c = GREEN if w["auc"] >= 0.5 else RED
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=c, outline=(255, 255, 255), width=2)

    for i in range(0, n, 2):
        x = left + step * (i + 0.7)
        d.text((x - 32, bottom + 12), wins[i]["val_start"][:7],
               font=font(13), fill=TEXT_L)

    d.text((left, 78),
           "均值 %.4f   中位数 %.4f   标准差 %.4f   低于随机的窗口 %.1f%%" % (
               s["auc_mean"], s["auc_median"], s["auc_std"], s["pct_below_random"] * 100),
           font=font(16, True), fill=TEXT)
    save(img, "fig2_walk_forward_auc.png")
    return "fig2_walk_forward_auc.png"


# ------------------------------------------------ 图3 分市场状态 vs 基准
def fig_regime():
    at = load("attribution.json")
    if not at:
        return None
    reg = at["regime"]
    if not reg:
        return None
    img, d = new_canvas("图%d  分市场状态的策略与基准收益" % _post_loss_figure_number(7))
    left, top, right, bottom = 120, 120, 1140, 520
    allv = [r["benchmark_mean"] for r in reg] + [r["strategy_mean"] for r in reg]
    vmax = max(abs(v) for v in allv) * 1.3
    vmin = -vmax
    draw_axes(d, left, top, right, bottom, vmin, vmax,
              [vmin, vmin * 0.5, 0, vmax * 0.5, vmax], "{:+.0%}")

    y0 = bottom - (0 - vmin) / (vmax - vmin) * (bottom - top)
    d.line([(left, y0), (right, y0)], fill=(148, 163, 184), width=2)

    n = len(reg)
    slot = (right - left) / n
    bw = slot * 0.24
    for i, r in enumerate(reg):
        cx = left + slot * (i + 0.5)
        for off, val, col, lab in ((-bw * 0.6, r["benchmark_mean"], GRAY, "基准"),
                                    (bw * 0.6, r["strategy_mean"], BLUE, "策略")):
            h = abs(val) / vmax * (bottom - top) * 0.5
            y1 = y0 - h if val >= 0 else y0
            d.rectangle([cx + off - bw / 2, y1, cx + off + bw / 2, y1 + h], fill=col)
        d.text((cx - 28, bottom + 12), r["regime"], font=font(15), fill=TEXT)
        ex = r["excess_mean"]
        d.text((cx - 34, top - 6), "%+.2f%%" % (ex * 100),
               font=font(14, True), fill=(GREEN if ex >= 0 else RED))

    d.rectangle([left, 76, left + 12, 88], fill=GRAY)
    d.text((left + 20, 72), "基准收益", font=font(14), fill=TEXT_L)
    d.rectangle([left + 120, 76, left + 132, 88], fill=BLUE)
    d.text((left + 140, 72), "策略收益", font=font(14), fill=TEXT_L)
    d.text((left + 260, 72), "柱上方数字 = 该状态下的平均超额收益",
           font=font(14), fill=TEXT_L)
    save(img, "fig3_regime_excess.png")
    return "fig3_regime_excess.png"


# ------------------------------------------------------- 图4 净值曲线
def fig_nav():
    wf = load("walk_forward.json")
    if not wf:
        return None
    agg = wf.get("backtest_aggregated") or {}
    st = agg.get("strategy", {}).get("nav")
    bm = agg.get("benchmark", {}).get("nav")
    if not st or not bm:
        return None

    img, d = new_canvas("图%d  滚动验证期净值：策略与基准" % _post_loss_figure_number(6))
    left, top, right, bottom = 110, 120, 1150, 520

    def to_log(v):
        return math.log10(max(v, 1e-6))

    ls = [to_log(x) for x in st]
    lb = [to_log(x) for x in bm]
    ymin = min(min(ls), min(lb))
    ymax = max(max(ls), max(lb))
    pad = (ymax - ymin) * 0.08
    ymin, ymax = ymin - pad, ymax + pad

    ticks = []
    v = math.floor(ymin)
    while v <= ymax:
        ticks.append(v)
        v += 1
    draw_axes(d, left, top, right, bottom, ymin, ymax, ticks, "{:.0f}")

    n = len(st)
    if n == 1:
        st = [1.0, st[0]]
        bm = [1.0, bm[0]]
        n = 2
    def path(vals):
        out = []
        for i, v in enumerate(vals):
            x = left + (right - left) * i / (n - 1)
            y = bottom - (v - ymin) / (ymax - ymin) * (bottom - top)
            out.append((x, y))
        return out

    d.line(path(lb), fill=GRAY, width=2)
    d.line(path(ls), fill=BLUE, width=3)

    d.rectangle([left, 76, left + 12, 88], fill=BLUE)
    params = agg.get("params", {})
    selection = "行业中性" if params.get("selection") == "neutral" else "全市场排序"
    d.text((left + 20, 72), "策略（%s Top-%s）" % (selection, params.get("k", "—")),
           font=font(14), fill=TEXT_L)
    d.rectangle([left + 230, 76, left + 242, 88], fill=GRAY)
    d.text((left + 250, 72), "基准（全样本等权）", font=font(14), fill=TEXT_L)
    d.text((left + 430, 72), "纵轴为净值（10 的幂），共 %d 个交易周期" % n,
           font=font(14), fill=TEXT_L)
    save(img, "fig4_nav_curve.png")
    return "fig4_nav_curve.png"


# ------------------------------------------------- 图8 SHAP summary beeswarm
def fig_shap_beeswarm():
    summary = load("shap_summary.json")
    features = (summary or {}).get("features", [])
    if not features:
        return None

    img, d = new_canvas("图%d  SHAP summary beeswarm（测试集）" % _post_loss_figure_number(8))
    left, top, right, bottom = 275, 135, 1125, 525
    features = features[:10]
    all_shap = [abs(float(v)) for f in features for v in f.get("shap_values", [])
                if v is not None and math.isfinite(float(v))]
    if not all_shap:
        return None
    x_limit = max(float(np.quantile(all_shap, 0.99)), 1e-6)
    row_gap = (bottom - top) / max(len(features), 1)

    def color_for_percentile(q):
        if q is None or not math.isfinite(float(q)):
            return GRAY
        q = min(1.0, max(0.0, float(q)))
        low, middle, high = (59, 130, 246), (226, 232, 240), (239, 68, 68)
        if q <= 0.5:
            ratio, start, end = q * 2, low, middle
        else:
            ratio, start, end = (q - 0.5) * 2, middle, high
        return tuple(round(a + (b - a) * ratio) for a, b in zip(start, end))

    d.line([(left, top), (left, bottom)], fill=AXIS, width=2)
    d.line([(left, bottom), (right, bottom)], fill=AXIS, width=2)
    for tick_ratio in (-1, -0.5, 0, 0.5, 1):
        x = left + (right - left) * (tick_ratio + 1) / 2
        d.line([(x, top), (x, bottom)],
               fill=(203, 213, 225) if tick_ratio == 0 else (241, 245, 249),
               width=2 if tick_ratio == 0 else 1)
        d.text((x - 30, bottom + 8), "%.3f" % (tick_ratio * x_limit),
               font=font(12), fill=TEXT_L)

    for feature_index, feature in enumerate(features):
        center_y = top + row_gap * (feature_index + 0.5)
        d.line([(left, center_y), (right, center_y)], fill=(248, 250, 252), width=1)
        d.text((left - 12, center_y - 9), feature.get("name_cn", feature.get("feature", "")),
               font=font(14), fill=TEXT, anchor="ra")
        values = feature.get("shap_values", [])
        percentiles = feature.get("feature_value_percentiles", [])
        for sample_index, value in enumerate(values):
            if value is None or not math.isfinite(float(value)):
                continue
            normalized_x = max(-1.0, min(1.0, float(value) / x_limit))
            x = left + (right - left) * (normalized_x + 1) / 2
            jitter = (((sample_index * 37 + feature_index * 61) % 101) / 100 - 0.5) * row_gap * 0.68
            y = center_y + jitter
            percentile = percentiles[sample_index] if sample_index < len(percentiles) else None
            color = color_for_percentile(percentile)
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=color)

    d.text((left, 575), "SHAP 值（log-odds）：正值提高模型分数，负值降低模型分数",
           font=font(14), fill=TEXT_L)
    legend_x, legend_y, legend_w = 790, 76, 170
    for i in range(legend_w):
        d.line([(legend_x + i, legend_y), (legend_x + i, legend_y + 12)],
               fill=color_for_percentile(i / (legend_w - 1)), width=1)
    d.text((legend_x - 30, legend_y - 2), "低", font=font(13), fill=TEXT_L)
    d.text((legend_x + legend_w + 6, legend_y - 2), "高", font=font(13), fill=TEXT_L)
    d.text((legend_x + 40, legend_y + 16), "标准化特征值分位", font=font(12), fill=TEXT_L)
    d.text((left, 610),
           "输入特征经逐日缩尾、行业中性化与截面 z-score 标准化；样本数=%s，日期数=%s。" % (
               summary.get("sample_rows", "—"), summary.get("sample_dates", "—")),
           font=font(13), fill=TEXT_L)
    save(img, "fig5_shap_beeswarm.png")
    legacy_bar = os.path.join(OUT, "fig5_feature_importance.png")
    if os.path.exists(legacy_bar):
        os.remove(legacy_bar)
    return "fig5_shap_beeswarm.png"


# ------------------------------------------------------ 图6 排序指标对比
def fig_ranking_metrics():
    payload = load("evaluation_metrics.json")
    if not payload:
        return None
    models = payload.get("comparison", {})
    metrics = ("NDCG@5", "Precision@5", "AUC")
    rows = [(name, values) for name, values in models.items()
            if any(metric in values for metric in metrics)]
    if not rows:
        return None

    img, d = new_canvas("图2  测试集推荐排序指标对比")
    left, top, right, bottom = 270, 150, 1130, 530
    values = [[row.get(metric) for metric in metrics] for _, row in rows]
    max_value = max(float(v) for row in values for v in row if v is not None)
    ymax = max(0.55, max_value * 1.15)
    colors = (BLUE, GREEN, GOLD)
    slot = (bottom - top) / max(len(rows), 1)
    bar_h = min(18, slot * .2)
    d.line([(left, top), (left, bottom)], fill=AXIS, width=2)
    d.line([(left, bottom), (right, bottom)], fill=AXIS, width=2)
    for tick in range(5):
        value = ymax * tick / 4
        x = left + (right - left) * tick / 4
        d.line([(x, top), (x, bottom)], fill=(241, 245, 249), width=1)
        d.text((x - 14, bottom + 7), "%.2f" % value, font=font(12), fill=TEXT_L)
    for i, (label, _) in enumerate(rows):
        group_top = top + slot * i
        d.text((left - 210, group_top + slot * .42), label[:22], font=font(14), fill=TEXT)
        for j, metric in enumerate(metrics):
            value = values[i][j]
            if value is None:
                continue
            width = max(2, float(value) / ymax * (right - left))
            y = group_top + slot * .18 + j * (bar_h + 5)
            d.rectangle([left, y, left + width, y + bar_h], fill=colors[j])
            d.text((min(left + width + 8, right - 42), y - 1),
                   "%.3f" % float(value), font=font(12), fill=TEXT_L)
    for j, metric in enumerate(metrics):
        x = left + j * (right - left) / len(metrics)
        d.rectangle([x, 92, x + 12, 104], fill=colors[j])
        d.text((x + 18, 88), metric, font=font(14), fill=TEXT_L)
    d.text((left, 590), "指标按测试日期逐截面计算后取均值；随机基线用于参照。",
           font=font(14), fill=TEXT_L)
    save(img, "fig6_ranking_metrics.png")
    return "fig6_ranking_metrics.png"


# ------------------------------------------------------ 图3 Precision@K / NDCG@K 曲线
def fig_topk_curves():
    payload = load("evaluation_metrics.json")
    curves = (payload or {}).get("ranking_curves", {})
    if not curves:
        return None

    img, d = new_canvas("图3  测试集 Precision@K / NDCG@K")
    colors = {
        "LightGBM (Ours)": BLUE,
        "Random Guess": GRAY,
        "Logistic Regression": GREEN,
        "Random Forest": GOLD,
    }
    labels = {
        "LightGBM (Ours)": "本文 LightGBM",
        "Random Guess": "随机排序",
        "Logistic Regression": "逻辑回归",
        "Random Forest": "随机森林",
    }

    def draw_panel(x0, x1, title, metric):
        y0, y1 = 145, 520
        d.text((x0, 105), title, font=font(18, True), fill=TEXT)
        d.line([(x0 + 48, y0), (x0 + 48, y1)], fill=AXIS, width=2)
        d.line([(x0 + 48, y1), (x1, y1)], fill=AXIS, width=2)
        for tick in range(5):
            value = tick / 4
            y = y1 - value * (y1 - y0)
            d.line([(x0 + 48, y), (x1, y)], fill=(241, 245, 249), width=1)
            d.text((x0 + 5, y - 8), "%.2f" % value, font=font(12), fill=TEXT_L)

        first = next(iter(curves.values()))
        ks = first.get("ks", [])
        if len(ks) < 2:
            return
        for name, curve in curves.items():
            values = curve.get(metric, [])
            count = min(len(ks), len(values))
            if count < 2:
                continue
            points = []
            for i, value in enumerate(values[:count]):
                x = x0 + 48 + (x1 - (x0 + 48)) * i / (len(ks) - 1)
                y = y1 - min(1.0, max(0.0, float(value))) * (y1 - y0)
                points.append((x, y))
            color = colors.get(name, (139, 92, 246))
            d.line(points, fill=color, width=3 if "LightGBM" in name else 2)
            for x, y in points:
                d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=color)

        for i, k in enumerate(ks):
            if i == 0 or i == len(ks) - 1 or (i + 1) % 5 == 0:
                x = x0 + 48 + (x1 - (x0 + 48)) * i / (len(ks) - 1)
                d.text((x - 8, y1 + 8), str(k), font=font(12), fill=TEXT_L)

    draw_panel(55, 585, "Precision@K", "precision")
    draw_panel(650, 1180, "NDCG@K", "ndcg")
    legend_names = [name for name in curves if name in labels]
    legend_start = 145
    for index, name in enumerate(legend_names):
        x = legend_start + index * 245
        color = colors.get(name, GRAY)
        d.line([(x, 570), (x + 24, 570)], fill=color, width=4)
        d.text((x + 31, 560), labels[name], font=font(13), fill=TEXT_L)
    meta = payload.get("ranking_curve_meta", {})
    d.text((55, 590), "Precision@K 为前 K 名中未来 5 日跑赢当日候选池均值的比例。",
           font=font(12), fill=TEXT_L)
    d.text((55, 610), "各 K 使用相同测试日期截面等权平均；纳入 %s / %s 个日期，K=1…%s；随机基线为 %s 次随机排序均值。" % (
        meta.get("n_dates", "—"), meta.get("total_dates", "—"), meta.get("max_k", "—"),
        meta.get("random_baseline_repeats", 0)),
        font=font(13), fill=TEXT_L)
    save(img, "fig_topk_curves.png")
    return "fig_topk_curves.png"


# ------------------------------------------------------ 图7 训练损失曲线
def fig_loss_curve():
    payload = load("evaluation_metrics.json")
    history = (payload or {}).get("meta", {}).get("loss_history", {})
    train = history.get("train", [])
    validation = history.get("validation", [])
    n = min(len(train), len(validation))
    if n < 2:
        return None

    train = [float(v) for v in train[:n]]
    validation = [float(v) for v in validation[:n]]
    lo = min(train + validation)
    hi = max(train + validation)
    padding = max((hi - lo) * 0.12, 0.01)
    ymin, ymax = max(0.0, lo - padding), hi + padding
    if ymax <= ymin:
        ymax = ymin + 0.1

    img, d = new_canvas("图4  LightGBM 训练与验证 Binary Logloss")
    left, top, right, bottom = 105, 105, 1135, 535
    tick_count = 5
    yticks = [ymin + (ymax - ymin) * i / (tick_count - 1)
              for i in range(tick_count)]
    draw_axes(d, left, top, right, bottom, ymin, ymax, yticks, fmt="{:.3f}")

    def points(values):
        return [(
            left + (right - left) * i / max(n - 1, 1),
            bottom - (value - ymin) / (ymax - ymin) * (bottom - top),
        ) for i, value in enumerate(values)]

    d.line(points(train), fill=BLUE, width=3)
    d.line(points(validation), fill=GOLD, width=3)
    for label, color, x in (("训练集", BLUE, 825), ("验证集", GOLD, 955)):
        d.line([(x, 73), (x + 25, 73)], fill=color, width=4)
        d.text((x + 32, 63), label, font=font(16), fill=TEXT)

    for iteration in (1, max(1, n // 2), n):
        x = left + (right - left) * (iteration - 1) / max(n - 1, 1)
        d.line([(x, bottom), (x, bottom + 5)], fill=AXIS, width=1)
        d.text((x - 18, bottom + 10), str(iteration), font=font(13), fill=TEXT_L)
    d.text((left, 585), "横轴：Boosting 迭代轮次；验证集曲线用于观察泛化趋势，不使用测试集损失选轮数。",
           font=font(14), fill=TEXT_L)
    save(img, "fig7_loss_curve.png")
    return "fig7_loss_curve.png"


if __name__ == "__main__":
    made = []
    for fn in (fig_factor_ic, fig_walk_forward, fig_regime, fig_nav,
               fig_shap_beeswarm, fig_ranking_metrics, fig_topk_curves,
               fig_loss_curve):
        try:
            r = fn()
            if r:
                made.append(r)
        except Exception as e:
            print("FAIL", fn.__name__, e)
    print("total:", len(made))
