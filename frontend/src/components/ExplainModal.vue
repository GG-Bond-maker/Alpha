<template>
  <dialog 
    ref="dialogRef" 
    closedby="any" 
    aria-labelledby="dialogTitle"
    class="explain-dialog"
  >
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>正在计算 TreeSHAP 特征贡献归因...</p>
    </div>

    <div v-else-if="data" class="dialog-content">
      <!-- 头部信息 -->
      <div class="dialog-header">
        <div>
          <div class="header-badges">
            <span class="badge badge-blue">{{ data.industry }}</span>
            <span class="badge badge-gold">模型池内第 {{ data.predicted_rank }} 名</span>
            <span class="stock-code">{{ data.stock_code }}</span>
          </div>
          <h2 id="dialogTitle" class="stock-title">{{ data.stock_name }} - 特征归因诊断</h2>
        </div>
        <button class="close-btn" @click="closeModal" aria-label="关闭">&times;</button>
      </div>

      <div class="dialog-body">
        <!-- 结构化自然语言理由卡片 -->
        <div class="reason-card">
          <div class="reason-title">
            <span class="icon-tag">模型</span>
            <strong>特征归因摘要</strong>
          </div>
          <p class="reason-text">{{ data.natural_language_reason }}</p>
        </div>

        <!-- 预测得分分解汇总 -->
        <div class="score-summary">
          <div class="score-pill">
            <span class="label">基准输出值 (Base Value):</span>
            <strong class="value">{{ data.base_value }} (log-odds)</strong>
          </div>
          <div class="score-pill plus">
            <span class="label">正向特征总贡献:</span>
            <strong class="value">+{{ totalPositiveShap }}</strong>
          </div>
          <div class="score-pill minus">
            <span class="label">负向特征总扣减:</span>
            <strong class="value">{{ totalNegativeShap }}</strong>
          </div>
          <div class="score-pill total">
            <span class="label">模型输出 (log-odds):</span>
            <strong class="value">{{ data.predicted_margin }}</strong>
          </div>
        </div>

        <!-- ECharts 瀑布图容器 -->
        <div class="chart-wrapper">
          <h3 class="section-title">SHAP 瀑布归因图 (log-odds 空间)</h3>
          <p class="section-desc">图中基准值、SHAP 贡献与最终模型输出均为原始 LightGBM log-odds。排序分数 {{ data.predicted_score }}；校准后跑赢概率 {{ data.calibrated_probability == null ? '未生成' : (data.calibrated_probability * 100).toFixed(1) + '%' }}。SHAP 解释模型分数，不解释收益或保证。</p>
          <div ref="waterfallChartRef" class="echart-box"></div>
        </div>

        <div v-if="data.factor_breakdown?.length" class="table-wrapper">
          <h3 class="section-title">多因子对照依据 · {{ data.factor_score?.toFixed(1) }} / 100</h3>
          <p class="section-desc">方向与权重来自训练期；这是可解释对照分数，默认推荐仍按 LightGBM 排序。</p>
          <table><thead><tr><th>因子</th><th>方向</th><th>训练 IC</th><th>权重</th><th>当日方向分位</th></tr></thead><tbody><tr v-for="factor in data.factor_breakdown" :key="factor.feature"><td>{{ factor.name_cn }}</td><td>{{ factor.direction > 0 ? '较高值优先' : '较低值优先' }}</td><td>{{ factor.ic?.toFixed(4) }}</td><td>{{ (factor.weight * 100).toFixed(1) }}%</td><td>{{ factor.percentile == null ? '缺失' : (factor.percentile * 100).toFixed(1) + '%' }}</td></tr></tbody></table>
        </div>

        <!-- 特征明细清单 -->
        <div class="table-wrapper">
          <h3 class="section-title">多维特征 SHAP 贡献明细表</h3>
          <table>
            <thead>
              <tr>
                <th>特征指标</th>
                <th>指标实际取值</th>
                <th>SHAP 贡献分 (Impact)</th>
                <th>驱动方向</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="feat in sortedFeatures" :key="feat.feature_key">
                <td><strong>{{ feat.name_cn }}</strong></td>
                <td>{{ feat.feature_value }}</td>
                <td :class="feat.shap_value > 0 ? 'text-pos' : feat.shap_value < 0 ? 'text-neg' : 'text-muted'">
                  {{ feat.shap_value >= 0 ? '+' + feat.shap_value : feat.shap_value }}
                </td>
                <td>
                  <span v-if="feat.shap_value > 0" class="badge badge-stock-up">正向驱动</span>
                  <span v-else-if="feat.shap_value < 0" class="badge badge-stock-down">负向压制</span>
                  <span v-else class="badge badge-silver">中性</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="dialog-footer">
        <button class="btn btn-outline" @click="closeModal">关闭</button>
      </div>
    </div>
  </dialog>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import * as echarts from 'echarts'

const dialogRef = ref(null)
const waterfallChartRef = ref(null)
const data = ref(null)
const loading = ref(false)
let chartInstance = null

const totalPositiveShap = computed(() => {
  if (!data.value) return 0
  const sum = data.value.features
    .filter(f => f.shap_value > 0)
    .reduce((acc, f) => acc + f.shap_value, 0)
  return sum.toFixed(3)
})

const totalNegativeShap = computed(() => {
  if (!data.value) return 0
  const sum = data.value.features
    .filter(f => f.shap_value < 0)
    .reduce((acc, f) => acc + f.shap_value, 0)
  return sum.toFixed(3)
})

const sortedFeatures = computed(() => {
  if (!data.value) return []
  return [...data.value.features].sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value))
})

