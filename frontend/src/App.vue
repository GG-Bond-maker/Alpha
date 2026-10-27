<template>
  <div class="app-shell">
    <!-- ============ 侧边栏 ============ -->
    <aside class="sidebar" :class="{ 'is-collapsed': collapsed }">
      <div class="sidebar-brand">
        <div class="sidebar-brand-icon">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline>
            <polyline points="16 7 22 7 22 13"></polyline>
          </svg>
        </div>
        <div class="sidebar-brand-text">
          <div class="sidebar-brand-title">股票推荐系统</div>
          <div class="sidebar-brand-sub">LightGBM + 特征归因</div>
        </div>
      </div>

      <nav class="sidebar-nav">
        <div v-for="group in navGroups" :key="group.label" class="nav-group">
          <div class="nav-group-label">{{ group.label }}</div>
          <button
            v-for="item in group.items"
            :key="item.key"
            class="nav-item"
            :class="{ 'is-active': currentTab === item.key }"
            :title="item.label"
            @click="switchTab(item.key)"
          >
            <span class="nav-item-icon" v-html="item.icon"></span>
            <span class="nav-item-label">{{ item.label }}</span>
          </button>
        </div>
      </nav>

      <div class="sidebar-footer">
        <button class="sidebar-toggle" @click="collapsed = !collapsed"
                :title="collapsed ? '展开侧边栏' : '收起侧边栏'">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline v-if="collapsed" points="9 18 15 12 9 6"></polyline>
            <polyline v-else points="15 18 9 12 15 6"></polyline>
          </svg>
          <span v-if="!collapsed">收起</span>
        </button>
      </div>
    </aside>

    <!-- ============ 主区域 ============ -->
    <div class="main-area" :class="{ 'is-expanded': collapsed }">
      <header class="topbar">
        <div>
          <div class="topbar-title">{{ currentMeta.title }}</div>
          <div class="topbar-desc">{{ currentMeta.desc }}</div>
        </div>
        <div class="topbar-actions">
          <!-- 实时风控守卫胶囊 -->
          <button
            class="risk-capsule"
            :class="isRiskTriggered ? 'is-halted' : 'is-unassessed'"
            :title="isRiskTriggered ? '风控已熔断，点击打开风控驾驶舱' : '真实持仓风险未完整评估，点击查看筛查范围'"
            @click="showRiskCockpit = true"
          >
            <span class="risk-dot"></span>
            <span class="risk-text">{{ isRiskTriggered ? '🚨 紧急风控熔断中' : '持仓风险未评估' }}</span>
          </button>

          <span class="source-tag" :class="dataSourceClass">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="9"></circle>
            </svg>
            {{ dataSourceLabel }}
          </span>
          <button class="btn btn-outline btn-sm" @click="refreshCurrent" :disabled="loading">
            {{ loading ? '加载中' : '刷新' }}
          </button>
        </div>
      </header>

      <main class="content">
        <div v-if="experiment" class="experiment-status" :class="{ 'is-legacy': experiment.status !== 'complete' }" role="status">
          <template v-if="experiment.status === 'complete'">
            <strong>实验批次 {{ experiment.run_id }}</strong>
            <span>标签样本截至 {{ experiment.panel?.date_range?.[1]?.slice(0, 10) }} · {{ experiment.panel?.stocks }} 只股票</span>
            <span v-if="!experiment.panel?.point_in_time_universe">当前成分股回溯，存在幸存者偏差</span>
          </template>
          <template v-else>{{ experiment.message }}</template>
        </div>
        <section v-if="currentTab === 'home'">
          <HomeDashboardView @switchTab="switchTab" @viewKline="viewKline" />
        </section>

        <section v-else-if="currentTab === 'recommend'">
          <RecommendationView ref="recommendationViewRef" :key="'recommend-' + refreshKey"
            @explain="showExplain" @viewKline="viewKline" @risk="riskStatus = $event" />
        </section>

        <section v-else-if="currentTab === 'kline'">
          <StockKlineView :key="'kline-' + refreshKey" ref="klineViewRef" @switchTab="switchTab" />
        </section>

        <section v-else-if="currentTab === 'manage'">
          <StockManageView :key="'manage-' + refreshKey" @viewKline="viewKline" @explain="showExplain" />
        </section>

        <section v-else-if="currentTab === 'global'">
          <GlobalExplainView :key="'global-' + refreshKey" />
        </section>

        <section v-else-if="currentTab === 'metrics'">
          <MetricsView :key="'metrics-' + refreshKey" />
        </section>

        <section v-else-if="currentTab === 'backtest'">
          <BacktestView :key="'backtest-' + refreshKey" />
        </section>

        <section v-else-if="currentTab === 'factors'">
          <FactorDiagnosisView :key="'factors-' + refreshKey" />
        </section>

        <section v-else-if="currentTab === 'walkforward'">
          <WalkForwardView :key="'walkforward-' + refreshKey" />
        </section>

        <section v-else-if="currentTab === 'attribution'">
          <AttributionView :key="'attribution-' + refreshKey" />
        </section>

        <section v-else-if="currentTab === 'diagnostics'">
          <ExperimentDiagnosticsView :key="'diagnostics-' + refreshKey" />
        </section>

        <section v-else-if="currentTab === 'engineering'">
          <DataEngineeringView :key="'engineering-' + refreshKey" @switchTab="switchTab" />
        </section>
      </main>
    </div>

    <ExplainModal ref="explainModalRef" />
    <RiskCockpitModal
      :visible="showRiskCockpit"
      :status-data="riskStatus"
      @close="showRiskCockpit = false"
      @refresh="fetchRiskStatus"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, defineAsyncComponent } from 'vue'
