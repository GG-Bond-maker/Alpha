<template>
  <div class="kline-view-container">
    <!-- 股票代码搜索与选择栏 -->
    <div class="search-panel">
      <!-- 股票代码搜索、板块与时间范围选择栏 -->
      <div class="search-form">
        <label class="search-label">所属板块</label>
        <div class="select-wrapper">
          <select v-model="selectedBoardFilter" class="stock-select range-select" @change="handleBoardFilterChange">
            <option value="全部">全部板块（沪深300）</option>
            <option value="主板">主板 (沪深)</option>
            <option value="创业板">创业板</option>
            <option value="科创板">科创板</option>
            <option value="北交所">北交所</option>
          </select>
        </div>

        <label class="search-label">选择标的</label>
        <div class="combobox-container" ref="comboboxRef">
          <div class="combobox-control" :class="{ 'is-focused': isDropdownOpen }" @click="toggleDropdown">
            <span class="combobox-icon">🔍</span>
            <input
              ref="searchInputRef"
              type="text"
              class="combobox-input"
              :value="isDropdownOpen ? searchQuery : displayStockText"
              :placeholder="displayStockText || '搜索代码 / 名称 / 行业...'"
              @input="onSearchInput"
              @focus="openDropdown"
              @keydown="handleKeyDown"
            />
            <button v-if="searchQuery" class="combobox-clear" @click.stop="clearSearch">×</button>
            <span class="combobox-arrow" :class="{ 'is-open': isDropdownOpen }">▾</span>
          </div>

          <div v-if="isDropdownOpen" class="combobox-dropdown">
            <div class="combobox-dropdown-header">
              <span>共 {{ searchFilteredStocks.length }} 只标的 ({{ selectedBoardFilter }})</span>
              <span class="combobox-hint">↑↓ 切换 · Enter 选中</span>
            </div>
            <div class="combobox-dropdown-list" ref="dropdownListRef">
              <div
                v-for="(stock, idx) in searchFilteredStocks"
                :key="stock.full_code"
                class="combobox-item"
                :class="{
                  'is-active': stock.full_code === selectedStockCode,
                  'is-highlighted': idx === highlightedIndex
                }"
                @click="selectStock(stock)"
                @mouseenter="highlightedIndex = idx"
              >
                <div class="stock-item-main">
                  <span class="stock-item-code">{{ stock.full_code }}</span>
                  <span class="stock-item-name">{{ stock.name }}</span>
                </div>
                <div class="stock-item-tags">
                  <span class="badge badge-silver" style="font-size: 11px;">{{ stock.board || '主板' }}</span>
                  <span class="stock-item-industry">{{ stock.industry || '未分类' }}</span>
                </div>
                <span v-if="stock.full_code === selectedStockCode" class="stock-item-check">✓</span>
              </div>
              <div v-if="searchFilteredStocks.length === 0" class="combobox-empty">
                未找到匹配股票，请尝试其他关键词
              </div>
            </div>
          </div>
        </div>

        <label class="search-label">时间跨度</label>
        <div class="select-wrapper">
          <select v-model="selectedTimeRange" class="stock-select range-select" @change="handleSearch">
            <option v-for="opt in timeRangeOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>

        <button class="btn btn-primary" @click="handleSearch" :disabled="loading">
          {{ loading ? '查询中...' : '立即查询' }}
        </button>
      </div>

      <!-- 选中股票的简要行情状态卡片只显示真实行情 -->
      <div v-if="klineData && !klineData.is_synthetic" class="stock-info-strip">
        <span class="tag-badge">{{ currentStockBoard }}</span>
        <span class="stock-name-strong">{{ klineData.stock_name }} ({{ selectedStockCode }})</span>
        <span class="stat-item">最新价: <strong>¥{{ klineData.latest_close }}</strong></span>
        <span class="stat-item" :class="klineData.change_pct > 0 ? 'text-pos' : klineData.change_pct < 0 ? 'text-neg' : 'text-muted'">
          涨跌幅: <strong>{{ klineData.change_pct >= 0 ? '+' : '' }}{{ klineData.change_pct }}%</strong>
        </span>
        <span class="stat-item">
          历史跨度: <strong style="color: var(--primary);">{{ klineData.start_date }} ~ {{ klineData.end_date }} ({{ klineData.total_count }} 交易日)</strong>
        </span>
        <span class="stat-item">周期最高: <strong class="text-pos">¥{{ klineData.highest }} ({{ klineData.highest_date }})</strong></span>
        <span class="stat-item">周期最低: <strong class="text-neg">¥{{ klineData.lowest }} ({{ klineData.lowest_date }})</strong></span>
      </div>
    </div>

    <div v-if="loading" class="card chart-feedback">
      <div class="loading-state">
        <div class="spinner"></div>
        正在拉取行情数据与技术指标...
      </div>
    </div>
    <div v-else-if="klineData?.is_synthetic" class="card chart-feedback data-warning">
      <strong>当前没有可用的真实行情</strong>
      <p>行情接口返回了模拟占位数据。为避免误读，系统已隐藏这组模拟报价、K 线和成交量，请更新行情后重试。</p>
    </div>
    <div v-else-if="requestError" class="card chart-feedback data-warning">
      <strong>行情加载失败</strong>
      <p>{{ requestError }}</p>
    </div>

    <template v-else-if="klineData">
      <!-- 图表 1: 股票 K 线图 -->
      <div class="chart-card">
        <div class="chart-title-bar">
          <h3>日 K 线与移动均线系统</h3>
          <span class="badge-sub">前复权日 K 线、MA5/10/20/30 多周期均线与极值参考线</span>
        </div>
        <div ref="klineChartRef" class="echarts-container" style="height: 520px;"></div>
      </div>

      <!-- 图表 2: 股票走势图 (成交量与均量线 / MACD / RSI 多指标切换) -->
      <div class="chart-card">
        <div class="chart-title-bar indicator-title-bar">
          <div class="title-with-actions">
            <h3>{{ subChartTitle }}</h3>
            <span class="badge-sub">{{ subChartSubtitle }}</span>
          </div>
          <div class="indicator-segmented-control">
            <button
              type="button"
              class="indicator-btn"
              :class="{ active: subChartType === 'vol' }"
              @click="setSubChartType('vol')"
            >
              📊 成交量 (VOL)
            </button>
            <button
              type="button"
              class="indicator-btn"
              :class="{ active: subChartType === 'macd' }"
              @click="setSubChartType('macd')"
            >
              🌊 动能 (MACD 12,26,9)
            </button>
            <button
              type="button"
              class="indicator-btn"
              :class="{ active: subChartType === 'rsi' }"
              @click="setSubChartType('rsi')"
            >
              ⚡ 强弱 (RSI 14)
            </button>
          </div>
        </div>
        <div ref="trendChartRef" class="echarts-container" style="height: 270px;"></div>
      </div>
    </template>
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
const requestError = ref('')

