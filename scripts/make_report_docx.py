# -*- coding: utf-8 -*-
"""生成论文写作参考文档（DOCX）

把项目的全部实证结论、数据表格与图表汇总为一份可直接引用的文档。
数据全部来自 saved_models/ 下的实际产物，无任何手写数值。
"""
import json
import os
from datetime import datetime

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SM = os.path.join(BASE, "saved_models")
FIGS = os.path.join(BASE, "docs", "figures")
OUT = os.path.join(BASE, "docs", "论文写作参考_实验结果与分析.docx")

CJK = "微软雅黑"
ACCENT = RGBColor(0x1D, 0x4E, 0xD8)
MUTED = RGBColor(0x64, 0x74, 0x8B)
WARN = RGBColor(0xB4, 0x53, 0x09)


def load(name):
    p = os.path.join(SM, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def set_cjk(run, name=CJK):
    run.font.name = name
    r = run._element.rPr.rFonts
    r.set(qn("w:eastAsia"), name)


def p(text="", size=10.5, bold=False, color=None, style=None, space_after=6,
      align=None, indent=None):
    para = doc.add_paragraph(style=style)
    para.paragraph_format.space_after = Pt(space_after)
    para.paragraph_format.line_spacing = 1.45
    if indent is not None:
        para.paragraph_format.first_line_indent = Pt(indent)
    if align:
        para.alignment = align
    if text:
        run = para.add_run(text)
        run.font.size = Pt(size)
        run.bold = bold
        if color:
            run.font.color.rgb = color
        set_cjk(run)
    return para


def heading(text, level=1):
    sizes = {1: 15, 2: 12.5, 3: 11}
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(16 if level == 1 else 11)
    para.paragraph_format.space_after = Pt(7)
    run = para.add_run(text)
    run.bold = True
    run.font.size = Pt(sizes.get(level, 11))
    run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A) if level == 1 else ACCENT
    set_cjk(run)
    return para


def bullet(text, size=10.5):
    para = doc.add_paragraph(style="List Bullet")
    para.paragraph_format.space_after = Pt(3)
    para.paragraph_format.line_spacing = 1.4
    run = para.add_run(text)
    run.font.size = Pt(size)
    set_cjk(run)
    return para


def table(headers, rows, widths=None, font_size=9.5):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        para = hdr[i].paragraphs[0]
        para.paragraph_format.space_after = Pt(2)
        run = para.add_run(str(h))
        run.bold = True
        run.font.size = Pt(font_size)
        set_cjk(run)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            para = cells[i].paragraphs[0]
            para.paragraph_format.space_after = Pt(2)
            run = para.add_run(str(v))
            run.font.size = Pt(font_size)
            set_cjk(run)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


def figure(fname, caption, width=14.5):
    path = os.path.join(FIGS, fname)
    if not os.path.exists(path):
        p("[缺失图：%s]" % fname, color=WARN)
        return
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(8)
    para.paragraph_format.space_after = Pt(3)
    para.add_run().add_picture(path, width=Cm(width))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(12)
    run = cap.add_run(caption)
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED
    set_cjk(run)


def callout(title, text, color=ACCENT):
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(5)
    para.paragraph_format.space_after = Pt(3)
    run = para.add_run(title)
    run.bold = True
    run.font.size = Pt(10.5)
    run.font.color.rgb = color
    set_cjk(run)
    para2 = doc.add_paragraph()
    para2.paragraph_format.space_after = Pt(4)
    para2.paragraph_format.line_spacing = 1.4
    run2 = para2.add_run(text)
    run2.font.size = Pt(10)
    set_cjk(run2)


def fmt(value, digits=4):
    return "—" if value is None else ("%.*f" % (digits, value))


def pct(value, digits=2):
    return "—" if value is None else ("%.*f%%" % (digits, value * 100))


def factor_category(factor):
    raw = factor[:-4] if factor.endswith("_neu") else factor
    if raw in {"momentum_20d", "momentum_60d", "volatility_20d", "turnover_proxy"}:
        return "量价"
    if raw in {"pe_ttm", "pb", "roe", "roa", "gross_margin", "net_margin",
               "debt_ratio", "revenue_growth", "profit_growth"}:
        return "基本面"
    return "技术"


