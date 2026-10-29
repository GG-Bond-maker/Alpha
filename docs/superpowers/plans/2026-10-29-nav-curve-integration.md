# 样本外累计净值走势与超额区间图表集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在系统前端 Web 界面（滚动回测 `WalkForwardView.vue` 与量化尽调研报 `TearsheetModal.vue`）中落地《样本外累计净值走势与超额区间对比》看板，并基于项目真实数据和双模交互（动态 ECharts / 原图实证）实现对应功能。

**Architecture:** 
1. 数据层：前端复用 `/api/v1/evaluation/walk-forward` 接口中 `backtest_aggregated` 的真实策略净值、基准净值和日期序列，动态计算年化收益与超额区间。
2. 可视化层：使用 ECharts 实现高精度的双线走势与跑赢（青蓝）/跑输（浅粉）多边形区域填色（Band Filling），支持 DataZoom 缩放与 Crosshair 穿透 Tooltip。
3. 交互层：提供“动态交互图表 / 参考实证原图”双模无缝切换与全屏灯箱放大查看。

**Tech Stack:** Vue 3 (Composition API, `<script setup>`), ECharts 5.x, CSS3 Flexbox/Grid, Vite.

**Spec:** `docs/superpowers/specs/2026-10-29-nav-curve-integration-design.md`

## Global Constraints

- 基准名称与数值必须从项目实际数据（沪深300候选池/全样本等权基准）动态读取，不得硬编码中证500或假数据。
- 策略费率严格依据当前配置（如 35bp 双边摩擦或项目实际 buy_cost / sell_cost）。
- 保持既有前端页面风格一致，不破坏其他 Tab 功能与样式。
- 通过 `npm run build` 打包构建，保证零构建错误。

## Review Focus

- 空数据或加载中状态下图表是否健壮防崩；
- 策略净值与基准净值序列长度不一致或只有 1 个周期的边界处理；
- 跑赢/跑输阴影计算在两线频繁交叉时插值点是否无缝平滑；
- 双模切换（ECharts $\leftrightarrow$ 原版实证图）状态与图表 resize 是否正常；
- TearsheetModal 弹窗打开时图表自适应尺寸渲染。

---

### Task 1: 样式支持与静态实证原图资产确认

**Files:**
- Asset: `frontend/public/images/nav_curve_reference.png`
- Modify: `frontend/src/style.css`

**Interfaces:**
- Consumes: Static asset `/images/nav_curve_reference.png`
- Produces: CSS classes for dual-mode toggle, chart legends, lightbox, and band statistics.

- [ ] **Step 1: 检查静态图片资产有效性与尺寸**
  确保 `frontend/public/images/nav_curve_reference.png` 存在且可通过静态路径访问。

- [ ] **Step 2: 在 `frontend/src/style.css` 中添加双模图表与跑赢/跑输区间专属样式**
  包含 `.nav-chart-wrapper`, `.chart-mode-pill`, `.band-legend-item`, `.band-tag-win`, `.band-tag-lag`, `.nav-reference-img`, `.nav-lightbox-modal` 等类。

- [ ] **Step 3: 运行验证**
  检查 CSS 语法与图片存在性。

---

### Task 2: 在 `WalkForwardView.vue` 中集成高阶动态净值与超额区间图表

**Files:**
- Modify: `frontend/src/components/WalkForwardView.vue`

**Interfaces:**
- Consumes: `data.backtest_aggregated` (contains `strategy.nav`, `benchmark.nav`, `dates`, `params`) from `/api/v1/evaluation/walk-forward`
- Produces: Interactive ECharts chart with win/lag polygon area fills, DataZoom, dynamic benchmark name/metrics, and dual-mode toggle.

- [ ] **Step 1: 扩展模板，在 `agg-block` 下方增加累计净值大图容器与控制器**
  加入：
  - 模式切换胶囊按钮（`📊 动态交互走势` / `🖼️ 参考实证原图`）；
  - 动态标头：展示当前实验真实策略年化、项目实际基准名称与年化、超额年化、双边摩擦成本；
  - ECharts 容器挂载点与原图实证挂载点；
  - 跑赢/跑输区间指示图例。

- [ ] **Step 2: 实现 ECharts 跑赢/跑输双色阴影带算法**
  计算策略与基准净值的相对差值：
  - 当策略 $\ge$ 基准时，生成青蓝色透明遮罩；
  - 当策略 $<$ 基准时，生成浅粉红色透明遮罩；
  - 对交叉点进行线性插值，生成平滑边界。

- [ ] **Step 3: 配置 ECharts 折线、Tooltip 与 DataZoom**
  - 策略线：深蓝 `#2563eb`；
  - 基准线：褐红 `#c2410c`（动态显示项目基准名称与年化，如 `基准（等权全样本，年化 5.79%）`）；
  - Crosshair Tooltip 穿透，显示调仓日、两线净值、超额收益与跑赢状态；
  - 底部配置 DataZoom 时间轴滑动器。

- [ ] **Step 4: 添加原图放大预览 Lightbox 交互**
  支持点击“参考实证原图”时弹出全屏灯箱，查看原始实证图。

- [ ] **Step 5: 验证 `WalkForwardView.vue` 渲染**
  测试页面加载、数据刷新与模式切换。

---

### Task 3: 在 `TearsheetModal.vue` 中同步增强累计净值与超额区间展现

**Files:**
- Modify: `frontend/src/components/TearsheetModal.vue`

**Interfaces:**
- Consumes: `backtest` prop (or aggregated data)
- Produces: Integrated cumulative NAV factsheet section supporting print and preview.

- [ ] **Step 1: 在 `TearsheetModal.vue` 增加“样本外长周期累计净值与基准对照”章节**
  展示项目真实基准与策略走势指标对比卡片，并提供实证图谱/交互缩略图。

- [ ] **Step 2: 保持打印与 PDF 导出兼容**
  确保在打印媒体查询（`@media print`）下，图表与指标清晰完整呈现，无换页断裂。

- [ ] **Step 3: 验证弹窗打开与关闭交互**
  确保弹窗打开时图表尺寸正常自适应。

---

### Task 4: 前端构建与全量端到端验证

**Files:**
- Check: `frontend/dist`
- Verify: `scripts/verify_ui.py` (or Node build)

- [ ] **Step 1: 执行前端构建**
  Run: `cd frontend; npm run build`
  Expected: Build succeeds with 0 errors.

- [ ] **Step 2: 执行运行时校验**
  Run: `python scripts/verify_ui.py`
  Expected: All checks pass.
