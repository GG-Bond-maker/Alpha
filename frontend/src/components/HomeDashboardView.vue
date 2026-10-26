<template>
  <div>
    <div v-if="loading" class="card">
      <div class="loading-state">
        <div class="spinner"></div>
        正在加载系统概览...
      </div>
    </div>

    <template v-else>
      <!-- 核心指标 -->
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">股票池规模</div>
          <div class="stat-value">{{ overview.pool_size || 0 }}</div>
          <div class="stat-hint">只核心标的</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">面板样本量</div>
          <div class="stat-value">{{ formatInt(panel.rows) }}</div>
          <div class="stat-hint">
            {{ panel.stocks }} 只 × {{ panel.dates }} 个截面
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">测试集 AUC</div>
          <div class="stat-value" :class="aucClass(model.test_auc)">
            {{ model.test_auc != null ? model.test_auc.toFixed(4) : '—' }}
          </div>
          <div class="stat-hint">样本外，未参与调参</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">回测超额年化</div>
          <div class="stat-value" :class="signClass(bt.excess_annual)">
            {{ pct(bt.excess_annual) }}
          </div>
          <div class="stat-hint">已扣除交易成本</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">策略夏普</div>
          <div class="stat-value">{{ bt.sharpe != null ? bt.sharpe.toFixed(3) : '—' }}</div>
          <div class="stat-hint">年化口径</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最大回撤</div>
          <div class="stat-value text-neg">{{ pct(bt.max_drawdown) }}</div>
          <div class="stat-hint">净值峰值回落</div>
        </div>
      </div>

      <!-- 数据口径提示 -->
      <div class="card notice-card">
        <div class="notice-row">
          <span class="source-tag is-real">
            标签口径：截面超额收益
          </span>
          <span class="notice-text">
            预测目标为未来 5 个交易日收益高于当日候选池平均收益，而非绝对上涨。
            面板区间 {{ panel.date_range ? panel.date_range[0] : '—' }} 至
            {{ panel.date_range ? panel.date_range[1] : '—' }}。
          </span>
        </div>
      </div>

      <div class="split-grid">
        <!-- 特征重要性 -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">全局特征重要性</div>
              <div class="card-subtitle">TreeSHAP Mean |SHAP| 排序</div>
            </div>
            <button class="btn btn-ghost btn-sm" @click="$emit('switchTab', 'global')">查看详情</button>
          </div>
          <div ref="chartRef" style="height: 300px;"></div>
        </div>

        <!-- 最新推荐 -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">最新截面推荐</div>
              <div class="card-subtitle">
                {{ overview.latest_date || '—' }} · Top {{ overview.latest_count || 0 }}
                · 按跑赢候选池均值分数排序
              </div>
            </div>
            <button class="btn btn-ghost btn-sm" @click="$emit('switchTab', 'recommend')">查看全部</button>
          </div>

          <div v-if="topPicks.length === 0" class="empty-state">
            <div class="empty-state-title">暂无推荐数据</div>
            <div class="empty-state-desc">请先运行训练脚本生成推荐结果</div>
          </div>

          <div v-else class="pick-list">
            <div v-for="(item, idx) in topPicks" :key="item.stock_code" class="pick-row">
              <span class="pick-rank" :class="'rank-' + (idx + 1)">{{ idx + 1 }}</span>
              <div class="pick-main">
                <div class="pick-name">{{ item.stock_name }}</div>
                <div class="pick-meta">
                  <code class="code-font">{{ item.stock_code }}</code>
                  <span class="badge badge-silver">{{ item.board }}</span>
                </div>
              </div>
              <div class="pick-prob">
                <span :class="probClass(item.probability)">{{ (item.probability * 100).toFixed(1) }}%</span>
                <div class="prob-bar-track">
                  <div class="prob-bar-fill"
                       :style="{ width: (item.probability * 100) + '%', background: probColor(item.probability) }">
                  </div>
                </div>
              </div>
              <button class="btn btn-outline btn-sm" @click="$emit('viewKline', item)">K线</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 快捷入口 -->
      <div class="card">
        <div class="card-title" style="margin-bottom: 14px;">快速导航</div>
        <div class="shortcut-grid">
          <button v-for="s in shortcuts" :key="s.key" class="shortcut" @click="$emit('switchTab', s.key)">
            <div class="shortcut-title">{{ s.title }}</div>
            <div class="shortcut-desc">{{ s.desc }}</div>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

defineEmits(['switchTab', 'viewKline'])

