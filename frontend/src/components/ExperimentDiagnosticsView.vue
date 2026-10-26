<template>
  <div v-if="loading" class="card" role="status">正在加载本批次实验诊断…</div>
  <div v-else-if="error" class="card" role="alert">
    <p>{{ error }}</p><button class="btn btn-outline" @click="load">重新加载</button>
  </div>
  <div v-else class="diagnostics">
    <div class="card diagnostic-context">
      <p>测试区间 <strong>{{ data.date_range?.join(' 至 ') }}</strong> · 以下图表均来自该区间的真实模型输出。</p>
      <dl>
        <div><dt>Brier 分数</dt><dd>{{ number(data.calibration?.brier_score) }}</dd></div>
        <div><dt>校准误差 ECE</dt><dd>{{ number(data.calibration?.ece) }}</dd></div>
        <div><dt>平均 Rank IC</dt><dd>{{ number(data.rank_ic?.mean) }}</dd></div>
        <div><dt>IC 的 HAC t 值</dt><dd>{{ number(data.rank_ic?.hac_t, 2) }}</dd></div>
      </dl>
      <p class="diagnostic-note">模型分数表示跑赢当日候选池均值的倾向；未经概率校准。测试标签仅用于诊断，不据此调整模型。</p>
    </div>
    <div class="diagnostic-panels">
      <section class="card">
        <h2>概率可靠性图</h2>
        <p class="diagnostic-note">越接近虚线，分组预测均值与实际跑赢比例越一致；点大小表示样本数量。</p>
        <div ref="calibrationRef" class="diagnostic-chart" role="img" aria-label="预测分数分箱均值与实际跑赢比例散点图"></div>
        <details><summary>查看分箱数据</summary>
          <div class="table-wrap"><table><thead><tr><th>区间</th><th>样本</th><th>预测均值</th><th>实际比例</th></tr></thead><tbody>
            <tr v-for="row in data.calibration?.bins || []" :key="row.lower"><td>{{ row.lower.toFixed(1) }}–{{ row.upper.toFixed(1) }}</td><td>{{ row.count }}</td><td>{{ percent(row.mean_prediction) }}</td><td>{{ percent(row.observed_rate) }}</td></tr>
          </tbody></table></div>
        </details>
      </section>
      <section class="card">
        <h2>截面 Rank IC 随时间变化</h2>
        <p class="diagnostic-note">每天比较模型排序与未来超额收益排序。20 日均值用于观察信号变化，HAC t 值考虑标签重叠。</p>
        <div ref="icRef" class="diagnostic-chart" role="img" aria-label="每日 Rank IC 和二十日滚动均值折线图"></div>
      </section>
      <section class="card">
        <div class="diagnostic-heading"><h2>平仓月份收益分布</h2>
          <select v-model="monthlyMode" class="form-select" aria-label="选择月度收益口径"><option value="strategy">策略净收益</option><option value="benchmark">基准净收益</option><option value="relative">相对基准收益</option></select>
        </div>
        <p class="diagnostic-note">{{ data.monthly_note }}</p>
        <div ref="monthlyRef" class="diagnostic-chart" role="img" aria-label="按平仓月份归属的已完成持有期收益热力图"></div>
        <details><summary>查看逐月数据</summary>
          <div class="table-wrap"><table><thead><tr><th>平仓月份</th><th>持有期数</th><th>策略净收益</th><th>基准净收益</th></tr></thead><tbody>
            <tr v-for="row in data.monthly_settled_returns || []" :key="row.month"><td>{{ row.month }}</td><td>{{ row.periods }}</td><td>{{ percent(row.strategy) }}</td><td>{{ percent(row.benchmark) }}</td></tr>
          </tbody></table></div>
        </details>
      </section>
      <section class="card">
        <div class="diagnostic-heading"><h2>SHAP 特征依赖图</h2>
          <select v-if="features.length" v-model="selectedFeature" class="form-select" aria-label="选择 SHAP 特征"><option v-for="f in features" :key="f.feature" :value="f.feature">{{ f.name_cn }}</option></select>
        </div>
        <p class="diagnostic-note">横轴是行业中性化并标准化后的模型输入，纵轴是 log-odds 贡献；体现模型关联，不表示因果效应。</p>
        <div v-if="features.length" ref="shapRef" class="diagnostic-chart" role="img" aria-label="标准化特征值和 SHAP 贡献散点图"></div>
        <p v-else class="diagnostic-note">本批次尚无 SHAP 抽样数据。</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const loading = ref(true), error = ref(''), data = ref({}), features = ref([])
