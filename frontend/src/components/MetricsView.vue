<template>
  <div>
    <div v-if="loading" class="card">
      <div class="loading-state">
        <div class="spinner"></div>
        正在加载评测结果...
      </div>
    </div>

    <div v-else-if="isEmpty" class="card">
      <div class="empty-state">
        <div class="empty-state-title">暂无评测结果</div>
        <div class="empty-state-desc">{{ message }}</div>
      </div>
    </div>

    <template v-else>
      <div class="card notice-card">
        <span class="source-tag is-real">测试集口径</span>
        <span class="notice-text">
          {{ meta.test_rows ? meta.test_rows.toLocaleString() : '—' }} 条样本 /
          {{ meta.test_dates || '—' }} 个截面 ·
          标签为「{{ meta.label_mode === 'excess_return_5d' ? '5 日截面超额收益' : meta.label_mode }}」·
          正样本占比 {{ meta.test_pos_rate != null ? (meta.test_pos_rate * 100).toFixed(1) + '%' : '—' }}
        </span>
      </div>

      <div v-if="hasErrors" class="card warn-card">
        <div class="card-title" style="margin-bottom: 6px;">部分模型评测失败</div>
        <div class="err-list">
          <div v-for="(msg, name) in errors" :key="name">
            <strong>{{ name }}</strong>：{{ msg }}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">基线对比</div>
            <div class="card-subtitle">
              全部模型在同一测试集、同一特征集上评估；排序指标按截面计算后取均值
            </div>
          </div>
          <button class="btn btn-outline btn-sm" @click="fetchMetrics">刷新</button>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>模型</th>
                <th>NDCG@5</th>
                <th>NDCG@10</th>
                <th>Precision@5</th>
                <th>Precision@10</th>
                <th>HitRate@5</th>
                <th>AUC</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in tableRows" :key="row.name" :class="{ 'row-highlight': row.isOurs }">
                <td>
                  <strong>{{ row.name }}</strong>
                  <span v-if="row.isOurs" class="badge badge-blue" style="margin-left: 6px;">本文方法</span>
                </td>
                <td :class="bestClass('NDCG@5', row.m['NDCG@5'])">{{ fmt(row.m['NDCG@5']) }}</td>
                <td :class="bestClass('NDCG@10', row.m['NDCG@10'])">{{ fmt(row.m['NDCG@10']) }}</td>
                <td :class="bestClass('Precision@5', row.m['Precision@5'])">{{ fmt(row.m['Precision@5']) }}</td>
                <td :class="bestClass('Precision@10', row.m['Precision@10'])">{{ fmt(row.m['Precision@10']) }}</td>
                <td>{{ fmt(row.m['HitRate@5']) }}</td>
                <td :class="bestClass('AUC', row.m['AUC'])">{{ fmt(row.m['AUC']) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="footnote">
          加粗表示该指标在全部模型中排名第一。若本文方法未占优，说明在当前特征集下
          提升幅度未超过基线，属于需要如实报告的实验结果。
        </div>
      </div>

      <div class="chart-grid">
        <div class="card topk-card">
          <div class="card-title" style="margin-bottom: 4px;">Precision@K / NDCG@K</div>
          <div class="card-subtitle" style="margin-bottom: 10px;">
            测试集按交易日截面等权汇总；各 K 使用相同日期，范围 K=1…{{ rankingCurveMeta.max_k || 0 }}，
            截面 {{ rankingCurveMeta.n_dates || 0 }} / {{ rankingCurveMeta.total_dates || 0 }}；
            随机线为 {{ rankingCurveMeta.random_baseline_repeats || 0 }} 次随机排序均值。
            Precision@K 表示前 K 名中跑赢当日候选池均值的比例
          </div>
          <div v-if="hasTopKCurves" class="topk-grid">
            <div ref="precisionRef" style="height: 320px;"></div>
            <div ref="ndcgKRef" style="height: 320px;"></div>
          </div>
          <div v-else class="empty-state compact-empty">
            <div class="empty-state-title">暂无逐 K 评测曲线</div>
            <div class="empty-state-desc">重新运行训练评测后生成 ranking_curves</div>
          </div>
        </div>
        <div class="card">
          <div class="card-title" style="margin-bottom: 4px;">分类能力对比</div>
          <div class="card-subtitle" style="margin-bottom: 10px;">AUC，0.5 相当于随机猜测</div>
          <div ref="aucRef" style="height: 320px;"></div>
        </div>
        <div v-if="hasLossHistory" class="card loss-card">
          <div class="card-title" style="margin-bottom: 4px;">训练损失变化</div>
          <div class="card-subtitle" style="margin-bottom: 10px;">
            每轮 boosting 的 Binary Logloss；验证集用于观察泛化趋势，未使用测试集损失调参
          </div>
          <div ref="lossRef" style="height: 320px;"></div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const loading = ref(true)
const comparison = ref({})
const errors = ref({})
const meta = ref({})
const rankingCurves = ref({})
const rankingCurveMeta = ref({})
const message = ref('')
const aucRef = ref(null)
const precisionRef = ref(null)
const ndcgKRef = ref(null)
const lossRef = ref(null)
let aucChart = null
let precisionChart = null
let ndcgKChart = null
let lossChart = null

const isEmpty = computed(() => Object.keys(comparison.value).length === 0)
const hasErrors = computed(() => Object.keys(errors.value).length > 0)
const hasTopKCurves = computed(() =>
  Object.keys(rankingCurves.value).length > 0 && rankingCurveMeta.value.max_k > 0
)
const lossHistory = computed(() => meta.value.loss_history || {})
const hasLossHistory = computed(() =>
  lossHistory.value.train?.length > 0 && lossHistory.value.validation?.length > 0
)

const tableRows = computed(() =>
  Object.entries(comparison.value).map(([name, m]) => ({
    name,
    m,
    isOurs: name.includes('LightGBM'),
  }))
)

// 每个指标的最优值，用于加粗高亮
const bestOf = (key) => {
  const vals = tableRows.value.map((r) => r.m[key]).filter((v) => typeof v === 'number')
  return vals.length ? Math.max(...vals) : null
}

const bestClass = (key, v) => (v != null && v === bestOf(key) ? 'cell-best' : '')
const fmt = (v) => (v == null ? '—' : Number(v).toFixed(4))

const fetchMetrics = async () => {
  loading.value = true
  try {
    const res = await api.getEvaluationMetrics()
    comparison.value = res.data?.comparison || {}
    errors.value = res.data?.errors || {}
    meta.value = res.data?.meta || {}
    rankingCurves.value = res.data?.ranking_curves || {}
    rankingCurveMeta.value = res.data?.ranking_curve_meta || {}
    message.value = res.data?.message || ''
  } catch (err) {
    message.value = '加载失败：' + err.message
  } finally {
    loading.value = false
    // loading 为真时图表容器不在 DOM 中，必须等切换完成后再渲染
    await nextTick()
    renderCharts()
  }
}

const barOption = (names, series) => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11.5 } },
  grid: { left: 12, right: 20, top: 40, bottom: 20, containLabel: true },
  xAxis: {
    type: 'category',
    data: names,
    axisLabel: { interval: 0, fontSize: 11, color: '#475569', width: 90, overflow: 'break' },
    axisLine: { lineStyle: { color: '#e2e8f0' } },
  },
  yAxis: {
    type: 'value',
    axisLabel: { fontSize: 11, color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#f1f5f9' } },
  },
  series,
})

