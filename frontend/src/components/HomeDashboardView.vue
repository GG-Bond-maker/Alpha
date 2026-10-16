<template>
  <div class="home-dashboard">
    <!-- 顶部欢迎与系统状态横幅 -->
    <div class="welcome-banner">
      <div class="banner-content">
        <div class="banner-badge">LightGBM 股票智能推荐系统 v2.0</div>
        <h2 class="banner-title">A 股全板块智能选股与推荐决策平台</h2>
        <p class="banner-desc">
          全面覆盖中国 A 股全部板块（主板 / 创业板 / 科创板 / 北交所），基于 LightGBM 机器学习模型与 Optuna 贝叶斯超参数优化，结合经典技术指标体系，提供高置信度多头排序推荐与 XAI 可解释性分析。
        </p>
      </div>
      <div class="banner-date">
        <span class="label">当前分析截面</span>
        <strong class="date-val">{{ stats.update_date || '最新交易日' }}</strong>
      </div>
    </div>

    <!-- 4 个核心指标统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon" style="background: #eff6ff; color: #2563eb;">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="12" rx="2"></rect><line x1="2" y1="20" x2="22" y2="20"></line></svg>
        </div>
        <div>
          <div class="stat-label">核心预测模型</div>
          <div class="stat-val">LightGBM</div>
          <div class="stat-sub">Optuna 贝叶斯寻优</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon" style="background: #f0fdf4; color: #16a34a;">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18"></path><path d="M5 21V7l8-4v18"></path><path d="M19 21V11l-6-4"></path></svg>
        </div>
        <div>
          <div class="stat-label">标的覆盖范围</div>
          <div class="stat-val">{{ stats.total_stocks_count || 500 }} 只</div>
          <div class="stat-sub">A 股全板块核心资产池</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon" style="background: #fefce8; color: #ca8a04;">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle></svg>
        </div>
        <div>
          <div class="stat-label">模型离线评测精度</div>
          <div class="stat-val">AUC {{ stats.model_metrics?.auc || '0.715' }}</div>
          <div class="stat-sub">NDCG@10 {{ stats.model_metrics?.ndcg_at_10 || '0.783' }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon" style="background: #fdf2f8; color: #db2777;">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
        </div>
        <div>
          <div class="stat-label">A 级高置信推荐</div>
          <div class="stat-val text-pos">{{ stats.rating_distribution?.A || 0 }} 只</div>
          <div class="stat-sub">看涨概率 ≥ 75%</div>
        </div>
      </div>
    </div>

    <!-- 核心板块：评级分布与重点标的前瞻 -->
    <div class="dashboard-split">
      <!-- 左侧：推荐评级分布环形图 -->
      <div class="card chart-card">
        <div class="card-header">
          <h3>全板块股票推荐评级分布</h3>
          <span class="sub-tip">A/B/C 三级分类体系</span>
        </div>
        <div ref="pieChartRef" style="height: 280px;"></div>
      </div>

      <!-- 右侧：今日重点看涨标的前瞻 -->
      <div class="card picks-card">
        <div class="card-header">
          <h3>重点看涨标的前瞻清单 (Top 5)</h3>
          <span class="sub-tip">按 LightGBM 看涨概率降序排列</span>
        </div>
        <div class="top-picks-list">
          <div 
            v-for="(item, idx) in stats.top_picks" 
            :key="item.stock_code"
            class="pick-row"
          >
            <div class="pick-rank" :class="'rank-' + (idx + 1)">0{{ idx + 1 }}</div>
            <div class="pick-info">
              <strong class="pick-name">{{ item.stock_name }}</strong>
              <div style="display: flex; gap: 4px; align-items: center;">
                <code class="pick-code">{{ item.stock_code }}</code>
                <span v-if="item.board" class="badge" style="font-size: 11px; padding: 1px 4px;">{{ item.board }}</span>
              </div>
            </div>
            <div class="pick-rating">
              <span v-if="item.recommend_rating === 'A'" class="badge-rating-a">评级 A</span>
              <span v-else class="badge-rating-b">评级 B</span>
            </div>
            <div class="pick-prob">
              <div class="prob-num">{{ (((item.probability ?? item.predicted_score ?? 0) * 100)).toFixed(1) }}%</div>
              <div class="prob-bar-bg">
                <div 
                  class="prob-bar-fill" 
                  :style="{ 
                    width: Math.min(100, Math.max(0, ((item.probability ?? item.predicted_score ?? 0) * 100))) + '%',
                    background: item.recommend_rating === 'A' ? '#10b981' : '#f59e0b'
                  }"
                ></div>
              </div>
            </div>
            <div class="pick-actions">
              <button class="btn btn-sm btn-outline" @click="$emit('viewKline', item)">查看走势</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 快捷功能通道导航 -->
    <div class="card shortcuts-card">
      <h3 class="shortcuts-title">核心功能工作台快捷入口</h3>
      <div class="shortcuts-grid">
        <div class="shortcut-box" @click="$emit('switchTab', 'recommend')">
          <div class="sc-title">Top-K 智能推荐</div>
          <div class="sc-desc">截面排序榜单、A/B/C 评级、导出 Excel 报表</div>
        </div>

        <div class="shortcut-box" @click="$emit('switchTab', 'kline')">
          <div class="sc-title">行情走势与技术指标</div>
          <div class="sc-desc">专业日 K 蜡烛图、MA 均线系统与成交量走势</div>
        </div>

        <div class="shortcut-box" @click="$emit('switchTab', 'manage')">
          <div class="sc-title">股票池与标的管理</div>
          <div class="sc-desc">股票池检索、评级筛选与重点关注标的标记</div>
        </div>

        <div class="shortcut-box" @click="$emit('switchTab', 'global')">
          <div class="sc-title">TreeSHAP 归因透视</div>
          <div class="sc-desc">全市场宏观特征重要性与个股可解释诊断</div>
        </div>

        <div class="shortcut-box" @click="$emit('switchTab', 'engineering')">
          <div class="sc-title">数据工程与模型生命周期</div>
          <div class="sc-desc">行情实时数据更新、LightGBM 重训与自动调度</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

