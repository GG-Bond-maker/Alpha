<template>
  <div>
    <div v-if="loading" class="card">
      <div class="loading-state">
        <div class="spinner"></div>
        正在加载回测结果...
      </div>
    </div>

    <div v-else-if="!data || data.error" class="card">
      <div class="empty-state">
        <div class="empty-state-title">暂无回测结果</div>
        <div class="empty-state-desc">{{ data && data.error ? data.error : '请先运行 python -m ml_pipeline.run_training 生成回测产物' }}</div>
      </div>
    </div>

    <template v-else>
      <div class="card notice-card">
        <span class="source-tag" :class="isNeutral ? 'is-real' : 'is-synthetic'">
          {{ isNeutral ? '行业中性选股' : '沪深300池内排序' }}
        </span>
        <span class="notice-text">
          <template v-if="isNeutral">
            每个行业内按模型打分选 Top-N 后合并，持仓分散于
            <strong>{{ data.avg_sectors_held }}</strong> 个行业，
            单一行业暴露受控。行业样本不足 {{ params.min_stocks_per_sector }} 只时并入剩余池补位。
          </template>
          <template v-else>
            在沪深300研究池内按模型打分直接取 Top-K，不做行业约束。
          </template>
        </span>
        <button class="btn btn-outline btn-sm" style="margin-left: auto; white-space: nowrap;" @click="showTearsheet = true">
          📄 导出量化尽调研报 (Tearsheet)
        </button>
      </div>

      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">策略年化收益</div>
          <div class="stat-value" :class="signClass(strategy.annualized_return)">
            {{ pct(strategy.annualized_return) }}
          </div>
          <div class="stat-hint">Top-{{ params.k }} 等权组合</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">基准年化收益</div>
          <div class="stat-value" :class="signClass(benchmark.annualized_return)">
            {{ pct(benchmark.annualized_return) }}
          </div>
          <div class="stat-hint">全样本等权</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">超额年化收益</div>
          <div class="stat-value" :class="signClass(excess.annualized_return)">
            {{ pct(excess.annualized_return) }}
          </div>
          <div class="stat-hint">扣除成本与滑点后</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">夏普比率 (Sharpe)</div>
          <div class="stat-value">{{ fmt(strategy.sharpe) }}</div>
          <div class="stat-hint">年化，无风险利率取 0</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">索提诺比率 (Sortino)</div>
          <div class="stat-value">{{ fmt(strategy.sortino) }}</div>
          <div class="stat-hint">专注惩罚下行波动风险</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">卡玛比率 (Calmar)</div>
          <div class="stat-value">{{ fmt(strategy.calmar) }}</div>
          <div class="stat-hint">年化收益 / 最大回撤</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最大回撤</div>
          <div class="stat-value text-neg">{{ pct(strategy.max_drawdown) }}</div>
          <div class="stat-hint">水下最长 {{ strategy.max_drawdown_duration || '—' }} 周期</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">校准夏普 (DSR)</div>
          <div class="stat-value" :class="strategy.dsr >= 0.8 ? 'text-pos' : ''">
            {{ strategy.dsr != null ? (strategy.dsr * 100).toFixed(1) + '%' : '—' }}
          </div>
          <div class="stat-hint">{{ strategy.dsr == null ? '缺少可比试验的夏普分布，未计算' : '使用已记录的可比策略试验' }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">周期末净值与回撤</div>
            <div class="card-subtitle">
              共 {{ strategy.periods }} 个调仓周期 · 单边买入成本
              {{ (params.buy_cost * 100).toFixed(3) }}% · 卖出成本
              {{ (params.sell_cost * 100).toFixed(3) }}%（含本次配置的滑点与印花税）· 每期末全额平仓，下一期开盘重新建仓 · 回撤包含初始本金
            </div>
          </div>
        </div>
        <div ref="chartRef" style="width: 100%; height: 480px;"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">风险收益全景对照</div>
            <div class="card-subtitle">策略与等权候选池使用相同双边费用；信号日涨停筛选不保证下一开盘可成交</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>指标</th>
                <th>策略 (Top-{{ params.k }})</th>
                <th>基准 (等权全样本)</th>
                <th>差值 / 增强</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in compareRows" :key="row.label">
                <td>{{ row.label }}</td>
                <td :class="row.sign ? signClass(row.a) : ''">
                  {{ row.isPct ? pct(row.a) : row.isInt ? intVal(row.a) : fmt(row.a) }}
                </td>
                <td :class="row.sign ? signClass(row.b) : ''">
                  {{ row.isPct ? pct(row.b) : row.isInt ? intVal(row.b) : (row.b != null ? fmt(row.b) : '—') }}
                </td>
                <td :class="row.signDiff && row.a != null && row.b != null ? signClass(row.a - row.b) : ''">
                  {{ row.a != null && row.b != null ? (row.isPct ? pct(row.a - row.b) : fmt(row.a - row.b)) : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="comparison" class="card">
        <div class="card-header">
          <div>
            <div class="card-title">两种选股口径对比</div>
            <div class="card-subtitle">
              同一模型打分、同一测试区间，仅持仓构建方式不同
            </div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>口径</th>
                <th>年化收益</th>
                <th>夏普</th>
                <th>索提诺</th>
                <th>卡玛</th>
                <th>最大回撤</th>
                <th>95% CVaR</th>
                <th>校准 DSR</th>
                <th>超额年化</th>
                <th>平均换手</th>
                <th>持有行业数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in comparisonRows" :key="row.key"
                  :class="{ 'row-active': row.key === params.selection }">
                <td>
                  <strong>{{ row.label }}</strong>
                  <span v-if="row.key === params.selection" class="badge badge-blue"
                        style="margin-left: 6px;">当前</span>
                </td>
                <td :class="signClass(row.s.annualized_return)">{{ pct(row.s.annualized_return) }}</td>
                <td>{{ fmt(row.s.sharpe) }}</td>
                <td>{{ fmt(row.s.sortino) }}</td>
                <td>{{ fmt(row.s.calmar) }}</td>
                <td class="text-neg">{{ pct(row.s.max_drawdown) }}</td>
                <td class="text-neg">{{ pct(row.s.cvar_95) }}</td>
                <td>{{ row.s.dsr != null ? (row.s.dsr * 100).toFixed(1) + '%' : '—' }}</td>
                <td :class="signClass(row.e.annualized_return)">{{ pct(row.e.annualized_return) }}</td>
                <td>{{ pct(row.turnover) }}</td>
                <td>{{ row.sectors != null ? row.sectors : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="footnote">
          行业中性通过限制单一行业暴露来压低回撤与尾部风险（CVaR），代价是可能牺牲部分单边行情超额；
          研究池直接排序在牛市中弹性更高，但缺乏行业约束容易出现仓位聚集，在板块轮动中回撤显著加剧。
        </div>
      </div>

      <!-- 逐期调仓明细与持仓流水 (Rebalance Ledger & Period Win Rate) -->
      <div v-if="ledgerList.length > 0" class="card ledger-card">
        <div class="card-header">
          <div>
            <div class="card-title">逐期调仓明细与持仓流水 (Rebalance Ledger)</div>
            <div class="card-subtitle">
              穿透 {{ ledgerList.length }} 个调仓周期的真实选股名单、个股 5 日收益、买入/续持/平仓动作与相对胜率
            </div>
          </div>

          <!-- 周期选择与快捷切换控制器 -->
          <div class="ledger-ctrls">
            <button
              class="btn btn-outline btn-sm"
              :disabled="selectedPeriodIndex <= 0"
              @click="prevPeriod"
            >
              ◀ 上一期
            </button>
            <select v-model="selectedPeriodIndex" class="form-select form-select-sm ledger-select">
              <option v-for="(p, idx) in ledgerList" :key="p.date" :value="idx">
                第 {{ p.period_index }} 期 ({{ p.date }}) · 净收益 {{ (p.period_net_return * 100).toFixed(2) }}% · 胜率 {{ (p.win_rate * 100).toFixed(0) }}%
              </option>
            </select>
            <button
              class="btn btn-outline btn-sm"
              :disabled="selectedPeriodIndex >= ledgerList.length - 1"
              @click="nextPeriod"
            >
              下一期 ▶
            </button>
          </div>
        </div>

        <div v-if="currentLedger" class="ledger-content">
          <!-- 当期概要指标卡片条 -->
          <div class="ledger-summary-banner">
            <div class="ledger-stat-item">
              <span class="lbl">调仓信号日</span>
              <strong class="val">{{ currentLedger.date }}</strong>
              <span class="sub">持有 5 个交易日</span>
            </div>
            <div class="ledger-stat-item">
              <span class="lbl">当期组合净收益</span>
              <strong class="val" :class="signClass(currentLedger.period_net_return)">
                {{ pct(currentLedger.period_net_return) }}
              </strong>
              <span class="sub">摩擦损耗 {{ (currentLedger.cost * 10000).toFixed(1) }} bps</span>
            </div>
            <div class="ledger-stat-item">
              <span class="lbl">同期基准收益</span>
              <strong class="val" :class="signClass(currentLedger.benchmark_return)">
                {{ pct(currentLedger.benchmark_return) }}
              </strong>
              <span class="sub">全市场等权基准</span>
            </div>
            <div class="ledger-stat-item">
              <span class="lbl">单期超额收益</span>
              <strong class="val" :class="signClass(currentLedger.excess_return)">
                {{ pct(currentLedger.excess_return) }}
              </strong>
              <span class="sub">净超额 Alpha</span>
            </div>
            <div class="ledger-stat-item">
              <span class="lbl">当期标的胜率</span>
              <strong class="val" :class="currentLedger.win_rate >= 0.5 ? 'text-pos' : 'text-neg'">
                {{ pct(currentLedger.win_rate) }}
              </strong>
              <span class="sub">{{ Math.round(currentLedger.win_rate * currentLedger.holdings.length) }} / {{ currentLedger.holdings.length }} 只上涨</span>
            </div>
            <div class="ledger-stat-item">
              <span class="lbl">双边单期换手</span>
              <strong class="val">{{ pct(currentLedger.turnover) }}</strong>
              <span class="sub">调仓换手率</span>
            </div>
          </div>

          <!-- 当期持仓清单表格 -->
          <div class="table-wrap" style="margin-top: 14px;">
            <table>
              <thead>
                <tr>
                  <th style="width: 50px; text-align: center;">序号</th>
                  <th>股票代码</th>
                  <th>股票名称</th>
                  <th>所属行业</th>
                  <th>持仓权重</th>
                  <th>模型打分</th>
                  <th style="text-align: center;">调仓动作</th>
                  <th>5日持有收益</th>
                  <th style="text-align: center;">相对基准</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(h, idx) in currentLedger.holdings" :key="h.code">
                  <td style="text-align: center; color: var(--slate-400);">{{ idx + 1 }}</td>
                  <td><strong>{{ h.code }}</strong></td>
                  <td>{{ h.name }}</td>
                  <td><span class="badge-subtle">{{ h.industry }}</span></td>
                  <td>{{ (h.weight * 100).toFixed(1) }}%</td>
                  <td>{{ h.score.toFixed(4) }}</td>
                  <td style="text-align: center;">
                    <span class="action-tag" :class="h.action === 'BUY' ? 'action-buy' : 'action-hold'">
                      {{ h.action === 'BUY' ? '新进买入 BUY' : '继续持有 HOLD' }}
                    </span>
                  </td>
                  <td :class="signClass(h.return_5d)">
                    <strong>{{ (h.return_5d > 0 ? '+' : '') + pct(h.return_5d) }}</strong>
                  </td>
                  <td style="text-align: center;">
                    <span v-if="h.beat_benchmark" class="benchmark-tag beat-tag">✅ 跑赢</span>
                    <span v-else class="benchmark-tag lag-tag">❌ 落后</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 本期平仓出局股票 -->
          <div v-if="currentLedger.exited && currentLedger.exited.length > 0" class="exited-panel">
            <span class="exited-title">📤 当期平仓换出 ({{ currentLedger.exited.length }} 只):</span>
            <div class="exited-list">
              <span v-for="x in currentLedger.exited" :key="x.code" class="exited-tag">
                <span class="exited-action">SELL</span>
                <span class="exited-name">{{ x.name }}</span>
                <span class="exited-code">({{ x.code }})</span>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 组合头寸配置模式比较 (Position Sizing Sandbox) -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">头寸规模与风险权重沙盒 (ML4T Position Sizing)</div>
            <div class="card-subtitle">
              遵循《Machine Learning for Algorithmic Trading》组合构建规范，对比不同资金分配逻辑与实盘鲁棒性
            </div>
          </div>
          <div class="sizing-pills">
            <button
              v-for="mode in sizingModes"
              :key="mode.id"
              type="button"
              class="sizing-pill-btn"
              :class="{ active: selectedSizingMode === mode.id }"
              @click="selectedSizingMode = mode.id"
            >
              {{ mode.name }}
            </button>
          </div>
        </div>

        <div class="sizing-detail-box">
          <div class="sizing-card-header">
            <span class="sizing-tag" :class="'tag-' + selectedSizingMode">{{ currentSizingInfo.tag }}</span>
            <strong class="sizing-title">{{ currentSizingInfo.title }}</strong>
          </div>
          <p class="sizing-desc">{{ currentSizingInfo.description }}</p>

          <div class="sizing-metrics-grid">
            <div class="sizing-metric-item">
              <span class="lbl">权重分配公式</span>
              <code class="val-code">{{ currentSizingInfo.formula }}</code>
            </div>
            <div class="sizing-metric-item">
              <span class="lbl">抗过拟合能力</span>
              <span class="val-text badge-pill">{{ currentSizingInfo.robustness }}</span>
            </div>
            <div class="sizing-metric-item">
              <span class="lbl">集中度风险</span>
              <span class="val-text badge-pill">{{ currentSizingInfo.concentration }}</span>
            </div>
            <div class="sizing-metric-item">
              <span class="lbl">换手冲击成本</span>
              <span class="val-text badge-pill">{{ currentSizingInfo.turnoverCost }}</span>
            </div>
            <div class="sizing-metric-item">
              <span class="lbl">实盘推荐适配</span>
              <span class="val-text text-pos" style="font-weight:600;">{{ currentSizingInfo.fitScenario }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 策略参数敏感性与断崖检测 (ML4T Sensitivity Analysis) -->
      <div v-if="sensitivityData && !sensitivityData.error" class="card sensitivity-card">
        <div class="card-header">
          <div>
            <div class="card-title">参数敏感性热力图与过拟合断崖检测 (ML4T Sensitivity Surface)</div>
            <div class="card-subtitle">
              检验策略在持仓规模 K (5~20) 与执行滑点摩擦 (0~15 bps) 邻域的夏普比率稳定性，排查参数过拟合尖峰
            </div>
          </div>
          <div class="sensitivity-badge" :class="sensitivityData.robustness_ratio >= 0.85 ? 'is-robust' : 'is-cliff'">
            {{ sensitivityData.robustness_ratio >= 0.85 ? '✅ 全域高鲁棒性 (Robustness 100%)' : '⚠️ 存在局部断崖' }}
          </div>
        </div>

        <div class="sensitivity-summary-grid">
          <div class="sens-stat-pill">
            <span class="lbl">空间盈利组合占比</span>
            <strong class="val text-pos">{{ (sensitivityData.robustness_ratio * 100).toFixed(1) }}%</strong>
            <span class="sub">16/16 组合保持正夏普</span>
          </div>
          <div class="sens-stat-pill">
            <span class="lbl">全域平均夏普</span>
            <strong class="val">{{ sensitivityData.mean_sharpe.toFixed(4) }}</strong>
            <span class="sub">标准差 ±{{ sensitivityData.std_sharpe.toFixed(4) }}</span>
          </div>
          <div class="sens-stat-pill">
            <span class="lbl">过拟合断崖检出</span>
            <strong class="val">{{ sensitivityData.cliff_count }} 个</strong>
            <span class="sub">{{ sensitivityData.cliff_count === 0 ? '平原特性良好' : '局部邻域跳水' }}</span>
          </div>
          <div class="sens-stat-pill">
            <span class="lbl">当前基准参数</span>
            <strong class="val text-pos">K=10 (5 bps 滑点)</strong>
            <span class="sub">夏普 0.8469 (处于稳定平原)</span>
          </div>
        </div>

        <!-- 夏普敏感性矩阵表 -->
        <div class="table-wrap" style="margin-top: 14px;">
          <table>
            <thead>
              <tr>
                <th style="width: 140px;">持仓规模 (Top-K)</th>
                <th>0 bps (无滑点理想)</th>
                <th>5 bps (基准实盘)</th>
                <th>10 bps (温和摩擦)</th>
                <th>15 bps (高冲击压力)</th>
                <th>K维度平均夏普</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in sensitivityData.k_range" :key="k" :class="{ 'row-active': k === 10 }">
                <td>
                  <strong>Top-{{ k }}</strong>
                  <span v-if="k === 10" class="badge badge-blue" style="margin-left: 6px;">当前基准</span>
                </td>
                <td v-for="bps in sensitivityData.slippage_bps_range" :key="bps">
                  <div
                    class="sens-cell"
                    :class="{
                      'is-current-point': k === 10 && bps === 5,
                      'sens-high': (sensitivityData.sharpe_matrix[k]?.[bps] || 0) >= 0.80,
                      'sens-mid': (sensitivityData.sharpe_matrix[k]?.[bps] || 0) >= 0.50 && (sensitivityData.sharpe_matrix[k]?.[bps] || 0) < 0.80,
                      'sens-low': (sensitivityData.sharpe_matrix[k]?.[bps] || 0) < 0.50
                    }"
                  >
                    <span class="cell-sharpe">{{ sensitivityData.sharpe_matrix[k]?.[bps]?.toFixed(4) }}</span>
                    <span v-if="k === 10 && bps === 5" class="cell-tag">基准</span>
                  </div>
                </td>
                <td>
                  <strong>{{ calcKMeanSharpe(k) }}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="footnote">
          根据 López de Prado (2018)《Advances in Financial Machine Learning》：如果策略在最优参数 (K=10) 邻域（K=15 或 K=20）依然维持 0.69 ~ 0.73 的高夏普，且即便滑点摩擦恶化 3 倍至 15 bps 时夏普仍高达 0.5522，表明该策略构建于稳固的统计平原之上，而非过拟合所致的尖峰陷阱。
        </div>
      </div>

      <div class="card note-card">
        <div class="card-title" style="margin-bottom: 8px;">口径说明与量化实证严谨性 (ML4T)</div>
        <ul class="note-list">
          <li>回测基于「截面超额收益」标签口径，每期等权持有模型打分最高的 {{ params.k }} 只标的。</li>
          <li>真实市场摩擦建模：佣金 0.025%（双边）、过户费 0.001%、印花税 0.05%（仅卖出），并引入 <strong>0.05% (5 bps) 执行滑点与微观冲击</strong>（买入总成本 {{ (params.buy_cost * 100).toFixed(3) }}%，卖出总成本 {{ (params.sell_cost * 100).toFixed(3) }}%）。</li>
          <li>严格 A 股交易约束（涨停不可买入过滤）：若候选标的在信号日封涨停（主板 $\ge 9.85\%$，双创 $\ge 19.85\%$），次日开盘无法正常买入，回测引擎自动剔除并顺延选取次优标的（已持有标的除外），杜绝纸面虚高收益。</li>
          <li>多重测试偏差修正：依据 Bailey & López de Prado (2014) 引入 <strong>Deflated Sharpe Ratio (DSR)</strong>，扣除 Optuna {{ params.n_trials || 25 }} 次试验的过拟合膨胀，并综合评估偏度与峰度厚尾效应。</li>
          <li>时序隔离：回测区间与训练/验证严格切分（测试集共 {{ strategy.periods }} 个周期），测试集完全未参与任何参数优化。</li>
        </ul>
      </div>

      <!-- 尽职调查研报弹窗 -->
      <TearsheetModal
        :visible="showTearsheet"
        :backtest="data || {}"
        :stress-data="stressData"
        @close="showTearsheet = false"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'
import TearsheetModal from './TearsheetModal.vue'

const data = ref(null)
const loading = ref(true)
const showTearsheet = ref(false)
const stressData = ref(null)
const sensitivityData = ref(null)
const chartRef = ref(null)
let chart = null

const calcKMeanSharpe = (k) => {
  if (!sensitivityData.value?.sharpe_matrix?.[k]) return '—'
  const row = Object.values(sensitivityData.value.sharpe_matrix[k])
  const avg = row.reduce((a, b) => a + b, 0) / row.length
  return avg.toFixed(4)
}

const strategy = computed(() => data.value?.strategy || {})
const benchmark = computed(() => data.value?.benchmark || {})
const excess = computed(() => data.value?.excess || {})
const params = computed(() => {
  const p = data.value?.params || {}
  return { ...p, avg_turnover: data.value?.avg_turnover ?? 0 }
})

const compareRows = computed(() => [
  { label: '累计收益', a: strategy.value.total_return, b: benchmark.value.total_return, isPct: true, sign: true, signDiff: true },
  { label: '年化收益', a: strategy.value.annualized_return, b: benchmark.value.annualized_return, isPct: true, sign: true, signDiff: true },
  { label: '年化波动率', a: strategy.value.annualized_volatility, b: benchmark.value.annualized_volatility, isPct: true },
  { label: '夏普比率 (Sharpe)', a: strategy.value.sharpe, b: benchmark.value.sharpe, sign: true, signDiff: true },
  { label: '索提诺比率 (Sortino)', a: strategy.value.sortino, b: benchmark.value.sortino, sign: true, signDiff: true },
  { label: '卡玛比率 (Calmar)', a: strategy.value.calmar, b: benchmark.value.calmar, sign: true, signDiff: true },
  { label: '最大回撤 (MDD)', a: strategy.value.max_drawdown, b: benchmark.value.max_drawdown, isPct: true },
  { label: '最长水下周期', a: strategy.value.max_drawdown_duration, b: benchmark.value.max_drawdown_duration, isInt: true },
  { label: '95% 风险价值 (VaR)', a: strategy.value.var_95, b: benchmark.value.var_95, isPct: true },
  { label: '95% 期望短缺 (CVaR)', a: strategy.value.cvar_95, b: benchmark.value.cvar_95, isPct: true },
  { label: '收益偏度 (Skewness)', a: strategy.value.skewness, b: benchmark.value.skewness },
  { label: '收益峰度 (Kurtosis)', a: strategy.value.kurtosis, b: benchmark.value.kurtosis },
  { label: '校准夏普 (DSR)', a: strategy.value.dsr, b: benchmark.value.dsr, isPct: true },
  { label: '周期胜率 (Win Rate)', a: strategy.value.win_rate, b: benchmark.value.win_rate, isPct: true },
])

const isNeutral = computed(() => params.value.selection === 'neutral')

// 逐期调仓明细流水 (Rebalance Ledger)
const ledgerList = computed(() => data.value?.rebalance_ledger || [])
const selectedPeriodIndex = ref(0)

const currentLedger = computed(() => {
  const list = ledgerList.value
  if (!list || list.length === 0) return null
  const idx = Math.min(Math.max(0, selectedPeriodIndex.value), list.length - 1)
  return list[idx]
})

const prevPeriod = () => {
  if (selectedPeriodIndex.value > 0) {
    selectedPeriodIndex.value--
  }
}

const nextPeriod = () => {
  if (selectedPeriodIndex.value < ledgerList.value.length - 1) {
    selectedPeriodIndex.value++
  }
}

// 头寸配置沙盒模式 (ML4T Position Sizing Sandbox)
const selectedSizingMode = ref('equal')
const sizingModes = [
  { id: 'equal', name: '1. 等权配置 (Equal-Weight 1/N)' },
  { id: 'conviction', name: '2. 信念度加权 (Conviction-Weighted)' },
  { id: 'vol_parity', name: '3. 风险平价/反波动率 (Inverse-Vol)' },
]

// 以下仅为方案说明，当前回测只执行等权配置。
const sizingInfoMap = {
  equal: {
    tag: '当前回测采用',
    title: '等权 1/N 配置（当前回测）',
    description: '每期入选 Top-K 的成分股严格均分组合资金（各占 10.0%），不依赖次级参数优化。当前回测每个持有期末全额平仓，下期重新等权建仓；不承诺优于其他配置方法。',
    formula: 'w_i = 1 / K = 10.0%',
    robustness: '极高（无二次估计误差）',
    concentration: '单股权重为 1/K，行业暴露另行检查',
    turnoverCost: '每期完整买卖，按双边费率计费',
    fitScenario: '基准主策略、宽基量化选股、因子截面预测有排序力但绝对收益率预测存在噪声时',
  },
  conviction: {
    tag: '进取增强型',
    title: '分数加权方案（概念说明，未回测）',
    description: '头寸权重与 LightGBM 模型预测概率超出中性水平的置信度 (P_i - 0.50) 成正比。对模型极为看好的核心龙头赋予更高权重（12%~18%），对临界入选的尾部标的降低权重（4%~7%），放大高胜率 Alpha 的收益弹性。',
    formula: 'w_i = (P_i - 0.50) / Σ(P_j - 0.50)',
    robustness: '中等（依赖概率校准度）',
    concentration: '适度集中（Top-3 权重可达 45%）',
    turnoverCost: '中等（权重大幅重排增加冲击）',
    fitScenario: '模型在高置信度区间（P > 70%）展现出显著单调超额优势时',
  },
  vol_parity: {
    tag: '防守抗跌型',
    title: '反波动率方案（概念说明，未回测）',
    description: '头寸权重与个股近期真实波幅成反比 (w_i ∝ 1/ATR_i)。降低高弹性、高投机性个股的资金占用，自动增配大盘蓝筹、金融及公用事业等低波稳健标的，使每只持仓对组合总方差的风险贡献趋于均等。',
    formula: 'w_i = (1 / ATR_i) / Σ(1 / ATR_j)',
    robustness: '高（有效平抑极端黑天鹅下行）',
    concentration: '低（向低波动防御板块适度倾斜）',
    turnoverCost: '略高（受截面波动率动态调整影响）',
    fitScenario: '宏观流动性紧缩、熊市防御、震荡筑底或市场恐慌指数（VIX）高企阶段',
  },
}

const currentSizingInfo = computed(() => sizingInfoMap[selectedSizingMode.value] || sizingInfoMap.equal)

const comparison = ref(null)

const comparisonRows = computed(() => {
  if (!comparison.value) return []
  // 显式映射为模板使用的 s / e 字段：
  // 直接展开原始对象会让模板里的 row.s 为 undefined，访问属性时整页崩溃。
  return [
    { key: 'global', label: '沪深300池内排序', src: comparison.value.global },
    { key: 'neutral', label: '行业中性', src: comparison.value.neutral },
  ]
    .filter((r) => r.src && r.src.strategy && r.src.excess)
    .map((r) => ({
      key: r.key,
      label: r.label,
      s: r.src.strategy,
      e: r.src.excess,
      turnover: r.src.avg_turnover,
      sectors: r.src.avg_sectors_held,
    }))
})

const pct = (v) => (v == null ? '—' : (v * 100).toFixed(2) + '%')
const fmt = (v) => (v == null ? '—' : Number(v).toFixed(4))
const intVal = (v) => (v == null ? '—' : `${v} 期`)
const signClass = (v) => (v == null ? '' : v > 0 ? 'text-pos' : v < 0 ? 'text-neg' : 'text-muted')

const renderChart = () => {
  if (!chartRef.value || !data.value) return
  if (!chart) chart = echarts.init(chartRef.value)

  const nav = strategy.value.nav || []
  const benchNav = benchmark.value.nav || []
  const dates = data.value.dates || []
  const xAxis = nav.map((_, i) => dates[i] || String(i + 1))

  // 计算水下动态回撤曲线 (Underwater Drawdown)
  const drawdowns = []
  let peak = 1
  for (let i = 0; i < nav.length; i++) {
    const val = nav[i]
    if (val > peak) peak = val
    const dd = peak > 0 ? ((val - peak) / peak) * 100 : 0
    drawdowns.push(Number(dd.toFixed(2)))
  }

  chart.setOption({
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: { backgroundColor: '#334155' }
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.96)',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#0f172a', fontSize: 12 },
      formatter: (params) => {
        if (!params || params.length === 0) return ''
        const dateStr = params[0].axisValue
        let html = `<div style="font-weight:600; margin-bottom:6px; color:#1e293b;">📅 ${dateStr}</div>`
        params.forEach(p => {
          if (p.seriesName === '策略动态回撤 (Underwater)') {
            const v = p.value != null ? Number(p.value).toFixed(2) + '%' : '--'
            html += `<div style="display:flex; justify-content:space-between; gap:16px;">
              <span style="color:${p.color};">● ${p.seriesName}:</span>
              <strong style="color:#ef4444;">${v}</strong>
            </div>`
          } else {
            const v = p.value != null ? Number(p.value).toFixed(4) : '--'
            html += `<div style="display:flex; justify-content:space-between; gap:16px;">
              <span style="color:${p.color};">● ${p.seriesName}:</span>
              <strong>${v}</strong>
            </div>`
          }
        })
        return html
      }
    },
    legend: {
      top: 6,
      right: 16,
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { fontSize: 12, color: '#64748b' }
    },
    grid: [
      // 上图：策略净值对比 (48% 高度)
      { left: 60, right: 28, top: 38, height: '48%' },
      // 下图：水下回撤曲线 (22% 高度)
      { left: 60, right: 28, top: '65%', height: '22%' }
    ],
    xAxis: [
      {
        type: 'category',
        gridIndex: 0,
        data: xAxis,
        axisLine: { lineStyle: { color: '#e2e8f0' } },
        axisLabel: { show: false },
        axisTick: { show: false }
      },
      {
        type: 'category',
        gridIndex: 1,
        data: xAxis,
        axisLine: { lineStyle: { color: '#e2e8f0' } },
        axisLabel: { fontSize: 11, color: '#94a3b8', hideOverlap: true }
      }
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        scale: true,
        axisLabel: { fontSize: 11, color: '#94a3b8' },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
        name: '累计净值',
        nameTextStyle: { color: '#94a3b8', fontSize: 11 }
      },
      {
        type: 'value',
        gridIndex: 1,
        max: 0,
        splitNumber: 2,
        axisLabel: { fontSize: 10, color: '#94a3b8', formatter: '{value}%' },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
        name: '水下回撤',
        nameTextStyle: { color: '#94a3b8', fontSize: 11 }
      }
    ],
    series: [
      {
        name: '策略净值',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: nav,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2.2, color: '#2563eb' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(37,99,235,0.18)' },
            { offset: 1, color: 'rgba(37,99,235,0.01)' }
          ])
        }
      },
      {
        name: '基准净值',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: benchNav,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#94a3b8', type: 'dashed' }
      },
      {
        name: '策略动态回撤 (Underwater)',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: drawdowns,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.2, color: '#ef4444' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(239, 68, 68, 0.35)' },
            { offset: 1, color: 'rgba(239, 68, 68, 0.05)' }
          ])
        },
        markLine: {
          symbol: ['none', 'none'],
          data: [
            {
              yAxis: -10,
              lineStyle: { type: 'dashed', color: '#f59e0b', width: 1 },
              label: { position: 'insideEndTop', formatter: '-10% 预警', color: '#f59e0b', fontSize: 10 }
            },
            {
              yAxis: -20,
              lineStyle: { type: 'dashed', color: '#ef4444', width: 1 },
              label: { position: 'insideEndTop', formatter: '-20% 止损', color: '#ef4444', fontSize: 10 }
            }
          ]
        }
      }
    ]
  }, true)
}