# ================================================================ 数据载入
rep = load("training_report.json") or {}
fd = load("factor_diagnosis.json") or {}
wf = load("walk_forward.json") or {}
at = load("attribution.json") or {}
bc = load("backtest_comparison.json") or {}
gi = load("global_importance.json") or []

doc = Document()

# 页面设置 A4
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.6)
sec.top_margin = sec.bottom_margin = Cm(2.4)

style = doc.styles["Normal"]
style.font.name = CJK
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn("w:eastAsia"), CJK)

# ================================================================ 封面区
title = doc.add_paragraph()
title.style = doc.styles["Title"]
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
title.paragraph_format.space_before = Pt(40)
title.paragraph_format.space_after = Pt(6)
run = title.add_run("基于 LightGBM 与特征归因的股票推荐系统")
run.bold = True
run.font.size = Pt(21)
run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)
set_cjk(run)

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
sub.paragraph_format.space_after = Pt(24)
run = sub.add_run("实验结果与分析 · 论文写作参考资料")
run.font.size = Pt(13)
run.font.color.rgb = ACCENT
set_cjk(run)

panel = rep.get("panel", {})
date_range = panel.get("date_range") or ["—", "—"]
universe_mode = "历史成分股" if panel.get("point_in_time_universe") else "当前成分股回溯"
meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.paragraph_format.space_after = Pt(30)
run = meta.add_run(
    "建模范畴：沪深 300 候选池　|　样本区间：%s 至 %s　|　股票池口径：%s\n"
    "生成时间：%s" % (str(date_range[0])[:10], str(date_range[-1])[:10], universe_mode,
                      datetime.now().strftime("%Y-%m-%d %H:%M"))
)
run.font.size = Pt(9)
run.font.color.rgb = MUTED
set_cjk(run)

# ================================================================ 摘要
heading("一、核心结论摘要", 1)

callout(
    "一句话结论",
    "本项目实现了从训练期因子筛选、LightGBM 截面排序，到 Top-K 推荐、TreeSHAP 归因和"
    "滚动回测的流程。当前模型分数对应未来 5 个交易日跑赢当日有效候选池平均收益的倾向，"
    "不表示绝对上涨；分数尚未校准，主要用于候选排序。结果摘要应以本次训练产物为准，"
    "并结合历史成分股覆盖与回测成交假设解释。",
    ACCENT,
)

p("项目最终形成的四条实证结论，建议论文按此结构组织分析章节：", bold=True, space_after=6)

mm_summary = rep.get("model_metrics", {})
wf_summary = wf.get("summary", {})
bt_summary = wf.get("backtest_summary", {})
attr_reg = at.get("regression", {})
selected = panel.get("selected_factors", [])
conclusion_rows = [
    ("因子有效性", "%d 个因子进入最终模型" % len(selected),
     "筛选方式：%s" % panel.get("factor_selection_mode", "见 selected_factors.json")),
    ("模型预测力", "测试集 AUC %s" % fmt(mm_summary.get("test", {}).get("auc")),
     "滚动 AUC 均值 %s；低于 0.5 的窗口占比 %s" % (
         fmt(wf_summary.get("auc_mean")), pct(wf_summary.get("pct_below_random"), 1))),
    ("组合收益", "滚动回测窗口 %s 个" % bt_summary.get("n_windows", 0),
     "窗口超额年化均值 %s；正超额窗口占比 %s" % (
         pct(bt_summary.get("excess_ann_mean")), pct(bt_summary.get("excess_positive_ratio"), 1))),
    ("业绩归因", "Beta %s；年化 Alpha %s" % (
        fmt(attr_reg.get("beta")), pct(attr_reg.get("alpha_annual"))),
     "Alpha p 值 %s；R² %s" % (fmt(attr_reg.get("alpha_p")), fmt(attr_reg.get("r_squared")))),
]
table(["分析层次", "结论", "关键证据"], conclusion_rows, widths=[3.0, 5.5, 7.5])

