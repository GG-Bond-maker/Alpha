import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

export const api = {
  // 获取截面日期列表
  getDates() {
    return apiClient.get('/recommend/dates')
  },
  
  // 获取 Top-K 推荐股票列表
  getTopK(date, k = 10, industry = null, board = null) {
    const params = { k }
    if (date) params.date = date
    if (industry && industry !== '全部') params.industry = industry
    if (board && board !== '全部') params.board = board
    return apiClient.get('/recommend/topk', { params })
  },
  
  // 获取个股 SHAP 局部归因与诊断理由
  getStockExplanation(stockCode, date) {
    const params = {}
    if (date) params.date = date
    return apiClient.get(`/explain/local/${stockCode}`, { params })
  },
  
  // 获取全局特征重要性
  getGlobalImportance() {
    return apiClient.get('/explain/global')
  },
  
  // 获取模型评测指标对比
  getEvaluationMetrics() {
    return apiClient.get('/evaluation/metrics')
  },

  // 导出 Excel 选股推荐报表
  exportExcel() {
    window.open('/api/v1/recommend/export_excel', '_blank')
  },

  // 获取板块列表 (主板、创业板、科创板、北交所)
  getStockBoards() {
    return apiClient.get('/stock/boards')
  },

  // 获取可选全板块股票池列表
  getStockPool(board = null) {
    const params = {}
    if (board && board !== '全部') params.board = board
    return apiClient.get('/stock/pool', { params })
  },

  // 兼容别名
  getMainBoardPool() {
    return apiClient.get('/stock/pool')
  },

  // 获取主板股票 K 线图与均线走势数据 (默认 10~15 年跨度，约 3800 根K线)
  getStockKline(code, limit = 3800) {
    return apiClient.get(`/stock/kline/${code}`, { params: { limit } })
  },

  // 获取 LightGBM 推荐系统首页全局概览数据
  getOverviewStats() {
    return apiClient.get('/stock/overview/stats')
  },

  // 获取主板股票池及推荐状态管理列表
  getStockManageList(params = {}) {
    return apiClient.get('/stock/manage/list', { params })
  },

  // 切换主板股票重点关注状态
  toggleFavorite(code) {
    return apiClient.post('/stock/manage/toggle_favorite', { code })
  },

  // 获取数据工程与模型生命周期全景状态
  getEngineeringStatus() {
    return apiClient.get('/engineering/status')
  },

  // 触发数据更新与最新预测
  triggerDataUpdate(payload = { force_refresh: false, sync_recommendations: true }) {
    return apiClient.post('/engineering/data/update', payload)
  },

  // 触发 LightGBM 模型重新训练 (force_retrain 与 Optuna)
  triggerModelTrain(payload = { force_retrain: true, use_optuna: true, n_trials: 15, retrain_single_models: false }) {
    return apiClient.post('/engineering/model/train', payload)
  },

  // 获取实时控制台日志
  getEngineeringLogs(limit = 100) {
    return apiClient.get('/engineering/logs', { params: { limit } })
  },

  // 清空控制台日志
  clearEngineeringLogs() {
    return apiClient.post('/engineering/logs/clear')
  },

  // 获取自动调度配置
  getScheduleConfig() {
    return apiClient.get('/engineering/schedule')
  },

  // 更新自动调度配置
  updateScheduleConfig(config) {
    return apiClient.post('/engineering/schedule', config)
  },

  // 清理缓存
  clearEngineeringCache(target = 'data') {
    return apiClient.post('/engineering/cache/clear', { target })
  }
}
