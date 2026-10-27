# 基于 LightGBM 与特征归因的股票推荐系统

毕业设计项目：面向 A 股候选池的截面选股排序、Top-K 推荐、TreeSHAP 归因与历史回测。

项目的核心任务是排序候选股票，不是预测股票一定会上涨。模型分数表示个股未来 5 个交易日收益高于当日候选池平均收益的估计概率；推荐列表按该分数从高到低排序。原始模型分数主要用于相对排序；独立验证区间拟合的单调 Platt 校准概率单独显示。

## 系统流程

```text
日线与基本面数据
        ↓
技术、量价、估值与财务因子
        ↓
按交易日做截面行业中性化与标准化
        ↓
训练期因子诊断 → LightGBM 二分类排序分数
        ↓                         ↓
测试集排序评价               TreeSHAP 全局与个股归因
        ↓
Top-K 等权组合回测与滚动窗口验证
```

| 功能 | 主要实现 |
| --- | --- |
| 面板构建、标签与时序切分 | `ml_pipeline/dataset.py` |
| 因子检验与训练期筛选 | `ml_pipeline/factor_diagnosis.py` |
| LightGBM 与日期分组调参 | `models/model_trainer.py` |
| Top-K 组合回测 | `ml_pipeline/backtest.py` |
| 滚动窗口验证 | `ml_pipeline/walk_forward.py` |
| TreeSHAP 归因 | `ml_pipeline/train_explainer.py` |
| REST API 与推荐界面 | `backend/`、`frontend/` |

## 标签与推荐口径

信号在交易日 `t` 收盘后生成。前瞻收益按下一交易日开盘买入、持有至第 5 个交易日收盘计算：

```text
ret_5d_fwd = close[t+5] / open[t+1] - 1
excess_ret_5d = ret_5d_fwd - 当日有效候选池的平均 ret_5d_fwd
target_up = excess_ret_5d > 0
```

LightGBM 输出 `target_up` 的原始模型分数，描述相对跑赢候选池均值的倾向，不代表绝对收益为正。原始分数和校准后概率分开保存、评估和显示；即使经过校准，也不能当作真实概率保证。A/B/C 评级按当日候选池的相对排名分档：A 为前 10%，B 为随后 20%，C 为其余标的；Top-K 推荐仍以横截面排序为主。

## 数据与历史成分股

当前线上候选池由 `config/config.py` 中的沪深 300 池配置。历史回测若要避免幸存者偏差，必须提供真实的历史成分股与行业生效期文件：`data/csi300_membership_history.csv`。字段格式见 `data/csi300_membership_history_template.csv`：

```text
code,name,industry,board,start_date,end_date
```

起止日期均包含在有效期内；仍在指数内的股票 `end_date` 留空。项目不会从当前成分股名单伪造历史成分股。如果该文件不存在，训练流程会退回当前候选池回溯，并在 `training_report.json` 标记幸存者偏差；这种结果只能视为受限的探索性回测，不能宣称已消除幸存者偏差。

财务字段应按公告可用日期滞后对齐。请检查 `data/factor_fetcher.py` 的数据源与披露日期处理，并在论文中记录数据来源、覆盖区间、复权方式和缺失处理。

## 训练与启动

安装依赖：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

完整训练并生成模型、评估、回测、归因及最新截面推荐：

```powershell
python -m ml_pipeline.run_training --scheme robust --k 10
```

小样本参数 `--limit` 仅用于检查数据与代码流程，结果不应用作论文主结论。训练会在 `saved_models/runs/<run_id>/` 隔离生成模型、归因、评测与推荐。只有校验通过后才原子切换 `saved_models/current.json`；失败不会替换当前完整模型。

用已训练模型刷新最新截面推荐：

```powershell
python main.py --k 10
```

`main.py --board 主板` 只筛选导出结果，模型分数仍按完整候选池计算。`--limit` 只用于小样本预览，会写入独立预览文件，不覆盖完整推荐缓存。

生成论文图表与实验结果 Word 参考文档：

```powershell
python scripts/make_figures.py
python scripts/make_report_docx.py
```

启动 API 与前端：

```powershell
python backend/run_server.py
```

默认访问 `http://127.0.0.1:8008`，API 文档为 `http://127.0.0.1:8008/docs`。前端独立开发可在 `frontend/` 执行 `npm install`、`npm run dev`；发布构建使用 `npm run build`。

## 方法与验证设计

### 因子构建及中性化

候选因子包括技术指标、量价派生指标，以及估值和财务指标。模型使用的每个交易日截面因子先缩尾，再按行业去均值；样本不足或行业未知时退回全截面去均值，随后做截面标准化。中性化仅使用该交易日可观察到的信息。

因子诊断使用模型实际输入的中性化列，报告截面 Spearman IC、Newey–West HAC t 统计量及相关性。默认 `robust` 在训练期内部的三个连续时间折比较固定候选：中性化 IC 筛选、既有量价、增强量价、滚动窗口和更浅树。覆盖率与去常数筛选均仅使用每折训练数据；按截面 AUC 均值减去 0.25 倍折间标准差选型。单因子 IC 用于诊断，不再是所有候选的唯一入模门槛。