# ================================================================ 实验设置
heading("二、实验设置", 1)

heading("2.1 数据与样本", 2)
panel = rep.get("panel", {})
p("本次面板包含沪深 300 候选池的历史行情与模型特征。股票池口径为“%s”。"
  % ("按历史成分股与行业生效日期过滤" if panel.get("point_in_time_universe") else
     "当前成分股回溯；由于没有历史成分股生效期文件，存在幸存者偏差"), indent=21)

table(
    ["项目", "数值"],
    [
        ("成分股数量", "%d 只" % panel.get("stocks", 0)),
        ("交易截面数", "%d 个" % panel.get("dates", 0)),
        ("面板样本量", "{:,} 行".format(panel.get("rows", 0))),
        ("样本区间", "%s 至 %s" % (
            str(panel.get("date_range", ["", ""])[0])[:10],
            str(panel.get("date_range", ["", ""])[1])[:10])),
        ("标签口径", "未来 5 个交易日收益是否高于当日有效候选池均值"),
        ("进出场口径", "下一交易日开盘买入，第 5 个交易日收盘卖出"),
        ("历史成分股", "已启用" if panel.get("point_in_time_universe") else "未提供历史成分股文件"),
    ],
    widths=[4.5, 9.5],
)

heading("2.2 防泄漏设计", 2)
p("量化研究中前视偏差是最容易犯也最致命的错误。本项目在四个环节做了显式防护：", indent=21)
table(
    ["风险点", "处理方式"],
    [
        ("bfill 把未来值回填到过去", "特征清洗只用 ffill；LightGBM 保留缺失值"),
        ("财报数据使用未公开信息", "按法定披露截止日做保守滞后（Q1→4/30，年报→次年4/30）"),
        ("前瞻收益标签跨越切分边界", "按 5 个交易日设置边界隔离期"),
        ("验证折参与特征筛选", "因子筛选在每个训练折内重新执行"),
        ("测试集信息进入拟合或调参", "最终模型只用训练集拟合；验证与测试仅用于评价"),
    ],
    widths=[5.5, 8.5],
)

heading("2.3 模型与超参数", 2)
bp = rep.get("best_params", {})
p("采用 LightGBM 二分类模型，超参数由 Optuna 贝叶斯优化在训练集内部用 TimeSeriesSplit "
  "交叉验证搜索得到。最终参数如下：", indent=21)
table(
    ["参数", "取值", "参数", "取值"],
    [
        ("n_estimators", bp.get("n_estimators"), "num_leaves", bp.get("num_leaves")),
        ("learning_rate", round(bp.get("learning_rate", 0), 6), "subsample",
         round(bp.get("subsample", 0), 4)),
        ("max_depth", bp.get("max_depth"), "colsample_bytree",
         round(bp.get("colsample_bytree", 0), 4)),
        ("reg_alpha", round(bp.get("reg_alpha", 0), 6), "reg_lambda",
         round(bp.get("reg_lambda", 0), 8)),
    ],
    widths=[3.6, 3.4, 3.6, 3.4],
)

# ================================================================ 因子
heading("三、因子有效性检验", 1)

p("因子是否能进入模型，不凭经验判断，而是由训练区间内的截面 IC 与 HAC t 值决定。"
  "对每个因子逐交易日计算因子值与未来 5 日收益的 Spearman 秩相关，再跨截面汇总：", indent=21)

bullet("IC：每个截面的秩相关，跨截面取均值，衡量横截面区分能力")
bullet("t 值：Newey–West HAC 估计，滞后阶数为 4，以处理相邻 5 日前瞻收益导致的序列相关")
bullet("入选标准：|IC| ≥ 0.015 且 |t| ≥ 2.0，再经相关性去冗余（|r| > 0.7 剔除）")

p("", space_after=2)
table(
    ["因子", "类别", "IC 均值", "ICIR", "t 值", "结论"],
    [(r["factor"], factor_category(r["factor"]), "%.4f" % r["ic_mean"], "%.3f" % r.get("icir", 0),
      "%.2f" % r["t_stat"], "入选" if r.get("in_model") else "—")
     for r in fd.get("results", [])[:14]],
    widths=[3.4, 2.2, 2.4, 2.2, 2.0, 2.2],
)