// 可搜索下拉选择器交互状态
const comboboxRef = ref(null)
const searchInputRef = ref(null)
const dropdownListRef = ref(null)
const searchQuery = ref('')
const isDropdownOpen = ref(false)
const highlightedIndex = ref(0)

const displayStockText = computed(() => {
  if (!selectedStockCode.value) return ''
  const code = selectedStockCode.value.split('.')[0]
  const s = stockPool.value.find(item => item.code === code)
  if (s) {
    return `${s.full_code} ${s.name} (${s.industry || s.board || '主板'})`
  }
  return selectedStockCode.value
})

const filteredStockPool = computed(() => {
  if (selectedBoardFilter.value === '全部') {
    return stockPool.value
  }
  return stockPool.value.filter(s => (s.board || '主板') === selectedBoardFilter.value)
})

const searchFilteredStocks = computed(() => {
  const base = filteredStockPool.value
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return base
  return base.filter(s => {
    const code = (s.code || '').toLowerCase()
    const fullCode = (s.full_code || '').toLowerCase()
    const name = (s.name || '').toLowerCase()
    const ind = (s.industry || '').toLowerCase()
    return code.includes(q) || fullCode.includes(q) || name.includes(q) || ind.includes(q)
  })
})

const openDropdown = () => {
  isDropdownOpen.value = true
  highlightedIndex.value = 0
}

const closeDropdown = () => {
  isDropdownOpen.value = false
  searchQuery.value = ''
}

