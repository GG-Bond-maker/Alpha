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
        <section v-if="currentTab === 'home'">
          <HomeDashboardView @switchTab="switchTab" @viewKline="viewKline" />
        </section>

        <section v-else-if="currentTab === 'recommend'">
          <div class="filter-bar">
            <div class="filter-field">
              <label class="filter-label">截面日期</label>
              <select v-model="selectedDate" @change="fetchRecommendations" class="form-select">
                <option v-for="d in datesList" :key="d" :value="d">{{ d }}</option>
              </select>
            </div>
            <div class="filter-field">
              <label class="filter-label">板块</label>
              <select v-model="selectedBoard" @change="fetchRecommendations" class="form-select">
                <option value="全部">全部板块</option>
                <option value="主板">主板</option>
                <option value="创业板">创业板</option>
                <option value="科创板">科创板</option>
                <option value="北交所">北交所</option>
              </select>
            </div>
            <div class="filter-field">
              <label class="filter-label">推荐数量</label>
              <select v-model="selectedK" @change="fetchRecommendations" class="form-select">
                <option :value="5">Top 5</option>
                <option :value="10">Top 10</option>
                <option :value="15">Top 15</option>
                <option :value="20">Top 20</option>
              </select>
            </div>
            <div class="filter-field">
              <label class="filter-label">行业</label>
              <select v-model="selectedIndustry" @change="fetchRecommendations" class="form-select">
                <option value="全部">全部行业</option>
                <option v-for="ind in industryList" :key="ind" :value="ind">{{ ind }}</option>
              </select>
            </div>
            <button class="btn btn-success" style="margin-left: auto;" @click="handleExportExcel">
              导出 Excel
            </button>
          </div>

          <div class="card">
            <div class="card-header">
              <div>
                <div class="card-title">推荐清单 (Top-{{ selectedK }})</div>
                <div class="card-subtitle">
                  候选标的 <strong>{{ totalCandidates }}</strong> 只 ·
                  截面分档 A 前10% / B 随后20% / C 其余
                </div>
              </div>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style="width: 64px;">排位</th>
                    <th>代码</th>
                    <th>名称</th>
                    <th>板块</th>
                    <th>行业</th>
                    <th>评级</th>
                    <th>跑赢候选池均值概率</th>
                    <th>涨停</th>
                    <th>收盘价</th>
                    <th>涨跌幅</th>
                    <th>RSI14</th>
                    <th>MACD</th>
                    <th style="text-align: center;">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="loading">
                    <td colspan="13">
                      <div class="loading-state">
                        <div class="spinner"></div>
                        正在计算截面排序...
                      </div>
                    </td>
                  </tr>
                  <tr v-else-if="stockList.length === 0">
                    <td colspan="13">
                      <div class="empty-state">
                        <div class="empty-state-title">暂无推荐结果</div>
                        <div class="empty-state-desc">请调整筛选条件或点击刷新</div>
                      </div>
                    </td>
                  </tr>
                  <tr v-for="item in stockList" :key="item.stock_code">
                    <td>
                      <span class="badge" :class="rankBadgeClass(item.predicted_rank)">
                        {{ String(item.predicted_rank || 0).padStart(2, '0') }}
                      </span>
                    </td>
                    <td><code class="code-font">{{ item.stock_code }}</code></td>
                    <td><strong>{{ item.stock_name }}</strong></td>
                    <td><span class="badge badge-silver">{{ item.board || '主板' }}</span></td>
                    <td class="text-muted">{{ item.industry || '综合' }}</td>
                    <td>
                      <span :class="'badge-rating-' + (item.recommend_rating || 'c').toLowerCase()">
                        {{ item.recommend_rating }} 级
                      </span>
                    </td>
                    <td>
                      <div class="prob-bar">
                        <span :class="probClass(item.probability)">
                          {{ (item.probability * 100).toFixed(1) }}%
                        </span>
                        <div class="prob-bar-track">
                          <div class="prob-bar-fill"
                               :style="{ width: Math.min(100, item.probability * 100) + '%', background: probColor(item.probability) }">
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span v-if="item.is_limit_up === '是'" class="badge-limit-up">涨停</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td>{{ item.close_price != null ? '¥' + item.close_price : '—' }}</td>
                    <td :class="(item.pct_chg || 0) >= 0 ? 'text-pos' : 'text-neg'">
                      {{ (item.pct_chg || 0) >= 0 ? '+' : '' }}{{ item.pct_chg || 0 }}%
                    </td>
                    <td>{{ item.rsi14 != null ? item.rsi14.toFixed(1) : '—' }}</td>
                    <td :class="(item.macd || 0) >= 0 ? 'text-pos' : 'text-neg'">
                      {{ item.macd != null ? item.macd.toFixed(3) : '—' }}
                    </td>
                    <td style="text-align: center; white-space: nowrap;">
                      <button class="btn btn-outline btn-sm" @click="viewKline(item)">K线</button>
                      <button class="btn btn-primary btn-sm" style="margin-left: 6px;" @click="showExplain(item)">
                        归因
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section v-else-if="currentTab === 'kline'">
          <StockKlineView ref="klineViewRef" @switchTab="switchTab" />
        </section>

        <section v-else-if="currentTab === 'manage'">
          <StockManageView @viewKline="viewKline" @explain="showExplain" />
        </section>

        <section v-else-if="currentTab === 'global'">
          <GlobalExplainView />
        </section>

        <section v-else-if="currentTab === 'metrics'">
          <MetricsView />
        </section>

        <section v-else-if="currentTab === 'backtest'">
          <BacktestView />
        </section>

        <section v-else-if="currentTab === 'factors'">
          <FactorDiagnosisView />
        </section>

        <section v-else-if="currentTab === 'walkforward'">
          <WalkForwardView />
        </section>

        <section v-else-if="currentTab === 'attribution'">
          <AttributionView />
        </section>

        <section v-else-if="currentTab === 'engineering'">
          <DataEngineeringView @switchTab="switchTab" />
        </section>
      </main>
    </div>

    <ExplainModal ref="explainModalRef" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { api } from './api'
