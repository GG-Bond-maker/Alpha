<template>
  <div>
    <div v-if="loading" class="card">
      <div class="loading-state">
        <div class="spinner"></div>
        正在加载业绩归因...
      </div>
    </div>

    <div v-else-if="!data || data.error" class="card">
      <div class="empty-state">
        <div class="empty-state-title">暂无归因结果</div>
        <div class="empty-state-desc">{{ data && data.error ? data.error : '请先运行 python -m ml_pipeline.run_training' }}</div>
      </div>
    </div>

    <template v-else>
      <!-- 结论 -->
      <div class="card verdict-card">
        <div class="verdict-head">
          <span class="source-tag" :class="reg.alpha_significant ? 'is-real' : 'is-synthetic'">
            {{ reg.alpha_significant ? 'Alpha 显著' : 'Alpha 不显著' }}
          </span>
          <strong class="verdict-text">{{ data.conclusion.verdict }}</strong>
        </div>
        <ul class="verdict-points">
          <li v-for="(p, i) in data.conclusion.points" :key="i">{{ p }}</li>
        </ul>
      </div>

      <!-- 核心指标 -->
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">Alpha（年化）</div>
          <div class="stat-value" :class="reg.alpha_significant ? 'text-pos' : 'text-muted'">
            {{ pct(reg.alpha_annual) }}
          </div>
          <div class="stat-hint">
            t = {{ reg.alpha_t }} · p = {{ reg.alpha_p }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Beta</div>
          <div class="stat-value" :class="reg.beta > 1 ? 'text-neg' : ''">
            {{ fmt(reg.beta) }}
          </div>
          <div class="stat-hint">1 表示与市场同步</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">R²（市场解释度）</div>
          <div class="stat-value">{{ pct(reg.r_squared) }}</div>
          <div class="stat-hint">越高说明越依赖市场</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">信息比率 IR</div>
          <div class="stat-value">{{ fmt(data.relative.information_ratio) }}</div>
          <div class="stat-hint">
            跟踪误差 {{ pct(data.relative.tracking_error_annual) }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">超额显著性</div>
          <div class="stat-value" :class="data.relative.excess_significant ? 'text-pos' : 'text-muted'">
            {{ data.relative.excess_significant ? '显著' : '不显著' }}
          </div>
          <div class="stat-hint">t = {{ data.relative.excess_t }} · p = {{ data.relative.excess_p }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Beta 中性化后年化</div>
          <div class="stat-value">{{ pct(data.beta_neutralized.annualized_return) }}</div>
          <div class="stat-hint">纯选股能力的上界</div>
        </div>
      </div>

      <!-- 回归明细 -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">回归结果</div>
            <div class="card-subtitle">
              r<sub>策略</sub> = α + β · r<sub>基准</sub> + ε　·　样本 {{ data.periods }} 个交易周期
            </div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>参数</th>
                <th>估计值</th>
                <th>标准误</th>
                <th>t 值</th>
                <th>p 值</th>
                <th>95% 置信区间</th>
                <th>结论</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Alpha（每期）</strong></td>
                <td>{{ reg.alpha_period }}</td>
                <td>{{ reg.alpha_se_period }}</td>
                <td>{{ reg.alpha_t }}</td>
                <td>{{ reg.alpha_p }}</td>
                <td class="text-muted">年化 {{ pct(reg.alpha_ci95_annual[0]) }} ~ {{ pct(reg.alpha_ci95_annual[1]) }}</td>
                <td>
                  <span v-if="reg.alpha_significant" class="badge badge-green">显著异于 0</span>
                  <span v-else class="badge badge-silver">无法拒绝 α = 0</span>
                </td>
              </tr>
              <tr>
                <td><strong>Beta</strong></td>
                <td>{{ reg.beta }}</td>
                <td>{{ reg.beta_se }}</td>
                <td>{{ reg.beta_t_vs_1 }}</td>
                <td>{{ reg.beta_p_gt1 }}</td>
                <td class="text-muted">t 值对应 H₀: β = 1</td>
                <td>
                  <span v-if="reg.beta_above_one" class="badge badge-red">显著大于 1</span>
                  <span v-else class="badge badge-silver">与 1 无显著差异</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 分市场状态 -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">分市场状态表现</div>
            <div class="card-subtitle">
              按基准收益五等分，若超额随市场涨跌单调变化，说明超额来自 beta 敞口
            </div>
          </div>
          <span v-if="data.excess_monotonic_with_market" class="badge badge-gold">超额随市场单调</span>
        </div>
        <div ref="regimeRef" style="height: 320px;"></div>
        <div class="table-wrap" style="margin-top: 12px;">
          <table>
            <thead>
              <tr>
                <th>市场状态</th>
                <th>周期数</th>
                <th>基准收益</th>
                <th>策略收益</th>
                <th>超额收益</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in data.regime" :key="r.regime">
                <td><strong>{{ r.regime }}</strong></td>
                <td>{{ r.n_periods }}</td>
                <td :class="r.benchmark_mean >= 0 ? 'text-pos' : 'text-neg'">{{ pct(r.benchmark_mean) }}</td>
                <td :class="r.strategy_mean >= 0 ? 'text-pos' : 'text-neg'">{{ pct(r.strategy_mean) }}</td>
                <td :class="r.excess_mean >= 0 ? 'text-pos' : 'text-neg'">
                  <strong>{{ pct(r.excess_mean) }}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Beta 中性化 -->
      <div class="card">
        <div class="card-title" style="margin-bottom: 8px;">Beta 中性化对照</div>
        <div class="card-subtitle" style="margin-bottom: 14px;">
          把策略收益减去 β × 基准收益，剩下的即为纯选股部分；这是选股能力的乐观上界
        </div>
        <div class="neutral-grid">
          <div class="neutral-item">
            <span class="n-label">年化收益</span>
            <strong :class="signClass(data.beta_neutralized.annualized_return)">
              {{ pct(data.beta_neutralized.annualized_return) }}
            </strong>
          </div>
          <div class="neutral-item">
            <span class="n-label">年化波动</span>
            <strong>{{ pct(data.beta_neutralized.annualized_volatility) }}</strong>
          </div>
          <div class="neutral-item">
            <span class="n-label">夏普比率</span>
            <strong>{{ fmt(data.beta_neutralized.sharpe) }}</strong>
          </div>
          <div class="neutral-item">
            <span class="n-label">最大回撤</span>
            <strong class="text-neg">{{ pct(data.beta_neutralized.max_drawdown) }}</strong>
          </div>
        </div>
      </div>

      <!-- 历史极端危机情景压力测试 (Crisis Stress Testing) -->
      <div v-if="stressData && stressData.historical_crises" class="card">
        <div class="card-header">
          <div>
            <div class="card-title">历史极端危机情景压力测试 (Crisis Stress Testing)</div>
            <div class="card-subtitle">
              遵循 ML4T 压力测试规范：对 A 股 2015 股灾、2016 熔断、2018 贸易战、2020 疫情等 6 大极端黑天鹅时期进行复盘检验
            </div>
          </div>
          <span class="badge badge-blue">
            危机跑赢率: {{ (stressData.summary?.win_rate * 100).toFixed(0) }}% ({{ stressData.summary?.win_crises }}/{{ stressData.summary?.total_tested_crises }})
          </span>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>极端危机情景</th>
                <th>时间窗口</th>
                <th>核心市场机制</th>
                <th>策略累计收益</th>
                <th>基准同期收益</th>
                <th>超额 Alpha</th>
                <th>区间最大回撤</th>
                <th>防御力评级</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in stressData.historical_crises" :key="c.id">
                <td><strong>{{ c.name }}</strong></td>
                <td style="font-size: 11px;">{{ c.start_date }} ~ {{ c.end_date }}</td>
                <td style="font-size: 12px; color: var(--slate-600);">{{ c.description }}</td>
                <td :class="signClass(c.strategy_return)">{{ pct(c.strategy_return) }}</td>
                <td :class="signClass(c.benchmark_return)">{{ pct(c.benchmark_return) }}</td>
                <td class="text-pos"><strong>+{{ pct(c.excess_return) }}</strong></td>
                <td class="text-neg">{{ pct(c.max_drawdown) }}</td>
                <td><span class="badge" :class="c.badge_type">{{ c.resilience }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="stress-summary-bar">
          <strong>压力测试综合实证结论：</strong> {{ stressData.summary?.overall_assessment }}
        </div>
      </div>

      <div class="card note-card">
        <div class="card-title" style="margin-bottom: 8px;">方法说明</div>
        <ul class="note-list">
          <li><strong>Alpha</strong>：剥离市场影响后的选股能力，是判断模型是否有真实价值的关键指标。</li>
          <li><strong>Beta</strong>：策略对市场涨跌的敏感度。Beta = 1 表示与市场同步，大于 1 表示放大了市场波动。</li>
          <li><strong>R²</strong>：策略收益中被市场收益解释的比例。R² 很高时，即便总收益可观也主要归功于市场。</li>
          <li><strong>信息比率</strong>：超额收益均值除以跟踪误差，衡量跑赢基准的稳定性；一般认为 > 0.5 才算可用。</li>
          <li><strong>分市场状态</strong>：若下跌市跑输、上涨市跑赢，则超额来自 beta 敞口而非选股。</li>
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
const data = ref(null)
const stressData = ref(null)
const regimeRef = ref(null)
let chart = null

const reg = computed(() => data.value?.regression || {})

const pct = (v) => (v == null ? '—' : (v * 100).toFixed(2) + '%')
const fmt = (v) => (v == null ? '—' : Number(v).toFixed(4))
const signClass = (v) => (v == null ? '' : v > 0 ? 'text-pos' : v < 0 ? 'text-neg' : 'text-muted')

const renderChart = () => {
  if (!regimeRef.value || !data.value?.regime?.length) return
  if (!chart) chart = echarts.init(regimeRef.value)

  const regimes = data.value.regime.map((r) => r.regime)
  const bench = data.value.regime.map((r) => r.benchmark_mean * 100)
  const strat = data.value.regime.map((r) => r.strategy_mean * 100)

  chart.setOption({
    grid: { left: 56, right: 24, top: 40, bottom: 40 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => v.toFixed(3) + '%' },
    legend: { top: 8, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 12 } },
    xAxis: {
      type: 'category',
      data: regimes,
      axisLabel: { fontSize: 12, color: '#475569' },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'value',
      name: '平均周期收益 (%)',
      nameTextStyle: { fontSize: 11, color: '#94a3b8' },
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
    },
    series: [
      {
        name: '基准',
        type: 'bar',
        data: bench,
        barWidth: '32%',
        itemStyle: { color: '#94a3b8', borderRadius: [3, 3, 0, 0] },
      },
      {
        name: '策略',
        type: 'bar',
        data: strat,
        barWidth: '32%',
        itemStyle: { color: '#2563eb', borderRadius: [3, 3, 0, 0] },
      },
    ],
  })
}

const handleResize = () => chart?.resize()

onMounted(async () => {
  try {
    const [res, stress] = await Promise.all([
      api.getAttribution(),
      api.getStressTest().catch(() => ({ data: null })),
    ])
    data.value = res.data
    stressData.value = stress.data && !stress.data.error ? stress.data : null
  } catch (err) {
    data.value = { error: '加载失败：' + err.message }
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
.stress-summary-bar {
  margin-top: 14px;
  padding: 12px 16px;
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: 6px;
  font-size: 13px;
  color: var(--slate-700);
  line-height: 1.7;
}

.verdict-card {
  background: linear-gradient(180deg, #ffffff 0%, var(--slate-50) 100%);
  border: 1px solid var(--slate-200);
}

.verdict-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.verdict-text {
  font-size: 15px;
  color: var(--slate-900);
}

.verdict-points {
  margin: 0;
  padding-left: 20px;
  font-size: 13.5px;
  color: var(--slate-700);
  line-height: 1.9;
}

.neutral-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px;
}

.neutral-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: var(--slate-50);
  border-radius: var(--radius-md);
}

.n-label {
  font-size: 12px;
  color: var(--slate-500);
}

.neutral-item strong {
  font-size: 17px;
  font-variant-numeric: tabular-nums;
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