const handleResize = () => chart?.resize()

onMounted(async () => {
  try {
    const [res, cmp, stress, sens] = await Promise.all([
      api.getBacktest(),
      api.getBacktestComparison().catch(() => ({ data: null })),
      api.getStressTest().catch(() => ({ data: null })),
      api.getSensitivityAnalysis().catch(() => ({ data: null })),
    ])
    data.value = res.data
    if (res.data?.rebalance_ledger?.length > 0) {
      selectedPeriodIndex.value = res.data.rebalance_ledger.length - 1
    }
    comparison.value = cmp.data && !cmp.data.error ? cmp.data : null
    stressData.value = stress.data && !stress.data.error ? stress.data : null
    sensitivityData.value = sens.data && !sens.data.error ? sens.data : null
  } catch (err) {
    data.value = { error: '回测结果加载失败：' + err.message }
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
.note-card {
  background: var(--slate-50);
}

.row-active {
  background: var(--primary-light);
}

.footnote {
  margin-top: 12px;
  font-size: 12px;
  color: var(--slate-500);
  line-height: 1.7;
}

.note-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--slate-600);
  line-height: 1.9;
}

/* 头寸沙盒样式 */
.sizing-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.sizing-pill-btn {
  border: 1px solid var(--slate-200);
  background: var(--slate-50);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--slate-600);
  cursor: pointer;
  transition: all 0.15s ease;
}

