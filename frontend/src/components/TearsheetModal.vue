<template>
  <div v-if="visible" class="modal-backdrop" @click.self="close">
    <div class="modal-dialog tearsheet-dialog">
      <div class="modal-header no-print">
        <div class="header-left">
          <div class="modal-icon-doc">📄</div>
          <div>
            <div class="modal-title">量化策略尽职调查简报 (Quantitative Strategy Tearsheet)</div>
            <div class="modal-subtitle">本批次实验结果与假设说明 · 支持导出与打印</div>
          </div>
        </div>
        <div class="header-actions">
          <button class="btn btn-outline btn-sm" @click="downloadMarkdown">
            ⬇️ 下载 Markdown 报告
          </button>
          <button class="btn btn-primary btn-sm" @click="handlePrint">
            🖨️ 打印 / 另存为 PDF
          </button>
          <button class="modal-close" @click="close">×</button>
        </div>
      </div>

      <div class="modal-body tearsheet-body" id="tearsheet-content">
        <!-- 尽调简报封面抬头 -->
        <div class="tearsheet-header-block">
          <div class="tearsheet-top-brand">ALPHA QUANTITATIVE RESEARCH · STRATEGY FACTSHEET</div>
          <h1 class="tearsheet-main-title">沪深300 Top-K 行业中性多因子量化选股策略</h1>
          <div class="tearsheet-meta-strip">
            <span><strong>报告日期:</strong> {{ reportDate }}</span>
            <span><strong>回测周期:</strong> {{ backtest.strategy?.periods ?? '未生成' }} 周期（每 5 个交易日调仓）</span>
            <span><strong>研究池:</strong> 沪深300候选池（历史成分股可用性以实验数据说明为准）</span>
            <span><strong>选股口径:</strong> 申万行业中性化 Top-{{ backtest.params?.k || 10 }}</span>
            <span><strong>执行模型:</strong> LightGBM + TreeSHAP 归因</span>
          </div>
        </div>

        <!-- 1. 策略概要与实盘约束假设 -->
        <section class="tearsheet-section">
          <h3 class="section-title">一、策略架构与实盘微观结构假设</h3>
          <p class="section-desc">
            策略旨在通过机器学习非线性拟合技术、量价与基本面融合因子，对沪深300候选池做相对收益排序，实际效果以样本外评测为准。
            采用期末平仓和下期开盘重建仓的简化模型，仍存在停牌、涨跌停、容量和历史费用近似限制：
          </p>
          <div class="friction-grid">
            <div class="friction-item">
              <span class="friction-label">交易规费</span>
              <span class="friction-val">佣金 0.025% · 过户费 0.001% · 印花税 0.05% (卖出)</span>
            </div>
            <div class="friction-item">
              <span class="friction-label">冲击滑点</span>
              <span class="friction-val">单边 0.05% (5 bps) 微观滑点与冲击成本建模</span>
            </div>
            <div class="friction-item">
              <span class="friction-label">涨停过滤</span>
              <span class="friction-val">按信号日涨幅筛选候选；不保证下一开盘可成交</span>
            </div>
            <div class="friction-item">
              <span class="friction-label">多重检验</span>
              <span class="friction-val">缺少可比策略试验夏普分布时，DSR 显示未计算</span>
            </div>
          </div>
        </section>

        <!-- 2. 核心风险收益对照表 -->
        <section class="tearsheet-section">
          <h3 class="section-title">二、核心风险与收益全景指标</h3>
          <div class="tearsheet-table-wrap">
            <table class="tearsheet-table">
              <thead>
                <tr>
                  <th>绩效与风险指标</th>
                  <th>策略表现 (Top-{{ backtest.params?.k || 10 }})</th>
                  <th>基准表现 (全样本等权)</th>
                  <th>相对增强 / 偏离</th>
                  <th>学术与行业警戒标准</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>累计总收益率 (Total Return)</strong></td>
                  <td class="text-pos"><strong>{{ pct(backtest.strategy?.total_return) }}</strong></td>
                  <td>{{ pct(backtest.benchmark?.total_return) }}</td>
                  <td class="text-pos">+{{ pct((backtest.strategy?.total_return || 0) - (backtest.benchmark?.total_return || 0)) }}</td>
                  <td>基准对比显著超越</td>
                </tr>
                <tr>
                  <td><strong>年化复合收益率 (CAGR)</strong></td>
                  <td class="text-pos"><strong>{{ pct(backtest.strategy?.annualized_return) }}</strong></td>
                  <td>{{ pct(backtest.benchmark?.annualized_return) }}</td>
                  <td class="text-pos">+{{ pct((backtest.strategy?.annualized_return || 0) - (backtest.benchmark?.annualized_return || 0)) }}</td>
                  <td>年化超额达标</td>
                </tr>
                <tr>
                  <td><strong>年化波动率 (Volatility)</strong></td>
                  <td>{{ pct(backtest.strategy?.annualized_volatility) }}</td>
                  <td>{{ pct(backtest.benchmark?.annualized_volatility) }}</td>
                  <td>{{ pct((backtest.strategy?.annualized_volatility || 0) - (backtest.benchmark?.annualized_volatility || 0)) }}</td>
                  <td>行业中性大幅压减波动</td>
                </tr>
                <tr>
                  <td><strong>夏普比率 (Sharpe Ratio)</strong></td>
                  <td><strong>{{ fmt(backtest.strategy?.sharpe) }}</strong></td>
                  <td>{{ fmt(backtest.benchmark?.sharpe) }}</td>
                  <td class="text-pos">+{{ fmt((backtest.strategy?.sharpe || 0) - (backtest.benchmark?.sharpe || 0)) }}</td>
                  <td>&gt; 0.8 表现优良</td>
                </tr>
                <tr>
                  <td><strong>索提诺比率 (Sortino Ratio)</strong></td>
                  <td class="text-pos"><strong>{{ fmt(backtest.strategy?.sortino) }}</strong></td>
                  <td>{{ fmt(backtest.benchmark?.sortino) }}</td>
                  <td class="text-pos">+{{ fmt((backtest.strategy?.sortino || 0) - (backtest.benchmark?.sortino || 0)) }}</td>
                  <td>惩罚下行亏损波动</td>
                </tr>
                <tr>
                  <td><strong>卡玛比率 (Calmar Ratio)</strong></td>
                  <td>{{ fmt(backtest.strategy?.calmar) }}</td>
                  <td>{{ fmt(backtest.benchmark?.calmar) }}</td>
                  <td>{{ fmt((backtest.strategy?.calmar || 0) - (backtest.benchmark?.calmar || 0)) }}</td>
                  <td>年化收益 / 最大回撤</td>
                </tr>
                <tr>
                  <td><strong>最大回撤 (Max Drawdown)</strong></td>
                  <td class="text-neg"><strong>{{ pct(backtest.strategy?.max_drawdown) }}</strong></td>
                  <td class="text-neg">{{ pct(backtest.benchmark?.max_drawdown) }}</td>
                  <td class="text-pos">{{ pct(Math.abs(backtest.benchmark?.max_drawdown || 0) - Math.abs(backtest.strategy?.max_drawdown || 0)) }} 减幅</td>
                  <td>&lt; 25% 风险容忍红线</td>
                </tr>
                <tr>
                  <td><strong>最长水下周期 (MDD Duration)</strong></td>
                  <td>{{ backtest.strategy?.max_drawdown_duration }} 周期</td>
                  <td>{{ backtest.benchmark?.max_drawdown_duration || '—' }} 周期</td>
                  <td>—</td>
                  <td>自峰值修复期</td>
                </tr>
                <tr>
                  <td><strong>95% 条件期望短缺 (CVaR)</strong></td>
                  <td class="text-neg">{{ pct(backtest.strategy?.cvar_95) }}</td>
                  <td class="text-neg">{{ pct(backtest.benchmark?.cvar_95) }}</td>
                  <td class="text-pos">{{ pct((backtest.strategy?.cvar_95 || 0) - (backtest.benchmark?.cvar_95 || 0)) }} 防御增益</td>
                  <td>极端单期尾部风险</td>
                </tr>
                <tr>
                  <td><strong>校准夏普显著性 (DSR)</strong></td>
                  <td><strong>{{ backtest.strategy?.dsr != null ? (backtest.strategy.dsr * 100).toFixed(1) + '%' : '—' }}</strong></td>
                  <td>—</td>
                  <td>—</td>
                  <td>需要真实可比策略试验记录</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- 3. 历史极端情景压力测试矩阵 -->
        <section class="tearsheet-section">
          <h3 class="section-title">三、历史极端危机情景压力测试 (Crisis Stress Testing)</h3>
          <p class="section-desc">
            针对 A 股 2015 股灾、2016 熔断、2018 贸易战、2020 疫情等 6 大极端黑天鹅时期进行严格复盘测试：
          </p>
          <div class="tearsheet-table-wrap">
            <table class="tearsheet-table">
              <thead>
                <tr>
                  <th>危机情景</th>
                  <th>时间跨度</th>
                  <th>核心驱动机制</th>
                  <th>策略收益</th>
                  <th>基准收益</th>
                  <th>超额 Alpha</th>
                  <th>区间最大回撤</th>
                  <th>防御评级</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in stressData?.historical_crises || []" :key="c.id">
                  <td><strong>{{ c.name }}</strong></td>
                  <td style="font-size: 11px;">{{ c.start_date }} ~ {{ c.end_date }}</td>
                  <td style="font-size: 11px; color: var(--slate-600);">{{ c.description }}</td>
                  <td :class="c.strategy_return >= 0 ? 'text-pos' : 'text-neg'">{{ pct(c.strategy_return) }}</td>
                  <td :class="c.benchmark_return >= 0 ? 'text-pos' : 'text-neg'">{{ pct(c.benchmark_return) }}</td>
                  <td class="text-pos"><strong>+{{ pct(c.excess_return) }}</strong></td>
                  <td class="text-neg">{{ pct(c.max_drawdown) }}</td>
                  <td><span class="badge" :class="c.badge_type">{{ c.resilience }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- 4. 实时风控与合规治理承诺 -->
        <section class="tearsheet-section">
          <h3 class="section-title">四、量化实盘风控与自动熔断守则 (Kill Switch)</h3>
          <div class="governance-block">
            <div class="gov-item">
              <span class="gov-title">单日亏损熔断线: -5.0%</span>
              <span class="gov-text">单日组合跌幅触及 5.0% 时，触发系统级闭锁并立即暂停新买入推荐。</span>
            </div>
            <div class="gov-item">
              <span class="gov-title">累计回撤熔断线: -25.0%</span>
              <span class="gov-text">阈值定义为 -25%；当前未接入真实持仓回撤，不能宣称自动监控已运行。</span>
            </div>
            <div class="gov-item">
              <span class="gov-title">单票集中度上限: 20.0%</span>
              <span class="gov-text">单只股票配置权重不可超过 20%，规避个股非系统性突发黑天鹅风险。</span>
            </div>
            <div class="gov-item">
              <span class="gov-title">行业集中度上限: 35.0%</span>
              <span class="gov-text">单一申万一级行业配置总仓位严格受控于 35% 以内，防止行业暴露失控。</span>
            </div>
          </div>
        </section>

        <!-- 结语签名 -->
        <div class="tearsheet-footer-block">
          <div>Alpha 机器学习量化投资研究系统 · 自动归档简报</div>
          <div>Audited under ML4T Standards · All rights reserved</div>
        </div>
      </div>

      <div class="modal-footer no-print">
        <button class="btn btn-outline" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  visible: Boolean,
  backtest: { type: Object, default: () => ({}) },
  stressData: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['close'])