figure("fig1_factor_ic.png", "图 1　因子有效性检验：截面 IC 与 t 值")

heading("3.1 入模因子", 2)
p("下表报告的检验仅使用最终训练区间。通过 IC 与 HAC t 门槛的因子再做相关性去冗余；"
  "若没有因子通过，系统仅以训练期 |IC| 排名前五的候选因子作为明确标记的回退方案。"
  "该结果不包含验证期或测试期标签信息。", indent=21)
selection_period = panel.get("factor_selection_period") or ["—", "—"]
table(
    ["最终入模因子", "筛选方式", "筛选区间"],
    [("、".join(selected) if selected else "—",
      panel.get("factor_selection_mode", "—"),
      "%s 至 %s" % (str(selection_period[0])[:10], str(selection_period[-1])[:10]))],
    widths=[6.0, 4.0, 4.0],
)

# ================================================================ 模型
heading("四、模型预测能力", 1)

heading("4.1 时序切分结果", 2)
mm = rep.get("model_metrics", {})
table(
    ["数据集", "AUC", "准确率", "样本数", "截面数", "正样本率"],
    [(name, fmt(mm[name].get("auc")), fmt(mm[name].get("accuracy")),
      "{:,}".format(mm[name]["n_rows"]), mm[name]["n_dates"],
      fmt(mm[name].get("pos_rate")))
     for name in ("train", "val", "test") if name in mm],
    widths=[2.4, 2.2, 2.2, 3.0, 2.2, 2.4],
)

callout(
    "必须如实说明的问题",
    "单次切分和滚动窗口反映不同时间段的市场状态。请依据本次报告中的 AUC、截面 AUC、"
    "NDCG@K 和各窗口分布陈述预测能力；不要把略高于 0.5 的点估计解读为显著有效，"
    "除非另行给出置信区间或统计检验。",
    WARN,
)

heading("4.2 基线对比", 2)
bl = rep.get("baseline_comparison", {})
table(
    ["模型", "NDCG@5", "Precision@5", "AUC"],
    [(name, fmt(values.get("NDCG@5")), fmt(values.get("Precision@5")),
      fmt(values.get("AUC"))) for name, values in bl.items()],
    widths=[6.0, 3.0, 3.0, 3.0],
)

p("模型比较用于检查 LightGBM 相对随机、逻辑回归与随机森林的排序表现。"
  "是否优于基线应结合各指标以及跨日期波动评估；本表的均值本身不构成显著性检验。", indent=21)
figure("fig6_ranking_metrics.png", "图 2　测试集推荐排序指标基线比较")
p("Precision@K 表示推荐前 K 名中，未来 5 日收益高于当日候选池平均收益的比例。"
  "随机基线为固定种子生成的多次随机排序均值；各 K 在相同测试日期集合上等权汇总。", indent=21)
figure("fig_topk_curves.png", "图 3　测试集 Precision@K 与 NDCG@K 曲线（各 K 使用相同日期截面）")

loss_history = rep.get("loss_history", {})
has_loss_history = len(loss_history.get("train", [])) >= 2 and len(loss_history.get("validation", [])) >= 2
post_loss_figure_offset = 1 if has_loss_history else 0
if has_loss_history:
    heading("4.3 训练损失变化", 2)
    p("图中展示最终 LightGBM 模型在每轮 Boosting 后的训练集与验证集 Binary Logloss。"
      "训练损失下降而验证损失持续上升时，可能提示过拟合；本项目固定迭代轮数由训练集内部时序交叉验证确定，"
      "验证曲线用于观察训练过程，不依据测试集损失选择模型。", indent=21)
    figure("fig7_loss_curve.png", "图 4　LightGBM 训练集与验证集 Binary Logloss 曲线")

heading("4.4 滚动窗口验证", 2)
sf = wf.get("summary", {})
p("单次三段切分的结果依赖切分点所处市场状态。为得到更可靠的估计，"
  "采用滚动窗口：每个窗口使用此前历史训练，再对后续区间评分。窗口数、步长与检验长度"
  "以本次实验配置为准。", indent=21)

