<template>
  <div class="kline-view-container">
    <!-- 标的行情走势分析专业抬头 -->
    <div class="page-header-card">
      <div class="header-main">
        <h2 class="view-title">股票行情走势与技术指标分析</h2>
        <p class="view-desc">
          覆盖 A 股全市场多层次标的，集成日 K 线系统、MA5/10/20/30 多周期均线、极值支撑阻力参考线及成交量能联动分析
        </p>
      </div>
      <div class="header-tags-group">
        <span class="status-pill pill-blue">日 K 线行情</span>
        <span class="status-pill pill-green">MA5/10/20/30 均线</span>
        <span class="status-pill pill-purple">Volume 成交量能</span>
      </div>
    </div>

    <!-- 股票代码搜索与选择栏 -->
    <div class="search-panel">
      <!-- 股票代码搜索、板块与时间范围选择栏 -->
      <div class="search-form">
        <label class="search-label">所属板块</label>
        <div class="select-wrapper">
          <select v-model="selectedBoardFilter" class="stock-select range-select" @change="handleBoardFilterChange">
            <option value="全部">全部板块 (全A股)</option>
            <option value="主板">主板 (沪深)</option>
            <option value="创业板">创业板</option>
            <option value="科创板">科创板</option>
            <option value="北交所">北交所</option>
          </select>
        </div>

        <label class="search-label" style="margin-left: 10px;">选择标的</label>
        <div class="select-wrapper">
          <select v-model="selectedStockCode" class="stock-select" @change="handleSearch">
            <option v-for="stock in filteredStockPool" :key="stock.code" :value="stock.full_code">
              [{{ stock.board || '主板' }}] {{ stock.full_code }} {{ stock.name }} ({{ stock.industry }})
            </option>
          </select>
        </div>

        <label class="search-label" style="margin-left: 10px;">时间跨度</label>
        <div class="select-wrapper">
          <select v-model="selectedTimeRange" class="stock-select range-select" @change="handleSearch">
            <option v-for="opt in timeRangeOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>

        <button class="btn-search" @click="handleSearch" :disabled="loading">
          {{ loading ? '查询中...' : '立即查询' }}
        </button>
      </div>

      <!-- 选中股票的简要行情状态卡片 (支持10~15年完整周期统计) -->
      <div v-if="klineData" class="stock-info-strip">
        <span class="tag-badge">{{ currentStockBoard }}</span>
        <span class="stock-name-strong">{{ klineData.stock_name }} ({{ selectedStockCode }})</span>
        <span class="stat-item">最新价: <strong>¥{{ klineData.latest_close }}</strong></span>
        <span class="stat-item" :class="klineData.change_pct >= 0 ? 'text-pos' : 'text-neg'">
          涨跌幅: <strong>{{ klineData.change_pct >= 0 ? '+' : '' }}{{ klineData.change_pct }}%</strong>
        </span>
        <span class="stat-item">
          历史跨度: <strong style="color: #2563eb;">{{ klineData.start_date }} ~ {{ klineData.end_date }} ({{ klineData.total_count }} 交易日 / {{ klineData.years_span }} 年)</strong>
        </span>
        <span class="stat-item">周期最高: <strong class="text-pos">¥{{ klineData.highest }} ({{ klineData.highest_date }})</strong></span>
        <span class="stat-item">周期最低: <strong class="text-neg">¥{{ klineData.lowest }} ({{ klineData.lowest_date }})</strong></span>
      </div>
    </div>

    <!-- 图表 1: 股票 K 线图 -->
    <div class="chart-card">
      <div class="chart-title-bar">
        <h3>日 K 线与移动均线系统</h3>
        <span class="badge-sub">前复权日 K 线、MA5/10/20/30 多周期均线与极值参考线</span>
      </div>
      
      <div v-if="loading" class="chart-loading">
        <div class="spinner"></div>
        <p>正在拉取行情数据与技术指标...</p>
      </div>
      <div ref="klineChartRef" class="echarts-container" style="height: 520px;"></div>
    </div>

    <!-- 图表 2: 股票走势图 (成交量与均量线) -->
    <div class="chart-card">
      <div class="chart-title-bar">
        <h3>成交量走势 (Volume)</h3>
        <span class="badge-sub">成交量能量柱状图与量价动能联动</span>
      </div>
      <div ref="trendChartRef" class="echarts-container" style="height: 260px;"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const emit = defineEmits(['switchTab'])

const stockPool = ref([])
const selectedBoardFilter = ref('全部')
// 默认选中华泰证券或中信证券 600030.SH
const selectedStockCode = ref('600030.SH')
const loading = ref(false)
const klineData = ref(null)

const filteredStockPool = computed(() => {
  if (selectedBoardFilter.value === '全部') {
    return stockPool.value
  }
  return stockPool.value.filter(s => (s.board || '主板') === selectedBoardFilter.value)
})