const toggleDropdown = () => {
  if (isDropdownOpen.value) {
    closeDropdown()
  } else {
    openDropdown()
    nextTick(() => searchInputRef.value?.focus())
  }
}

const onSearchInput = (e) => {
  searchQuery.value = e.target.value
  if (!isDropdownOpen.value) isDropdownOpen.value = true
  highlightedIndex.value = 0
}

const clearSearch = () => {
  searchQuery.value = ''
  highlightedIndex.value = 0
  searchInputRef.value?.focus()
}

const selectStock = (stock) => {
  selectedStockCode.value = stock.full_code
  closeDropdown()
  handleSearch()
}

const scrollToHighlighted = () => {
  nextTick(() => {
    if (!dropdownListRef.value) return
    const el = dropdownListRef.value.children[highlightedIndex.value]
    if (el) el.scrollIntoView({ block: 'nearest' })
  })
}

const handleKeyDown = (e) => {
  if (!isDropdownOpen.value) {
    if (e.key === 'ArrowDown' || e.key === 'Enter') {
      openDropdown()
    }
    return
  }
  const list = searchFilteredStocks.value
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (list.length > 0) {
      highlightedIndex.value = (highlightedIndex.value + 1) % list.length
      scrollToHighlighted()
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (list.length > 0) {
      highlightedIndex.value = (highlightedIndex.value - 1 + list.length) % list.length
      scrollToHighlighted()
    }
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (list.length > 0 && highlightedIndex.value >= 0 && highlightedIndex.value < list.length) {
      selectStock(list[highlightedIndex.value])
    }
  } else if (e.key === 'Escape') {
    closeDropdown()
  }
}

const handleClickOutside = (e) => {
  if (comboboxRef.value && !comboboxRef.value.contains(e.target)) {
    closeDropdown()
  }
}

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

// 历史数据周期选择器；实际起止时间由本地可用的真实历史行情决定。
const selectedTimeRange = ref(3800)
const timeRangeOptions = [
  { label: '全部可用历史 (最多 3800 根)', value: 3800 },
  { label: '近 10 年 (最多 2420 根)', value: 2420 },
  { label: '近 5 年 (最多 1210 根)', value: 1210 },
  { label: '近 3 年 (最多 726 根)', value: 726 },
  { label: '近 1 年 (最多 242 根)', value: 242 }
]

const klineChartRef = ref(null)
const trendChartRef = ref(null)
let klineChart = null
let trendChart = null

// 副图指标类型: 'vol' (成交量), 'macd' (MACD指标), 'rsi' (RSI14)
const subChartType = ref('vol')

const subChartTitle = computed(() => {
  if (subChartType.value === 'macd') return 'MACD 异同移动平均线 (12, 26, 9)'
  if (subChartType.value === 'rsi') return 'RSI 14日相对强弱指标'
  return '成交量走势 (Volume)'
})

const subChartSubtitle = computed(() => {
  if (subChartType.value === 'macd') return '快慢线交叉 (DIF/DEA) 与动能多空能量柱'
  if (subChartType.value === 'rsi') return '动量摆动指标 · 70 超买警戒线 · 30 超卖反弹线'
  return '成交量能量柱状图与均量线联动 (VOL_MA5 / VOL_MA10)'
})

const setSubChartType = (type) => {
  subChartType.value = type
  if (klineData.value) {
    renderTrendChart(klineData.value)
  }
}

// 移动平均计算
const calcMA = (data, period) => {
  const result = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null)
      continue
    }
    let sum = 0
    let count = 0
    for (let j = 0; j < period; j++) {
      const v = data[i - j]
      if (v != null) {
        sum += v
        count++
      }
    }
    result.push(count === period ? Number((sum / period).toFixed(2)) : null)
  }
  return result
}

// 指数移动平均 (EMA)
const calcEMA = (data, period) => {
  if (!data || data.length === 0) return []
  const k = 2 / (period + 1)
  const ema = []
  let prev = data[0]
  ema.push(prev)
  for (let i = 1; i < data.length; i++) {
    const val = data[i] * k + prev * (1 - k)
    ema.push(val)
    prev = val
  }
  return ema
}