import { api } from './api'
import ExplainModal from './components/ExplainModal.vue'
import RiskCockpitModal from './components/RiskCockpitModal.vue'
const GlobalExplainView = defineAsyncComponent(() => import('./components/GlobalExplainView.vue'))
const MetricsView = defineAsyncComponent(() => import('./components/MetricsView.vue'))
const StockKlineView = defineAsyncComponent(() => import('./components/StockKlineView.vue'))
const HomeDashboardView = defineAsyncComponent(() => import('./components/HomeDashboardView.vue'))
const StockManageView = defineAsyncComponent(() => import('./components/StockManageView.vue'))
const DataEngineeringView = defineAsyncComponent(() => import('./components/DataEngineeringView.vue'))
const BacktestView = defineAsyncComponent(() => import('./components/BacktestView.vue'))
const FactorDiagnosisView = defineAsyncComponent(() => import('./components/FactorDiagnosisView.vue'))
const WalkForwardView = defineAsyncComponent(() => import('./components/WalkForwardView.vue'))
const AttributionView = defineAsyncComponent(() => import('./components/AttributionView.vue'))

const ExperimentDiagnosticsView = defineAsyncComponent(() => import('./components/ExperimentDiagnosticsView.vue'))
const experiment = ref(null)
const fetchExperiment = async () => {
  try { experiment.value = (await api.getExperiment()).data }
  catch { experiment.value = { status: 'unknown', message: '实验批次信息加载失败，请刷新重试。' } }
}

const RecommendationView = defineAsyncComponent(() => import('./components/RecommendationView.vue'))
const recommendationViewRef = ref(null)
const collapsed = ref(false)
const currentTab = ref('home')
const loading = ref(false)
const refreshKey = ref(0)

const showRiskCockpit = ref(false)
const riskStatus = ref(null)
const isRiskTriggered = computed(() => Boolean(riskStatus.value?.triggered))

const fetchRiskStatus = async () => {
  try {
    const res = await api.getRiskStatus()
    riskStatus.value = res.data
  } catch (err) {
    console.error('获取风控状态失败:', err)
  }
}

const explainModalRef = ref(null)
const klineViewRef = ref(null)

const svg = (paths) =>
  '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + paths + '</svg>'