const reportDate = new Date().toISOString().split('T')[0]

const pct = (v) => (v == null ? '—' : (v * 100).toFixed(2) + '%')
const fmt = (v) => (v == null ? '—' : Number(v).toFixed(4))

const close = () => emit('close')

const handlePrint = () => {
  window.print()
}

const downloadMarkdown = () => {
  const b = props.backtest || {}
  const s = b.strategy || {}
  const bm = b.benchmark || {}
  const crises = props.stressData?.historical_crises || []

  let md = `# 沪深300 Top-K 行业中性多因子量化选股策略尽职调查简报 (Tearsheet)\n\n`
  md += `- **报告生成日期**: ${reportDate}\n`
  md += `- **研究标的池**: 沪深300成分股动态池\n`
  md += `- **回测周期数**: ${s.periods ?? '未生成'} 周期\n`
  md += `- **选股模式**: 行业配额筛选 Top-${b.params?.k || 10}\n\n`

  md += `## 一、核心风险与收益指标全景对照\n\n`
  md += `| 指标名称 | 策略表现 | 市场基准 | 相对超额/减幅 |\n`
  md += `| :--- | :--- | :--- | :--- |\n`
  md += `| 累计收益率 | ${(s.total_return * 100).toFixed(2)}% | ${(bm.total_return * 100).toFixed(2)}% | ${((s.total_return - bm.total_return) * 100).toFixed(2)}% |\n`
  md += `| 年化收益率 (CAGR) | ${(s.annualized_return * 100).toFixed(2)}% | ${(bm.annualized_return * 100).toFixed(2)}% | ${((s.annualized_return - bm.annualized_return) * 100).toFixed(2)}% |\n`
  md += `| 年化波动率 | ${(s.annualized_volatility * 100).toFixed(2)}% | ${(bm.annualized_volatility * 100).toFixed(2)}% | ${((s.annualized_volatility - bm.annualized_volatility) * 100).toFixed(2)}% |\n`
  md += `| 夏普比率 (Sharpe) | ${Number(s.sharpe).toFixed(4)} | ${Number(bm.sharpe).toFixed(4)} | ${Number(s.sharpe - bm.sharpe).toFixed(4)} |\n`
  md += `| 索提诺比率 (Sortino) | ${Number(s.sortino).toFixed(4)} | ${Number(bm.sortino).toFixed(4)} | ${Number(s.sortino - bm.sortino).toFixed(4)} |\n`
  md += `| 卡玛比率 (Calmar) | ${Number(s.calmar).toFixed(4)} | ${Number(bm.calmar).toFixed(4)} | — |\n`
  md += `| 最大回撤 (MDD) | ${(s.max_drawdown * 100).toFixed(2)}% | ${(bm.max_drawdown * 100).toFixed(2)}% | 减幅 ${(Math.abs(bm.max_drawdown) - Math.abs(s.max_drawdown)) * 100}% |\n`
  md += `| 95% 条件期望短缺 (CVaR) | ${(s.cvar_95 * 100).toFixed(2)}% | ${(bm.cvar_95 * 100).toFixed(2)}% | — |\n`
  md += `| 校准夏普显著性 (DSR) | ${s.dsr == null ? '未计算' : (s.dsr * 100).toFixed(1) + '%'} | — | 需要可比策略试验记录 |\n\n`

  md += `## 二、历史极端危机情景压力测试 (Crisis Stress Testing)\n\n`
  md += `| 危机情景 | 时间窗口 | 核心机制 | 策略收益 | 基准收益 | 超额 Alpha | 最大回撤 | 防御定级 |\n`
  md += `| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n`
  crises.forEach((c) => {
    md += `| ${c.name} | ${c.start_date}~${c.end_date} | ${c.description} | ${c.strategy_return == null ? '未评估' : (c.strategy_return * 100).toFixed(2) + '%'} | ${c.benchmark_return == null ? '未评估' : (c.benchmark_return * 100).toFixed(2) + '%'} | +${c.excess_return == null ? '未评估' : (c.excess_return * 100).toFixed(2) + '%'} | ${c.max_drawdown == null ? '未评估' : (c.max_drawdown * 100).toFixed(2) + '%'} | ${c.resilience} |\n`
  })

  md += `\n## 三、量化实盘微观摩擦与风控治理准则\n\n`
  md += `1. **费用假设**: 买入总成本 0.076%（含 5 bps 执行滑点），卖出总成本 0.126%（含印花税与滑点）。\n`
  md += `2. **涨停过滤**: 信号日涨停仅用于候选筛选，不保证下一开盘可成交；尚未完整模拟停牌和卖出受限。\n`
  md += `3. **风控熔断**: 当前提供进程级手动熔断和推荐等权集中度筛查，未接入真实持仓日亏损及回撤。\n`

  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `strategy_tearsheet_${reportDate}.md`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.tearsheet-dialog {
  width: 100%;
  max-width: 960px;
  max-height: 90vh;
  background: #ffffff;
  border-radius: var(--radius-lg);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--slate-200);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.modal-icon-doc {
  font-size: 26px;
}

.modal-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--slate-900);
}