// MACD 指标计算 (DIF, DEA, MACD 柱)
const calcMACD = (closes) => {
  if (!closes || closes.length === 0) return { dif: [], dea: [], macd: [] }
  const ema12 = calcEMA(closes, 12)
  const ema26 = calcEMA(closes, 26)
  const dif = ema12.map((val, i) => Number((val - ema26[i]).toFixed(3)))
  const dea = calcEMA(dif, 9).map(v => Number(v.toFixed(3)))
  const macd = dif.map((d, i) => Number(((d - dea[i]) * 2).toFixed(3)))
  return { dif, dea, macd }
}

// Wilder's 14 周期 RSI 计算
const calcRSI = (closes, period = 14) => {
  if (!closes || closes.length <= period) return []
  const rsi = new Array(closes.length).fill(null)
  let gains = 0
  let losses = 0

  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1]
    if (diff >= 0) gains += diff
    else losses += Math.abs(diff)
  }
  let avgGain = gains / period
  let avgLoss = losses / period
  rsi[period] = avgLoss === 0 ? 100 : Number((100 - (100 / (1 + avgGain / avgLoss))).toFixed(2))

  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1]
    const gain = diff > 0 ? diff : 0
    const loss = diff < 0 ? Math.abs(diff) : 0
    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period
    if (avgLoss === 0) {
      rsi[i] = 100
    } else {
      const rs = avgGain / avgLoss
      rsi[i] = Number((100 - (100 / (1 + rs))).toFixed(2))
    }
  }
  return rsi
}

const handleResize = () => {
  if (klineChart) klineChart.resize()
  if (trendChart) trendChart.resize()
}

// 加载可选沪深300成分股
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
    console.error('加载沪深300成分股失败:', err)
  }
}