const renderCharts = () => {
  const names = tableRows.value.map((r) => r.name)
  if (names.length === 0) return

  if (aucRef.value) {
    if (aucChart) aucChart.dispose()
    aucChart = echarts.init(aucRef.value)
    aucChart.setOption({
      ...barOption(names, [
        { name: 'AUC', type: 'bar', data: tableRows.value.map((r) => r.m.AUC), itemStyle: { color: '#8b5cf6', borderRadius: [3, 3, 0, 0] }, barWidth: '46%' },
      ]),
      yAxis: {
        type: 'value',
        min: 0.45,
        max: 0.6,
        axisLabel: { fontSize: 11, color: '#94a3b8' },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      series: [{
        name: 'AUC',
        type: 'bar',
        data: tableRows.value.map((r) => r.m.AUC),
        itemStyle: { color: '#8b5cf6', borderRadius: [3, 3, 0, 0] },
        barWidth: '46%',
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#ef4444', type: 'dashed', width: 1 },
          data: [{ yAxis: 0.5, label: { formatter: '随机猜测 0.5', fontSize: 10, color: '#ef4444' } }],
        },
      }],
    })
  }

  const renderTopK = (element, metric, title) => {
    if (!element || !hasTopKCurves.value) return null
    const firstCurve = Object.values(rankingCurves.value)[0]
    const chart = echarts.init(element)
    const colors = {
      'LightGBM (Ours)': '#2563eb',
      'Random Guess': '#94a3b8',
      'Logistic Regression': '#10b981',
      'Random Forest': '#f59e0b',
    }
    chart.setOption({
      title: { text: title, left: 12, top: 0, textStyle: { fontSize: 14, color: '#334155' } },
      tooltip: { trigger: 'axis', valueFormatter: (v) => Number(v).toFixed(4) },
      legend: { top: 22, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 10.5 } },
      grid: { left: 48, right: 18, top: 58, bottom: 40 },
      xAxis: {
        type: 'category',
        name: 'K',
        nameLocation: 'middle',
        nameGap: 25,
        data: firstCurve.ks,
        axisLabel: { fontSize: 10, color: '#64748b', interval: Math.max(0, Math.floor(firstCurve.ks.length / 8) - 1) },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 1,
        axisLabel: { fontSize: 10, color: '#94a3b8' },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      series: Object.entries(rankingCurves.value).map(([name, curve]) => ({
        name,
        type: 'line',
        data: curve[metric],
        showSymbol: true,
        symbolSize: 4,
        smooth: false,
        lineStyle: { width: name.includes('LightGBM') ? 2.5 : 1.5, color: colors[name] || '#8b5cf6' },
        itemStyle: { color: colors[name] || '#8b5cf6' },
      })),
    })
    return chart
  }

  precisionChart?.dispose()
  ndcgKChart?.dispose()
  precisionChart = renderTopK(precisionRef.value, 'precision', 'Precision@K')
  ndcgKChart = renderTopK(ndcgKRef.value, 'ndcg', 'NDCG@K')

  if (lossRef.value && hasLossHistory.value) {
    if (lossChart) lossChart.dispose()
    lossChart = echarts.init(lossRef.value)
    const history = lossHistory.value
    const count = Math.min(history.train.length, history.validation.length)
    lossChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11.5 } },
      grid: { left: 52, right: 24, top: 40, bottom: 38 },
      xAxis: {
        type: 'category',
        name: '迭代轮次',
        nameLocation: 'middle',
        nameGap: 28,
        data: (history.iterations || Array.from({ length: count }, (_, i) => i + 1)).slice(0, count),
        axisLabel: { fontSize: 11, color: '#64748b' },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
      },
      yAxis: {
        type: 'value',
        name: 'Binary Logloss',
        scale: true,
        axisLabel: { fontSize: 11, color: '#94a3b8' },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      series: [
        { name: '训练集', type: 'line', showSymbol: false, data: history.train.slice(0, count), lineStyle: { width: 2, color: '#2563eb' } },
        { name: '验证集', type: 'line', showSymbol: false, data: history.validation.slice(0, count), lineStyle: { width: 2, color: '#f59e0b' } },
      ],
    })
  }
}

const handleResize = () => {
  aucChart?.resize()
  precisionChart?.resize()
  ndcgKChart?.resize()
  lossChart?.resize()
}

onMounted(() => {
  fetchMetrics()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  aucChart?.dispose()
  precisionChart?.dispose()
  ndcgKChart?.dispose()
  lossChart?.dispose()
})
</script>

<style scoped>
.notice-card {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background: var(--slate-50);
  padding: 14px 18px;
}

.notice-text {
  font-size: 12.5px;
  color: var(--slate-600);
}

.warn-card {
  border-color: #fde68a;
  background: var(--warning-light);
}

.err-list {
  font-size: 12.5px;
  color: #92400e;
  line-height: 1.8;
}

.row-highlight {
  background: var(--primary-light);
}

.cell-best {
  font-weight: 700;
  color: var(--slate-900);
}

.footnote {
  margin-top: 12px;
  font-size: 12px;
  color: var(--slate-500);
  line-height: 1.7;
}

.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.loss-card {
  grid-column: 1 / -1;
}

.topk-card {
  grid-column: 1 / -1;
}

.topk-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.compact-empty {
  padding: 26px 0;
}

@media (max-width: 1100px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }

  .topk-grid {
    grid-template-columns: 1fr;
  }
}
</style>
