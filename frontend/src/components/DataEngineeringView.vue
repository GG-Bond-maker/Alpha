<template>
  <div class="engineering-container">
    <!-- 顶部概览与任务状态横幅 -->
    <div class="banner-card">
      <div class="banner-header">
        <div class="banner-title-box">
          <div class="banner-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>
          </div>
          <div>
            <div class="banner-engine-title">实时任务调度与执行引擎</div>
            <p class="banner-sub">
              支持日频行情更新、训练期时序比较与 LightGBM 推荐模型重训
            </p>
          </div>
        </div>

        <div class="task-badge-box">
          <div class="status-indicator" :class="taskState.status">
            <span class="dot"></span>
            <span class="status-text">{{ statusLabel }}</span>
          </div>
          <button class="btn btn-outline btn-sm" @click="fetchStatus" :disabled="loadingStatus">
            {{ loadingStatus ? '刷新中...' : '刷新状态' }}
          </button>
        </div>
      </div>

      <!-- 执行中的进度条动画 -->
      <div v-if="taskState.status === 'running'" class="running-progress-wrap">
        <div class="progress-info">
          <span class="progress-step">{{ taskState.current_step }}</span>
          <span class="progress-pct">{{ taskState.progress }}%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" :style="{ width: taskState.progress + '%' }"></div>
        </div>
      </div>

      <!-- 执行成功快捷通知 -->
      <div v-else-if="taskState.status === 'completed'" class="completed-alert">
        <span>最近任务已顺利执行完毕！({{ taskState.end_time }}) 最新预测数据已热加载并就绪。</span>
        <div class="alert-actions">
          <button class="btn btn-primary btn-xs" @click="$emit('switchTab', 'recommend')">查看最新推荐</button>
          <button class="btn btn-outline btn-xs" @click="$emit('switchTab', 'kline')">查看走势分析</button>
        </div>
      </div>

      <!-- 执行失败报警 -->
      <div v-else-if="taskState.status === 'failed'" class="failed-alert">
        <span>任务执行遇到异常: {{ taskState.error_msg }}</span>
      </div>
    </div>

    <!-- 4 个核心系统指标卡片 -->
    <div class="stats-row">
      <div class="metric-card">
        <div class="m-icon" style="background: #eff6ff; color: #2563eb;">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
        </div>
        <div class="m-content">
          <div class="m-label">行情数据缓存状态</div>
          <div class="m-val">{{ dataInfo.cache_file_count || 0 }} 只标的</div>
          <div class="m-sub">
            磁盘占用: {{ dataInfo.total_cache_size_mb || 0 }} MB | 最新: {{ dataInfo.latest_trade_date || '最新交易日' }}
          </div>
        </div>
      </div>

      <div class="metric-card">
        <div class="m-icon" style="background: #f0fdf4; color: #16a34a;">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="12" rx="2"></rect><line x1="2" y1="20" x2="22" y2="20"></line></svg>
        </div>
        <div class="m-content">
          <div class="m-label">LightGBM 推荐模型</div>
          <div class="m-val">{{ modelInfo.market_model?.version || 'v2.0' }}</div>
          <div class="m-sub">
            最后训练: {{ modelInfo.market_model?.last_trained || '已就绪' }}
          </div>
        </div>
      </div>

      <div class="metric-card">
        <div class="m-icon" style="background: #fefce8; color: #ca8a04;">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
        </div>
        <div class="m-content">
          <div class="m-label">离线验证集精度</div>
          <div class="m-val">AUC {{ formatMetric(modelInfo.market_model?.metrics?.auc) }}</div>
          <div class="m-sub">
            NDCG@10: {{ formatMetric(modelInfo.market_model?.metrics?.ndcg_at_10) }} | 准确率: {{ formatPercent(modelInfo.market_model?.metrics?.accuracy) }}%
          </div>
        </div>
      </div>

      <div class="metric-card">
        <div class="m-icon" style="background: #faf5ff; color: #9333ea;">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
        </div>
        <div class="m-content">
          <div class="m-label">盘后自动更新策略</div>
          <div class="m-val">{{ scheduleConfig.enabled ? (schedulerStatus.active ? '执行器运行中' : '执行器未启动') : '已暂停' }}</div>
          <div class="m-sub">
            {{ scheduleConfig.cron_time }} 交易日执行 ({{ scheduleConfig.sync_prediction ? '同步预测' : '仅拉取' }})
          </div>
        </div>
      </div>
    </div>

    <!-- 主操作区网格 -->
    <div class="pipeline-grid">
      <!-- 模块 1: 数据更新管道 -->
      <div class="card panel-card">
        <div class="panel-header">
          <div class="ph-title">
            <h3>数据更新 (Data Pipeline)</h3>
          </div>
          <span class="badge badge-blue">日频数据实时摄取</span>
        </div>

        <div class="panel-body">
          <div class="tip-box info">
            <span class="tip-tag">TIP</span>
            <div class="tip-content">
              <strong>业务提示：</strong> 股票数据实时变化，建议每个交易日收盘后运行程序以拉取最新日K线、更新技术指标并获取最新预测结果。
            </div>
          </div>

          <div class="config-form">
            <label class="checkbox-option">
              <input type="checkbox" v-model="dataUpdateForm.force_refresh" />
              <div>
                <strong>强制重新拉取沪深300行情数据</strong>
                <p class="desc">忽略本地历史缓存，为沪深300当前成分股重新同步日线行情与前复权因子</p>
              </div>
            </label>

            <label class="checkbox-option">
              <input type="checkbox" v-model="dataUpdateForm.sync_recommendations" />
              <div>
                <strong>数据更新后自动运行预测并导出 Excel</strong>
                <p class="desc">自动为沪深300当前成分股打分排序，刷新推荐列表并生成带日期的 Excel 报表</p>
              </div>
            </label>
          </div>

          <div class="action-btn-row">
            <button 
              class="btn btn-primary" 
              @click="handleTriggerDataUpdate" 
              :disabled="taskState.status === 'running'"
            >
              {{ taskState.status === 'running' && taskState.task_type === 'data_update' ? '正在更新数据...' : '立即执行数据更新与预测' }}
            </button>
          </div>

          <!-- 定时调度快捷设置 -->
          <div class="sub-schedule-section">
            <div class="sub-title">盘后自动化更新调度（北京时间）：</div>
            <p v-if="scheduleError" role="alert" class="text-neg">{{ scheduleError }}</p>
            <p v-if="schedulerStatus.error" role="status">{{ schedulerStatus.error }}</p>
            <div class="schedule-inputs">
              <label class="switch-label">
                <input type="checkbox" v-model="scheduleConfig.enabled" @change="handleSaveSchedule" />
                <span>启用自动更新</span>
              </label>
              <div class="input-inline">
                <span>执行时间：</span>
                <input 
                  type="time" 
                  v-model="scheduleConfig.cron_time" 
                  class="time-control" 
                  @change="handleSaveSchedule"
                />
              </div>
              <span class="hint-small">建议设定为交易日 15:35 之后（交易所收盘清算完成）</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 模块 2: 模型更新与重训 -->
      <div class="card panel-card">
        <div class="panel-header">
          <div class="ph-title">
            <h3>模型训练与寻优 (Model Training)</h3>
          </div>
          <span class="badge badge-gold">LightGBM + TreeSHAP</span>
        </div>

        <div class="panel-body">
          <div class="tip-box highlight">
            <span class="tip-tag">RULE</span>
            <div class="tip-content">
              <strong>模型重训规则：</strong> 默认在训练期内比较有限候选方案。验证集用于概率校准，测试集用于复核；完成检查后更新 LightGBM 与 TreeSHAP。
            </div>
          </div>

          <div class="config-form">
            <label class="checkbox-option">
              <input type="checkbox" v-model="modelTrainForm.force_retrain" />
              <div>
                <strong class="text-strong-gold">强制重新训练模型 (force_retrain=True)</strong>
                <p class="desc">重新构建训练批次；模型只拟合训练区间，失败时保留当前批次。</p>
              </div>
            </label>

            <label class="checkbox-option">
              <span>训练方案</span>
              <select v-model="modelTrainForm.scheme" class="form-select" aria-label="训练方案">
                <option value="robust">固定候选时序比较（推荐）</option>
                <option value="legacy">旧版 Optuna 搜索</option>
              </select>
            </label>
            <p class="desc" v-if="modelTrainForm.scheme === 'robust'">比较浅树、量价特征与滚动窗口；每折只用过去数据筛选特征，不保证 AUC 提升。</p>

            <label v-if="modelTrainForm.scheme === 'legacy'" class="checkbox-option">
              <input type="checkbox" v-model="modelTrainForm.use_optuna" />
              <div>
                <strong>开启 Optuna 贝叶斯超参数自动寻优</strong>
                <p class="desc">仅在训练期内搜索树深度、学习率和正则化参数；更多试验可能增加选择偏差。</p>
              </div>
            </label>

            <div v-if="modelTrainForm.scheme === 'legacy' && modelTrainForm.use_optuna" class="slider-row">
              <div class="slider-label">
                <span>Optuna 优化试验轮数 (n_trials):</span>
                <strong>{{ modelTrainForm.n_trials }} 轮</strong>
              </div>
              <input 
                type="range" 
                v-model.number="modelTrainForm.n_trials" 
                min="5" 
                max="40" 
                step="5" 
                class="range-control"
              />
            </div>

            <p class="desc">所有候选股票使用同一个截面 LightGBM 模型，以统一口径比较预测与特征归因。</p>
          </div>

          <div class="action-btn-row">
            <button 
              class="btn btn-gold" 
              @click="handleTriggerModelTrain" 
              :disabled="taskState.status === 'running'"
            >
              {{ taskState.status === 'running' && taskState.task_type === 'model_train' ? '正在重训模型中...' : '开始训练 LightGBM 模型' }}
            </button>
          </div>

          <!-- 当前模型超参数一览 -->
          <div class="sub-schedule-section">
            <div class="sub-title">当前批次模型参数：</div>
            <div class="param-tags">
              <span class="param-tag">树数量: {{ modelInfo.market_model?.best_params?.n_estimators ?? '—' }}</span>
              <span class="param-tag">学习率: {{ modelInfo.market_model?.best_params?.learning_rate ?? '—' }}</span>
              <span class="param-tag">最大深度: {{ modelInfo.market_model?.best_params?.max_depth ?? '—' }}</span>
              <span class="param-tag">样本采样: {{ modelInfo.market_model?.best_params?.subsample ?? '—' }}</span>
              <span class="param-tag">特征采样: {{ modelInfo.market_model?.best_params?.colsample_bytree ?? '—' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 模块 3: 特征工程与缓存治理卡片 -->
    <div class="card cache-feature-card">
      <div class="cf-left">
        <h4>特征工程与标的库治理</h4>
        <p class="cf-desc">
          基础技术指标缓存包含 <strong>{{ dataInfo.feature_count ?? '—' }} 项</strong>。模型实际使用的量价因子以当前训练批次与因子检验页为准。
        </p>
        <div class="feature-pills">
          <span v-for="feat in (dataInfo.feature_list || []).slice(0, 12)" :key="feat" class="feature-pill">{{ feat }}</span>
          <span v-if="(dataInfo.feature_list || []).length > 12" class="feature-pill more">+{{ dataInfo.feature_list.length - 12 }} 更多</span>
        </div>
      </div>

      <div class="cf-right">
        <button class="btn btn-outline btn-sm" @click="handleClearCache('data')" title="清空已下载的历史行情CSV缓存">
          清理行情数据缓存
        </button>
        <button class="btn btn-outline btn-sm" @click="handleClearCache('models')" title="清理单股临时模型文件">
          清理个股临时模型
        </button>
      </div>
    </div>

    <!-- 模块 3.5: 特征与模型稳定性监控 (ML4T PSI Drift Monitor) -->
    <div class="card drift-card">
      <div class="drift-header">
        <div class="drift-title-group">
          <div class="drift-title">
            <span class="drift-icon">🔬</span>
            <h3>特征与模型漂移监控 (ML4T Population Stability Index, PSI)</h3>
          </div>
          <p class="drift-sub">
            依据《Machine Learning for Algorithmic Trading》第 9、26 章规范：以模型训练集分布为基准，量化检验测试集/近期窗口的群体稳定性指数 (PSI) 与双样本 KS 检验，防范非平稳性数据漂移造成实盘下行风险。
          </p>
        </div>
        <div class="drift-actions">
          <div v-if="driftReport" class="drift-badge" :class="'drift-' + (driftReport.overall_status || 'HEALTHY').toLowerCase()">
            {{ driftReport.overall_label }}
          </div>
          <button class="btn btn-outline btn-sm" :disabled="loadingDrift" @click="handleRefreshDrift">
            {{ loadingDrift ? '检测计算中...' : '重新检测 PSI' }}
          </button>
        </div>
      </div>

      <div v-if="loadingDrift && !driftReport" class="drift-loading">
        <div class="spinner"></div>
        <span>正在执行双样本 KS 检验与分箱 PSI 积分计算...</span>
      </div>

      <div v-else-if="driftReport" class="drift-body">
        <!-- 核心统计概览条 -->
        <div class="drift-stats-grid">
          <div class="drift-stat-pill">
            <span class="lbl">训练集基准样本</span>
            <strong class="val">{{ driftReport.train_samples?.toLocaleString() }} 条</strong>
          </div>
          <div class="drift-stat-pill">
            <span class="lbl">测试监控样本</span>
            <strong class="val">{{ driftReport.test_samples?.toLocaleString() }} 条</strong>
          </div>
          <div class="drift-stat-pill">
            <span class="lbl">特征最大 PSI</span>
            <strong class="val" :class="driftReport.max_feature_psi < 0.10 ? 'text-pos' : 'text-neg'">
              {{ driftReport.max_feature_psi }}
            </strong>
          </div>
          <div class="drift-stat-pill" v-if="driftReport.prediction_drift">
            <span class="lbl">预测概率分布 PSI</span>
            <strong class="val text-pos">{{ driftReport.prediction_drift.psi }} ({{ driftReport.prediction_drift.status_label }})</strong>
          </div>
          <div class="drift-stat-pill" v-if="driftReport.target_drift">
            <span class="lbl">目标收益分布 PSI</span>
            <strong class="val text-pos">{{ driftReport.target_drift.psi }} ({{ driftReport.target_drift.status_label }})</strong>
          </div>
        </div>

        <div class="drift-summary-text">
          <span class="summary-prefix">监控结论：</span>{{ driftReport.summary_desc }}
        </div>

        <!-- 详细特征稳定性矩阵表 -->
        <div class="table-wrap" style="margin-top: 14px;">
          <table>
            <thead>
              <tr>
                <th>特征指标</th>
                <th>业务维度</th>
                <th>入模状态</th>
                <th>基准均值 ± 标准差</th>
                <th>当前均值 ± 标准差</th>
                <th>群体稳定性指数 (PSI)</th>
                <th>双样本 KS 检验</th>
                <th style="text-align: center;">漂移诊断</th>
                <th>运维建议</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="feat in (driftReport.features || [])" :key="feat.feature">
                <td>
                  <strong>{{ feat.name_cn }}</strong>
                  <div class="feat-code">{{ feat.feature }}</div>
                </td>
                <td><span class="badge-subtle">{{ feat.category }}</span></td>
                <td>
                  <span v-if="feat.is_model_input" class="tag-input-feat">核心特征</span>
                  <span v-else class="tag-pool-feat">池级指标</span>
                </td>
                <td>{{ feat.ref_mean.toFixed(3) }} <span class="sub-std">±{{ feat.ref_std.toFixed(3) }}</span></td>
                <td>{{ feat.cur_mean.toFixed(3) }} <span class="sub-std">±{{ feat.cur_std.toFixed(3) }}</span></td>
                <td>
                  <strong :class="feat.psi < 0.10 ? 'text-pos' : feat.psi < 0.20 ? 'text-warn' : 'text-neg'">
                    {{ feat.psi.toFixed(4) }}
                  </strong>
                </td>
                <td>
                  <div class="ks-val">D = {{ feat.ks_stat.toFixed(3) }}</div>
                  <div class="ks-p">p = {{ feat.ks_pvalue_fmt }}</div>
                </td>
                <td style="text-align: center;">
                  <span class="status-pill" :class="'pill-' + feat.status.toLowerCase()">
                    {{ feat.status_label }}
                  </span>
                </td>
                <td><span class="action-desc">{{ feat.action }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="drift-footnote">
          <strong>PSI 判定标准：</strong>
          PSI 分级阈值：&lt; 0.10、0.10 ~ 0.20、&ge; 0.20。分布差异不能直接推断预测能力、市场状态或重训收益，应结合样本外表现判断。
        </div>
      </div>
    </div>

    <!-- 模块 4: 实时工程执行终端 (Terminal Console) -->
    <div class="terminal-card">
      <div class="terminal-header">
        <div class="terminal-controls">
          <span class="ctrl-dot red"></span>
          <span class="ctrl-dot yellow"></span>
          <span class="ctrl-dot green"></span>
          <span class="term-title">terminal — Data & Model Pipeline Execution Console (实时日志流)</span>
        </div>
        <div class="terminal-actions">
          <label class="auto-scroll-label">
            <input type="checkbox" v-model="autoScroll" />
            <span>自动滚动</span>
          </label>
          <button class="term-btn" @click="fetchLogs" title="立即刷新日志">刷新</button>
          <button class="term-btn" @click="handleClearLogs" title="清空日志输出">清屏</button>
        </div>
      </div>

      <div ref="terminalBodyRef" class="terminal-body">
        <div v-if="logs.length === 0" class="term-empty">
          <span class="term-dim">等待执行指令中... 终端处于监听状态。</span>
        </div>
        <div v-for="(log, idx) in logs" :key="idx" class="term-line">
          <span class="term-time">[{{ (log.time || '').includes(' ') ? log.time.split(' ')[1] : (log.time || '--') }}]</span>
          <span class="term-level" :class="log.level">[{{ log.level }}]</span>
          <span class="term-msg">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { api } from '../api'

defineEmits(['switchTab'])

// 状态与指标
const loadingStatus = ref(false)
const taskState = ref({
  status: 'idle',
  task_type: null,
  progress: 0,
  current_step: '系统就绪',
  start_time: null,
  end_time: null,
  error_msg: null
})

const dataInfo = ref({})
const modelInfo = ref({})
const schedulerStatus = ref({})
const formatMetric = (v) => v == null ? '—' : Number(v).toFixed(4)
const formatPercent = (v) => v == null ? '—' : (v * 100).toFixed(1)
const scheduleError = ref('')
const scheduleConfig = ref({
  enabled: false,
  cron_time: '15:35',
  sync_prediction: true
})

// 数据更新表单
const dataUpdateForm = ref({
  force_refresh: false,
  sync_recommendations: true
})

// 模型训练表单
const modelTrainForm = ref({
  scheme: 'robust',
  force_retrain: true,
  use_optuna: true,
  n_trials: 15,
  retrain_single_models: false
})

// 日志与终端
const logs = ref([])
const autoScroll = ref(true)
const terminalBodyRef = ref(null)

let pollTimer = null

const statusLabel = computed(() => {
  switch (taskState.value.status) {
    case 'running': return '正在后台执行...'
    case 'completed': return '就绪 (最近任务已完成)'
    case 'failed': return '异常中止'
    default: return '空闲 (随时可启动)'
  }
})

// 加载全量状态
const fetchStatus = async () => {
  loadingStatus.value = true
  try {
    const res = await api.getEngineeringStatus()
    taskState.value = res.data.task_state || {}
    dataInfo.value = res.data.data_engineering || {}
    modelInfo.value = res.data.model_lifecycle || {}
    scheduleConfig.value = res.data.schedule || {}
    schedulerStatus.value = res.data.scheduler || {}
  } catch (err) {
    console.error('获取数据工程状态失败:', err)
  } finally {
    loadingStatus.value = false
  }
}

// 加载日志
const fetchLogs = async () => {
  try {
    const res = await api.getEngineeringLogs(150)
    logs.value = res.data.logs || []
    if (autoScroll.value) {
      await nextTick()
      scrollToBottom()
    }
  } catch (err) {
    console.error('获取工程日志失败:', err)
  }
}

const scrollToBottom = () => {
  if (terminalBodyRef.value) {
    terminalBodyRef.value.scrollTop = terminalBodyRef.value.scrollHeight
  }
}

// 触发数据更新
const handleTriggerDataUpdate = async () => {
  try {
    await api.triggerDataUpdate(dataUpdateForm.value)
    await fetchStatus()
    await fetchLogs()
    startPolling()
  } catch (err) {
    alert('启动数据更新失败: ' + (err.response?.data?.detail || err.message))
  }
}

// 触发模型重训
const handleTriggerModelTrain = async () => {
  try {
    await api.triggerModelTrain(modelTrainForm.value)
    await fetchStatus()
    await fetchLogs()
    startPolling()
  } catch (err) {
    alert('启动模型重训失败: ' + (err.response?.data?.detail || err.message))
  }
}

// 保存自动调度设置
const handleSaveSchedule = async () => {
  try {
    scheduleError.value = ''
    await api.updateScheduleConfig(scheduleConfig.value)
    await fetchStatus()
  } catch (err) {
    scheduleError.value = '保存失败，请检查时间格式或服务连接。'
    await fetchStatus()
  }
}

// 清理缓存
const handleClearCache = async (target) => {
  if (!confirm(`确定清理本地 ${target === 'data' ? '历史行情' : '临时模型'} 缓存文件吗？`)) return
  try {
    const res = await api.clearEngineeringCache(target)
    alert(res.data.message)
    await fetchStatus()
    await fetchLogs()
  } catch (err) {
    alert('清理缓存失败: ' + err.message)
  }
}

// 清空日志
const handleClearLogs = async () => {
  try {
    await api.clearEngineeringLogs()
    logs.value = []
  } catch (err) {
    console.error('清空日志失败:', err)
  }
}

// 定时轮询器（当有任务运行或刚启动时以 1.5s 频率刷新）
const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(async () => {
    await fetchStatus()
    await fetchLogs()
    if (taskState.value.status !== 'running') {
      stopPolling()
    }
  }, 1500)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 特征与模型漂移监控 (ML4T PSI Drift)
const driftReport = ref(null)
const loadingDrift = ref(false)

const fetchDrift = async () => {
  loadingDrift.value = true
  try {
    const res = await api.getDriftStatus()
    driftReport.value = res.data
  } catch (err) {
    console.error('获取特征漂移监控报告失败:', err)
  } finally {
    loadingDrift.value = false
  }
}

const handleRefreshDrift = async () => {
  loadingDrift.value = true
  try {
    const res = await api.refreshDriftStatus()
    driftReport.value = res.data.report || res.data
  } catch (err) {
    alert('刷新漂移监控失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    loadingDrift.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    fetchStatus(),
    fetchLogs(),
    fetchDrift()
  ])
  if (taskState.value.status === 'running') {
    startPolling()
  }
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.engineering-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 顶部状态大横幅 */
.banner-card {
  background: #ffffff;
  border-radius: var(--radius-lg);
  border: 1px solid var(--slate-200);
  box-shadow: var(--shadow-sm);
  padding: 22px 26px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.banner-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.banner-title-box {
  display: flex;
  align-items: center;
  gap: 14px;
}

.banner-icon {
  font-size: 34px;
  width: 52px;
  height: 52px;
  background: #f1f5f9;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.banner-engine-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--slate-900);
}

.banner-sub {
  font-size: 13px;
  color: var(--slate-600);
  margin-top: 3px;
}

.task-badge-box {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
}

.status-indicator.idle {
  background: #f1f5f9;
  color: #475569;
}
.status-indicator.idle .dot { background: #94a3b8; }

.status-indicator.running {
  background: #eff6ff;
  color: #1d4ed8;
  animation: pulse 1.5s infinite;
}
.status-indicator.running .dot { background: #2563eb; }

.status-indicator.completed {
  background: #f0fdf4;
  color: #15803d;
}
.status-indicator.completed .dot { background: #16a34a; }

.status-indicator.failed {
  background: #fef2f2;
  color: #b91c1c;
}
.status-indicator.failed .dot { background: #dc2626; }

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

@keyframes pulse {
  0% { opacity: 0.8; }
  50% { opacity: 1; }
  100% { opacity: 0.8; }
}

/* 运行进度条 */
.running-progress-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #f8fafc;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  border: 1px solid #bfdbfe;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: #1e3a8a;
}

.progress-bar-bg {
  width: 100%;
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #10b981);
  transition: width 0.3s ease;
}

.completed-alert {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  padding: 10px 16px;
  border-radius: var(--radius-md);
  font-size: 13px;
  color: #065f46;
  font-weight: 500;
}

.alert-actions {
  display: flex;
  gap: 8px;
}

.btn-xs {
  padding: 3px 10px;
  font-size: 12px;
}

.failed-alert {
  background: #fef2f2;
  border: 1px solid #fecaca;
  padding: 10px 16px;
  border-radius: var(--radius-md);
  font-size: 13px;
  color: #991b1b;
}

/* 4 格统计指标 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.metric-card {
  background: #ffffff;
  border-radius: var(--radius-lg);
  border: 1px solid var(--slate-200);
  box-shadow: var(--shadow-sm);
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.m-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.m-label {
  font-size: 12px;
  color: var(--slate-500);
  font-weight: 500;
}

.m-val {
  font-size: 18px;
  font-weight: 700;
  color: var(--slate-900);
  margin: 2px 0;
}

.m-sub {
  font-size: 11px;
  color: var(--slate-500);
}

/* 两个核心操作面板网格 */
.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 20px;
}

.panel-card {
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--slate-100);
}

.ph-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ph-title h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--slate-900);
}

.panel-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
}

/* 提示卡片 */
.tip-box {
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  font-size: 13px;
  line-height: 1.5;
}

.tip-box.info {
  background: #eff6ff;
  border: 1px solid #dbeafe;
  color: #1e40af;
}

.tip-box.highlight {
  background: #fffbeb;
  border: 1px solid #fef3c7;
  color: #92400e;
}

.tip-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.checkbox-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
  padding: 10px 12px;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  transition: background 0.2s;
}

.checkbox-option:hover {
  background: var(--slate-50);
}

.checkbox-option input {
  margin-top: 3px;
  width: 16px;
  height: 16px;
}

.checkbox-option strong {
  font-size: 14px;
  color: var(--slate-800);
}

.text-strong-gold {
  color: #b45309;
}

.checkbox-option .desc {
  font-size: 12px;
  color: var(--slate-500);
  margin-top: 2px;
}

.slider-row {
  background: #f8fafc;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--slate-200);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.slider-label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--slate-700);
}

.range-control {
  width: 100%;
}

.action-btn-row {
  margin-top: 4px;
}

.action-btn-row .btn {
  width: 100%;
  padding: 12px;
  font-size: 15px;
  font-weight: 600;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
}

.btn-gold {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  color: #ffffff;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-gold:hover:not(:disabled) {
  background: linear-gradient(135deg, #d97706, #b45309);
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
}

.sub-schedule-section {
  border-top: 1px dashed var(--slate-200);
  padding-top: 14px;
  margin-top: 4px;
}

.sub-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--slate-700);
  margin-bottom: 8px;
}

.schedule-inputs {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.switch-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--slate-700);
  cursor: pointer;
}