const openModal = async (explainData) => {
  data.value = explainData
  dialogRef.value.showModal()
  await nextTick()
  initWaterfallChart()
}

const closeModal = () => {
  if (dialogRef.value) {
    dialogRef.value.close()
  }
}

const initWaterfallChart = () => {
  if (!waterfallChartRef.value || !data.value) return
  if (chartInstance) {
    chartInstance.dispose()
  }
  chartInstance = echarts.init(waterfallChartRef.value)

  // 准备瀑布图数据
  const sorted = [...data.value.features].sort((a, b) => b.shap_value - a.shap_value)
  const categories = ['基准 log-odds', ...sorted.map(f => f.name_cn), '模型输出']
  
  // 瀑布图辅助柱与实际柱
  const baseVal = data.value.base_value
  let currentVal = baseVal
  const placeholderData = [0]
  const posData = [baseVal >= 0 ? baseVal : 0]
  const negData = [baseVal < 0 ? -baseVal : 0]

  sorted.forEach(f => {
    const val = f.shap_value
    if (val >= 0) {
      placeholderData.push(currentVal)
      posData.push(val)
      negData.push('-')
      currentVal += val
    } else {
      currentVal += val
      placeholderData.push(currentVal)
      posData.push('-')
      negData.push(-val)
    }
  })

  // 最终总分
  placeholderData.push(0)
  posData.push(data.value.predicted_margin >= 0 ? data.value.predicted_margin : '-')
  negData.push(data.value.predicted_margin < 0 ? -data.value.predicted_margin : '-')

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const item = params[1] && params[1].value !== '-' ? params[1] : params[2]
        return `${item.name}<br/>${item.seriesName}: ${item.value}`
      }
    },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category',
      data: categories,
      axisLabel: { interval: 0, rotate: 30, fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      name: '模型输出 (log-odds)'
    },
    series: [
      {
        name: '辅助基底',
        type: 'bar',
        stack: '总量',
        itemStyle: { borderColor: 'transparent', color: 'transparent' },
        emphasis: { itemStyle: { borderColor: 'transparent', color: 'transparent' } },
        data: placeholderData
      },
      {
        name: '正向贡献 (+)',
        type: 'bar',
        stack: '总量',
        itemStyle: { color: '#dc2626', borderRadius: [4, 4, 0, 0] },
        data: posData
      },
      {
        name: '负向扣减 (-)',
        type: 'bar',
        stack: '总量',
        itemStyle: { color: '#16a34a', borderRadius: [4, 4, 0, 0] },
        data: negData
      }
    ]
  }

  chartInstance.setOption(option)
}

onMounted(() => {
  // 遵循 Modern Web Guidance：针对不支持 closedby 的浏览器的光轻量兜底
  if (dialogRef.value && !('closedBy' in HTMLDialogElement.prototype)) {
    dialogRef.value.addEventListener('click', (event) => {
      if (event.target !== dialogRef.value) return
      const rect = dialogRef.value.getBoundingClientRect()
      const isContent = (
        rect.top <= event.clientY &&
        event.clientY <= rect.top + rect.height &&
        rect.left <= event.clientX &&
        event.clientX <= rect.left + rect.width
      )
      if (!isContent) {
        dialogRef.value.close()
      }
    })
  }

  window.addEventListener('resize', () => {
    if (chartInstance) chartInstance.resize()
  })
})

defineExpose({ openModal })
</script>

<style scoped>
.explain-dialog {
  max-width: 950px;
  width: 92vw;
  max-height: 88vh;
  overflow-y: auto;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 20px 24px;
  border-bottom: 1px solid var(--slate-200);
  position: sticky;
  top: 0;
  background: #ffffff;
  z-index: 10;
}

.header-badges {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.stock-code {
  font-family: monospace;
  font-size: 13px;
  color: var(--slate-600);
}

.stock-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--slate-900);
}

.close-btn {
  background: transparent;
  border: none;
  font-size: 28px;
  color: var(--slate-600);
  cursor: pointer;
  line-height: 1;
}

.dialog-body {
  padding: 24px;
}

.reason-card {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: var(--radius-md);
  padding: 16px;
  margin-bottom: 20px;
}

.reason-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  color: #166534;
  margin-bottom: 8px;
}

.reason-text {
  font-size: 14px;
  line-height: 1.6;
  color: #14532d;
  white-space: pre-line;
}

.score-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}

.score-pill {
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  padding: 12px;
  display: flex;
  flex-direction: column;
}

.score-pill .label {
  font-size: 12px;
  color: var(--slate-600);
}

.score-pill .value {
  font-size: 18px;
  margin-top: 4px;
  color: var(--slate-800);
}

.score-pill.plus .value { color: var(--stock-up, #dc2626); }
.score-pill.minus .value { color: var(--stock-down, #16a34a); }
.score-pill.total { background: #eff6ff; border-color: #bfdbfe; }
.score-pill.total .value { color: #1d4ed8; font-size: 20px; }

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--slate-800);
  margin-bottom: 4px;
}

.section-desc {
  font-size: 13px;
  color: var(--slate-600);
  margin-bottom: 12px;
}

.chart-wrapper {
  margin-bottom: 28px;
}

.echart-box {
  width: 100%;
  height: 320px;
}

.text-pos { color: var(--stock-up, #dc2626); font-weight: 600; }
.text-neg { color: var(--stock-down, #16a34a); font-weight: 600; }

.dialog-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--slate-200);
  display: flex;
  justify-content: flex-end;
}
</style>
