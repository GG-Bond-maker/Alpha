<template>
  <div class="app-layout">
    <!-- 顶部应用标题栏 -->
    <header class="app-header">
      <div class="container header-container">
        <div class="brand">
          <div class="brand-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline>
              <polyline points="16 7 22 7 22 13"></polyline>
            </svg>
          </div>
          <div>
            <h1 class="brand-title">基于 LightGBM 与特征归因的 A 股智能选股与可视化推荐系统 v2.0</h1>
            <p class="brand-sub">全面覆盖中国 A 股全部板块 (主板 / 创业板 / 科创板 / 北交所) | LightGBM 推荐预测 | 交互式 K 线走势分析 | TreeSHAP 归因诊断</p>
          </div>
        </div>
        <div class="header-tags">
          <span class="badge badge-blue">A 股全板块覆盖</span>
          <span class="badge badge-green">Optuna 贝叶斯调优</span>
          <span class="badge badge-gold">日K线与均线系统</span>
          <span class="badge badge-silver">TreeSHAP XAI 解释</span>
        </div>
      </div>
    </header>

    <!-- 主体区域 -->
    <main class="container">
      <!-- 导航标签页 -->
      <nav class="tabs-nav">
        <button 
          class="tab-btn" 
          :class="{ active: currentTab === 'home' }"
          @click="handleSwitchTab('home')"
        >
          全景概览
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: currentTab === 'recommend' }"
          @click="handleSwitchTab('recommend')"
        >
          Top-K 智能选股推荐
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: currentTab === 'kline' }"
          @click="handleSwitchTab('kline')"
        >
          行情走势与技术指标
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: currentTab === 'manage' }"
          @click="handleSwitchTab('manage')"
        >
          股票池与标的管理
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: currentTab === 'engineering' }"
          @click="handleSwitchTab('engineering')"
        >
          数据工程与生命周期
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: currentTab === 'global' }"
          @click="handleSwitchTab('global')"
        >
          全局特征归因透视
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: currentTab === 'metrics' }"
          @click="handleSwitchTab('metrics')"
        >
          算法评测与基线对比
        </button>
      </nav>

      <!-- 标签页 0: 首页看板 -->
      <section v-if="currentTab === 'home'">
        <HomeDashboardView @switchTab="handleSwitchTab" @viewKline="handleViewKline" />
      </section>

      <!-- 标签页 1: 股票推荐面板 -->
      <section v-if="currentTab === 'recommend'" class="tab-content">
        <!-- 筛选与控制栏 -->
        <div class="card filter-card">
          <div class="filter-group">
            <label class="filter-label">截面日期：</label>
            <select v-model="selectedDate" @change="fetchRecommendations" class="select-control">
              <option v-for="d in datesList" :key="d" :value="d">{{ d }} (最新截面)</option>
            </select>
          </div>

          <div class="filter-group">
            <label class="filter-label">股票板块：</label>
            <select v-model="selectedBoard" @change="fetchRecommendations" class="select-control">
              <option value="全部">全部板块 (全市场)</option>
              <option value="主板">主板 (沪深主板)</option>
              <option value="创业板">创业板</option>
              <option value="科创板">科创板</option>
              <option value="北交所">北交所</option>
            </select>
          </div>

          <div class="filter-group">
            <label class="filter-label">推荐数量 K：</label>
            <select v-model="selectedK" @change="fetchRecommendations" class="select-control">
              <option :value="5">Top 5 优选标的</option>
              <option :value="10">Top 10 优选标的</option>
              <option :value="15">Top 15 优选标的</option>
              <option :value="20">Top 20 优选标的</option>
            </select>
          </div>

          <div class="filter-group">
            <label class="filter-label">行业分类：</label>
            <select v-model="selectedIndustry" @change="fetchRecommendations" class="select-control">
              <option value="全部">全部行业</option>
              <option v-for="ind in industryList" :key="ind" :value="ind">{{ ind }}</option>
            </select>
          </div>

          <button class="btn btn-primary" @click="fetchRecommendations" :disabled="loading">
            {{ loading ? '计算中...' : '刷新推荐结果' }}
          </button>

          <button class="btn btn-success" @click="handleExportExcel">
            导出 Excel 报表
          </button>
        </div>

        <!-- 推荐排行榜表格 -->
        <div class="card">
          <div class="table-header">
            <div>
              <h2>A 股优质股票排序推荐清单 (Top-{{ selectedK }})</h2>
              <p class="table-sub">
                当前截面候选标的总数: <strong>{{ totalCandidates }}</strong> 只 | 范围覆盖: <strong>A 股全部板块 (沪深主板 / 创业板 / 科创板 / 北交所)</strong>
              </p>
            </div>
            <div class="hint-text">评级说明：A 级（高置信度多头，概率≥75%）、B 级（中等置信度，60%~75%）、C 级（防守标的，&lt;60%） | 支持联动查看日 K 线与 TreeSHAP 归因诊断</div>
          </div>

          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th style="width: 70px;">排位</th>
                  <th>股票代码</th>
                  <th>股票名称</th>
                  <th>所属板块</th>
                  <th>所属行业</th>
                  <th>推荐评级</th>
                  <th>预测看涨概率</th>
                  <th>是否涨停</th>
                  <th>最新收盘价</th>
                  <th>当日涨幅</th>
                  <th>14日RSI</th>
                  <th>MACD</th>
                  <th>20日均线比率</th>
                  <th style="text-align: center; min-width: 200px;">综合操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="loading">
                  <td colspan="14" style="text-align: center; padding: 36px 0; color: var(--slate-600);">
                    <div style="font-size: 16px; margin-bottom: 6px; font-weight: 600;">计算分析中...</div>
                    <p>正在由 LightGBM 针对全市场资产池进行截面排序与打分...</p>
                  </td>
                </tr>
                <tr v-else-if="stockList.length === 0">
                  <td colspan="14" style="text-align: center; padding: 36px 0; color: var(--slate-500);">
                    <div style="font-size: 16px; margin-bottom: 6px; font-weight: 600;">暂无匹配推荐结果</div>
                    <p>请尝试选择其他截面日期、板块或行业分类，或点击上方「刷新推荐结果」。</p>
                  </td>
                </tr>
                <tr v-for="item in stockList" :key="item.stock_code">
                  <td>
                    <span v-if="item.predicted_rank === 1" class="badge badge-gold">01</span>
                    <span v-else-if="item.predicted_rank === 2" class="badge badge-silver">02</span>
                    <span v-else-if="item.predicted_rank === 3" class="badge badge-bronze">03</span>
                    <span v-else class="badge badge-blue">{{ String(item.predicted_rank || 0).padStart(2, '0') }}</span>
                  </td>
                  <td><code class="code-font">{{ item.stock_code }}</code></td>
                  <td><strong>{{ item.stock_name }}</strong></td>
                  <td>
                    <span class="badge" :class="getBoardBadgeClass(item.board)">
                      {{ item.board || '主板' }}
                    </span>
                  </td>
                  <td><span class="badge badge-silver">{{ item.industry || '综合' }}</span></td>
                  <td>
                    <span v-if="item.recommend_rating === 'A'" class="badge-rating-a">A 级 (高置信)</span>
                    <span v-else-if="item.recommend_rating === 'B'" class="badge-rating-b">B 级 (中置信)</span>
                    <span v-else class="badge-rating-c">C 级 (低置信)</span>
                  </td>
                  <td>
                    <div class="prob-bar-container">
                      <strong>{{ (((item.probability ?? item.predicted_score ?? 0) * 100)).toFixed(1) }}%</strong>
                      <div class="prob-bar-bg">
                        <div 
                          class="prob-bar-fill" 
                          :style="{ 
                            width: Math.min(100, Math.max(0, ((item.probability ?? item.predicted_score ?? 0) * 100))) + '%', 
                            background: (item.probability ?? item.predicted_score ?? 0) >= 0.75 ? '#10b981' : ((item.probability ?? item.predicted_score ?? 0) >= 0.6 ? '#f59e0b' : '#3b82f6') 
                          }"
                        ></div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span v-if="item.is_limit_up === '是'" class="badge-limit-up">涨停</span>
                    <span v-else style="color: #64748b;">否</span>
                  </td>
                  <td><strong>¥{{ item.close_price ?? item.price ?? item.pe_ratio ?? '--' }}</strong></td>
                  <td :class="(item.pct_chg || 0) >= 0 ? 'text-pos' : 'text-neg'">
                    {{ (item.pct_chg || 0) >= 0 ? '+' : '' }}{{ item.pct_chg || 0 }}%
                  </td>
                  <td>{{ item.rsi14 || 50.0 }}</td>
                  <td :class="(item.macd || 0) >= 0 ? 'text-pos' : 'text-neg'">{{ item.macd || 0.0 }}</td>
                  <td>{{ item.ema20_ratio || 1.0 }}</td>
                  <td style="text-align: center;">
                    <div style="display: flex; gap: 6px; justify-content: center;">
                      <button class="btn btn-primary btn-sm" @click="handleViewKline(item)" title="在可视化视图中查看K线走势">
                        查看K线
                      </button>
                      <button class="btn btn-outline btn-sm" @click="handleExplain(item)" title="查看 TreeSHAP 归因瀑布图">
                        归因诊断
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- 标签页: 股票K线走势与数据可视化 (复刻截图) -->
      <section v-if="currentTab === 'kline'">
        <StockKlineView ref="klineViewRef" @switchTab="handleSwitchTab" />
      </section>

      <!-- 标签页: 股票管理 (主板股票池检索与重点关注) -->
      <section v-if="currentTab === 'manage'">
        <StockManageView @viewKline="handleViewKline" @explain="handleExplain" />
      </section>

      <!-- 标签页: 数据工程与模型生命周期 (数据更新与模型重训) -->
      <section v-if="currentTab === 'engineering'">
        <DataEngineeringView @switchTab="handleSwitchTab" />
      </section>

      <!-- 标签页 2: 全局解释 -->
      <section v-if="currentTab === 'global'">
        <GlobalExplainView />
      </section>

      <!-- 标签页 3: 评测指标 -->
      <section v-if="currentTab === 'metrics'">
        <MetricsView />
      </section>
    </main>

    <!-- 弹出的可解释性诊断模态窗 -->
    <ExplainModal ref="explainModalRef" />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { api } from './api'
