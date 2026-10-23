<template>
  <div>
    <div v-if="loading" class="card">
      <div class="loading-state">
        <div class="spinner"></div>
        正在加载归因数据...
      </div>
    </div>

    <div v-else-if="factors.length === 0" class="card">
      <div class="empty-state">
        <div class="empty-state-title">暂无归因数据</div>
        <div class="empty-state-desc">请先运行 python -m ml_pipeline.run_training 生成 SHAP 产物</div>
      </div>
    </div>

    <template v-else>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">首要驱动因子</div>
          <div class="stat-value" style="font-size: 17px;">{{ topFactor?.name_cn || '—' }}</div>
          <div class="stat-hint">重要性占比 {{ topFactor ? (topFactor.importance * 100).toFixed(1) + '%' : '—' }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">归因算法</div>
          <div class="stat-value" style="font-size: 17px;">TreeSHAP</div>
          <div class="stat-hint">满足局部精度与一致性公理</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">特征维度</div>
          <div class="stat-value">{{ factors.length }}</div>
          <div class="stat-hint">行业中性化后的模型特征</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">加和一致性</div>
          <div class="stat-value" :class="additivity?.passed ? 'text-pos' : 'text-neg'">
            {{ additivity ? (additivity.passed ? '通过' : '未通过') : '—' }}
          </div>
          <div class="stat-hint">
            最大误差 {{ additivity ? additivity.max_abs_error : '—' }}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">SHAP summary beeswarm</div>
            <div class="card-subtitle">
              测试集 {{ summaryMeta.sample_rows || 0 }} 个样本 / {{ summaryMeta.sample_dates || 0 }} 个日期；
              中性化标准化特征的 SHAP 贡献分布，颜色表示特征值相对高低
            </div>
          </div>
          <button class="btn btn-outline btn-sm" @click="fetchData">刷新</button>
        </div>
        <div v-if="summaryFeatures.length" ref="chartRef" style="height: 480px;"></div>
        <div v-else class="empty-state">
          <div class="empty-state-title">暂无 SHAP 分布样本</div>
          <div class="empty-state-desc">请重新训练模型以生成 shap_summary.json</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title" style="margin-bottom: 14px;">特征重要性明细</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th style="width: 60px;">排名</th>
                <th>特征名称</th>
                <th>字段名</th>
                <th>Mean |SHAP|</th>
                <th>重要性占比</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(f, idx) in factors" :key="f.feature_key">
                <td><span class="badge badge-silver">{{ idx + 1 }}</span></td>
                <td><strong>{{ f.name_cn }}</strong></td>
                <td><code class="code-font">{{ f.feature_key }}</code></td>
                <td>{{ f.mean_abs_shap != null ? f.mean_abs_shap.toFixed(4) : '—' }}</td>
                <td>{{ (f.importance * 100).toFixed(2) }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card note-card">
        <div class="card-title" style="margin-bottom: 8px;">如何解读</div>
        <ul class="note-list">
          <li>横轴为 SHAP 值（模型原始 log-odds 空间）：正值提高模型分数，负值降低模型分数；每个点代表一个测试集样本。</li>
          <li>颜色表示该特征值在可视化样本中的相对分位；特征值是逐日缩尾、行业中性化并做截面 z-score 标准化后的模型输入。</li>
          <li>SHAP 描述模型中的关联贡献，不代表因果关系；个股局部归因仍可在 Top-K 推荐页查看。</li>
          <li>加和一致性校验确认 Σ SHAP + base_value 与模型原始输出一致，是归因可信的前提。</li>
          <li>若某特征排名靠前但缺乏经济学解释，应在论文中讨论其是否为伪因子，而非直接当作有效信号。</li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const loading = ref(true)
const factors = ref([])
const summaryFeatures = ref([])
const summaryMeta = ref({})
const additivity = ref(null)
const chartRef = ref(null)
let chart = null

const topFactor = computed(() => factors.value[0] || null)

const fetchData = async () => {
  loading.value = true
  try {
    const res = await api.getGlobalShapSummary()
    factors.value = res.data?.importance || []
    summaryFeatures.value = res.data?.summary?.features || []
    summaryMeta.value = res.data?.summary || {}
  } catch (err) {
    console.error('加载全局重要性失败:', err)
    factors.value = []
    summaryFeatures.value = []
    summaryMeta.value = {}
  } finally {
    loading.value = false
    // 必须等 loading 造成的 DOM 切换完成后再渲染：
    // loading 为真时模板不渲染图表容器，提前渲染会因 chartRef 为空而静默跳过。
    await nextTick()
    renderChart()
  }
}

const renderChart = () => {
  if (!chartRef.value || summaryFeatures.value.length === 0) return
  if (!chart) chart = echarts.init(chartRef.value)

  const sorted = summaryFeatures.value
  const featureNames = sorted.map((f) => f.name_cn || f.feature)
  const shapAbs = sorted.flatMap((f) => f.shap_values || []).map((v) => Math.abs(Number(v)))
    .filter(Number.isFinite).sort((a, b) => a - b)
  const xLimit = Math.max(shapAbs[Math.floor((shapAbs.length - 1) * 0.99)] || 0, 0.01)
  const points = []
  sorted.forEach((feature, featureIndex) => {
    const shapValues = feature.shap_values || []
    const featureValues = feature.feature_values || []
    const percentiles = feature.feature_value_percentiles || []
    shapValues.forEach((shapValue, sampleIndex) => {
      const value = Number(shapValue)
      if (!Number.isFinite(value)) return
      const jitter = (((sampleIndex * 37 + featureIndex * 17) % 97) / 97 - 0.5) * 0.58
      const rawFeatureValue = featureValues[sampleIndex]
      const percentile = percentiles[sampleIndex]
      points.push([
        Math.max(-xLimit, Math.min(xLimit, value)),
        featureIndex + jitter,
        percentile == null ? -1 : Number(percentile),
        rawFeatureValue == null ? null : Number(rawFeatureValue),
      ])
    })
  })

  chart.setOption({
    grid: { left: 150, right: 100, top: 20, bottom: 48 },
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const [shapValue, yValue, , featureValue] = params.value
        const name = featureNames[Math.round(yValue)] || '特征'
        const shownValue = featureValue == null ? '缺失' : Number(featureValue).toFixed(4)
        return `${name}<br/>SHAP 值：${Number(shapValue).toFixed(4)}<br/>标准化特征值：${shownValue}`
      },
    },
    xAxis: {
      type: 'value',
      name: 'SHAP 值（log-odds）',
      nameLocation: 'middle',
      nameGap: 30,
      min: -xLimit,
      max: xLimit,
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
    },
    yAxis: {
      type: 'value',
      min: -0.5,
      max: Math.max(sorted.length - 0.5, 0.5),
      interval: 1,
      inverse: true,
      axisLabel: {
        fontSize: 12,
        color: '#475569',
        formatter: (v) => featureNames[Math.round(v)] || '',
      },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    visualMap: {
      type: 'continuous',
      dimension: 2,
      min: 0,
      max: 1,
      orient: 'vertical',
      right: 4,
      top: 'middle',
      itemHeight: 140,
      text: ['高', '低'],
      textStyle: { color: '#64748b', fontSize: 11 },
      inRange: { color: ['#3b82f6', '#cbd5e1', '#ef4444'] },
      outOfRange: { color: '#94a3b8' },
      calculable: false,
    },
    series: [{
      name: '测试集样本',
      type: 'scatter',
      data: points,
      symbolSize: 7,
      itemStyle: { opacity: 0.72 },
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: { color: '#64748b', type: 'dashed', width: 1 },
        data: [{ xAxis: 0 }],
      },
    }],
  })
}

const handleResize = () => chart?.resize()

onMounted(async () => {
  await fetchData()
  try {
    const rep = await api.getTrainingReport()
    additivity.value = rep.data?.shap_additivity || null
  } catch (e) {
    additivity.value = null
  }
  window.addEventListener('resize', handleResize)
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

.note-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--slate-600);
  line-height: 1.9;
}
</style>