const currentStockBoard = computed(() => {
  const code = selectedStockCode.value ? selectedStockCode.value.split('.')[0] : ''
  const item = stockPool.value.find(s => s.code === code)
  if (item && item.board) return `${item.board}标的`
  if (code.startsWith('68')) return '科创板标的'
  if (code.startsWith('30')) return '创业板标的'
  if (code.startsWith('8') || code.startsWith('4') || code.startsWith('9')) return '北交所标的'
  return 'A股主板标的'
})

const handleBoardFilterChange = () => {
  if (filteredStockPool.value.length > 0) {
    // 若当前选中的股票不在该板块中，则自动切换为该板块第一只
    const code = selectedStockCode.value ? selectedStockCode.value.split('.')[0] : ''
    const match = filteredStockPool.value.find(s => s.code === code)
    if (!match) {
      selectedStockCode.value = filteredStockPool.value[0].full_code
      handleSearch()
    }
  }
}

// 历史数据周期选择器 (默认 15 年超级大周期，约 3800 根日K线)
const selectedTimeRange = ref(3800)
const timeRangeOptions = [
  { label: '全部 15 年大周期 (~3800K线)', value: 3800 },
  { label: '近 10 年大跨度 (~2420K线)', value: 2420 },
  { label: '近 5 年大跨度 (~1210K线)', value: 1210 },
  { label: '近 3 年行情 (~726K线)', value: 726 },
  { label: '近 1 年短周期 (~242K线)', value: 242 }
]

const klineChartRef = ref(null)
const trendChartRef = ref(null)
let klineChart = null
let trendChart = null

const handleResize = () => {
  if (klineChart) klineChart.resize()
  if (trendChart) trendChart.resize()
}

// 加载可选全板块股票池
const loadStockPool = async () => {
  try {
    const res = await api.getStockPool()
    stockPool.value = res.data

    // 关键防覆盖检查：如果外部已指定 selectedStockCode，绝不要覆盖重置它！
    if (selectedStockCode.value) {
      const currentPure = selectedStockCode.value.split('.')[0]
      const foundMatch = stockPool.value.find(s => s.code === currentPure)
      if (foundMatch) {
        selectedStockCode.value = foundMatch.full_code
        if (foundMatch.board && selectedBoardFilter.value !== '全部' && selectedBoardFilter.value !== foundMatch.board) {
          selectedBoardFilter.value = foundMatch.board
        }
        return
      }
    }

    // 仅在完全没有指定时，才设置默认股票
    const found = stockPool.value.find(s => s.code === '600030')
    if (found) {
      selectedStockCode.value = found.full_code
    } else if (stockPool.value.length > 0) {
      selectedStockCode.value = stockPool.value[0].full_code
    }
  } catch (err) {
    console.error('加载全板块股票池失败:', err)
  }
}

// 查询 K 线数据并渲染图表
const handleSearch = async () => {
  if (!selectedStockCode.value) return
  loading.value = true
  const pureCode = selectedStockCode.value.split('.')[0]
  
  try {
    const res = await api.getStockKline(pureCode, selectedTimeRange.value)
    klineData.value = res.data
    await nextTick()
    renderKlineChart(res.data)
    renderTrendChart(res.data)
    handleResize()
  } catch (err) {
    console.error('加载K线数据失败:', err)
  } finally {
    loading.value = false
  }
}

// 供外部直接调用：精确定位标的并渲染对应 K 线
const loadStockByCode = async (targetCodeOrItem) => {
  let targetCode = ''
  if (typeof targetCodeOrItem === 'string') {
    targetCode = targetCodeOrItem
  } else if (targetCodeOrItem) {
    targetCode = targetCodeOrItem.full_code || targetCodeOrItem.stock_code || targetCodeOrItem.code || ''
  }
  if (!targetCode) return

  const pureCode = String(targetCode).split('.')[0].trim().padStart(6, '0')

  // 若 stockPool 尚未加载完成，先执行加载
  if (stockPool.value.length === 0) {
    await loadStockPool()
  }

  const matched = stockPool.value.find(s => s.code === pureCode)
  if (matched) {
    selectedStockCode.value = matched.full_code
    // 如果当前选中的板块过滤不包含该股票，自动将板块调整匹配
    if (selectedBoardFilter.value !== '全部' && selectedBoardFilter.value !== matched.board) {
      selectedBoardFilter.value = matched.board
    }
  } else {
    let suffix = 'SH'
    if (pureCode.startsWith('60') || pureCode.startsWith('68')) suffix = 'SH'
    else if (pureCode.startsWith('00') || pureCode.startsWith('30')) suffix = 'SZ'
    else if (pureCode.startsWith('8') || pureCode.startsWith('4') || pureCode.startsWith('9')) suffix = 'BJ'
    selectedStockCode.value = `${pureCode}.${suffix}`
  }

  await handleSearch()
}