import ExplainModal from './components/ExplainModal.vue'
import GlobalExplainView from './components/GlobalExplainView.vue'
import MetricsView from './components/MetricsView.vue'
import StockKlineView from './components/StockKlineView.vue'
import HomeDashboardView from './components/HomeDashboardView.vue'
import StockManageView from './components/StockManageView.vue'
import DataEngineeringView from './components/DataEngineeringView.vue'

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

const industryList = [
  '食品饮料', '医药生物', '电子', '电力设备', '计算机', '非银金融', '银行', '汽车',
  '机械设备', '国防军工', '通信', '基础化工', '有色金属', '家用电器', '公用事业',
  '交通运输', '石油石化', '建筑装饰', '建筑材料', '商贸零售', '房地产', '传媒',
  '煤炭', '农林牧渔', '钢铁', '环保', '美容护理'
]

const getBoardBadgeClass = (board) => {
  switch (board) {
    case '主板': return 'badge-board-main'
    case '创业板': return 'badge-board-chinext'
    case '科创板': return 'badge-board-star'
    case '北交所': return 'badge-board-bse'
    default: return 'badge-silver'
  }
}

const handleSwitchTab = (tab) => {
  currentTab.value = tab
  if (tab === 'recommend') {
    if (stockList.value.length === 0) {
      fetchRecommendations()
    }
  } else if (tab === 'kline') {
    nextTick(() => {
      if (klineViewRef.value?.handleResize) {
        klineViewRef.value.handleResize()
      }
    })
  }
}

