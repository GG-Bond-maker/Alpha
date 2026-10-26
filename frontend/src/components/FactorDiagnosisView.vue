<template>
  <div>
    <div v-if="loading" class="card">
      <div class="loading-state">
        <div class="spinner"></div>
        正在加载因子诊断...
      </div>
    </div>

    <div v-else-if="results.length === 0" class="card">
      <div class="empty-state">
        <div class="empty-state-title">暂无因子诊断结果</div>
        <div class="empty-state-desc">{{ message }}</div>
      </div>
    </div>

    <template v-else>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">检验因子数</div>
          <div class="stat-value">{{ results.length }}</div>
          <div class="stat-hint">技术指标 + 量价 + 基本面</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">入选因子数</div>
          <div class="stat-value">{{ usable.length }}</div>
          <div class="stat-hint">|IC| ≥ {{ criteria.min_abs_ic }} 且 |t| ≥ {{ criteria.min_abs_t }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">有效截面数</div>
          <div class="stat-value">{{ formatInt(nSections) }}</div>
          <div class="stat-hint">{{ nStocks }} 只标的</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最强因子</div>
          <div class="stat-value" style="font-size: 16px;">{{ topFactor?.name_cn || '—' }}</div>
          <div class="stat-hint">IC = {{ topFactor?.ic_mean }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">因子有效性检验表</div>
            <div class="card-subtitle">
              IC 为逐截面 Spearman 秩相关的均值；t 值 = ICIR × √截面数，|t| ≥ 2 视为统计显著
            </div>
          </div>
          <button class="btn btn-outline btn-sm" @click="fetchData">刷新</button>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th style="width: 56px;">排名</th>
                <th>因子</th>
                <th>类别</th>
                <th>IC 均值</th>
                <th>ICIR</th>
                <th>t 值</th>
                <th>IC&gt;0 占比</th>
                <th>Top-Bottom</th>
                <th>单调</th>
                <th>结论</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, idx) in results" :key="r.factor"
                  :class="{ 'row-selected': r.factor === selectedFactor, 'row-in': r.usable }"
                  class="clickable-row"
                  @click="selectFactor(r.factor)">
                <td><span class="badge badge-silver">{{ idx + 1 }}</span></td>
                <td>
                  <strong>{{ r.name_cn || r.factor }}</strong>
                  <span v-if="r.factor === selectedFactor" class="badge badge-blue" style="margin-left: 6px;">查看中</span>
                </td>
                <td>
                  <span class="badge" :class="categoryClass(r.factor)">{{ categoryOf(r.factor) }}</span>
                </td>
                <td :class="r.ic_mean > 0 ? 'text-pos' : r.ic_mean < 0 ? 'text-neg' : 'text-muted'">{{ r.ic_mean.toFixed(4) }}</td>
                <td>{{ r.icir.toFixed(3) }}</td>
                <td :class="Math.abs(r.t_stat) >= 2 ? 'cell-strong' : ''">
                  {{ r.t_stat.toFixed(2) }}
                </td>
                <td>{{ (r.ic_positive_ratio * 100).toFixed(1) }}%</td>
                <td>
                  {{ r.top_minus_bottom != null ? (r.top_minus_bottom * 100).toFixed(2) + '%' : '—' }}
                </td>
                <td>
                  <span v-if="r.monotonic" class="badge badge-green">是</span>
                  <span v-else class="text-muted">否</span>
                </td>
                <td>
                  <span v-if="r.usable" class="badge badge-green">入选</span>
                  <span v-else class="badge badge-silver">剔除</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" ref="chartCardRef">
        <div class="card-header">
          <div>
            <div class="card-title">
              分层收益单调性
              <span v-if="currentFactor" class="badge badge-blue" style="font-size: 13px; margin-left: 8px;">
                {{ currentFactor.name_cn || currentFactor.factor }}
              </span>
            </div>
            <div class="card-subtitle">按因子值分 5 组，观察各组平均前瞻收益是否随因子值单调变化（点击上方表格行可直接切换）</div>
          </div>
          <select v-model="selectedFactor" class="form-select">
            <option v-for="r in results" :key="r.factor" :value="r.factor">
              {{ r.name_cn || r.factor }}
            </option>
          </select>
        </div>
        <div ref="layerRef" style="height: 320px;"></div>
      </div>

      <div class="card note-card">
        <div class="card-title" style="margin-bottom: 8px;">方法与解读</div>
        <ul class="note-list">
          <li><strong>IC（信息系数）</strong>：每个交易日内，因子值与未来 5 日收益的 Spearman 秩相关。均值越远离 0，说明因子的横截面区分能力越强。</li>
          <li><strong>ICIR</strong>：IC 均值除以 IC 标准差，衡量稳定性。日频 IC 波动大，ICIR 普遍偏低，因此不作为硬性门槛。</li>
          <li><strong>t 值</strong>：ICIR × √截面数，用于判断 IC 均值是否显著异于 0。|t| ≥ 2 相当于 95% 置信水平。</li>
          <li><strong>分层收益</strong>：若 Top 组收益显著高于 Bottom 组且中间单调，说明因子可用于排序；否则即使 IC 显著也难以转化为可交易信号。</li>
          <li>行业中性化在入模前完成：因子先按申万行业截面去均值，再标准化，避免模型学到「这是银行」而非「这个估值便宜」。</li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const loading = ref(true)
const results = ref([])
const usable = ref([])
const criteria = ref({ min_abs_ic: 0.015, min_abs_t: 2.0 })
const nSections = ref(0)
const nStocks = ref(0)
const message = ref('')
const selectedFactor = ref('')
const layerRef = ref(null)
const chartCardRef = ref(null)
let chart = null

const topFactor = computed(() => results.value[0] || null)
const currentFactor = computed(() => results.value.find((r) => r.factor === selectedFactor.value) || null)

const selectFactor = (factor) => {
  selectedFactor.value = factor
}

const FUNDAMENTAL = ['pe_ttm', 'pb', 'roe', 'roa', 'gross_margin', 'net_margin',
  'debt_ratio', 'revenue_growth', 'profit_growth']
const PRICE = ['momentum_20d', 'momentum_60d', 'volatility_20d', 'turnover_proxy']

const categoryOf = (f) => {
  if (FUNDAMENTAL.includes(f)) return '基本面'
  if (PRICE.includes(f)) return '量价'
  return '技术'
}

const categoryClass = (f) => {
  const c = categoryOf(f)
  if (c === '基本面') return 'badge-blue'
  if (c === '量价') return 'badge-gold'
  return 'badge-silver'
}

const formatInt = (v) => (v == null ? '—' : Number(v).toLocaleString())

const fetchData = async () => {
  loading.value = true
  try {
    const res = await api.getFactorDiagnosis()
    const d = res.data || {}
    results.value = d.results || []
    usable.value = d.usable_factors || []
    criteria.value = d.criteria || criteria.value
    nSections.value = d.n_sections_total || 0
    nStocks.value = d.n_stocks_total || 0
    message.value = d.message || ''
    if (!selectedFactor.value && results.value.length) {
      selectedFactor.value = results.value[0].factor
    }
  } catch (err) {
    message.value = '加载失败：' + err.message
  } finally {
    loading.value = false
    // loading 为真时图表容器不在 DOM 中，必须等切换完成后再渲染
    await nextTick()
    renderLayer()
  }
}

const renderLayer = () => {
  if (!layerRef.value) return
  const target = results.value.find((r) => r.factor === selectedFactor.value)
  if (!target || !target.layered_returns) return
  if (!chart) chart = echarts.init(layerRef.value)

  const layers = target.layered_returns
  const labels = layers.map((_, i) => 'Q' + (i + 1))
  const values = layers.map((v) => (v == null ? 0 : v * 100))

  chart.setOption({
    grid: { left: 56, right: 24, top: 30, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (v) => v.toFixed(3) + '%',
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { fontSize: 12, color: '#475569' },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'value',
      name: '平均前瞻收益 (%)',
      nameTextStyle: { fontSize: 11, color: '#94a3b8' },
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
    },
    series: [{
      type: 'bar',
      data: values,
      barWidth: '52%',
      itemStyle: {
        color: (p) => (p.value >= 0 ? '#dc2626' : '#16a34a'),
        borderRadius: [3, 3, 0, 0],
      },
      label: {
        show: true,
        position: 'top',
        fontSize: 11,
        color: '#64748b',
        formatter: (p) => p.value.toFixed(2) + '%',
      },
    }],
  }, true)
}

watch(selectedFactor, () => nextTick(renderLayer))
const handleResize = () => chart?.resize()

onMounted(() => {
  fetchData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.clickable-row {
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.clickable-row:hover {
  background-color: var(--slate-100) !important;
}

.row-selected {
  background: #eff6ff !important;
  box-shadow: inset 3px 0 0 var(--primary);
}

.row-selected td strong {
  color: var(--primary);
}

.row-in {
  background: #f0fdf4;
}

.cell-strong {
  font-weight: 700;
  color: var(--slate-900);
}

.note-card {
  background: var(--slate-50);
}

.note-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--slate-600);
  line-height: 1.9;
}
</style>
