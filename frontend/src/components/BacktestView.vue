<template>
  <div>
    <div v-if="loading" class="card">
      <div class="loading-state">
        <div class="spinner"></div>
        正在加载回测结果...
      </div>
    </div>

    <div v-else-if="!data || data.error" class="card">
      <div class="empty-state">
        <div class="empty-state-title">暂无回测结果</div>
        <div class="empty-state-desc">{{ data && data.error ? data.error : '请先运行 python -m ml_pipeline.run_training 生成回测产物' }}</div>
      </div>
    </div>

    <template v-else>
      <div class="card notice-card">
        <span class="source-tag" :class="isNeutral ? 'is-real' : 'is-synthetic'">
          {{ isNeutral ? '行业中性选股' : '全市场排序' }}
        </span>
        <span class="notice-text">
          <template v-if="isNeutral">
            每个行业内按模型打分选 Top-N 后合并，持仓分散于
            <strong>{{ data.avg_sectors_held }}</strong> 个行业，
            单一行业暴露受控。行业样本不足 {{ params.min_stocks_per_sector }} 只时并入剩余池补位。
          </template>
          <template v-else>
            全市场按模型打分直接取 Top-K，不做行业约束。
          </template>
        </span>
      </div>

      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">策略年化收益</div>
          <div class="stat-value" :class="signClass(strategy.annualized_return)">
            {{ pct(strategy.annualized_return) }}
          </div>
          <div class="stat-hint">Top-{{ params.k }} 等权组合</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">基准年化收益</div>
          <div class="stat-value" :class="signClass(benchmark.annualized_return)">
            {{ pct(benchmark.annualized_return) }}
          </div>
          <div class="stat-hint">全样本等权</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">超额年化收益</div>
          <div class="stat-value" :class="signClass(excess.annualized_return)">
            {{ pct(excess.annualized_return) }}
          </div>
          <div class="stat-hint">扣除交易成本后</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">夏普比率</div>
          <div class="stat-value">{{ fmt(strategy.sharpe) }}</div>
          <div class="stat-hint">年化，无风险利率取 0</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最大回撤</div>
          <div class="stat-value text-neg">{{ pct(strategy.max_drawdown) }}</div>
          <div class="stat-hint">净值峰值回落幅度</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">平均换手率</div>
          <div class="stat-value">{{ pct(params.avg_turnover) }}</div>
          <div class="stat-hint">每期持仓变动比例</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">策略净值曲线</div>
            <div class="card-subtitle">
              共 {{ strategy.periods }} 个调仓周期 · 单边买入成本
              {{ (params.buy_cost * 100).toFixed(3) }}% · 卖出成本
              {{ (params.sell_cost * 100).toFixed(3) }}%（含印花税）
            </div>
          </div>
        </div>
        <div ref="chartRef" style="width: 100%; height: 380px;"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">风险收益对照</div>
            <div class="card-subtitle">策略与基准在同一区间、同一成本口径下的对比</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>指标</th>
                <th>策略 (Top-{{ params.k }})</th>
                <th>基准 (等权全样本)</th>
                <th>差值</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in compareRows" :key="row.label">
                <td>{{ row.label }}</td>
                <td :class="signClass(row.a)">{{ row.fmt ? fmt(row.a) : pct(row.a) }}</td>
                <td :class="signClass(row.b)">{{ row.fmt ? fmt(row.b) : pct(row.b) }}</td>
                <td :class="signClass(row.a - row.b)">
                  {{ row.fmt ? fmt(row.a - row.b) : pct(row.a - row.b) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="comparison" class="card">
        <div class="card-header">
          <div>
            <div class="card-title">两种选股口径对比</div>
            <div class="card-subtitle">
              同一模型打分、同一测试区间，仅持仓构建方式不同
            </div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>口径</th>
                <th>年化收益</th>
                <th>夏普</th>
                <th>最大回撤</th>
                <th>超额年化</th>
                <th>平均换手</th>
                <th>持有行业数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in comparisonRows" :key="row.key"
                  :class="{ 'row-active': row.key === params.selection }">
                <td>
                  <strong>{{ row.label }}</strong>
                  <span v-if="row.key === params.selection" class="badge badge-blue"
                        style="margin-left: 6px;">当前</span>
                </td>
                <td :class="signClass(row.s.annualized_return)">{{ pct(row.s.annualized_return) }}</td>
                <td>{{ fmt(row.s.sharpe) }}</td>
                <td class="text-neg">{{ pct(row.s.max_drawdown) }}</td>
                <td :class="signClass(row.e.annualized_return)">{{ pct(row.e.annualized_return) }}</td>
                <td>{{ pct(row.turnover) }}</td>
                <td>{{ row.sectors != null ? row.sectors : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="footnote">
          行业中性通过限制单一行业暴露来压低回撤，代价是可能牺牲部分超额收益；
          全市场排序在单边行情中收益更高，但行业集中会放大回撤。二者应按风险偏好选择。
        </div>
      </div>

      <div class="card note-card">
        <div class="card-title" style="margin-bottom: 8px;">口径说明</div>
        <ul class="note-list">
          <li>回测基于「截面超额收益」标签口径，每期等权持有模型打分最高的 {{ params.k }} 只标的。</li>
          <li>交易成本按 A 股实际费率计入：佣金 0.025%（双边）、过户费 0.001%、印花税 0.05%（仅卖出）。</li>
          <li>净值按调仓周期复利，未考虑涨跌停无法成交、流动性冲击与分红再投资等细节。</li>
          <li>回测区间与训练/验证/测试的时序切分一致，测试集未参与任何调参。</li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const data = ref(null)
const loading = ref(true)
const chartRef = ref(null)
let chart = null

const strategy = computed(() => data.value?.strategy || {})
const benchmark = computed(() => data.value?.benchmark || {})
const excess = computed(() => data.value?.excess || {})
const params = computed(() => {
  const p = data.value?.params || {}
  return { ...p, avg_turnover: data.value?.avg_turnover ?? 0 }
})

const compareRows = computed(() => [
  { label: '累计收益', a: strategy.value.total_return, b: benchmark.value.total_return },
  { label: '年化收益', a: strategy.value.annualized_return, b: benchmark.value.annualized_return },
  { label: '年化波动率', a: strategy.value.annualized_volatility, b: benchmark.value.annualized_volatility },
  { label: '夏普比率', a: strategy.value.sharpe, b: benchmark.value.sharpe, fmt: true },
  { label: '最大回撤', a: strategy.value.max_drawdown, b: benchmark.value.max_drawdown },
  { label: '胜率', a: strategy.value.win_rate, b: benchmark.value.win_rate },
])

const isNeutral = computed(() => params.value.selection === 'neutral')

const comparison = ref(null)

const comparisonRows = computed(() => {
  if (!comparison.value) return []
  // 显式映射为模板使用的 s / e 字段：
  // 直接展开原始对象会让模板里的 row.s 为 undefined，访问属性时整页崩溃。
  return [
    { key: 'global', label: '全市场排序', src: comparison.value.global },
    { key: 'neutral', label: '行业中性', src: comparison.value.neutral },
  ]
    .filter((r) => r.src && r.src.strategy && r.src.excess)
    .map((r) => ({
      key: r.key,
      label: r.label,
      s: r.src.strategy,
      e: r.src.excess,
      turnover: r.src.avg_turnover,
      sectors: r.src.avg_sectors_held,
    }))
})

const pct = (v) => (v == null ? '—' : (v * 100).toFixed(2) + '%')
const fmt = (v) => (v == null ? '—' : Number(v).toFixed(4))
const signClass = (v) => (v == null ? '' : v >= 0 ? 'text-pos' : 'text-neg')

const renderChart = () => {
  if (!chartRef.value || !data.value) return
  if (!chart) chart = echarts.init(chartRef.value)

  const nav = strategy.value.nav || []
  const benchNav = benchmark.value.nav || []
  const dates = data.value.dates || []
  const xAxis = nav.map((_, i) => dates[i] || String(i + 1))

  chart.setOption({
    grid: { left: 56, right: 24, top: 40, bottom: 56 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v == null ? '—' : v.toFixed(4)),
    },
    legend: { top: 8, right: 8, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 12 } },
    xAxis: {
      type: 'category',
      data: xAxis,
      axisLabel: { fontSize: 11, color: '#94a3b8', hideOverlap: true },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
    },
    series: [
      {
        name: '策略净值',
        type: 'line',
        data: nav,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#2563eb' },
        areaStyle: { color: 'rgba(37,99,235,0.08)' },
      },
      {
        name: '基准净值',
        type: 'line',
        data: benchNav,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#94a3b8', type: 'dashed' },
      },
    ],
  })
}

const handleResize = () => chart?.resize()

onMounted(async () => {
  try {
    const [res, cmp] = await Promise.all([
      api.getBacktest(),
      api.getBacktestComparison().catch(() => ({ data: null })),
    ])
    data.value = res.data
    comparison.value = cmp.data && !cmp.data.error ? cmp.data : null
  } catch (err) {
    data.value = { error: '回测结果加载失败：' + err.message }
  } finally {
    loading.value = false
    await nextTick()
    renderChart()
    window.addEventListener('resize', handleResize)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.note-card {
  background: var(--slate-50);
}

.row-active {
  background: var(--primary-light);
}

.footnote {
  margin-top: 12px;
  font-size: 12px;
  color: var(--slate-500);
  line-height: 1.7;
}

.note-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--slate-600);
  line-height: 1.9;
}
</style>