const loadDates = async () => {
  try {
    const res = await api.getDates()
    datesList.value = res.data || []
    if (datesList.value.length > 0) {
      if (!selectedDate.value) {
        selectedDate.value = datesList.value[datesList.value.length - 1]
      }
    } else {
      selectedDate.value = '2026-10-13'
    }
  } catch (err) {
    console.error('加载交易日期列表失败:', err)
    selectedDate.value = '2026-10-13'
  }
  await fetchRecommendations()
}

const fetchRecommendations = async () => {
  loading.value = true
  try {
    const res = await api.getTopK(selectedDate.value, selectedK.value, selectedIndustry.value, selectedBoard.value)
    stockList.value = res.data.recommendations
    totalCandidates.value = res.data.total_candidates
  } catch (err) {
    console.error('获取股票推荐失败:', err)
  } finally {
    loading.value = false
  }
}

const handleExportExcel = () => {
  api.exportExcel()
}

// 点击表格中的「查看K线」，直接联动并切换到可视化选项卡
const handleViewKline = (item) => {
  currentTab.value = 'kline'
  nextTick(async () => {
    if (klineViewRef.value) {
      if (typeof klineViewRef.value.loadStockByCode === 'function') {
        await klineViewRef.value.loadStockByCode(item)
      } else {
        const rawCode = String(item.stock_code || item.code || '600030').padStart(6, '0')
        let suffix = 'SH'
        if (rawCode.startsWith('60') || rawCode.startsWith('68')) {
          suffix = 'SH'
        } else if (rawCode.startsWith('00') || rawCode.startsWith('30')) {
          suffix = 'SZ'
        } else if (rawCode.startsWith('8') || rawCode.startsWith('4') || rawCode.startsWith('9')) {
          suffix = 'BJ'
        }
        klineViewRef.value.selectedStockCode = `${rawCode}.${suffix}`
        await klineViewRef.value.handleSearch()
      }
    }
  })
}