// 渲染专业股票 K 线图 (复刻截图)
const renderKlineChart = (data) => {
  if (!klineChartRef.value) return
  if (!klineChart) {
    klineChart = echarts.init(klineChartRef.value)
  }

  const { dates, kline_values, ma5, ma10, ma20, ma30, highest, lowest, highest_date, lowest_date } = data
  const zoomStart = (dates.length > 2000) ? 70 : ((dates.length > 1000) ? 50 : 0)

  const option = {
    animation: true,
    backgroundColor: '#ffffff',
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        lineStyle: {
          color: '#999999',
          type: 'dashed'
        }
      },
      backgroundColor: 'rgba(50, 50, 50, 0.88)',
      borderColor: '#333',
      textStyle: {
        color: '#ffffff',
        fontSize: 12,
        lineHeight: 18
      },
      formatter: (params) => {
        if (!params || params.length === 0) return ''
        const dateStr = params[0].axisValue
        let html = `<strong>${dateStr}</strong><br/>`
        
        // 查找日K系列
        const kParam = params.find(p => p.seriesName === '日K')
        if (kParam && kParam.data) {
          // ECharts candlestick 数据格式: [index, open, close, lowest, highest]
          const [ , o, c, l, h ] = kParam.data
          html += `<span style="color:#ff4757;">● 日K:</span><br/>`
          html += `&nbsp;&nbsp;• open: ${o}<br/>`
          html += `&nbsp;&nbsp;• close: ${c}<br/>`
          html += `&nbsp;&nbsp;• lowest: ${l}<br/>`
          html += `&nbsp;&nbsp;• highest: ${h}<br/>`
        }

        // MA 均线
        params.forEach(p => {
          if (p.seriesName.startsWith('MA')) {
            const val = p.data !== null && p.data !== undefined ? p.data : '--'
            html += `<span style="color:${p.color};">● ${p.seriesName}:</span> ${val}<br/>`
          }
        })
        return html
      }
    },
    legend: {
      top: 10,
      left: 'center',
      data: ['日K', 'MA5', 'MA10', 'MA20', 'MA30'],
      textStyle: {
        color: '#333333',
        fontSize: 13
      }
    },
    grid: {
      left: '4%',
      right: '6%',
      top: 60,
      bottom: 80
    },
    xAxis: {
      type: 'category',
      data: dates,
      scale: true,
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#cccccc' } },
      axisLabel: { color: '#666666' },
      splitLine: { show: false }
    },
    yAxis: {
      scale: true,
      splitArea: { show: true },
      axisLine: { lineStyle: { color: '#cccccc' } },
      axisLabel: { color: '#666666' },
      splitLine: {
        show: true,
        lineStyle: { color: '#eeeeee' }
      }
    },
    dataZoom: [
      {
        type: 'inside',
        start: zoomStart,
        end: 100
      },
      {
        show: true,
        type: 'slider',
        top: '88%',
        start: zoomStart,
        end: 100,
        borderColor: '#cbd5e1',
        fillerColor: 'rgba(59, 130, 246, 0.15)'
      }
    ],
    series: [
      {
        name: '日K',
        type: 'candlestick',
        data: kline_values,
        itemStyle: {
          color: '#e84118',       // 阳线红
          color0: '#009432',      // 阴线绿
          borderColor: '#e84118',
          borderColor0: '#009432'
        },
        markPoint: {
          data: [
            {
              name: '最低值',
              coord: [lowest_date, lowest],
              value: lowest,
              symbol: 'circle',
              symbolSize: 28,
              itemStyle: { color: '#d63031' },
              label: {
                show: true,
                color: '#ffffff',
                fontWeight: 'bold',
                fontSize: 11
              }
            },
            {
              name: '最高值',
              coord: [highest_date, highest],
              value: highest,
              symbol: 'circle',
              symbolSize: 28,
              itemStyle: { color: '#d63031' },
              label: {
                show: true,
                color: '#ffffff',
                fontWeight: 'bold',
                fontSize: 11
              }
            }
          ]
        },
        markLine: {
          symbol: ['none', 'none'],
          data: [
            // 最低点水平线
            {
              yAxis: lowest,
              lineStyle: { type: 'dashed', color: '#d63031', width: 1.5 },
              label: { position: 'end', formatter: `${lowest}`, color: '#d63031', fontWeight: 'bold' }
            },
            // 最高点水平线
            {
              yAxis: highest,
              lineStyle: { type: 'dashed', color: '#d63031', width: 1.5 },
              label: { position: 'end', formatter: `${highest}`, color: '#d63031', fontWeight: 'bold' }
            },
            // 最低点到最高点的对角趋势线 (如截图所示)
            [
              { coord: [lowest_date, lowest], lineStyle: { type: 'dashed', color: '#d63031', width: 1.5 } },
              { coord: [highest_date, highest] }
            ]
          ]
        }
      },
      {
        name: 'MA5',
        type: 'line',
        data: ma5,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#e17055' },
        itemStyle: { color: '#e17055' }
      },
      {
        name: 'MA10',
        type: 'line',
        data: ma10,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#00b894' },
        itemStyle: { color: '#00b894' }
      },
      {
        name: 'MA20',
        type: 'line',
        data: ma20,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#0984e3' },
        itemStyle: { color: '#0984e3' }
      },
      {
        name: 'MA30',
        type: 'line',
        data: ma30,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#fdcb6e' },
        itemStyle: { color: '#fdcb6e' }
      }
    ]
  }

  klineChart.setOption(option, true)
}