table(
    ["统计量", "数值", "说明"],
    [
        ("窗口数", sf.get("n_windows"), "步长 %s 个交易日" % sf.get("step_days")),
        ("AUC 均值", fmt(sf.get("auc_mean")), "长期水平"),
        ("AUC 中位数", fmt(sf.get("auc_median")), "窗口中位数"),
        ("AUC 标准差", fmt(sf.get("auc_std")), "窗口间离散程度"),
        ("AUC 区间", "%s ~ %s" % (fmt(sf.get("auc_min")), fmt(sf.get("auc_max"))),
         "最差与最好窗口"),
        ("低于随机的窗口占比", pct(sf.get("pct_below_random"), 1),
         "衡量失效风险"),
        ("截面 AUC 均值", fmt(sf.get("section_auc_mean")),
         "剔除跨期漂移的选股能力"),
    ],
    widths=[4.8, 3.6, 5.6],
)

figure("fig2_walk_forward_auc.png", "图 %d　滚动窗口 AUC 与随机基线" % (4 + post_loss_figure_offset))

heading("4.5 因子跨窗口稳定性", 2)
fs = wf.get("factor_stability", {})
p("因子的方向是否在时间上稳定，比全样本 IC 是否显著更重要。"
  "统计各因子在多个验证窗口中的符号翻转次数与显著窗口数：", indent=21)
table(
    ["因子", "IC 均值", "IC 标准差", "IC>0 占比", "符号翻转", "显著窗口"],
    [(k.replace("_neu", ""), "%.4f" % v["ic_mean"], "%.4f" % v["ic_std"],
      "%.1f%%" % (v["ic_positive_ratio"] * 100), str(v["sign_flips"]),
      "%d / %d" % (v["n_significant"], v["n_windows"]))
     for k, v in fs.items()],
    widths=[4.2, 2.4, 2.4, 2.4, 2.0, 2.2],
)

p("因子跨窗口方向变化表示其历史相关性并非固定不变。请根据表中每个因子的窗口统计讨论"
  "稳定性，不要把单个全样本显著结果推断为未来稳定有效。", indent=21)

# ================================================================ 回测
heading("五、组合回测", 1)

heading("5.1 两种选股口径对比", 2)
p("在同一模型打分下比较两种持仓构建方式。行业中性指每个行业内按打分取 Top-N 后合并，"
  "用于限制单一行业暴露；行业样本不足 5 只时并入剩余池补位。", indent=21)

rows = []
for key, label in (("global", "全市场排序"), ("neutral", "行业中性")):
    if key in bc:
        s, e = bc[key]["strategy"], bc[key]["excess"]
        rows.append((label, "%.2f%%" % (s["annualized_return"] * 100),
                     "%.4f" % s["sharpe"], "%.2f%%" % (s["max_drawdown"] * 100),
                     "%.2f%%" % (e["annualized_return"] * 100),
                     "%.2f%%" % (bc[key]["avg_turnover"] * 100)))
if "neutral" in bc:
    b = bc["neutral"]["benchmark"]
    rows.append(("基准（等权全样本）", "%.2f%%" % (b["annualized_return"] * 100),
                 "%.4f" % b["sharpe"], "%.2f%%" % (b["max_drawdown"] * 100), "—", "—"))

table(["口径", "年化收益", "夏普", "最大回撤", "超额年化", "换手率"], rows,
      widths=[3.6, 2.6, 2.2, 2.6, 2.6, 2.4])

p("两种构建方式对应不同的行业暴露和风险特征。以表格中的本次实测值比较其收益、回撤、"
  "夏普与换手，论文应报告完整对照，不预设哪一种方式一定更优。", indent=21)

heading("5.2 滚动回测", 2)
bs = wf.get("backtest_summary", {})
p("单次回测同样依赖市场状态。每个滚动窗口由只使用此前数据训练的模型生成验证段预测。"
  "窗口统计单独列示；连续净值将这些预测按时间拼接后统一计算，以在窗口间延续持仓并计入换手成本：", indent=21)