const handleExplain = async (item) => {
  try {
    const rawCode = item.stock_code || item.code
    const pureCode = rawCode ? rawCode.split('.')[0] : ''
    const stockName = item.stock_name || item.name || pureCode
    const res = await api.getStockExplanation(pureCode, selectedDate.value)
    if (explainModalRef.value) {
      explainModalRef.value.openModal(res.data)
    }
  } catch (err) {
    const name = item.stock_name || item.name || item.code
    alert(`获取股票 ${name} 的归因失败: ` + err.message)
  }
}

onMounted(() => {
  loadDates()
})
</script>

<style scoped>
.app-header {
  background: #ffffff;
  border-bottom: 1px solid var(--slate-200);
  box-shadow: var(--shadow-sm);
  padding: 18px 0;
}

.header-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon {
  font-size: 32px;
}

.brand-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--slate-900);
}

.brand-sub {
  font-size: 13px;
  color: var(--slate-600);
  margin-top: 2px;
}

.header-tags {
  display: flex;
  gap: 8px;
}

.tabs-nav {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  border-bottom: 2px solid var(--slate-200);
  padding-bottom: 2px;
}

.tab-btn {
  padding: 10px 18px;
  font-size: 15px;
  font-weight: 600;
  color: var(--slate-600);
  background: transparent;
  border: none;
  border-bottom: 3px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-btn:hover {
  color: var(--primary);
}

.tab-btn.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

.filter-card {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  padding: 16px 20px;
  background: #ffffff;
  border-radius: var(--radius-lg);
  border: 1px solid var(--slate-200);
  margin-bottom: 20px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--slate-700);
}

.select-control {
  padding: 8px 12px;
  border: 1px solid var(--slate-300);
  border-radius: var(--radius-md);
  font-size: 14px;
  background: #ffffff;
  outline: none;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.table-sub {
  font-size: 13px;
  color: var(--slate-600);
  margin-top: 4px;
}

.hint-text {
  font-size: 13px;
  color: var(--warning);
  font-weight: 500;
}

.table-container {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 14px;
}

th {
  background-color: var(--slate-100);
  color: var(--slate-700);
  padding: 12px 14px;
  font-weight: 600;
  border-bottom: 1px solid var(--slate-200);
  white-space: nowrap;
}

td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--slate-200);
  vertical-align: middle;
}

tbody tr:hover {
  background-color: var(--slate-50);
}

.code-font {
  font-family: monospace;
  background: var(--slate-100);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--slate-800);
}

.score-text {
  color: var(--primary);
  font-size: 15px;
}

.badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.badge-blue {
  background: #dbeafe;
  color: #1e40af;
}

.badge-green {
  background: #dcfce7;
  color: #166534;
}

.badge-gold {
  background: #fef3c7;
  color: #92400e;
}

.badge-silver {
  background: #f1f5f9;
  color: #475569;
}

.badge-bronze {
  background: #ffedd5;
  color: #9a3412;
}

.badge-board-main {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
  font-weight: 600;
}

.badge-board-chinext {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
  font-weight: 600;
}

.badge-board-star {
  background: #f5f3ff;
  color: #6d28d9;
  border: 1px solid #ddd6fe;
  font-weight: 600;
}

.badge-board-bse {
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fed7aa;
  font-weight: 600;
}

.text-pos {
  color: #16a34a;
  font-weight: 600;
}

.text-neg {
  color: #dc2626;
  font-weight: 600;
}

.btn-sm {
  padding: 5px 10px;
  font-size: 13px;
}
</style>
