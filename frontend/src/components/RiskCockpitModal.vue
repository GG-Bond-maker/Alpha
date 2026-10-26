<template>
  <div v-if="visible" class="modal-backdrop" @click.self="close">
    <div class="modal-dialog risk-modal">
      <div class="modal-header">
        <div class="header-left">
          <div class="modal-icon-shield">🛡️</div>
          <div>
            <div class="modal-title">推荐风险筛查与手动熔断</div>
            <div class="modal-subtitle">推荐等权假设下的集中度筛查 · 未接入真实持仓风险</div>
          </div>
        </div>
        <button class="modal-close" @click="close">×</button>
      </div>

      <div class="modal-body">
        <!-- 实时状态横幅 -->
        <div class="status-banner" :class="isTriggered ? 'is-halted' : 'is-healthy'">
          <div class="banner-icon">{{ isTriggered ? '🚨' : '🟢' }}</div>
          <div class="banner-content">
            <div class="banner-title">
              {{ isTriggered ? '风控系统已触发熔断闭锁 (LATCHED)' : '真实持仓风险未完整评估' }}
            </div>
            <div class="banner-desc">
              {{ statusData?.reason || '等待风险数据，不能判断真实持仓是否安全' }}
            </div>
            <div v-if="statusData?.trigger_time" class="banner-time">
              熔断触发时间: {{ statusData.trigger_time }}
            </div>
          </div>
        </div>

        <!-- 4 大硬编码红线仪表盘 -->
        <div class="cockpit-grid">
          <div class="cockpit-card">
            <div class="card-head">
              <span class="gauge-label">单日亏损预警</span>
              <span class="threshold-tag text-neg">红线 {{ pct(thresholds.max_daily_loss) }}</span>
            </div>
            <div class="gauge-value" :class="gauges.daily_loss <= thresholds.max_daily_loss ? 'text-neg' : ''">
              {{ pct(gauges.daily_loss) }}
            </div>
            <div class="progress-bar-bg">
              <div class="progress-bar-fill" :style="{
                width: Math.min(100, (Math.abs(gauges.daily_loss || 0) / Math.abs(thresholds.max_daily_loss || 0.05)) * 100) + '%',
                background: Math.abs(gauges.daily_loss || 0) > Math.abs(thresholds.max_daily_loss || 0.05) ? '#dc2626' : '#2563eb'
              }"></div>
            </div>
            <div class="gauge-hint">单日净值回落达 5% 立即暂停买入</div>
          </div>

          <div class="cockpit-card">
            <div class="card-head">
              <span class="gauge-label">组合累计最大回撤</span>
              <span class="threshold-tag text-neg">红线 {{ pct(thresholds.max_drawdown) }}</span>
            </div>
            <div class="gauge-value" :class="gauges.drawdown <= thresholds.max_drawdown ? 'text-neg' : ''">
              {{ pct(gauges.drawdown) }}
            </div>
            <div class="progress-bar-bg">
              <div class="progress-bar-fill" :style="{
                width: Math.min(100, (Math.abs(gauges.drawdown || 0) / Math.abs(thresholds.max_drawdown || 0.25)) * 100) + '%',
                background: Math.abs(gauges.drawdown || 0) > Math.abs(thresholds.max_drawdown || 0.25) ? '#dc2626' : '#2563eb'
              }"></div>
            </div>
            <div class="gauge-hint">策略回撤触及 25% 启动底线熔断</div>
          </div>

          <div class="cockpit-card">
            <div class="card-head">
              <span class="gauge-label">单票最大持仓权重</span>
              <span class="threshold-tag">上限 {{ pct(thresholds.max_stock_weight) }}</span>
            </div>
            <div class="gauge-value text-pos">
              {{ pct(gauges.max_stock_weight) }}
            </div>
            <div class="progress-bar-bg">
              <div class="progress-bar-fill" :style="{
                width: Math.min(100, ((gauges.max_stock_weight || 0) / (thresholds.max_stock_weight || 0.2)) * 100) + '%',
                background: '#16a34a'
              }"></div>
            </div>
            <div class="gauge-hint">按当前查询推荐列表等权估算，不代表真实仓位</div>
          </div>

          <div class="cockpit-card">
            <div class="card-head">
              <span class="gauge-label">单行业最高集中度</span>
              <span class="threshold-tag">上限 {{ pct(thresholds.max_sector_concentration) }}</span>
            </div>
            <div class="gauge-value text-pos">
              {{ pct(gauges.max_sector_concentration) }}
            </div>
            <div class="progress-bar-bg">
              <div class="progress-bar-fill" :style="{
                width: Math.min(100, ((gauges.max_sector_concentration || 0) / (thresholds.max_sector_concentration || 0.35)) * 100) + '%',
                background: '#16a34a'
              }"></div>
            </div>
            <div class="gauge-hint">按当前推荐列表行业占比估算，未知行业需另行核验</div>
          </div>
        </div>

        <!-- 操作控制面板 -->
        <div class="action-card">
          <div class="action-header">
            <strong>熔断控制指令</strong>
            <span class="badge badge-silver">手动操作</span>
          </div>

          <div v-if="!isTriggered" class="halt-control">
            <p class="action-tip">如遇突发黑天鹅事件或数据链路异常，可手动触发紧急避险熔断，所有推荐标的将自动转为 HOLD 观望评级：</p>
            <div class="input-action-row">
              <input v-model="haltReason" type="text" class="form-input" placeholder="输入熔断原因（如：突发宏观风险排查）" />
              <button class="btn btn-danger" @click="handleManualTrigger" :disabled="actionLoading">
                {{ actionLoading ? '处理中...' : '🚨 紧急避险熔断' }}
              </button>
            </div>
          </div>

          <div v-else class="reset-control">
            <p class="action-tip text-neg">当前为进程级手动熔断状态。需输入服务端 ALPHA_RISK_RESET_TOKEN 配置的口令后恢复推荐；重启会重置进程状态。</p>
            <div class="input-action-row">
              <input v-model="resetToken" type="password" class="form-input" placeholder="输入服务端配置的解锁口令" />
              <button class="btn btn-primary" @click="handleReset" :disabled="actionLoading">
                {{ actionLoading ? '验证中...' : '🔓 鉴权解锁恢复' }}
              </button>
            </div>
            <div v-if="resetError" class="error-msg">{{ resetError }}</div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-outline" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { api } from '../api'