// 查询 K 线数据并渲染图表
const handleSearch = async () => {
  if (!selectedStockCode.value) return
  loading.value = true
  requestError.value = ''
  klineData.value = null
  if (klineChart) {
    klineChart.dispose()
    klineChart = null
  }
  if (trendChart) {
    trendChart.dispose()
    trendChart = null
  }
  const pureCode = selectedStockCode.value.split('.')[0]
  
  try {
    const res = await api.getStockKline(pureCode, selectedTimeRange.value)
    klineData.value = res.data
    if (res.data?.is_synthetic) return

    // 图表容器位于 v-else-if="loading" 之后；先结束加载态，等待容器挂载再初始化 ECharts。
    loading.value = false
    await nextTick()
    renderKlineChart(res.data)
    renderTrendChart(res.data)
    handleResize()
  } catch (err) {
    console.error('加载K线数据失败:', err)
    klineData.value = null
    requestError.value = '无法获取该标的的真实日线数据，请检查本地行情缓存或数据源后重试。'
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
  const zoomStart = 0

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

// 渲染副图 (支持 成交量VOL / MACD / RSI 多指标切换)
const renderTrendChart = (data) => {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }

  const { dates, volumes, kline_values } = data
  const closes = kline_values.map(k => k[1])
  const barColors = kline_values.map(k => k[1] >= k[0] ? '#e84118' : '#009432')
  const zoomStart = 0

  let option = {}

  if (subChartType.value === 'vol') {
    const volMa5 = calcMA(volumes, 5)
    const volMa10 = calcMA(volumes, 10)
    option = {
      animation: true,
      backgroundColor: '#ffffff',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          let html = `<div style="font-size:12px; line-height:1.6;">`
          html += `<strong>${params[0].axisValue}</strong><br/>`
          params.forEach(p => {
            const v = p.value != null ? Number(p.value).toLocaleString() : '--'
            html += `<span style="color:${p.color};">● ${p.seriesName}:</span> ${v} 股<br/>`
          })
          html += `</div>`
          return html
        }
      },
      legend: {
        top: 6,
        right: 16,
        data: ['成交量', 'MA5量', 'MA10量'],
        textStyle: { color: '#64748b', fontSize: 12 }
      },
      grid: {
        left: '4%',
        right: '6%',
        top: 30,
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
          formatter: (val) => (val >= 1e8 ? (val / 1e8).toFixed(1) + '亿' : (val / 10000).toFixed(0) + '万')
        },
        splitLine: {
          show: true,
          lineStyle: { color: '#eeeeee' }
        }
      },
      dataZoom: [{ type: 'inside', start: zoomStart, end: 100 }],
      series: [
        {
          name: '成交量',
          type: 'bar',
          data: volumes.map((v, i) => ({
            value: v,
            itemStyle: { color: barColors[i] }
          }))
        },
        {
          name: 'MA5量',
          type: 'line',
          data: volMa5,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.5, color: '#e17055' },
          itemStyle: { color: '#e17055' }
        },
        {
          name: 'MA10量',
          type: 'line',
          data: volMa10,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.5, color: '#0984e3' },
          itemStyle: { color: '#0984e3' }
        }
      ]
    }
  } else if (subChartType.value === 'macd') {
    const { dif, dea, macd } = calcMACD(closes)
    option = {
      animation: true,
      backgroundColor: '#ffffff',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params) => {
          let html = `<div style="font-size:12px; line-height:1.6;">`
          html += `<strong>${params[0].axisValue}</strong><br/>`
          params.forEach(p => {
            const v = p.value != null ? Number(p.value).toFixed(3) : '--'
            html += `<span style="color:${p.color};">● ${p.seriesName}:</span> ${v}<br/>`
          })
          html += `</div>`
          return html
        }
      },
      legend: {
        top: 6,
        right: 16,
        data: ['DIF (快线)', 'DEA (慢线)', 'MACD (动能柱)'],
        textStyle: { color: '#64748b', fontSize: 12 }
      },
      grid: {
        left: '4%',
        right: '6%',
        top: 30,
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
          formatter: (val) => val.toFixed(2)
        },
        splitLine: {
          show: true,
          lineStyle: { color: '#eeeeee' }
        }
      },
      dataZoom: [{ type: 'inside', start: zoomStart, end: 100 }],
      series: [
        {
          name: 'MACD (动能柱)',
          type: 'bar',
          data: macd.map(val => ({
            value: val,
            itemStyle: { color: val >= 0 ? '#dc2626' : '#16a34a' }
          }))
        },
        {
          name: 'DIF (快线)',
          type: 'line',
          data: dif,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.5, color: '#2563eb' },
          itemStyle: { color: '#2563eb' }
        },
        {
          name: 'DEA (慢线)',
          type: 'line',
          data: dea,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.5, color: '#d97706' },
          itemStyle: { color: '#d97706' }
        }
      ]
    }
  } else if (subChartType.value === 'rsi') {
    const rsi14 = calcRSI(closes, 14)
    option = {
      animation: true,
      backgroundColor: '#ffffff',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params) => {
          let html = `<div style="font-size:12px; line-height:1.6;">`
          html += `<strong>${params[0].axisValue}</strong><br/>`
          const v = params[0].value
          let state = '中性震荡'
          let stateColor = '#64748b'
          if (v >= 70) {
            state = '🔥 极度超买 (警惕高位回调)'
            stateColor = '#dc2626'
          } else if (v >= 55) {
            state = '📈 强势多头区间'
            stateColor = '#2563eb'
          } else if (v <= 30) {
            state = '💎 深度超卖 (反弹机会蓄积)'
            stateColor = '#16a34a'
          } else if (v <= 45) {
            state = '📉 弱势空头区间'
            stateColor = '#d97706'
          }
          html += `<span style="color:#8b5cf6;">● RSI(14):</span> <strong>${v != null ? v : '--'}</strong><br/>`
          html += `<span style="color:${stateColor}; font-weight:600;">信号状态: ${state}</span><br/>`
          html += `</div>`
          return html
        }
      },
      legend: {
        top: 6,
        right: 16,
        data: ['RSI(14)'],
        textStyle: { color: '#64748b', fontSize: 12 }
      },
      grid: {
        left: '4%',
        right: '6%',
        top: 30,
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
        min: 0,
        max: 100,
        splitNumber: 4,
        axisLine: { lineStyle: { color: '#cccccc' } },
        axisLabel: { color: '#666666' },
        splitLine: {
          show: true,
          lineStyle: { color: '#eeeeee' }
        }
      },
      dataZoom: [{ type: 'inside', start: zoomStart, end: 100 }],
      series: [
        {
          name: 'RSI(14)',
          type: 'line',
          data: rsi14,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: '#8b5cf6' },
          itemStyle: { color: '#8b5cf6' },
          markLine: {
            symbol: ['none', 'none'],
            data: [
              {
                yAxis: 70,
                lineStyle: { type: 'dashed', color: '#dc2626', width: 1.2 },
                label: { position: 'end', formatter: '超买 70', color: '#dc2626', fontSize: 11 }
              },
              {
                yAxis: 50,
                lineStyle: { type: 'dotted', color: '#94a3b8', width: 1 },
                label: { position: 'end', formatter: '多空中线 50', color: '#94a3b8', fontSize: 10 }
              },
              {
                yAxis: 30,
                lineStyle: { type: 'dashed', color: '#16a34a', width: 1.2 },
                label: { position: 'end', formatter: '超卖 30', color: '#16a34a', fontSize: 11 }
              }
            ]
          }
        }
      ]
    }
  }

  trendChart.setOption(option, true)

  // 联动两个图表的 dataZoom
  echarts.connect([klineChart, trendChart])
}

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('click', handleClickOutside)
  // 若外部尚未触发加载 K 线，则执行默认的初始化
  if (!klineData.value) {
    await loadStockPool()
    await handleSearch()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('click', handleClickOutside)
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

/* 可搜索下拉组合框 */
.combobox-container {
  position: relative;
  min-width: 330px;
}

.combobox-control {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.combobox-control:hover {
  border-color: #94a3b8;
}

.combobox-control.is-focused {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}

.combobox-icon {
  font-size: 13px;
  color: #64748b;
  user-select: none;
}

.combobox-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  color: #1e293b;
  background: transparent;
  padding: 2px 0;
  width: 100%;
}

.combobox-input::placeholder {
  color: #64748b;
}

.combobox-clear {
  border: none;
  background: none;
  color: #94a3b8;
  font-size: 16px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.combobox-clear:hover {
  color: #475569;
}

.combobox-arrow {
  font-size: 12px;
  color: #94a3b8;
  transition: transform 0.2s;
  user-select: none;
}

.combobox-arrow.is-open {
  transform: rotate(180deg);
}

.combobox-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.05);
  z-index: 100;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.combobox-dropdown-header {
  padding: 8px 12px;
  font-size: 11px;
  color: #64748b;
  background: #f8fafc;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.combobox-hint {
  color: #94a3b8;
}

.combobox-dropdown-list {
  max-height: 280px;
  overflow-y: auto;
}

.combobox-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid #f8fafc;
  transition: background 0.15s ease;
}