const selectedFeature = ref(''), monthlyMode = ref('strategy')
const calibrationRef = ref(null), icRef = ref(null), monthlyRef = ref(null), shapRef = ref(null)
const charts = []
let observer
const number = (v, digits = 4) => v == null ? '—' : Number(v).toFixed(digits)
const percent = (v) => v == null ? '—' : (v * 100).toFixed(2) + '%'
const base = { textStyle: { fontFamily: 'Microsoft YaHei, sans-serif', color: '#334155' }, animation: false,
  grid: { left: 55, right: 24, top: 36, bottom: 56 }, tooltip: { trigger: 'item', confine: true } }

function mountChart(element, options) {
  if (!element) return
  const chart = echarts.getInstanceByDom(element) || echarts.init(element, null, { renderer: 'svg' })
  if (!charts.includes(chart)) charts.push(chart)
  chart.setOption({ ...base, ...options }, true)
}

function render() {
  const bins = (data.value.calibration?.bins || []).filter(b => b.count)
  mountChart(calibrationRef.value, {
    xAxis: { type: 'value', min: 0, max: 1, name: '预测分数', nameLocation: 'middle', nameGap: 32 },
    yAxis: { type: 'value', min: 0, max: 1, name: '实际跑赢比例' },
    series: [{ type: 'line', data: [[0, 0], [1, 1]], symbol: 'none', lineStyle: { type: 'dashed', color: '#64748b' }, silent: true },
      { type: 'scatter', data: bins.map(b => [b.mean_prediction, b.observed_rate, b.count]),
        symbolSize: v => 8 + Math.min(14, Math.log1p(v[2])), itemStyle: { color: '#2563eb' },
        tooltip: { formatter: p => `预测均值 ${percent(p.value[0])}<br>实际比例 ${percent(p.value[1])}<br>样本 ${p.value[2]}` } }],
  })
  const ic = data.value.rank_ic || {}
  mountChart(icRef.value, {
    tooltip: { trigger: 'axis', confine: true }, legend: { data: ['每日 IC', '20 日均值'], top: 0 },
    xAxis: { type: 'category', data: ic.dates || [], axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', name: 'Rank IC' },
    dataZoom: [{ type: 'inside', filterMode: 'none' }],
    series: [{ name: '每日 IC', type: 'line', data: ic.values || [], showSymbol: false, lineStyle: { color: '#94a3b8', width: 1 } },
      { name: '20 日均值', type: 'line', data: ic.rolling_20 || [], showSymbol: false, lineStyle: { color: '#2563eb', width: 2 },
        markLine: { symbol: 'none', data: [{ yAxis: 0 }], lineStyle: { color: '#475569' } } }],
  })
  const months = data.value.monthly_settled_returns || []
  const years = [...new Set(months.map(r => r.month.slice(0, 4)))].sort().reverse()
  const points = months.map(r => [Number(r.month.slice(5)) - 1, years.indexOf(r.month.slice(0, 4)),
    monthlyMode.value === 'relative' ? (1 + r.strategy) / (1 + r.benchmark) - 1 : r[monthlyMode.value], r.periods])
  const limit = Math.max(0.01, ...points.map(p => Math.abs(p[2])))
  mountChart(monthlyRef.value, {
    grid: { left: 55, right: 24, top: 25, bottom: 90 },
    xAxis: { type: 'category', data: Array.from({ length: 12 }, (_, i) => `${i + 1}月`) },
    yAxis: { type: 'category', data: years, splitArea: { show: true } },
    visualMap: { min: -limit, max: limit, orient: 'horizontal', left: 'center', bottom: 5,
      dimension: 2, inRange: { color: ['#1d4ed8', '#ffffff', '#b42318'] }, text: ['盈利', '亏损'], formatter: v => percent(v) },
    series: [{ type: 'heatmap', data: points, label: { show: (monthlyRef.value?.clientWidth || 0) >= 460, formatter: p => (p.value[2] * 100).toFixed(1) + '%' },
      tooltip: { formatter: p => `${years[p.value[1]]}-${String(p.value[0] + 1).padStart(2, '0')}<br>${percent(p.value[2])}<br>已完成持有期 ${p.value[3]}` } }],
  })
  const feature = features.value.find(f => f.feature === selectedFeature.value)
  if (feature) {
    const samples = (feature.feature_values || []).map((v, i) => [v, feature.shap_values?.[i]])
      .filter(v => v.every(n => n != null && Number.isFinite(Number(n))))
    mountChart(shapRef.value, { xAxis: { type: 'value', name: '标准化特征值', nameLocation: 'middle', nameGap: 32 },
      yAxis: { type: 'value', name: 'SHAP (log-odds)' },
      series: [{ type: 'scatter', data: samples, symbolSize: 5, itemStyle: { color: '#2563eb', opacity: 0.5 } }],
    })
  }
}

async function load() {
  loading.value = true
  error.value = ''
  for (const chart of charts.splice(0)) chart.dispose()
  observer?.disconnect()
  try {
    const [diagnostics, summary] = await Promise.all([api.getDiagnostics(), api.getGlobalShapSummary()])
    if (diagnostics.data.error) throw new Error(diagnostics.data.error)
    data.value = diagnostics.data
    features.value = summary.data?.summary?.features || []
    selectedFeature.value = features.value[0]?.feature || ''
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '加载失败，请重试。'
  } finally {
    loading.value = false
    await nextTick()
    if (!error.value) {
      render()
      observer = new ResizeObserver(() => { charts.forEach(c => c.resize()); render() })
      for (const node of [calibrationRef.value, icRef.value, monthlyRef.value, shapRef.value]) if (node) observer.observe(node)
    }
  }
}
watch([monthlyMode, selectedFeature], () => { if (!loading.value && !error.value) render() })
onMounted(load)
onBeforeUnmount(() => { observer?.disconnect(); charts.forEach(c => c.dispose()) })
</script>

<style scoped>
.diagnostic-panels { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.diagnostic-panels .card { min-width: 0; margin: 0; }
.diagnostic-panels h2 { font-size: 17px; font-weight: 650; margin: 0 0 10px; color: #0f172a; }
.diagnostic-note { color: #475569; font-size: 14px; line-height: 1.65; margin: 8px 0 12px; }
.diagnostic-chart { width: 100%; height: 330px; }
.diagnostic-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.diagnostic-heading select { max-width: 220px; min-width: 0; }
.diagnostic-context p { line-height: 1.6; margin: 0 0 12px; }
.diagnostic-context dl { display: flex; gap: 18px 40px; flex-wrap: wrap; margin: 16px 0; font-variant-numeric: tabular-nums; }
.diagnostic-context dt { font-size: 14px; color: #475569; margin-bottom: 4px; }
.diagnostic-context dd { margin: 0; font-size: 19px; font-weight: 650; color: #0f172a; }
details { margin-top: 12px; }
summary { cursor: pointer; color: #1d4ed8; font-size: 14px; padding: 6px 0; }
select:focus-visible, summary:focus-visible { outline: 2px solid #2563eb; outline-offset: 3px; }
@media (max-width: 1100px) { .diagnostic-panels { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .diagnostic-chart { height: 300px; } .diagnostic-heading select { width: 100%; max-width: none; } }
</style>
