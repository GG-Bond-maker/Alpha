<template>
  <div class="recommendation-view">
    <ol class="selection-flow" aria-label="选股与预测流程">
      <li><strong>规则筛选</strong><span>行情、成交、历史长度及风险标记</span></li>
      <li><strong>多因子对照</strong><span>训练期 Rank IC 权重</span></li>
      <li><strong>LightGBM 排序</strong><span>默认采用原始模型分数</span></li>
      <li><strong>概率校准</strong><span>只在独立验证区间拟合</span></li>
    </ol>

    <form class="card selection-form" @submit.prevent="fetchResults">
      <div class="selection-controls">
        <label>行情日期<select v-model="filters.date" class="form-select" @change="fetchResults"><option v-for="date in dates" :key="date" :value="date">{{ date }}</option></select></label>
        <label>排序方式<select v-model="filters.rank_by" class="form-select" @change="fetchResults"><option value="lightgbm">LightGBM 模型 · 默认</option><option value="factor" :disabled="!factorReady">多因子排名 · 对照</option></select></label>
        <label>推荐数量<select v-model="filters.k" class="form-select" @change="fetchResults"><option v-for="k in [5, 10, 20, 30, 50]" :key="k" :value="k">Top {{ k }}</option></select></label>
        <label>板块<select v-model="filters.board" class="form-select" @change="fetchResults"><option value="">全部板块</option><option v-for="board in boards" :key="board">{{ board }}</option></select></label>
        <label>行业<select v-model="filters.industry" class="form-select" @change="fetchResults"><option value="">全部行业</option><option v-for="industry in industries" :key="industry">{{ industry }}</option></select></label>
        <label>20 日均成交额<select v-model="filters.min_amount" class="form-select" @change="fetchResults"><option :value="0">不加额外门槛</option><option :value="10000000">至少 1,000 万元</option><option :value="50000000">至少 5,000 万元</option><option :value="100000000">至少 1 亿元</option></select></label>
      </div>
      <div class="selection-actions">
        <label class="checkbox-label"><input v-model="filters.exclude_limit_up" type="checkbox" @change="fetchResults">剔除信号日近涨停</label>
        <span class="muted">基础筛选：有效行情、当日有成交、至少 120 个历史交易日、无当前名称风险标记。</span>
        <button type="button" class="btn btn-outline btn-sm" @click="reset">重置筛选</button>
      </div>
    </form>

    <div v-if="error" class="card" role="alert"><p>{{ error }}</p><button class="btn btn-outline" @click="fetchResults">重试</button></div>
    <div v-else-if="loading" class="card loading-state" role="status">正在读取候选、筛选依据与预测…</div>
    <template v-else>
      <section class="card selection-summary" aria-label="筛选结果摘要">
        <div><strong>{{ result.screening?.input_count ?? '—' }}</strong><span>当前范围候选</span></div>
        <div><strong>{{ result.screening?.eligible_count ?? '未评估' }}</strong><span>通过基础及附加筛选</span></div>
        <div><strong>{{ result.screening?.excluded_count ?? '—' }}</strong><span>被规则排除</span></div>
        <div><strong>{{ items.length }}</strong><span>当前展示</span></div>
        <details v-if="Object.keys(result.screening?.reason_counts || {}).length"><summary>查看排除原因</summary><ul><li v-for="(count, reason) in result.screening.reason_counts" :key="reason">{{ reason }}：{{ count }} 只</li></ul></details>
      </section>

      <div class="selection-notes" role="status">
        <p v-if="calibration?.weak_validation_signal"><strong>验证信号较弱：</strong>校准未学到正向斜率，概率退回验证区间平均跑赢比例；列表仍按 LightGBM 原始分数排序。</p>
        <p v-if="!calibration">本批次尚无独立验证区间校准器，校准概率显示为空，请完成训练后再引用。</p>
        <p v-else>校准拟合区间 {{ calibration.fit_period?.join(' 至 ') }}，共 {{ calibration.fit_dates }} 个日期。校准概率是跑赢候选池平均收益的估计，不是上涨概率、收益率或置信区间。</p>
        <p>{{ result.screening?.note }}</p>
      </div>

      <section class="card recommendation-results">
        <div class="card-header"><div><h2 class="card-title">{{ filters.rank_by === 'lightgbm' ? 'LightGBM 推荐清单' : '多因子对照清单' }}</h2><p class="card-subtitle">行情 {{ result.date }} · SHAP 解释模型分数，多因子得分单独列示依据。</p></div><button class="btn btn-outline btn-sm" :disabled="!items.length" @click="exportCurrent">导出当前结果 CSV</button></div>
        <div v-if="!items.length" class="empty-state"><p class="empty-state-title">当前条件没有可展示的候选</p><p class="empty-state-desc">可降低成交额门槛、调整板块或行业；不会使用旧日期或编造分数补位。</p></div>
        <div v-else class="table-wrap desktop-results"><table>
          <thead><tr><th>当前排名</th><th>股票 / 板块</th><th>行业</th><th>模型排序分数</th><th>校准后跑赢概率</th><th>多因子得分 / 排名</th><th>收盘价</th><th>20 日均成交额</th><th>查看依据</th></tr></thead>
          <tbody><template v-for="item in items" :key="item.stock_code">
            <tr><td>{{ item.predicted_rank }}</td><td><strong>{{ item.stock_name }}</strong><span class="stock-meta">{{ item.stock_code }} · {{ item.board }}</span></td><td>{{ item.industry }}</td><td class="numeric">{{ decimal(item.predicted_score) }}<span class="stock-meta">模型池内第 {{ item.model_rank ?? '—' }} 名</span></td><td class="numeric">{{ percent(item.calibrated_probability) }}</td><td class="numeric">{{ decimal(item.factor_score, 1) }}<span class="stock-meta">因子第 {{ item.factor_rank ?? '—' }} 名</span></td><td class="numeric">{{ decimal(item.close_price, 2) }}</td><td>{{ amount(item.avg_amount_20d) }}</td><td><div class="row-actions"><button class="btn btn-outline btn-sm" @click="expanded = expanded === item.stock_code ? '' : item.stock_code" :aria-expanded="expanded === item.stock_code">因子依据</button><button class="btn btn-primary btn-sm" @click="emit('explain', item)">SHAP 归因</button><button class="btn btn-outline btn-sm" @click="emit('viewKline', item.stock_code)">K 线</button></div></td></tr>
            <tr v-if="expanded === item.stock_code" class="factor-detail"><td colspan="9"><p><strong>{{ item.stock_name }} 的多因子排名依据</strong> · 方向和权重只来自训练区间；分位数来自当前候选池。</p><div v-if="item.factor_breakdown?.length" class="table-wrap"><table><thead><tr><th>因子</th><th>方向</th><th>训练 Rank IC</th><th>权重</th><th>当日方向分位</th><th>加权分</th></tr></thead><tbody><tr v-for="factor in item.factor_breakdown" :key="factor.feature"><td>{{ factor.name_cn }}</td><td>{{ factor.direction > 0 ? '较高值优先' : '较低值优先' }}</td><td>{{ decimal(factor.ic) }}</td><td>{{ percent(factor.weight) }}</td><td>{{ percent(factor.percentile) }}</td><td>{{ decimal(factor.contribution, 1) }}</td></tr></tbody></table></div><p v-else>本批次没有可用的多因子排名依据。</p></td></tr>
          </template></tbody>
        </table></div>
        <div class="mobile-results"><article v-for="item in items" :key="item.stock_code" class="mobile-stock"><div class="mobile-stock-heading"><strong>{{ item.predicted_rank }}. {{ item.stock_name }}</strong><span>{{ item.stock_code }} · {{ item.industry }}</span></div><dl><div><dt>模型排序分数</dt><dd>{{ decimal(item.predicted_score) }}</dd></div><div><dt>校准跑赢概率</dt><dd>{{ percent(item.calibrated_probability) }}</dd></div><div><dt>多因子得分</dt><dd>{{ decimal(item.factor_score, 1) }} / 100</dd></div><div><dt>20 日均成交额</dt><dd>{{ amount(item.avg_amount_20d) }}</dd></div></dl><div class="row-actions"><button class="btn btn-primary btn-sm" @click="emit('explain', item)">SHAP 与因子依据</button><button class="btn btn-outline btn-sm" @click="emit('viewKline', item.stock_code)">查看 K 线</button></div></article></div>
      </section>
      <section v-if="items.length" class="card"><h2 class="card-title">推荐等权假设下的行业集中度</h2><p class="card-subtitle">按本页候选等权估算，未接入真实持仓；行业集中度与收益预测是不同的问题。</p><p v-if="sectors.some(s => s.name === '未分类')" class="muted">存在未分类股票，其合计占比不能视为同一真实行业的暴露。</p><div class="industry-distribution"><span v-for="sector in sectors" :key="sector.name">{{ sector.name }} <strong>{{ sector.count }} 只 · {{ percent(sector.weight) }}</strong></span></div></section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
