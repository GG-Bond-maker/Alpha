<template>
  <div class="global-view">
    <div class="card">
      <div class="section-header">
        <div>
          <h2>全局决策机制透明度透视 (Global Explainability)</h2>
          <p class="subtitle">基于全市场样本的 TreeSHAP 平均绝对贡献值 (Mean |SHAP|)，解析 LightGBM 推荐系统的宏观因子偏好</p>
        </div>
        <button class="btn btn-outline" @click="fetchData">刷新数据</button>
      </div>

      <div class="overview-grid">
        <div class="info-card">
          <div class="info-badge">CORE</div>
          <div>
            <div class="label">全市场头号驱动因子</div>
            <strong class="value">{{ topFactor ? topFactor.name_cn : '加载中...' }}</strong>
            <p class="desc">对全市场截面排序得分具备最强决定力</p>
          </div>
        </div>
        <div class="info-card">
          <div class="info-badge">ALGO</div>
          <div>
            <div class="label">归因算法机理</div>
            <strong class="value">TreeSHAP (博弈论Shapley值)</strong>
            <p class="desc">具备局部精度与一致性公理证明的精确归因</p>
          </div>
        </div>
        <div class="info-card">
          <div class="info-badge">OPT</div>
          <div>
            <div class="label">推荐优化目标</div>
            <strong class="value">LambdaMART (NDCG@K)</strong>
            <p class="desc">直接优化列表排序截面头部命中质量</p>
          </div>
        </div>
      </div>

      <div class="chart-container">
        <h3>全特征重要性排序图 (Mean Absolute SHAP Value)</h3>
        <p class="chart-sub">柱长代表该指标在模型做出的全部推荐决策中平均引起的得分波动幅度：</p>
        <div ref="chartRef" class="echart-global"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const chartRef = ref(null)
const factors = ref([])
const topFactor = ref(null)
let chartInstance = null

const fetchData = async () => {
  try {
    const res = await api.getGlobalImportance()
    factors.value = res.data
    if (factors.value.length > 0) {
      topFactor.value = factors.value[0]
    }
    await nextTick()
    renderChart()
  } catch (err) {
    console.error('获取全局重要性失败:', err)
  }
}

const renderChart = () => {
  if (!chartRef.value || factors.value.length === 0) return
  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartRef.value)

  // 翻转数组使最重要的特征在条形图顶部
  const reversed = [...factors.value].reverse()
  const yData = reversed.map(f => f.name_cn)
  const xData = reversed.map(f => f.importance)

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: '{b}: 平均绝对贡献 <strong>{c}</strong>'
    },
    grid: { left: '16%', right: '8%', bottom: '5%', top: '5%' },
    xAxis: {
      type: 'value',
      name: 'Mean |SHAP|'
    },
    yAxis: {
      type: 'category',
      data: yData,
      axisLabel: { fontSize: 13, fontWeight: 'bold' }
    },
    series: [
      {
        name: '特征贡献度',
        type: 'bar',
        data: xData,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#3b82f6' },
            { offset: 1, color: '#1d4ed8' }
          ]),
          borderRadius: [0, 6, 6, 0]
        },
        label: {
          show: true,
          position: 'right',
          valueAnimation: true,
          formatter: '{c}'
        }
      }
    ]
  }

  chartInstance.setOption(option)
}

onMounted(() => {
  fetchData()
  window.addEventListener('resize', () => {
    if (chartInstance) chartInstance.resize()
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

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.info-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  padding: 16px;
}

.info-card .icon {
  font-size: 28px;
}

.info-card .label {
  font-size: 12px;
  color: var(--slate-600);
}

.info-card .value {
  font-size: 16px;
  color: var(--slate-900);
  display: block;
  margin: 2px 0;
}

.info-card .desc {
  font-size: 12px;
  color: var(--slate-600);
}

.chart-container {
  margin-top: 10px;
}

.chart-sub {
  font-size: 13px;
  color: var(--slate-600);
  margin-bottom: 12px;
}

.echart-global {
  width: 100%;
  height: 420px;
}
</style>