.input-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--slate-600);
}

.time-control {
  padding: 4px 8px;
  border: 1px solid var(--slate-300);
  border-radius: 4px;
  font-size: 13px;
}

.hint-small {
  font-size: 12px;
  color: var(--slate-400);
}

.param-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.param-tag {
  background: #f1f5f9;
  border: 1px solid var(--slate-200);
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--slate-700);
  font-family: monospace;
}

/* 特征与缓存治理卡片 */
.cache-feature-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 18px 24px;
}

.cf-left h4 {
  font-size: 15px;
  font-weight: 700;
  color: var(--slate-900);
}

.cf-desc {
  font-size: 13px;
  color: var(--slate-600);
  margin: 4px 0 8px 0;
}

.feature-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.feature-pill {
  background: #f8fafc;
  border: 1px solid var(--slate-200);
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--slate-700);
  font-family: monospace;
}

.feature-pill.more {
  background: #e2e8f0;
  font-weight: 600;
}

.cf-right {
  display: flex;
  gap: 10px;
}

/* 终端控制台卡片 */
.terminal-card {
  background: #0f172a;
  border-radius: var(--radius-lg);
  border: 1px solid #334155;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.terminal-header {
  background: #1e293b;
  padding: 10px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #334155;
}

.terminal-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ctrl-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.ctrl-dot.red { background: #ef4444; }
.ctrl-dot.yellow { background: #f59e0b; }
.ctrl-dot.green { background: #10b981; }

.term-title {
  color: #94a3b8;
  font-size: 12px;
  font-family: monospace;
  margin-left: 6px;
}

.terminal-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.auto-scroll-label {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #94a3b8;
  font-size: 12px;
  cursor: pointer;
}

.term-btn {
  background: #334155;
  color: #f8fafc;
  border: none;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.term-btn:hover {
  background: #475569;
}

.terminal-body {
  height: 280px;
  overflow-y: auto;
  padding: 14px 18px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 12.5px;
  line-height: 1.6;
  color: #f8fafc;
  background: #090d16;
}

.term-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.term-dim {
  color: #475569;
}

.term-line {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
  word-break: break-all;
}

.term-time {
  color: #64748b;
  flex-shrink: 0;
}

.term-level {
  font-weight: 700;
  flex-shrink: 0;
}

.term-level.INFO { color: #38bdf8; }
.term-level.SUCCESS { color: #4ade80; }
.term-level.TRAIN { color: #facc15; }
.term-level.WARNING { color: #fb923c; }
.term-level.ERROR { color: #f87171; }

.term-msg {
  color: #e2e8f0;
}

/* 特征与模型漂移监控卡片 (ML4T PSI Drift) */
.drift-card {
  padding: 20px 24px;
  background: #ffffff;
  border-radius: var(--radius-lg, 8px);
  border: 1px solid var(--slate-200, #e2e8f0);
}

.drift-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.drift-title-group {
  flex: 1;
}

.drift-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.drift-title h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--slate-800, #1e293b);
  margin: 0;
}

.drift-icon {
  font-size: 18px;
}

.drift-sub {
  font-size: 13px;
  color: var(--slate-500, #64748b);
  margin-top: 4px;
  line-height: 1.5;
}

.drift-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}

.drift-badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.drift-badge.drift-healthy {
  background: #ecfdf5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}

.drift-badge.drift-warning {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}

.drift-badge.drift-critical {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.drift-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px;
  color: var(--slate-500);
  font-size: 13px;
  justify-content: center;
}

.drift-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.drift-stat-pill {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 10px 14px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.drift-stat-pill .lbl {
  font-size: 11px;
  color: #64748b;
}

.drift-stat-pill .val {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.drift-summary-text {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  margin-top: 14px;
  line-height: 1.5;
}

.summary-prefix {
  font-weight: 700;
}

.feat-code {
  font-family: monospace;
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

.tag-input-feat {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.tag-pool-feat {
  background: #f1f5f9;
  color: #475569;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.sub-std {
  font-size: 11px;
  color: #94a3b8;
}

.ks-val {
  font-size: 12px;
  font-weight: 600;
  color: #1e293b;
}

.ks-p {
  font-size: 11px;
  color: #64748b;
}

.status-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.status-pill.pill-stable {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
}

.status-pill.pill-moderate {
  background: #fffbeb;
  color: #b45309;
  border: 1px solid #fde68a;
}

.status-pill.pill-significant {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}

.action-desc {
  font-size: 12px;
  color: #334155;
}

.drift-footnote {
  font-size: 11px;
  color: #64748b;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #f1f5f9;
  line-height: 1.5;
}
</style>