table(
    ["统计量", "数值"],
    [
        ("超额年化 均值", "%.2f%%" % (bs.get("excess_ann_mean", 0) * 100)),
        ("超额年化 中位数", "%.2f%%" % (bs.get("excess_ann_median", 0) * 100)),
        ("超额年化 标准差", "%.2f%%" % (bs.get("excess_ann_std", 0) * 100)),
        ("正超额窗口占比", "%.1f%%" % (bs.get("excess_positive_ratio", 0) * 100)),
        ("窗口策略年化区间", "%.2f%% ~ %.2f%%" % (bs.get("strategy_ann_min", 0) * 100,
                                              bs.get("strategy_ann_max", 0) * 100)),
        ("最差窗口回撤", "%.2f%%" % (bs.get("strategy_mdd_worst", 0) * 100)),
    ],
    widths=[5.5, 8.5],
)

agg = wf.get("backtest_aggregated", {})
if agg.get("strategy"):
    st, bn, ex = agg["strategy"], agg["benchmark"], agg["excess"]
    table(
        ["拼接净值指标", "策略", "基准", "超额"],
        [
            ("年化收益", "%.2f%%" % (st["annualized_return"] * 100),
             "%.2f%%" % (bn["annualized_return"] * 100),
             "%.2f%%" % (ex["annualized_return"] * 100)),
            ("年化波动", "%.2f%%" % (st["annualized_volatility"] * 100),
             "%.2f%%" % (bn["annualized_volatility"] * 100), "—"),
            ("夏普比率", "%.4f" % st["sharpe"], "%.4f" % bn["sharpe"],
             "%.4f" % ex["sharpe"]),
            ("最大回撤", "%.2f%%" % (st["max_drawdown"] * 100),
             "%.2f%%" % (bn["max_drawdown"] * 100), "—"),
            ("交易周期数", str(st["periods"]), str(bn["periods"]), "—"),
        ],
        widths=[4.4, 3.6, 3.6, 3.4],
    )

figure("fig4_nav_curve.png", "图 %d　滚动验证期净值：策略与基准对比（纵轴为对数刻度）" % (5 + post_loss_figure_offset))

# ================================================================ 归因（核心）
heading("六、业绩归因（本文核心分析）", 1)

callout(
    "为什么必须做这一步",
    "回测报出的「超额年化」回答不了最要紧的问题：这个超额来自选股能力（alpha），"
    "还是仅仅因为承担了更多市场风险（beta）？若不拆开，把 beta 暴露带来的收益"
    "记成「模型有效」，是典型的业绩归因错误。",
    ACCENT,
)

heading("6.1 回归结果", 2)
rg = at.get("regression", {})
p("对拼接净值做 OLS 回归：r_策略 = α + β · r_基准 + ε，"
  "交易周期数：%s。" % (at.get("periods") or "未估计"), indent=21)

ci = rg.get("alpha_ci95_annual", [None, None])
table(
    ["参数", "估计值", "标准误", "t 值", "p 值", "结论"],
    [
        ("Alpha（每期）", fmt(rg.get("alpha_period"), 6),
         fmt(rg.get("alpha_se_period"), 6), fmt(rg.get("alpha_t"), 3),
         fmt(rg.get("alpha_p")),
         ("未估计" if rg.get("alpha_significant") is None else
          ("显著异于 0" if rg.get("alpha_significant") else "无法拒绝 α=0"))),
        ("Alpha（年化）", pct(rg.get("alpha_annual")),
         "—", "—", "—",
         "置信区间 %s ~ %s" % (pct(ci[0]), pct(ci[1]))),
        ("Beta", fmt(rg.get("beta")), fmt(rg.get("beta_se")),
         fmt(rg.get("beta_t_vs_1"), 2), fmt(rg.get("beta_p_gt1")),
         ("未估计" if rg.get("beta_above_one") is None else
          ("显著大于 1" if rg.get("beta_above_one") else "与 1 无显著差异"))),
        ("R²", fmt(rg.get("r_squared")), "—", "—", "—",
         "市场解释比例的描述性指标"),
    ],
    widths=[3.0, 2.8, 2.4, 2.0, 2.0, 4.0],
)