.combobox-item:hover,
.combobox-item.is-highlighted {
  background: #f1f5f9;
}

.combobox-item.is-active {
  background: #eff6ff;
}

.stock-item-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stock-item-code {
  font-family: monospace;
  font-weight: 600;
  color: #1e293b;
  font-size: 13px;
}

.stock-item-name {
  font-weight: 600;
  color: #0f172a;
  font-size: 13px;
}

.stock-item-tags {
  display: flex;
  align-items: center;
  gap: 6px;
}

.stock-item-industry {
  font-size: 11px;
  color: #64748b;
}

.stock-item-check {
  color: #2563eb;
  font-weight: bold;
  font-size: 13px;
  margin-left: 6px;
}

.combobox-empty {
  padding: 20px;
  text-align: center;
  font-size: 13px;
  color: #94a3b8;
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

.chart-feedback {
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  color: #64748b;
  text-align: center;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.data-warning {
  flex-direction: column;
  gap: 8px;
  color: #92400e;
  background: #fffbeb;
  border-color: #fde68a;
}

.data-warning p {
  max-width: 680px;
  margin: 0;
  line-height: 1.6;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e2e8f0;
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.indicator-title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.title-with-actions {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.indicator-segmented-control {
  display: inline-flex;
  background: var(--slate-100, #f1f5f9);
  padding: 3px;
  border-radius: 8px;
  gap: 4px;
  border: 1px solid var(--slate-200, #e2e8f0);
}

.indicator-btn {
  border: none;
  background: transparent;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--slate-600, #475569);
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
}

.indicator-btn:hover {
  color: var(--slate-900, #0f172a);
}

.indicator-btn.active {
  background: #ffffff;
  color: var(--primary, #2563eb);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}
</style>