const emit = defineEmits(['explain', 'viewKline', 'risk'])
const defaults = { date: '', rank_by: 'lightgbm', k: 10, board: '', industry: '', min_amount: 0, exclude_limit_up: false }
const filters = ref({ ...defaults }), dates = ref([]), pool = ref([]), result = ref({})
const loading = ref(true), error = ref(''), expanded = ref('')
let requestId = 0
const items = computed(() => result.value.recommendations || [])
const calibration = computed(() => result.value.selection_layer?.calibration)
const factorReady = computed(() => Boolean(result.value.selection_layer?.factor_ranker?.factors?.length))
const boards = computed(() => [...new Set(pool.value.map(r => r.board))].filter(Boolean).sort())
const industries = computed(() => [...new Set(pool.value.map(r => r.industry))].filter(Boolean).sort())
const decimal = (value, digits = 4) => value == null ? '—' : Number(value).toFixed(digits)
const percent = value => value == null ? '—' : (value * 100).toFixed(1) + '%'
const amount = value => value == null ? '未知' : value >= 1e8 ? (value / 1e8).toFixed(2) + ' 亿元' : (value / 1e4).toFixed(0) + ' 万元'
const sectors = computed(() => {
  const counts = new Map()
  items.value.forEach(item => counts.set(item.industry || '未分类', (counts.get(item.industry || '未分类') || 0) + 1))
  return [...counts].map(([name, count]) => ({ name, count, weight: count / items.value.length })).sort((a, b) => b.count - a.count)
})
async function fetchResults() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  expanded.value = ''
  try {
    const response = await api.getSelection({ ...filters.value, date: filters.value.date || undefined })
    if (id !== requestId) return
    result.value = response.data
    emit('risk', response.data.risk_guard)
  } catch (err) {
    if (id === requestId) error.value = err.response?.data?.detail || '推荐结果加载失败，请检查连接后重试。'
  } finally {
    if (id === requestId) loading.value = false
  }
}
function reset() {
  filters.value = { ...defaults, date: dates.value.at(-1) || '' }
  fetchResults()
}
function exportCurrent() {
  const header = ['行情日期', '当前排名', '排序方式', '代码', '名称', '行业', '模型分数', '校准跑赢概率', '多因子得分', '20日平均成交额']
  const rows = items.value.map(r => [result.value.date, r.predicted_rank, filters.value.rank_by, r.stock_code, r.stock_name, r.industry, r.predicted_score, r.calibrated_probability, r.factor_score, r.avg_amount_20d])
  const escape = value => '"' + String(value ?? '').replace(/^[=+@-]/, s => "'" + s).replaceAll('"', '""') + '"'
  const blob = new Blob(['\ufeff' + [header, ...rows].map(row => row.map(escape).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob), anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `recommendations-${result.value.date}-${filters.value.rank_by}.csv`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onMounted(async () => {
  try {
    const [dateResponse, poolResponse] = await Promise.all([api.getDates(), api.getStockPool()])
    dates.value = dateResponse.data || []
    pool.value = poolResponse.data || []
    filters.value.date = dates.value.at(-1) || ''
    await fetchResults()
  } catch {
    error.value = '候选池或日期读取失败，请刷新页面重试。'
    loading.value = false
  }
})
onBeforeUnmount(() => { requestId++ })
defineExpose({ refresh: fetchResults })
</script>

<style scoped>
.selection-flow { display: flex; flex-wrap: wrap; list-style: none; gap: 16px 28px; margin: 0 0 20px; padding: 0; }
.selection-flow li { display: flex; flex-direction: column; gap: 4px; }
.selection-flow strong { font-size: 15px; color: #0f172a; }
.selection-flow span, .muted { font-size: 13px; color: #475569; }
.selection-controls { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px 20px; }
.selection-controls label { display: flex; flex-direction: column; gap: 6px; font-size: 14px; color: #334155; min-width: 0; }
.selection-controls select { width: 100%; min-width: 0; }
.selection-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 16px; }
.checkbox-label { display: flex; gap: 8px; align-items: center; font-size: 14px; }
.selection-summary { display: flex; flex-wrap: wrap; gap: 18px 36px; align-items: baseline; }
.selection-summary > div { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: #475569; }
.selection-summary strong { font-size: 21px; color: #0f172a; font-variant-numeric: tabular-nums; }
.selection-summary details { font-size: 14px; color: #334155; }
.selection-summary ul { padding-left: 18px; margin-top: 8px; }
.selection-notes { font-size: 14px; line-height: 1.7; color: #475569; margin-bottom: 18px; max-width: 90ch; }
.selection-notes p + p { margin-top: 6px; }
.stock-meta { display: block; font-size: 12px; color: #475569; margin-top: 4px; white-space: nowrap; }
.numeric { font-variant-numeric: tabular-nums; }
.desktop-results table { min-width: 1100px; }
.row-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.factor-detail td { background: #f8fafc; }
.factor-detail p { margin-bottom: 10px; font-size: 14px; }
.industry-distribution { display: flex; flex-wrap: wrap; gap: 10px 24px; margin-top: 18px; font-size: 14px; }
.industry-distribution strong { margin-left: 8px; font-weight: 600; }
.mobile-results { display: none; }
summary { cursor: pointer; }
select:focus-visible, summary:focus-visible, input:focus-visible { outline: 2px solid #2563eb; outline-offset: 3px; }
@media (min-width: 1500px) { .selection-controls { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
@media (max-width: 700px) {
  .selection-controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .selection-controls select { font-size: 16px; }
  .desktop-results { display: none; }
  .mobile-results { display: block; }
  .mobile-stock { padding: 18px 0; border-top: 1px solid #e2e8f0; }
  .mobile-stock-heading { display: flex; flex-direction: column; gap: 4px; font-size: 15px; }
  .mobile-stock-heading span { font-size: 13px; color: #475569; }
  .mobile-stock dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 14px 0; }
  .mobile-stock dt { font-size: 13px; color: #475569; }
  .mobile-stock dd { font-size: 16px; font-weight: 600; margin: 4px 0 0; }
  .recommendation-results .card-header { flex-wrap: wrap; gap: 12px; }
}
</style>