heading("6.2 分市场状态表现", 2)
p("按基准收益五等分，观察策略超额是否随市场方向变化。"
  "分组模式只提供描述性证据，应结合回归结果、分组样本数和不确定性区间解释。", indent=21)

table(
    ["市场状态", "周期数", "基准收益", "策略收益", "超额收益"],
    [(r["regime"], r["n_periods"], "%.2f%%" % (r["benchmark_mean"] * 100),
      "%.2f%%" % (r["strategy_mean"] * 100), "%.2f%%" % (r["excess_mean"] * 100))
     for r in at.get("regime", [])],
    widths=[3.6, 2.4, 3.2, 3.2, 3.2],
)

figure("fig3_regime_excess.png", "图 %d　分市场状态的策略与基准收益对比" % (6 + post_loss_figure_offset))

p("市场分组图用于观察策略与基准在不同环境下的表现。该图属于描述性分组分析，"
  "应结合回归置信区间和样本量解释，不能单独用于证明超额收益来源。", indent=21)

heading("6.3 Beta 中性化对照", 2)
nt = at.get("beta_neutralized", {})
p("把策略收益减去 β × 基准收益可构造一个线性 beta 调整后的残差序列。该序列依赖"
  "回归模型和基准选择，不能直接等同于纯选股收益或可交易的对冲组合。", indent=21)
table(
    ["指标", "数值"],
    [
        ("年化收益", pct(nt.get("annualized_return"))),
        ("年化波动", pct(nt.get("annualized_volatility"))),
        ("夏普比率", fmt(nt.get("sharpe"))),
        ("最大回撤", pct(nt.get("max_drawdown"))),
    ],
    widths=[5.5, 8.5],
)

heading("6.4 结论表述", 2)
p("以下为当前归因程序生成的摘要；论文引用前仍需核对基准、成本、有效样本期和统计假设：",
  bold=True, space_after=5)
for point in at.get("conclusion", {}).get("points", []):
    bullet(point, size=10)

callout(
    "归因结论的解释",
    "相对基准的超额收益与回归 alpha 是不同统计量。只观察到正超额不能证明 alpha 显著；"
    "应结合置信区间、p 值、beta 和风险暴露解释来源。",
    WARN,
)

# ================================================================ 归因可信度
heading("七、特征归因的可信度", 1)

p("TreeSHAP 的结论只有在满足加和一致性时才可信。样本数：%s；"
  "检查 Σ SHAP + base_value 是否等于模型原始输出（log-odds 空间）。" %
  (rep.get("shap_additivity", {}).get("n_samples") or "未校验"), indent=21)

sa = rep.get("shap_additivity", {})
table(
    ["校验项", "结果"],
    [
        ("空间", sa.get("space", "—")),
        ("最大绝对误差", fmt(sa.get("max_abs_error"), 6)),
        ("平均绝对误差", fmt(sa.get("mean_abs_error"), 6)),
        ("容差阈值", fmt(sa.get("tolerance"))),
        ("结论", "未校验" if sa.get("passed") is None else
         ("通过" if sa.get("passed") else "未通过")),
    ],
    widths=[5.5, 8.5],
)

p("全局 Mean |SHAP| 数值排序如下；图中的 beeswarm 展示排名靠前特征在测试样本中的贡献方向与分布：", indent=21)
table(
    ["排名", "特征", "Mean |SHAP|", "重要性占比"],
    [(i + 1, r["feature"].replace("_neu", ""), "%.4f" % r["mean_abs_shap"],
      "%.1f%%" % (r["importance_ratio"] * 100))
     for i, r in enumerate(gi)],
    widths=[2.0, 5.0, 3.6, 3.4],
)

figure("fig5_shap_beeswarm.png", "图 %d　测试集 SHAP summary beeswarm（特征为行业中性化后的截面标准化值）" % (7 + post_loss_figure_offset))

