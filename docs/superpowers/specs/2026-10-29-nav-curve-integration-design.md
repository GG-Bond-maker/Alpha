# 样本外累计净值图表与超额区间功能集成设计方案

## 1. 意图与背景 (Intent & Why)

用户需要在系统前端 Web 界面合适的位置集成《累计净值（样本外，含双边成本）》对比图表，并实现与其配套的交互与量化展示功能。
用户特别要求：**“不一定是中证 500 基准，要从项目出发”**。这意味着不能生搬硬套外来截图的特定标签（如硬编码“中证500”或固定数值 12.16%/9.03%），而是必须紧密结合本项目当前的研究池（沪深300候选池/全样本等权基准）、实际回测模型参数（每期等权 Top-K、扣除双边摩擦佣金+印花税+滑点）、真实实验产物数据（`walk_forward.json` 中聚合的 `backtest_aggregated` 与 `backtest_result.json`），实现严谨的量化展示。

---

## 2. 目标与非目标 (Goals, Non-Goals & Anti-Goals)

### 目标 (Goals)
1. **核心位置挂载**：
   - **主位置**：在【滚动回测 (`WalkForwardView.vue`)】页面的“拼接净值（全窗口连续运行）”区块中，补齐缺失的连续累计净值走势大图。
   - **辅位置**：在【量化尽调研报弹窗 (`TearsheetModal.vue`)】中嵌入该图表，支持研报打印与导出。
2. **专业量化可视化（动态 ECharts）**：
   - 策略曲线与基准曲线对比显示；
   - **跑赢区间（青浅蓝）与跑输区间（浅粉红）填充带**：当策略高于基准时填充跑赢阴影，低于基准时填充跑输阴影；
   - **量化交互**：十字光标 Crosshair 悬浮 Tooltip（显示具体日期、策略净值、基准净值、超额收益差及状态）、时间范围滑动器（DataZoom）；
   - **指标卡与参数提示**：从项目实际数据动态读取策略年化、基准年化、超额年化、最大回撤、交易周期数及双边费率。
3. **真实性与双模切换**：
   - **模式 1（默认）：项目实测连续净值（动态 ECharts）**：数据源自当前模型批次的真实滚动拼接回测；
   - **模式 2：实证参考快照（原图）**：可一键切换查看原版高清图（含灯箱全屏预览与说明），满足多重历史对照需求。
4. **前端构建验证**：确保 Vue 组件无编译警告、无类型错误，通过 `npm run build`。

### 非目标 (Non-Goals)
- 不修改底层机器学习训练流程或重新训练模型。
- 不更改已有 API 路由契约，纯前端充分复用已有 `/evaluation/walk-forward` 接口数据。

### 反目标 (Anti-Goals)
- 严禁硬编码静态数值伪造当前实验的年化收益和基准名称。
- 严禁使用不可缩放的低质量切图替换交互界面。

---

## 3. 方案对比与选择 (Approaches Considered & Selected)

在前期沟通中探讨了三种方案：
1. **方案一（已选定）：滚动回测双模集成**
   - 放置在 `WalkForwardView.vue`（补齐该模块视觉空白）与 `TearsheetModal.vue`。
   - 结合用户反馈“从项目出发”，采用动态数据驱动 + 双模切换（实测动态图 / 参考原图）。
2. **方案二：回测主页独立基准对抗卡片**
   - 放置在 `BacktestView.vue`。权衡：回测页已有单期净值与水下回撤图，略显拥挤，未解决滚动回测无图的问题。
3. **方案三：纯静态图片嵌入 + 灯箱**
   - 权衡：缺乏动态数据交互和时间区间钻取能力。

**选定方案**：方案一（增强版，紧密依托项目实际数据驱动基准与指标）。

---

## 4. 详细设计与实现细节 (Detailed Design)

### 4.1 数据映射与基准定义 (Project-Grounded Benchmark)
- 数据源：`api.getWalkForward()` $\rightarrow$ `data.backtest_aggregated`
  - 策略净值：`aggregated.strategy.nav`（数组）
  - 基准净值：`aggregated.benchmark.nav`（数组）
  - 时间序列：`aggregated.dates`（数组，日期字符串）
  - 策略参数：`aggregated.params`（含 selection 模式、买入卖出费率等）
  - 核心指标：
    - 策略年化收益率：`aggregated.strategy.annualized_return`
    - 基准年化收益率：`aggregated.benchmark.annualized_return`
    - 超额年化收益率：`aggregated.excess.annualized_return`
- 基准名称动态化：根据项目的股票池配置与回测参数，动态命名为 `全样本等权基准 (年化 X.XX%)`，不硬编码“中证500”。

### 4.2 ECharts 跑赢/跑输填色算法实现 (Win/Lag Band Area)
利用 ECharts 的 `custom` 系列或多段叠加阴影：
- 策略净值线：深蓝色 `#2563eb`，线宽 2.5px。
- 基准净值线：深褐红色 `#b91c1c` 或 `#c2410c`，线宽 2px。
- 填充区域：
  - 计算策略与基准在每个周期的差值 $\Delta_t = \text{nav}_{\text{strat}, t} - \text{nav}_{\text{bench}, t}$。
  - 通过 ECharts `renderItem` 自定义多边形算法，在 $\Delta_t \ge 0$ 的区间绘制浅青色块（`rgba(186, 230, 253, 0.45)`，跑赢）；在 $\Delta_t < 0$ 的区间绘制浅粉色块（`rgba(254, 202, 202, 0.45)`，跑输）。
  - 若相邻两点发生穿越（$\Delta_t \cdot \Delta_{t+1} < 0$），线性插值求出交点坐标进行精细三角形分割，确保填色无锯齿、不溢出。

### 4.3 界面与交互控制 (UI & Controls)
- 标头操作栏：
  - 图例：策略（含年化收益）、基准（含年化收益）、跑赢区间标识、跑输区间标识。
  - 模式切换：`[ 📊 动态交互图表 ]` / `[ 🖼️ 参考实证原图 ]` 切换胶囊按钮。
  - 缩放控制：底部集成 DataZoom 游标滑块，支持拖拽和区域放大。
- 全屏灯箱：点击原图可弹出高清 Modal 查看并支持保存。

---

## 5. 待构建任务清单 (What's Left to the Builder)
1. 在 `frontend/src/components/WalkForwardView.vue` 中集成该图表组件与双模视图。
2. 在 `frontend/src/components/TearsheetModal.vue` 中同步更新该图表展示。
3. 添加必要的 CSS 样式与响应式布局。
4. 运行 `npm run build` 和前端自动化测试验证无回归。