const props = defineProps({
  visible: Boolean,
  statusData: Object,
})

const emit = defineEmits(['close', 'refresh'])

const haltReason = ref('管理员手动触发紧急避险熔断')
const resetToken = ref('')
const resetError = ref('')
const actionLoading = ref(false)

const isTriggered = computed(() => Boolean(props.statusData?.triggered))
const thresholds = computed(() => props.statusData?.thresholds || {
  max_daily_loss: -0.05,
  max_drawdown: -0.25,
  max_stock_weight: 0.20,
  max_sector_concentration: 0.35,
})
const gauges = computed(() => props.statusData?.gauges || {
  daily_loss: null,
  drawdown: null,
  max_stock_weight: null,
  max_sector_concentration: null,
})

const pct = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%')

const close = () => emit('close')

const handleManualTrigger = async () => {
  actionLoading.value = true
  try {
    await api.triggerRisk(haltReason.value || '手动避险熔断')
    emit('refresh')
  } catch (err) {
    alert('触发熔断失败: ' + err.message)
  } finally {
    actionLoading.value = false
  }
}

const handleReset = async () => {
  actionLoading.value = true
  resetError.value = ''
  try {
    await api.resetRisk(resetToken.value)
    emit('refresh')
  } catch (err) {
    resetError.value = err.response?.data?.detail || err.message || '解锁失败'
  } finally {
    actionLoading.value = false
  }
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.risk-modal {
  width: 100%;
  max-width: 680px;
  background: #ffffff;
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: modalIn 0.2s ease-out;
}

@keyframes modalIn {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}

.modal-header {
  padding: 18px 24px;
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

.modal-icon-shield {
  font-size: 26px;
}

.modal-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--slate-900);
}

.modal-subtitle {
  font-size: 12px;
  color: var(--slate-500);
}

.modal-close {
  background: none;
  border: none;
  font-size: 22px;
  color: var(--slate-400);
  cursor: pointer;
}

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.status-banner {
  padding: 14px 18px;
  border-radius: 8px;
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.status-banner.is-healthy {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
}

.status-banner.is-halted {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.85; }
}

.banner-icon {
  font-size: 24px;
}

.banner-title {
  font-size: 15px;
  font-weight: 700;
}

.banner-desc {
  font-size: 13px;
  margin-top: 4px;
  opacity: 0.9;
}

.banner-time {
  font-size: 11px;
  margin-top: 6px;
  opacity: 0.75;
}

.cockpit-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

.cockpit-card {
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: 8px;
  padding: 12px 14px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.gauge-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--slate-700);
}

.threshold-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--slate-500);
}

.gauge-value {
  font-size: 20px;
  font-weight: 700;
  margin: 6px 0 8px;
  color: var(--slate-900);
}

.progress-bar-bg {
  width: 100%;
  height: 6px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}

.gauge-hint {
  font-size: 11px;
  color: var(--slate-500);
  margin-top: 6px;
}

.action-card {
  background: #ffffff;
  border: 1px solid var(--slate-200);
  border-radius: 8px;
  padding: 14px 16px;
}

.action-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.action-tip {
  font-size: 12px;
  color: var(--slate-600);
  margin-bottom: 10px;
}

.input-action-row {
  display: flex;
  gap: 10px;
}

.input-action-row .form-input {
  flex: 1;
  padding: 7px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
}

.btn-danger {
  background: #dc2626;
  color: #ffffff;
  border: none;
  padding: 7px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.btn-danger:hover {
  background: #b91c1c;
}

.error-msg {
  color: #dc2626;
  font-size: 12px;
  margin-top: 6px;
}

.modal-footer {
  padding: 12px 24px;
  border-top: 1px solid var(--slate-200);
  display: flex;
  justify-content: flex-end;
}
</style>