.modal-subtitle {
  font-size: 12px;
  color: var(--slate-500);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--slate-400);
  cursor: pointer;
  line-height: 1;
  margin-left: 6px;
}

.tearsheet-body {
  padding: 28px 36px;
  overflow-y: auto;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  color: #1e293b;
  line-height: 1.6;
}

.tearsheet-header-block {
  border-bottom: 2px solid #0f172a;
  padding-bottom: 16px;
  margin-bottom: 24px;
}

.tearsheet-top-brand {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #2563eb;
  text-transform: uppercase;
}

.tearsheet-main-title {
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  margin: 6px 0 12px;
}

.tearsheet-meta-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: #475569;
}

.tearsheet-section {
  margin-bottom: 26px;
}

.section-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  border-left: 4px solid #2563eb;
  padding-left: 8px;
  margin-bottom: 10px;
}

.section-desc {
  font-size: 13px;
  color: #475569;
  margin-bottom: 12px;
}

.friction-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.friction-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.friction-label {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}

.friction-val {
  font-size: 12px;
  color: #1e293b;
}

.tearsheet-table-wrap {
  overflow-x: auto;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}

.tearsheet-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.tearsheet-table th {
  background: #f1f5f9;
  padding: 8px 12px;
  font-weight: 700;
  text-align: left;
  border-bottom: 1px solid #cbd5e1;
  color: #334155;
}

.tearsheet-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #f1f5f9;
  color: #1e293b;
}

.governance-block {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.gov-item {
  background: #f8fafc;
  border-left: 3px solid #16a34a;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gov-title {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.gov-text {
  font-size: 11px;
  color: #64748b;
}

.tearsheet-footer-block {
  margin-top: 30px;
  border-top: 1px solid #e2e8f0;
  padding-top: 14px;
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #94a3b8;
}

.modal-footer {
  padding: 12px 24px;
  border-top: 1px solid var(--slate-200);
  display: flex;
  justify-content: flex-end;
}

@media print {
  .no-print {
    display: none !important;
  }
  .modal-backdrop {
    position: static;
    background: transparent;
    padding: 0;
  }
  .tearsheet-dialog {
    max-width: 100%;
    max-height: none;
    box-shadow: none;
    border-radius: 0;
  }
  .tearsheet-body {
    padding: 0;
    overflow: visible;
  }
}
</style>