// 导航按论文逻辑分组：推荐主线 -> 标的分析 -> 实验验证 -> 系统运维
const navGroups = [
  {
    label: '推荐主线',
    items: [
      { key: 'home', label: '全景概览', icon: svg('<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>') },
      { key: 'recommend', label: 'Top-K 选股推荐', icon: svg('<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>') },
      { key: 'global', label: '全局特征归因', icon: svg('<path d="M3 3v18h18"/><rect x="7" y="10" width="3" height="7"/><rect x="12" y="6" width="3" height="11"/><rect x="17" y="13" width="3" height="4"/>') },
    ],
  },
  {
    label: '标的分析',
    items: [
      { key: 'kline', label: '行情走势', icon: svg('<path d="M3 17l5-6 4 4 6-8"/><circle cx="21" cy="7" r="1.5"/>') },
      { key: 'manage', label: '股票池管理', icon: svg('<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>') },
    ],
  },
  {
    label: '实验验证',
    items: [
      { key: 'factors', label: '因子有效性检验', icon: svg('<path d="M3 3v18h18"/><path d="M7 16l4-5 3 3 5-7"/>') },
      { key: 'metrics', label: '算法评测对比', icon: svg('<path d="M9 3h6v6H9z"/><path d="M3 21h18"/><path d="M6 21V9H3v12"/><path d="M21 21V9h-3v12"/>') },
      { key: 'backtest', label: '组合回测', icon: svg('<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 15"/>') },
      { key: 'walkforward', label: '滚动窗口验证', icon: svg('<path d="M3 3v18h18"/><path d="M6 15l4-5 4 3 5-7"/><circle cx="6" cy="15" r="1.2"/><circle cx="10" cy="10" r="1.2"/><circle cx="14" cy="13" r="1.2"/><circle cx="19" cy="6" r="1.2"/>') },
      { key: 'diagnostics', label: '实验诊断图表', icon: svg('<path d="M3 3v18h18"/><path d="M7 15l4-7 4 4 5-8"/>') },
      { key: 'attribution', label: '业绩归因', icon: svg('<circle cx="12" cy="12" r="9"/><path d="M12 3v9l6 3"/>') },
    ],
  },
  {
    label: '系统运维',
    items: [
      { key: 'engineering', label: '数据与模型', icon: svg('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/>') },
    ],
  },
]

const TAB_META = {
  home: { title: '全景概览', desc: '推荐系统运行状态、核心指标与最新截面摘要' },
  recommend: { title: 'Top-K 选股推荐', desc: '按截面排序输出候选标的，支持板块与行业筛选' },
  global: { title: '全局特征归因', desc: '基于 TreeSHAP 的沪深300研究池特征重要性排序' },
  kline: { title: '行情走势', desc: '日 K 线、均线系统与成交量联动分析' },
  manage: { title: '股票池管理', desc: '标的全景检索、评级分布与重点关注管理' },
  factors: { title: '因子有效性检验', desc: 'IC / ICIR / t 值与分层收益单调性检验' },
  metrics: { title: '算法评测对比', desc: 'NDCG / Precision / AUC 基线与本文方法对比' },
  backtest: { title: '组合回测', desc: 'Top-K 等权组合净值、超额收益与风险指标' },
  walkforward: { title: '滚动窗口验证', desc: '逐窗口 AUC 分布与因子跨窗口稳定性' },
  attribution: { title: '业绩归因', desc: 'Alpha / Beta 分解、显著性检验与分市场状态表现' },
  diagnostics: { title: '实验诊断图表', desc: '概率可靠性、截面 Rank IC、平仓月收益与 SHAP 特征依赖' },
  engineering: { title: '数据与模型', desc: '数据更新、模型重训与运行日志' },
}

const currentMeta = computed(() => TAB_META[currentTab.value] || { title: '', desc: '' })

const dataSourceLabel = computed(() => experiment.value?.status === 'complete' ? '实验批次已校验' : '历史产物待重训')
const dataSourceClass = computed(() => experiment.value?.status === 'complete' ? 'is-real' : 'is-synthetic')

const switchTab = (tab) => {
  currentTab.value = tab
  if (tab === 'kline') {
    nextTick(() => klineViewRef.value?.handleResize?.())
  }
}

const refreshCurrent = async () => {
  await fetchExperiment()
  loading.value = true
  try {
    if (currentTab.value === 'recommend') {
      await recommendationViewRef.value?.refresh?.()
    } else {
      refreshKey.value++
    }
  } finally {
    loading.value = false
  }
}

const viewKline = (item) => {
  currentTab.value = 'kline'
  nextTick(async () => {
    const view = klineViewRef.value
    if (!view) return
    if (typeof view.loadStockByCode === 'function') {
      await view.loadStockByCode(item)
    }
  })
}

const showExplain = async (item) => {
  const rawCode = item.stock_code || item.code || ''
  const pureCode = String(rawCode).split('.')[0]
  try {
    const res = await api.getStockExplanation(pureCode, item.update_date || item.date || undefined)
    explainModalRef.value?.openModal(res.data)
  } catch (err) {
    alert('获取归因失败: ' + err.message)
  }
}

onMounted(() => {
  fetchExperiment()
  fetchRiskStatus()
})
</script>