import ExplainModal from './components/ExplainModal.vue'
import GlobalExplainView from './components/GlobalExplainView.vue'
import MetricsView from './components/MetricsView.vue'
import StockKlineView from './components/StockKlineView.vue'
import HomeDashboardView from './components/HomeDashboardView.vue'
import StockManageView from './components/StockManageView.vue'
import DataEngineeringView from './components/DataEngineeringView.vue'
import BacktestView from './components/BacktestView.vue'
import FactorDiagnosisView from './components/FactorDiagnosisView.vue'
import WalkForwardView from './components/WalkForwardView.vue'
import AttributionView from './components/AttributionView.vue'

const collapsed = ref(false)
const currentTab = ref('home')
const datesList = ref([])
const selectedDate = ref('')
const selectedBoard = ref('全部')
const selectedK = ref(10)
const selectedIndustry = ref('全部')
const totalCandidates = ref(0)
const stockList = ref([])
const loading = ref(false)

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
  global: { title: '全局特征归因', desc: '基于 TreeSHAP 的全市场特征重要性排序' },
  kline: { title: '行情走势', desc: '日 K 线、均线系统与成交量联动分析' },
  manage: { title: '股票池管理', desc: '标的全景检索、评级分布与重点关注管理' },
  factors: { title: '因子有效性检验', desc: 'IC / ICIR / t 值与分层收益单调性检验' },
  metrics: { title: '算法评测对比', desc: 'NDCG / Precision / AUC 基线与本文方法对比' },
  backtest: { title: '组合回测', desc: 'Top-K 等权组合净值、超额收益与风险指标' },
  walkforward: { title: '滚动窗口验证', desc: '逐窗口 AUC 分布与因子跨窗口稳定性' },
  attribution: { title: '业绩归因', desc: 'Alpha / Beta 分解、显著性检验与分市场状态表现' },
  engineering: { title: '数据与模型', desc: '数据更新、模型重训与运行日志' },
}

const currentMeta = computed(() => TAB_META[currentTab.value] || { title: '', desc: '' })

const industryList = [
  '食品饮料', '医药生物', '电子', '电力设备', '计算机', '非银金融', '银行', '汽车',
  '机械设备', '国防军工', '通信', '基础化工', '有色金属', '家用电器', '公用事业',
  '交通运输', '石油石化', '建筑装饰', '建筑材料', '商贸零售', '房地产', '传媒',
  '煤炭', '农林牧渔', '钢铁', '环保', '美容护理',
]

const dataSourceLabel = computed(() => (stockList.value.length > 0 ? '真实行情数据' : '等待数据'))
const dataSourceClass = computed(() => (stockList.value.length > 0 ? 'is-real' : 'is-synthetic'))

const rankBadgeClass = (rank) => {
  if (rank === 1) return 'badge-gold'
  if (rank === 2) return 'badge-silver'
  if (rank === 3) return 'badge-bronze'
  return 'badge-blue'
}

const probColor = (p) => (p >= 0.5 ? '#10b981' : '#ef4444')
const probClass = (p) => (p >= 0.5 ? 'text-pos' : 'text-neg')

const switchTab = (tab) => {
  currentTab.value = tab
  if (tab === 'recommend' && stockList.value.length === 0) {
    fetchRecommendations()
  } else if (tab === 'kline') {
    nextTick(() => klineViewRef.value?.handleResize?.())
  }
}

const refreshCurrent = () => {
  if (currentTab.value === 'recommend') fetchRecommendations()
  else window.location.reload()
}

const loadDates = async () => {
  try {
    const res = await api.getDates()
    datesList.value = res.data || []
    if (datesList.value.length > 0) {
      selectedDate.value = datesList.value[datesList.value.length - 1]
    }
  } catch (err) {
    console.error('加载截面日期失败:', err)
  }
  await fetchRecommendations()
}

const fetchRecommendations = async () => {
  loading.value = true
  try {
    const res = await api.getTopK(selectedDate.value, selectedK.value, selectedIndustry.value, selectedBoard.value)
    stockList.value = res.data.recommendations || []
    totalCandidates.value = res.data.total_candidates || 0
  } catch (err) {
    console.error('获取推荐失败:', err)
    stockList.value = []
  } finally {
    loading.value = false
  }
}

const handleExportExcel = () => api.exportExcel()

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
    const res = await api.getStockExplanation(pureCode, selectedDate.value)
    explainModalRef.value?.openModal(res.data)
  } catch (err) {
    alert('获取归因失败: ' + err.message)
  }
}

onMounted(loadDates)
</script>

<style scoped>
.text-warn {
  color: var(--warning);
  font-weight: 600;
}
</style>