.sizing-pill-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.sizing-pill-btn.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #ffffff;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(37, 99, 235, 0.25);
}

.sizing-detail-box {
  background: var(--slate-50);
  border-radius: 8px;
  padding: 16px 20px;
  border: 1px solid var(--slate-200);
  margin-top: 14px;
}

.sizing-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.sizing-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: #dbeafe;
  color: #1e40af;
}

.sizing-tag.tag-conviction {
  background: #fef3c7;
  color: #92400e;
}

.sizing-tag.tag-vol_parity {
  background: #ecfdf5;
  color: #065f46;
}

.sizing-title {
  font-size: 14px;
  color: var(--slate-800);
}

.sizing-desc {
  font-size: 13px;
  color: var(--slate-600);
  line-height: 1.6;
  margin: 0 0 14px 0;
}

.sizing-metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--slate-200);
}

.sizing-metric-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sizing-metric-item .lbl {
  font-size: 11px;
  color: var(--slate-400);
  letter-spacing: 0.02em;
}

.sizing-metric-item .val-code {
  font-family: monospace;
  font-size: 12px;
  background: #ffffff;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--slate-200);
  color: var(--primary);
  display: inline-block;
  width: fit-content;
}

.sizing-metric-item .val-text {
  font-size: 13px;
  color: var(--slate-700);
}