新增 5/10 日动量、当日开收盘收益、当日隔夜跳空、收盘区间位置及 20 日非流动性，匹配收盘生成信号、次日开盘入场的 5 日预测任务。完全缺失的 ROA/利润增长率不会通过质量筛选，重复的换手活跃度代理也不重复入模。当前基本面缺少可核实的真实公告时点和历史修订版本，因此全因子方案只作诊断对照，不参与默认方案选择。

每次计算候选得分前保存 `model_selection_protocol.json`，同时记录协议 SHA256；所有候选及选择结果保存在 `model_selection.json`，训练数据审计保存在 `training_data_audit.json`。`--scheme legacy --trials 20` 保留 Optuna 搜索入口，供显式对照使用；`--trials` 只影响 legacy 方案。

### 时序验证

数据按日期先后切分为训练、验证和测试区间，边界保留 5 个交易日间隔，并按真实 `label_end_date` 清除未成熟训练标签。LightGBM 只拟合训练区间，改进候选按日期等权训练；外部验证集用于独立概率校准，测试标签不进入选型、拟合或校准。滚动验证从方案选择结束日期之后开始，按冻结的方案在各窗口过去数据中重新做质量/因子筛选及训练。

原测试期已经在历次审查中查看，本次结果明确属于**回顾性复核**，不能称为全新盲测。`reference_comparison.json` 对旧新模型在相同测试样本、相同标签上比较，并以 20 日移动块 bootstrap 报告截面 AUC 差值的条件区间；该区间不消除历史选型偏差、幸存者偏差或供应商数据修订影响。仍需未来未观察数据的前瞻确认，不能据旧测试结果持续追加试验。

主要报告截面 AUC、NDCG@K、Precision@K、基线比较、因子 IC/HAC t 值及滚动窗口稳定性。Precision@K / NDCG@K 曲线在相同测试日期集合上计算，K 上限受可用候选数量约束。训练时逐轮记录训练集与验证集 Binary Logloss，用于观察收敛和过拟合趋势；该曲线不包含测试集损失，也不据此选择迭代轮数。排序指标按每个交易日的候选列表计算，再对交易日等权汇总，避免样本量大的日期支配结果。

### 回测口径

回测按分数构建 Top-K 等权组合，每 5 个交易日调仓，使用下一交易日开盘至第 5 个交易日收盘收益，期末全额平仓，下一期重新建仓；两期之间持有现金。每期对策略和等权候选池基准均计入完整双边佣金、过户费、滑点及卖出印花税。滚动样本外预测按时间合并，统一使用上述口径。回撤包含初始本金，周期内最大回撤仍需逐日盯市才能观察。

回测结果仍受历史成分股覆盖、停牌/涨跌停成交假设、复权和数据缺失等影响。当前成交模型未模拟冲击成本、涨跌停无法成交、融资约束或容量限制。论文应报告这些限制，并避免将历史收益表述为未来收益保证。

### 特征归因

全局归因使用测试期样本的 Mean |SHAP| 排序，个股解释使用生成推荐时保存的同一组行业中性化模型特征。局部 SHAP 的 base value、贡献和最终输出均在 LightGBM 原始 log-odds 空间；前端将它们分开显示，概率估计仅作为单独的模型输出展示。

SHAP 描述模型如何使用特征，不代表因果关系。全局重要性衡量影响幅度，不给出单调方向；个股正负贡献也不能单独解释为投资理由。

## 实验结果与图表

不要把旧模型生成的指标当作当前代码的实验结论。运行训练流程后，`saved_models/training_report.json`、`evaluation_metrics.json`、`walk_forward.json` 和 `attribution.json` 是各自指标的结果来源。报告与图表脚本从这些产物读取数字，不再在 README 中维护一组可能过期的固定指标。

论文图表包括：

1. 训练期因子 IC 与 HAC t 值；
2. 测试集 NDCG@5、Precision@5 与 AUC 基线比较；
3. 测试集 Precision@K 与 NDCG@K 随推荐深度变化；
4. LightGBM 训练集与验证集 Binary Logloss 随迭代轮次的变化；
5. 滚动窗口 AUC 与 0.5 随机基线；
6. 滚动验证期策略与基准净值；
7. 不同市场状态下的策略与基准收益；
8. 测试集 SHAP summary beeswarm，展示特征贡献方向与样本差异。

损失曲线在训练页面的评测区展示，并由 `scripts/make_figures.py` 输出为论文图。验证损失用于观察拟合趋势；最终模型迭代轮数由训练集内部交叉验证确定，不用测试集损失选轮数。现有旧模型如果未记录逐轮结果，需运行一次完整训练后才会生成这张图。

图片保存在 `docs/figures/`。每张图应与同一训练批次的 JSON 结果配套归档，避免图表和模型产物来自不同实验批次。

## 主要产物

