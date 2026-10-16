<template>
  <div class="metrics-view">
    <div class="card">
      <div class="section-header">
        <div>
          <h2>推荐系统实证评估与基线对比 (Empirical Evaluation)</h2>
          <p class="subtitle">采用信息检索与推荐系统标准评估准则（NDCG@K, Precision@K, HitRate@K），验证 LightGBM LambdaMART 相对基准算法的优越性</p>
        </div>
        <button class="btn btn-outline" @click="fetchMetrics">刷新评估数据</button>
      </div>

      <!-- 核心指标表格 -->
      <div class="table-container" style="margin-bottom: 28px;">
        <table>
          <thead>
            <tr>
              <th>对比算法模型</th>
              <th>模型建模范式</th>
              <th>NDCG@5</th>
              <th>NDCG@10</th>
              <th>Precision@5</th>
              <th>Precision@10</th>
              <th>HitRate@5</th>
              <th>HitRate@10</th>
            </tr>
          </thead>
          <tbody>
            <tr 
              v-for="(metrics, modelName) in metricsData" 
              :key="modelName"
              :class="{ 'highlight-row': modelName.includes('LightGBM') }"
            >
              <td>
                <strong>{{ modelName }}</strong>
                <span v-if="modelName.includes('LightGBM')" class="badge badge-blue" style="margin-left: 6px;">本文模型</span>
              </td>
              <td>
                <span v-if="modelName.includes('LightGBM')">Listwise (LambdaMART 截面排序)</span>
                <span v-else-if="modelName.includes('Ridge')">Pointwise (线性收益率回归)</span>
                <span v-else-if="modelName.includes('Random Forest')">Pointwise (非线性集成回归)</span>
                <span v-else>无监督 (随机均匀基线)</span>
              </td>
              <td><strong>{{ metrics['NDCG@5'] }}</strong></td>
              <td><strong>{{ metrics['NDCG@10'] }}</strong></td>
              <td>{{ metrics['Precision@5'] }}</td>
              <td>{{ metrics['Precision@10'] }}</td>
              <td>{{ metrics['HitRate@5'] }}</td>
              <td>{{ metrics['HitRate@10'] }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ECharts 对比柱状图 -->
      <div class="charts-grid">
        <div class="chart-card">
          <h3>排序折损累计增益对比 (NDCG@K)</h3>
          <p class="chart-desc">衡量推荐列表头部排列精准度，分值越接近 1.0 表明 Top 排序质量越好：</p>
          <div ref="ndcgChartRef" class="echart-box"></div>
        </div>

        <div class="chart-card">
          <h3>准确率对比 (Precision@K)</h3>
          <p class="chart-desc">衡量推荐出的 K 只股票中真正进入后验优质股票池的命中比例：</p>
          <div ref="precisionChartRef" class="echart-box"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const metricsData = ref({})
const ndcgChartRef = ref(null)
const precisionChartRef = ref(null)
let ndcgChart = null
let precisionChart = null

const fetchMetrics = async () => {
  try {
    const res = await api.getEvaluationMetrics()
    metricsData.value = res.data
    await nextTick()
    renderCharts()
  } catch (err) {
    console.error('获取评估指标失败:', err)
  }
}

const renderCharts = () => {
  if (!metricsData.value || Object.keys(metricsData.value).length === 0) return

  const modelNames = Object.keys(metricsData.value)
  const ndcg5 = modelNames.map(k => metricsData.value[k]['NDCG@5'])
  const ndcg10 = modelNames.map(k => metricsData.value[k]['NDCG@10'])
  const p5 = modelNames.map(k => metricsData.value[k]['Precision@5'])
  const p10 = modelNames.map(k => metricsData.value[k]['Precision@10'])

  // 1. NDCG 柱状图
  if (ndcgChartRef.value) {
    if (ndcgChart) ndcgChart.dispose()
    ndcgChart = echarts.init(ndcgChartRef.value)
    ndcgChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['NDCG@5', 'NDCG@10'] },
      grid: { left: '3%', right: '4%', bottom: '15%', top: '15%', containLabel: true },
      xAxis: {
        type: 'category',
        data: modelNames,
        axisLabel: { interval: 0, rotate: 20, fontSize: 11 }
      },
      yAxis: { type: 'value', min: 0, max: 1.0 },
      series: [
        { name: 'NDCG@5', type: 'bar', data: ndcg5, itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] } },
        { name: 'NDCG@10', type: 'bar', data: ndcg10, itemStyle: { color: '#10b981', borderRadius: [4, 4, 0, 0] } }
      ]
    })
  }

  // 2. Precision 柱状图
  if (precisionChartRef.value) {
    if (precisionChart) precisionChart.dispose()
    precisionChart = echarts.init(precisionChartRef.value)
    precisionChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['Precision@5', 'Precision@10'] },
      grid: { left: '3%', right: '4%', bottom: '15%', top: '15%', containLabel: true },
      xAxis: {
        type: 'category',
        data: modelNames,
        axisLabel: { interval: 0, rotate: 20, fontSize: 11 }
      },
      yAxis: { type: 'value', min: 0, max: 1.0 },
      series: [
        { name: 'Precision@5', type: 'bar', data: p5, itemStyle: { color: '#8b5cf6', borderRadius: [4, 4, 0, 0] } },
        { name: 'Precision@10', type: 'bar', data: p10, itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] } }
      ]
    })
  }
}

onMounted(() => {
  fetchMetrics()
  window.addEventListener('resize', () => {
    if (ndcgChart) ndcgChart.resize()
    if (precisionChart) precisionChart.resize()
  })
})
</script>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.subtitle {
  font-size: 14px;
  color: var(--slate-600);
  margin-top: 4px;
}

.highlight-row {
  background-color: #f0f7ff;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
  gap: 20px;
}

.chart-card {
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  padding: 16px;
}

.chart-desc {
  font-size: 13px;
  color: var(--slate-600);
  margin-bottom: 10px;
}

.echart-box {
  width: 100%;
  height: 320px;
}
</style>