// 渲染成交量走势图
const renderTrendChart = (data) => {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }

  const { dates, volumes, kline_values } = data
  const barColors = kline_values.map(k => k[1] >= k[0] ? '#e84118' : '#009432')
  const zoomStart = (dates.length > 2000) ? 70 : ((dates.length > 1000) ? 50 : 0)

  const option = {
    animation: true,
    backgroundColor: '#ffffff',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '4%',
      right: '6%',
      top: 20,
      bottom: 25
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#cccccc' } },
      axisLabel: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      scale: true,
      splitNumber: 3,
      axisLine: { lineStyle: { color: '#cccccc' } },
      axisLabel: {
        color: '#666666',
        formatter: (val) => (val / 10000).toFixed(0) + '万'
      },
      splitLine: {
        show: true,
        lineStyle: { color: '#eeeeee' }
      }
    },
    dataZoom: [
      {
        type: 'inside',
        start: zoomStart,
        end: 100
      }
    ],
    series: [
      {
        name: '成交量',
        type: 'bar',
        data: volumes.map((v, i) => ({
          value: v,
          itemStyle: { color: barColors[i] }
        }))
      }
    ]
  }

  trendChart.setOption(option, true)

  // 联动两个图表的 dataZoom
  echarts.connect([klineChart, trendChart])
}

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  // 若外部尚未触发加载 K 线，则执行默认的初始化
  if (!klineData.value) {
    await loadStockPool()
    await handleSearch()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (klineChart) klineChart.dispose()
  if (trendChart) trendChart.dispose()
})

defineExpose({ selectedStockCode, handleSearch, loadStockByCode, handleResize })
</script>

<style scoped>
.kline-view-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 标的行情走势分析专业抬头 */
.page-header-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #ffffff;
  padding: 16px 22px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--slate-200);
  box-shadow: var(--shadow-sm);
  flex-wrap: wrap;
  gap: 12px;
}

.header-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.view-title {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.2px;
}

.view-desc {
  font-size: 13px;
  color: #64748b;
  line-height: 1.4;
}

.header-tags-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 9999px;
  white-space: nowrap;
}

.pill-blue {
  background: #eff6ff;
  color: #2563eb;
  border: 1px solid #bfdbfe;
}

.pill-green {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #bbf7d0;
}

.pill-purple {
  background: #faf5ff;
  color: #9333ea;
  border: 1px solid #e9d5ff;
}

/* 搜索控制面板 */
.search-panel {
  background: #ffffff;
  border-radius: var(--radius-lg);
  border: 1px solid var(--slate-200);
  padding: 18px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  box-shadow: var(--shadow-sm);
}

.search-form {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.search-label {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.stock-select {
  padding: 8px 14px;
  font-size: 14px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  outline: none;
  min-width: 270px;
  background-color: #ffffff;
  color: #1e293b;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.stock-select:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}

.range-select {
  min-width: 210px;
  border-color: #cbd5e1;
  color: #1e293b;
  font-weight: 500;
}

.btn-search {
  background: #2563eb;
  color: #ffffff;
  border: none;
  padding: 8px 22px;
  font-size: 14px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-search:hover {
  background: #1d4ed8;
}

.btn-search:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.stock-info-strip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  flex-wrap: wrap;
  padding-top: 10px;
  border-top: 1px dashed var(--slate-200);
  font-size: 14px;
}

.tag-badge {
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
}

.stock-name-strong {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.chart-card {
  background: #ffffff;
  border-radius: var(--radius-lg);
  border: 1px solid var(--slate-200);
  box-shadow: var(--shadow-sm);
  padding: 20px;
}

.chart-title-bar {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 8px;
}

.chart-title-bar h3 {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
}

.badge-sub {
  font-size: 12px;
  color: #64748b;
}

.echarts-container {
  width: 100%;
}

.chart-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: #64748b;
  gap: 12px;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e2e8f0;
  border-top-color: #009432;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