callout(
    "解读要点",
    "beeswarm 横轴为模型原始 log-odds 空间中的 SHAP 贡献，正值提高模型分数、负值降低模型分数；颜色表示"
    "标准化特征值在可视化样本中的相对分位。SHAP 描述模型归因而非因果关系；若高排名特征缺乏经济学解释，"
    "论文中应讨论其是否为伪因子。",
    ACCENT,
)

# ================================================================ 局限
heading("八、已知局限与写作建议", 1)

heading("8.1 需要如实交代的局限", 2)
for item in [
    "模型输出未做概率校准，适合解释为候选池内的排序分数；不应称为经校准的绝对上涨概率。",
    ("已使用历史成分股和行业生效日期。" if panel.get("point_in_time_universe") else
     "未提供历史 CSI 300 成分股生效期文件，当前历史样本可能存在幸存者偏差。"),
    "历史回测采用下一交易日开盘买入、持有至第 5 个交易日收盘的简化执行假设，未模拟冲击成本、容量或涨跌停无法成交。",
    "基本面字段的数据源、公告日对齐与历史覆盖应单独核实；缺少历史披露时点数据会造成前视风险。",
    "TreeSHAP 是模型归因而非因果解释；全局重要性不表示方向，个股局部贡献不构成独立投资理由。",
    "单次切分和滚动窗口均有样本与市场状态依赖，应同时展示基线、离散程度及适用范围。",
]:
    bullet(item, size=10)

heading("8.2 建议的论文叙事", 2)
p("建议论文按“因子有效性—截面排序—组合表现—归因解释”的顺序讨论本次实验结果，"
  "并把运行产物中的统计证据与方法限制放在同一章节。不要从单一 AUC、SHAP 排名或"
  "回测年化收益推导市场有效性或因果结论。", indent=21)

heading("8.3 图附表索引", 2)
figure_index = [
    ("图 1", "因子有效性检验（IC 与 t 值）", "第三章 因子分析"),
    ("图 2", "测试集排序指标基线比较", "第四章 模型评价"),
    ("图 3", "Precision@K 与 NDCG@K 随推荐深度变化", "第四章 模型评价"),
]
next_figure_number = 4
if has_loss_history:
    figure_index.append(("图 4", "训练集与验证集 Binary Logloss 曲线", "第四章 模型评价"))
    next_figure_number = 5
figure_index.extend([
    ("图 %d" % next_figure_number, "滚动窗口 AUC", "第四章 模型评价"),
    ("图 %d" % (next_figure_number + 1), "滚动验证期净值曲线", "第五章 组合回测"),
    ("图 %d" % (next_figure_number + 2), "分市场状态的策略与基准收益", "第六章 业绩归因"),
    ("图 %d" % (next_figure_number + 3), "测试集 SHAP summary beeswarm", "第七章 归因可信度"),
])
table(
    ["编号", "内容", "建议放置章节"],
    figure_index,
    widths=[2.2, 7.8, 4.0],
)

# ================================================================ 附录
heading("附录：复现方式", 1)
p("本文档全部数值可由以下命令重新生成，产物位于 saved_models/：", indent=21)
p("python -m ml_pipeline.run_training --trials 20 --k 10", size=10, bold=True)

p("", space_after=4)
table(
    ["产物文件", "内容"],
    [
        ("factor_diagnosis.json", "因子有效性检验结果"),
        ("selected_factors.json", "入选因子（模型实际口径）"),
        ("evaluation_metrics.json", "基线对比指标与逐 K 排序曲线"),
        ("evaluation_metrics.json 中 meta.loss_history", "逐轮训练集与验证集 Binary Logloss"),
        ("shap_summary.json", "测试集 beeswarm 样本的 SHAP 值与标准化特征值"),
        ("backtest_comparison.json", "全市场 vs 行业中性回测"),
        ("walk_forward.json", "滚动窗口验证与滚动回测"),
        ("attribution.json", "Alpha / Beta 业绩归因"),
        ("shap_additivity.json", "归因加和一致性校验"),
        ("training_report.json", "训练与实验汇总"),
    ],
    widths=[6.0, 8.0],
)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
doc.save(OUT)
print("saved:", OUT)