const loading = ref(true)
const overview = ref({})
const topPicks = ref([])
const chartRef = ref(null)
let chart = null
let importanceCache = []

const panel = computed(() => overview.value.panel || {})
const model = computed(() => overview.value.model || {})
const bt = computed(() => overview.value.backtest || {})

const shortcuts = [
  { key: 'recommend', title: 'Top-K 选股推荐', desc: '截面排序、评级筛选与 Excel 导出' },
  { key: 'kline', title: '行情走势', desc: '日 K 线、均线系统与成交量联动' },
  { key: 'metrics', title: '算法评测对比', desc: '基线与本文方法的指标对照' },
  { key: 'backtest', title: '组合回测', desc: '净值曲线、超额收益与风险指标' },
  { key: 'engineering', title: '数据与模型', desc: '数据更新、模型重训与运行日志' },
]

const formatInt = (v) => (v == null ? '—' : Number(v).toLocaleString())
const pct = (v) => (v == null ? '—' : (v * 100).toFixed(2) + '%')
const signClass = (v) => (v == null ? '' : v > 0 ? 'text-pos' : v < 0 ? 'text-neg' : 'text-muted')
const aucClass = (v) => (v == null ? '' : v >= 0.55 ? 'text-primary' : v >= 0.52 ? '' : 'text-muted')
const probColor = (p) => (p >= 0.5 ? '#dc2626' : '#16a34a')
const probClass = (p) => (p >= 0.5 ? 'text-pos' : 'text-neg')

const renderChart = (items) => {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const sorted = [...items].sort((a, b) => a.importance - b.importance)
  chart.setOption({
    grid: { left: 128, right: 28, top: 12, bottom: 24 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (v) => (v * 100).toFixed(2) + '%',
    },
    xAxis: {
      type: 'value',
      axisLabel: { fontSize: 11, color: '#94a3b8', formatter: (v) => (v * 100).toFixed(0) + '%' },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
    },
    yAxis: {
      type: 'category',
      data: sorted.map((i) => i.name_cn),
      axisLabel: { fontSize: 11.5, color: '#475569' },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    series: [{
      type: 'bar',
      data: sorted.map((i) => i.importance),
      barWidth: '58%',
      itemStyle: { color: '#2563eb', borderRadius: [0, 3, 3, 0] },
    }],
  })
}

const handleResize = () => chart?.resize()

onMounted(async () => {
  try {
    const [ovRes, impRes, recRes] = await Promise.all([
      api.getOverviewStats(),
      api.getGlobalImportance(),
      api.getTopK(null, 5),
    ])
    overview.value = ovRes.data || {}
    topPicks.value = (recRes.data?.recommendations || []).slice(0, 5)
    importanceCache = impRes.data || []
    window.addEventListener('resize', handleResize)
  } catch (err) {
    console.error('概览加载失败:', err)
  } finally {
    loading.value = false
    // loading 为真时图表容器不在 DOM 中，必须等切换完成后再渲染
    await nextTick()
    renderChart(importanceCache)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.notice-card {
  background: var(--slate-50);
  padding: 14px 18px;
}

.notice-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.notice-text {
  font-size: 12.5px;
  color: var(--slate-600);
  flex: 1;
  min-width: 240px;
}

.split-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 1180px) {
  .split-grid {
    grid-template-columns: 1fr;
  }
}

.pick-list {
  display: flex;
  flex-direction: column;
}

.pick-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--slate-100);
}

.pick-row:last-child {
  border-bottom: none;
}

.pick-rank {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11.5px;
  font-weight: 700;
  flex-shrink: 0;
  background: var(--slate-100);
  color: var(--slate-600);
}

.pick-rank.rank-1 { background: #fef3c7; color: #b45309; }
.pick-rank.rank-2 { background: var(--slate-200); color: var(--slate-600); }
.pick-rank.rank-3 { background: #ffedd5; color: #c2410c; }

.pick-main {
  flex: 1;
  min-width: 0;
}

.pick-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--slate-900);
}

.pick-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 2px;
}

.pick-prob {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.shortcut-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.shortcut {
  text-align: left;
  padding: 14px 16px;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  background: #fff;
  cursor: pointer;
  transition: all 0.15s ease;
}

.shortcut:hover {
  border-color: var(--primary);
  background: var(--primary-light);
}

.shortcut-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--slate-900);
  margin-bottom: 3px;
}

.shortcut-desc {
  font-size: 12px;
  color: var(--slate-500);
  line-height: 1.5;
}

.text-warn {
  color: var(--warning);
  font-weight: 600;
}
</style>