defineEmits(['switchTab', 'viewKline'])

const stats = ref({})
const pieChartRef = ref(null)
let pieChart = null

const loadStats = async () => {
  try {
    const res = await api.getOverviewStats()
    stats.value = res.data
    await nextTick()
    renderPieChart(res.data.rating_distribution)
  } catch (err) {
    console.error('加载系统概览统计失败:', err)
  }
}

const renderPieChart = (dist) => {
  if (!pieChartRef.value) return
  if (!pieChart) {
    pieChart = echarts.init(pieChartRef.value)
  }

  const data = [
    { value: dist?.A || 0, name: 'A 级 (高置信看涨)', itemStyle: { color: '#10b981' } },
    { value: dist?.B || 0, name: 'B 级 (中置信看涨)', itemStyle: { color: '#f59e0b' } },
    { value: dist?.C || 0, name: 'C 级 (低置信防守)', itemStyle: { color: '#94a3b8' } }
  ]

  const option = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 只 ({d}%)' },
    legend: { bottom: '5%', left: 'center' },
    series: [
      {
        name: '推荐评级',
        type: 'pie',
        radius: ['45%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: false, position: 'center' },
        emphasis: {
          label: { show: true, fontSize: 16, fontWeight: 'bold' }
        },
        data: data
      }
    ]
  }

  pieChart.setOption(option, true)
}

onMounted(() => {
  loadStats()
})
</script>

<style scoped>
.home-dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.welcome-banner {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  color: #ffffff;
  padding: 28px 32px;
  border-radius: var(--radius-lg);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 20px;
}

.banner-badge {
  display: inline-block;
  background: rgba(59, 130, 246, 0.25);
  border: 1px solid rgba(59, 130, 246, 0.4);
  color: #93c5fd;
  font-size: 13px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 20px;
  margin-bottom: 10px;
}

.banner-title {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 8px;
}

.banner-desc {
  font-size: 14px;
  color: #cbd5e1;
  max-width: 780px;
  line-height: 1.6;
}

.banner-date {
  background: rgba(255, 255, 255, 0.08);
  padding: 16px 20px;
  border-radius: var(--radius-md);
  text-align: right;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.banner-date .label {
  display: block;
  font-size: 12px;
  color: #94a3b8;
}

.banner-date .date-val {
  font-size: 18px;
  color: #38bdf8;
  font-weight: 700;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.stat-card {
  background: #ffffff;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: var(--shadow-sm);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.stat-label {
  font-size: 13px;
  color: var(--slate-600);
}

.stat-val {
  font-size: 20px;
  font-weight: 700;
  color: var(--slate-900);
  margin: 2px 0;
}

.stat-sub {
  font-size: 12px;
  color: var(--slate-600);
}

.dashboard-split {
  display: grid;
  grid-template-columns: 1fr 1.3fr;
  gap: 20px;
}

@media (max-width: 900px) {
  .dashboard-split {
    grid-template-columns: 1fr;
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--slate-100);
  padding-bottom: 10px;
}

.card-header h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--slate-800);
}

.sub-tip {
  font-size: 12px;
  color: var(--slate-600);
}

.top-picks-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pick-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: var(--slate-50);
  border-radius: var(--radius-md);
  border: 1px solid var(--slate-200);
}

.pick-rank {
  font-size: 15px;
  font-weight: 800;
  color: #64748b;
  width: 28px;
}

.pick-rank.rank-1 { color: #eab308; }
.pick-rank.rank-2 { color: #94a3b8; }
.pick-rank.rank-3 { color: #ca8a04; }

.pick-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.pick-name {
  font-size: 14px;
  color: var(--slate-900);
}

.pick-code {
  font-size: 12px;
  color: var(--slate-600);
}

.pick-prob {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.prob-num {
  font-size: 14px;
  font-weight: 700;
  color: var(--primary);
}

.shortcuts-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 16px;
}

.shortcuts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.shortcut-box {
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  padding: 18px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.shortcut-box:hover {
  background: #ffffff;
  border-color: var(--primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.sc-icon {
  font-size: 28px;
  margin-bottom: 8px;
}

.sc-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--slate-900);
  margin-bottom: 4px;
}

.sc-desc {
  font-size: 12px;
  color: var(--slate-600);
  line-height: 1.4;
}
</style>
