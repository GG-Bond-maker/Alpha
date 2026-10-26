<template>
  <div>
    <div v-if="loading" class="card">
      <div class="loading-state">
        <div class="spinner"></div>
        正在加载滚动窗口验证结果...
      </div>
    </div>

    <div v-else-if="!data || data.error" class="card">
      <div class="empty-state">
        <div class="empty-state-title">暂无滚动窗口结果</div>
        <div class="empty-state-desc">{{ data && data.error ? data.error : '请运行 python -m ml_pipeline.run_training 生成产物' }}</div>
      </div>
    </div>

    <template v-else>
      <div class="card notice-card">
        <span class="source-tag is-real">Walk-Forward</span>
        <span class="notice-text">{{ data.note }}</span>
      </div>

      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">AUC 均值</div>
          <div class="stat-value" :class="signClass(summary.auc_mean - 0.5)">
            {{ summary.auc_mean != null ? summary.auc_mean.toFixed(4) : '—' }}
          </div>
          <div class="stat-hint">{{ summary.n_windows }} 个窗口</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">AUC 中位数</div>
          <div class="stat-value">{{ summary.auc_median != null ? summary.auc_median.toFixed(4) : '—' }}</div>
          <div class="stat-hint">剔除极端窗口的影响</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">AUC 标准差</div>
          <div class="stat-value">{{ summary.auc_std != null ? summary.auc_std.toFixed(4) : '—' }}</div>
          <div class="stat-hint">越小说明越稳定</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">低于随机的窗口</div>
          <div class="stat-value" :class="summary.pct_below_random > 0.3 ? 'text-danger' : 'text-success'">
            {{ summary.pct_below_random != null ? (summary.pct_below_random * 100).toFixed(1) + '%' : '—' }}
          </div>
          <div class="stat-hint">该比例越低越好</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">AUC 区间</div>
          <div class="stat-value" style="font-size: 15px;">
            {{ summary.auc_min != null ? summary.auc_min.toFixed(3) : '—' }}
            ~
            {{ summary.auc_max != null ? summary.auc_max.toFixed(3) : '—' }}
          </div>
          <div class="stat-hint">最好与最差的窗口</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">截面 AUC 均值</div>
          <div class="stat-value">{{ summary.section_auc_mean != null ? summary.section_auc_mean.toFixed(4) : '—' }}</div>
          <div class="stat-hint">剔除跨期漂移的选股能力</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">各窗口 AUC 时序</div>
            <div class="card-subtitle">
              每个窗口训练截至前一日、检验随后的 {{ summary.val_days }} 个交易日，
              步长 {{ summary.step_days }} 个交易日
            </div>
          </div>
        </div>
        <div ref="chartRef" style="height: 340px;"></div>
      </div>

      <div v-if="btSummary" class="card">
        <div class="card-header">
          <div>
            <div class="card-title">滚动回测（跨窗口）</div>
            <div class="card-subtitle">
              每个窗口用该窗口自行训练的模型打分并回测，再用拼接净值代表「按流程连续运行」的表现
            </div>
          </div>
        </div>
        <div class="stat-grid" style="margin-bottom: 16px;">
          <div class="stat-card">
            <div class="stat-label">超额年化均值</div>
            <div class="stat-value" :class="signClass(btSummary.excess_ann_mean)">
              {{ pct(btSummary.excess_ann_mean) }}
            </div>
            <div class="stat-hint">{{ btSummary.n_windows }} 个窗口取均值</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">超额年化中位数</div>
            <div class="stat-value" :class="signClass(btSummary.excess_ann_median)">
              {{ pct(btSummary.excess_ann_median) }}
            </div>
            <div class="stat-hint">剔除极端窗口影响</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">超额标准差</div>
            <div class="stat-value">{{ pct(btSummary.excess_ann_std) }}</div>
            <div class="stat-hint">越小说明越稳定</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">正超额窗口占比</div>
            <div class="stat-value" :class="btSummary.excess_positive_ratio >= 0.6 ? 'text-pos' : 'text-neg'">
              {{ (btSummary.excess_positive_ratio * 100).toFixed(1) }}%
            </div>
            <div class="stat-hint">跑赢基准的窗口比例</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">最差窗口回撤</div>
            <div class="stat-value text-neg">{{ pct(btSummary.strategy_mdd_worst) }}</div>
            <div class="stat-hint">所有窗口中的最低点</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">策略年化区间</div>
            <div class="stat-value" style="font-size: 15px;">
              {{ pct(btSummary.strategy_ann_min) }} ~ {{ pct(btSummary.strategy_ann_max) }}
            </div>
            <div class="stat-hint">最差与最好的窗口</div>
          </div>
        </div>

        <div v-if="aggregated" class="agg-block">
          <div class="agg-title">拼接净值（全窗口连续运行）</div>
          <div class="agg-grid">
            <div><span class="agg-label">年化收益</span>
              <strong :class="signClass(aggregated.strategy.annualized_return)">
                {{ pct(aggregated.strategy.annualized_return) }}
              </strong>
            </div>
            <div><span class="agg-label">夏普</span>
              <strong>{{ fmt(aggregated.strategy.sharpe) }}</strong>
            </div>
            <div><span class="agg-label">最大回撤</span>
              <strong class="text-neg">{{ pct(aggregated.strategy.max_drawdown) }}</strong>
            </div>
            <div><span class="agg-label">超额年化</span>
              <strong :class="signClass(aggregated.excess.annualized_return)">
                {{ pct(aggregated.excess.annualized_return) }}
              </strong>
            </div>
            <div><span class="agg-label">交易周期数</span>
              <strong>{{ aggregated.strategy.periods }}</strong>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title" style="margin-bottom: 14px;">窗口明细</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>检验区间</th>
                <th>训练样本</th>
                <th>检验样本</th>
                <th>整体 AUC</th>
                <th>截面 AUC 均值</th>
                <th>截面 AUC 中位数</th>
                <th>截面低于随机占比</th>
                <th>窗口超额年化</th>
                <th>窗口策略回撤</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="w in data.windows" :key="w.train_end">
                <td>
                  <code class="code-font">{{ w.val_start }}</code> ~ {{ w.val_end }}
                </td>
                <td>{{ formatInt(w.n_train) }}</td>
                <td>{{ formatInt(w.n_val) }}</td>
                <td :class="w.auc >= 0.5 ? 'text-pos' : 'text-neg'">
                  <strong>{{ w.auc.toFixed(4) }}</strong>
                </td>
                <td>{{ w.section_auc_mean != null ? w.section_auc_mean.toFixed(4) : '—' }}</td>
                <td>{{ w.section_auc_median != null ? w.section_auc_median.toFixed(4) : '—' }}</td>
                <td :class="w.section_auc_below_half > 0.5 ? 'text-neg' : ''">
                  {{ w.section_auc_below_half != null ? (w.section_auc_below_half * 100).toFixed(1) + '%' : '—' }}
                </td>
                <td :class="signClass(w.bt_excess_ann)">
                  {{ w.bt_excess_ann != null ? pct(w.bt_excess_ann) : '—' }}
                </td>
                <td class="text-neg">
                  {{ w.bt_strategy_mdd != null ? pct(w.bt_strategy_mdd) : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">因子跨窗口稳定性</div>
            <div class="card-subtitle">
              符号翻转次数越多，说明该因子的方向在时间上越不可靠
            </div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>因子</th>
                <th>IC 均值</th>
                <th>IC 标准差</th>
                <th>IC&gt;0 占比</th>
                <th>符号翻转</th>
                <th>平均 t 值</th>
                <th>显著窗口数</th>
                <th>评价</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(v, k) in data.factor_stability" :key="k">
                <td><strong>{{ featureName(k) }}</strong></td>
                <td :class="v.ic_mean >= 0 ? 'text-pos' : 'text-neg'">{{ v.ic_mean.toFixed(4) }}</td>
                <td>{{ v.ic_std.toFixed(4) }}</td>
                <td>{{ (v.ic_positive_ratio * 100).toFixed(1) }}%</td>
                <td :class="v.sign_flips > v.n_windows / 2 ? 'text-neg' : ''">{{ v.sign_flips }}</td>
                <td>{{ v.t_mean != null ? v.t_mean.toFixed(2) : '—' }}</td>
                <td>{{ v.n_significant }} / {{ v.n_windows }}</td>
                <td>
                  <span v-if="v.n_significant >= v.n_windows * 0.6" class="badge badge-green">稳定</span>
                  <span v-else-if="v.n_significant >= v.n_windows * 0.3" class="badge badge-gold">部分有效</span>
                  <span v-else class="badge badge-red">不稳定</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card note-card">
        <div class="card-title" style="margin-bottom: 8px;">如何解读</div>
        <ul class="note-list">
          <li>单次三段切分的验证结果高度依赖切分点所处市场状态，因此不应单独作为结论依据。</li>
          <li>滚动窗口给出的是 AUC 的分布：均值反映长期水平，标准差反映稳定性，低于随机的窗口占比反映失效风险。</li>
          <li>若某因子符号频繁翻转，说明其方向在时间上不可靠，即使全样本 IC 显著也不应重仓依赖。</li>
          <li>截面 AUC 剔除跨市场状态的漂移，更接近「同一交易日内选出跑赢标的」的真实能力。</li>
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
const chartRef = ref(null)
let chart = null

const summary = computed(() => data.value?.summary || {})
const btSummary = computed(() => data.value?.backtest_summary || null)
const aggregated = computed(() => data.value?.backtest_aggregated || null)
const pct = (v) => (v == null ? '—' : (v * 100).toFixed(2) + '%')
const fmt = (v) => (v == null ? '—' : Number(v).toFixed(4))

const NAMES = {
  ATR_ratio_neu: '相对真实波幅',
  MACD_norm_neu: '归一化 MACD',
  EMA20_ratio_neu: '价格/20日均线',
  momentum_20d_neu: '20日动量',
  momentum_60d_neu: '60日动量',
  volatility_20d_neu: '20日波动率',
  OBV_zscore_neu: '能量潮标准分',
  ma_gap_neu: '短期均线偏离度',
  roe_neu: '净资产收益率',
  pb_neu: '市净率',
  pe_ttm_neu: '市盈率',
}

const featureName = (k) => NAMES[k] || k
const formatInt = (v) => (v == null ? '—' : Number(v).toLocaleString())
const signClass = (v) => (v == null ? '' : v > 0 ? 'text-pos' : v < 0 ? 'text-neg' : 'text-muted')

const renderChart = () => {
  if (!chartRef.value || !data.value?.windows?.length) return
  if (!chart) chart = echarts.init(chartRef.value)

  const labels = data.value.windows.map((w) => w.val_start)
  const aucs = data.value.windows.map((w) => w.auc)
  const secs = data.value.windows.map((w) => w.section_auc_mean)

  chart.setOption({
    grid: { left: 56, right: 24, top: 40, bottom: 60 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => (v == null ? '—' : v.toFixed(4)) },
    legend: { top: 8, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 12 } },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { fontSize: 11, color: '#94a3b8', rotate: 30, hideOverlap: true },
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
        name: '整体 AUC',
        type: 'line',
        data: aucs,
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { width: 2, color: '#2563eb' },
        itemStyle: { color: '#2563eb' },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#ef4444', type: 'dashed', width: 1 },
          data: [{ yAxis: 0.5, label: { formatter: '随机基线 0.5', fontSize: 10, color: '#ef4444' } }],
        },
      },
      {
        name: '截面 AUC 均值',
        type: 'line',
        data: secs,
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { width: 1.5, color: '#10b981', type: 'dashed' },
        itemStyle: { color: '#10b981' },
      },
    ],
  })
}

const handleResize = () => chart?.resize()

onMounted(async () => {
  try {
    const res = await api.getWalkForward()
    data.value = res.data
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
  flex: 1;
  min-width: 240px;
}

.agg-block {
  border-top: 1px solid var(--slate-200);
  padding-top: 16px;
}

.agg-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--slate-700);
  margin-bottom: 12px;
}

.agg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 14px;
}

.agg-grid > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agg-label {
  font-size: 12px;
  color: var(--slate-500);
}

.agg-grid strong {
  font-size: 16px;
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