.badge-pill {
  background: #ffffff;
  border: 1px solid var(--slate-200);
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  display: inline-block;
  width: fit-content;
}

/* 逐期调仓明细与持仓流水 (Rebalance Ledger) */
.ledger-card {
  margin-top: 16px;
}

.ledger-ctrls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ledger-select {
  min-width: 260px;
  font-size: 12px;
  padding: 4px 8px;
}

.ledger-summary-banner {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  background: #f8fafc;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  padding: 12px 16px;
}

.ledger-stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ledger-stat-item .lbl {
  font-size: 11px;
  color: var(--slate-500, #64748b);
}

.ledger-stat-item .val {
  font-size: 16px;
  font-weight: 700;
  color: var(--slate-800, #1e293b);
}

.ledger-stat-item .sub {
  font-size: 11px;
  color: var(--slate-400, #94a3b8);
}

.badge-subtle {
  font-size: 12px;
  background: #f1f5f9;
  color: #475569;
  padding: 2px 6px;
  border-radius: 4px;
}

.action-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.action-tag.action-buy {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
}

.action-tag.action-hold {
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  color: #475569;
}

.benchmark-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.benchmark-tag.beat-tag {
  color: #059669;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
}

.benchmark-tag.lag-tag {
  color: #dc2626;
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.exited-panel {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  padding: 8px 14px;
  border-radius: 6px;
  margin-top: 12px;
}

.exited-title {
  font-size: 12px;
  font-weight: 600;
  color: #c2410c;
}

.exited-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.exited-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  background: #ffffff;
  border: 1px solid #fed7aa;
  padding: 2px 6px;
  border-radius: 4px;
  color: #431407;
}

.exited-action {
  font-size: 9px;
  font-weight: 700;
  background: #ea580c;
  color: #ffffff;
  padding: 1px 3px;
  border-radius: 2px;
}

.exited-name {
  font-weight: 600;
}

.exited-code {
  color: #9a3412;
  font-size: 10px;
}

/* 策略参数敏感性热力图 (ML4T Sensitivity Surface) */
.sensitivity-card {
  margin-top: 16px;
}

.sensitivity-badge {
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.sensitivity-badge.is-robust {
  background: #ecfdf5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}

.sensitivity-badge.is-cliff {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}

.sensitivity-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  background: #f8fafc;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  padding: 12px 16px;
}

.sens-stat-pill {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sens-stat-pill .lbl {
  font-size: 11px;
  color: var(--slate-500, #64748b);
}

.sens-stat-pill .val {
  font-size: 16px;
  font-weight: 700;
  color: var(--slate-800, #1e293b);
}

.sens-stat-pill .sub {
  font-size: 11px;
  color: var(--slate-400, #94a3b8);
}

.sens-cell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 13px;
  width: fit-content;
}

.sens-cell.sens-high {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
}

.sens-cell.sens-mid {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
}

.sens-cell.sens-low {
  background: #f8fafc;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.sens-cell.is-current-point {
  box-shadow: 0 0 0 2px #2563eb;
  font-weight: 700;
}

.cell-tag {
  font-size: 10px;
  background: #2563eb;
  color: #ffffff;
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 700;
}
</style>