| 文件 | 内容 |
| --- | --- |
| `saved_models/selected_factors.json` | 训练期入选因子、筛选区间与筛选方式 |
| `saved_models/lgbm_market_classifier.pkl` | 模型、时序切分和评估结果 |
| `saved_models/evaluation_metrics.json` | 模型基线、截面排序指标及 Precision@K / NDCG@K 曲线 |
| `saved_models/backtest_result.json` | 测试区间 Top-K 回测 |
| `saved_models/walk_forward.json` | 滚动窗口验证及连续回测 |
| `saved_models/global_importance.json` | 全局 TreeSHAP 重要性 |
| `saved_models/shap_summary.json` | beeswarm 图使用的测试集 SHAP 与标准化特征值样本 |
| `saved_models/attribution.json` | 策略收益 Alpha/Beta 分析（有可用滚动回测时） |
| `saved_models/training_report.json` | 数据、标签、指标及历史股票池口径摘要 |
| `data/processed/realtime_recommendations.csv` | 最新截面分数、行情和 SHAP 模型特征输入 |

## 论文中需要说明的限制

- 原始模型分数是相对候选池均值的二分类排序信号，不是绝对上涨概率；独立验证期校准概率另列，校准不保证后续区间有效。A/B/C 是截面相对档位，不代表置信度。
- 如果没有历史 CSI 300 成分股生效期数据，历史回测存在幸存者偏差。
- 5 日收益信号噪声较高，必须同时报告单次测试区间、滚动窗口分布、基线和交易成本。
- SHAP 是预测模型的特征归因，不是因果解释。
- 回测成交假设较理想；应说明停牌、涨跌停、滑点、冲击成本及容量限制。

## 2026-10-27 修复与验证

- 工程页从真实训练结果读取指标，移除了固定 AUC、参数和风控仪表值。
- 推荐只使用同一行情日期，缺失日期不再回退；完整精度保存模型输入，发布时校验推荐分数与特征一致。
- 标签按全市场观测交易日历对齐；训练边界同时检查真实标签结束时间。技术指标固定使用 Pandas 实现。
- 训练按批次隔离，包含文件 SHA-256、源码摘要、依赖版本、数据区间与股票池限制；小样本 `--limit` 只生成预览，不激活为正式模型。
- 风控目前提供推荐等权集中度筛查和进程级手动熔断。实际持仓日亏损及回撤没有数据时显示未评估；重置口令由环境变量 `ALPHA_RISK_RESET_TOKEN` 配置。
- 自动调度器随 API 生命周期运行，默认暂停。启用后按 Asia/Shanghai 时间执行；交易日历无法确认时跳过并记录原因，不用工作日假定替代交易日历。
- 新增“实验诊断图表”：概率可靠性、每日与滚动 Rank IC、按平仓月份归属的收益热力图、SHAP 特征依赖图。均由本批次测试数据生成。

仅使用本地原始因子缓存重建并训练：

```powershell
python -m ml_pipeline.run_training --cached --scheme robust --k 10
```

缓存训练不会补充最新行情；推荐页日期和实验数据区间是实际覆盖范围。未经历史成分股回放的数据仍有幸存者偏差。DSR 缺少真实可比策略试验分布时显示未计算。

验证命令：

```powershell
python -m unittest discover -s tests -v
python scripts/verify_runtime.py
python scripts/verify_ui.py
cd frontend
npm run build
```

浏览器验证使用本机 Chrome/Edge 与 Node，无需新增 npm 测试依赖。大体积实验目录、当前批次指针和实时快照不纳入 Git；新克隆需要准备数据并训练，交付演示环境时可单独打包完整实验目录和指针。论文图表脚本已跟随当前批次读取数据。

## 选股与预测层

默认保留 LightGBM 为推荐排序模型；多因子排名作为独立对照，不把两者用未经验证的任意权重混合。

1. **规则筛选**：同日有效行情、当日有成交、至少 120 个有效历史交易日、当前名称不含风险警示标记；支持板块、行业、20 日平均成交额门槛和信号日近涨停过滤。返回候选数、通过数、排除数与具体原因。规则筛选仅作用当前快照，不重算历史回测。
2. **多因子排名**：只在训练期计算中性化因子的每日 Rank IC，确定方向与归一化绝对 IC 权重；当前截面用方向分位数加权得到 0–100 分。显示每个因子的方向、IC、权重、当日分位及贡献；缺失必要因子时不编造分数。
3. **机器学习预测**：LightGBM 预测未来 5 个市场交易日跑赢当日候选池均值的模型分数。模型输入和持久化训练/测试快照保持完整精度，推荐页默认按原始分数排序。
4. **概率校准**：在训练后独立的验证区间拟合单调 Platt 校准器，按日期等权；非负斜率约束保证不反转原始模型方向。若验证信号弱到斜率为 0，概率退回验证期基准比例并明确提示，不把它包装成高置信度预测。

推荐页提供 LightGBM / 多因子对照切换、当前结果 CSV 导出、规则计数、SHAP 解释和因子明细；移动端用单股摘要展示。SHAP 始终解释 LightGBM 原始 log-odds，校准后概率另列，不能把 SHAP 当成因果收益敏感度。

新增 `calibration_report.json` 保存验证拟合范围及测试期校准前后 Brier / ECE；诊断页同时展示两种可靠性曲线。校准方法和参数不根据测试效果挑选，测试指标变差时也保留报告。