<style scoped>
.risk-capsule.is-unassessed { background: #f8fafc; border-color: #cbd5e1; color: #475569; }
.risk-capsule.is-unassessed .risk-dot { background: #64748b; }
.experiment-status { display: flex; flex-wrap: wrap; gap: 6px 20px; margin: 0 0 18px; padding: 12px 16px; border: 1px solid #cbd5e1; border-radius: 12px; background: #fff; color: #334155; font-size: 13px; line-height: 1.6; }
.experiment-status.is-legacy { background: #fffbeb; border-color: #d97706; color: #78350f; }

.text-warn {
  color: var(--warning);
  font-weight: 600;
}

/* 顶部风控守卫胶囊 */
.risk-capsule {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s ease;
  user-select: none;
}

.risk-capsule.is-healthy {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #166534;
}

.risk-capsule.is-healthy:hover {
  background: #dcfce7;
}

.risk-capsule.is-healthy .risk-dot {
  width: 7px;
  height: 7px;
  background: #16a34a;
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.2);
}

.risk-capsule.is-halted {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
  animation: pulseRisk 2s infinite;
}

.risk-capsule.is-halted:hover {
  background: #fee2e2;
}

.risk-capsule.is-halted .risk-dot {
  width: 7px;
  height: 7px;
  background: #dc2626;
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.2);
}

@keyframes pulseRisk {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.02); }
}

/* 推荐页面熔断告警横幅 */
.risk-halt-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  margin-bottom: 16px;
  cursor: pointer;
  transition: opacity 0.2s;
  padding: 12px 18px;
}

.risk-halt-banner:hover {
  opacity: 0.95;
}

.risk-banner-title {
  font-weight: 700;
  font-size: 14px;
}

.risk-banner-desc {
  font-size: 13px;
  margin-top: 4px;
  color: #b91c1c;
  line-height: 1.5;
}

/* 推荐表格关注星号与排序表头 */
.star-toggle-btn {
  background: transparent;
  border: none;
  font-size: 17px;
  cursor: pointer;
  color: #cbd5e1;
  transition: all 0.15s ease;
  padding: 0 4px;
  line-height: 1;
}

.star-toggle-btn:hover {
  transform: scale(1.25);
  color: #f59e0b;
}

.star-toggle-btn.is-active {
  color: #f59e0b;
}

.sortable-th {
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s ease;
}

.sortable-th:hover {
  background: var(--slate-100, #f1f5f9);
}

.sort-icon {
  font-size: 10px;
  margin-left: 2px;
  color: var(--slate-400);
}

.sortable-th.is-sorted .sort-icon {
  color: var(--primary);
  font-weight: bold;
}

/* 行业暴露与持仓集中度看板 (ML4T Exposure Analysis) */
.exposure-card {
  margin-bottom: 16px;
  padding: 16px 20px;
  background: #ffffff;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
}

.exposure-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.exposure-title-group {
  flex: 1;
}

.exposure-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--slate-800, #1e293b);
  display: flex;
  align-items: center;
  gap: 6px;
}

.exposure-icon {
  font-size: 16px;
}

.exposure-desc {
  font-size: 12px;
  color: var(--slate-500, #64748b);
  margin-top: 3px;
}

.exposure-status-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 20px;
  white-space: nowrap;
}

.exposure-status-badge.is-healthy {
  background: #ecfdf5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}

.exposure-status-badge.is-warn {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}

.exposure-bar-wrap {
  width: 100%;
  height: 12px;
  background: #f1f5f9;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  margin-bottom: 14px;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.06);
}

.exposure-bar-seg {
  height: 100%;
  transition: width 0.3s ease;
}

.exposure-footer {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.exposure-metrics-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.metric-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #f8fafc;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  font-size: 12px;
}

.metric-pill .lbl {
  color: #64748b;
}

.metric-pill .val {
  font-weight: 600;
  color: #0f172a;
}

.exposure-tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.sector-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 4px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  transition: all 0.15s ease;
}

.sector-tag:hover {
  border-color: #94a3b8;
  background: #f1f5f9;
}

.sector-tag.tag-concentrated {
  background: #fef2f2;
  border-color: #fca5a5;
  color: #991b1b;
}

.sector-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.tag-flag {
  font-size: 10px;
  padding: 1px 4px;
  background: #ef4444;
  color: #ffffff;
  border-radius: 3px;
  font-weight: 700;
  margin-left: 2px;
}
</style>
