<template>
  <div class="stock-manage-container">
    <!-- 控制与筛选面板 -->
    <div class="card filter-panel">
      <div class="filter-header">
        <div>
          <h2>A 股全板块股票池与推荐状态管理</h2>
          <p class="sub-text">展示 LightGBM 对未来 5 个交易日跑赢候选池平均收益的概率估计与排序，支持标记重点跟踪标的</p>
        </div>
        <div class="stats-badge-box">
          <span class="badge badge-blue">全板块资产池: {{ totalCount }} 只</span>
          <span class="badge badge-gold">重点关注: {{ favoriteCount }} 只</span>
        </div>
      </div>

      <div class="filter-controls">
        <!-- 搜索输入框 -->
        <div class="filter-item">
          <label>股票代码/名称：</label>
          <input 
            v-model="searchKeyword" 
            type="text" 
            placeholder="输入代码或名称 (如 600030 或 宁德时代)" 
            class="input-control"
            @input="fetchStocks"
          />
        </div>

        <!-- 板块选择按钮组 -->
        <div class="filter-item board-filter-group">
          <label>股票板块：</label>
          <div class="board-segmented-control">
            <button 
              v-for="b in boardList" 
              :key="b" 
              type="button"
              class="board-btn" 
              :class="{ 
                active: selectedBoard === b,
                'is-main': b === '主板',
                'is-chinext': b === '创业板',
                'is-star': b === '科创板',
                'is-bse': b === '北交所'
              }"
              @click="handleSelectBoard(b)"
            >
              {{ b === '全部' ? '全部板块' : b }}
            </button>
          </div>
        </div>

        <!-- 行业筛选 -->
        <div class="filter-item">
          <label>行业筛选：</label>
          <select v-model="selectedIndustry" class="select-control" @change="fetchStocks">
            <option value="全部">全部行业</option>
            <option v-for="ind in industryList" :key="ind" :value="ind">{{ ind }}</option>
          </select>
        </div>

        <!-- 推荐评级筛选 -->
        <div class="filter-item">
          <label>推荐评级：</label>
          <select v-model="selectedRating" class="select-control" @change="fetchStocks">
            <option value="全部">全部评级</option>
            <option value="A">A 级 (截面前 10%)</option>
            <option value="B">B 级 (随后 20%)</option>
            <option value="C">C 级 (其余标的)</option>
          </select>
        </div>

        <!-- 仅看重点自选 -->
        <div class="filter-item check-item">
          <label class="checkbox-label">
            <input type="checkbox" v-model="onlyFavorite" @change="fetchStocks" />
            ⭐ 仅显示重点关注标的
          </label>
        </div>

        <button class="btn btn-outline" @click="resetFilters">重置筛选</button>
      </div>
    </div>

    <!-- 股票管理与推荐状态列表表格 -->
    <div class="card">
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th style="width: 60px; text-align: center;">关注</th>
              <th>代码</th>
              <th>股票名称</th>
              <th>所属板块</th>
              <th>所属行业</th>
              <th>推荐评级</th>
              <th>跑赢候选池均值概率</th>
              <th>是否涨停</th>
              <th>最新收盘价</th>
              <th>当日涨幅</th>
              <th>14日RSI</th>
              <th>MACD</th>
              <th style="text-align: center; min-width: 180px;">操作联动</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="13" style="text-align: center; padding: 40px;">
                <div class="spinner" style="margin: 0 auto 10px auto;"></div>
                正在检索 A 股全板块股票资产池...
              </td>
            </tr>
            <tr v-else-if="stocksList.length === 0">
              <td colspan="13" style="text-align: center; padding: 40px; color: #94a3b8;">
                ⚠️ 未找到匹配的股票标的，请调整搜索、板块或行业筛选条件
              </td>
            </tr>
            <tr v-for="item in stocksList" :key="item.code">
              <!-- 星标切换 -->
              <td style="text-align: center;">
                <button 
                  class="star-btn" 
                  :class="{ active: item.is_favorite }"
                  @click="handleToggleFavorite(item)"
                  title="点击切换重点关注状态"
                >
                  {{ item.is_favorite ? '★' : '☆' }}
                </button>
              </td>
              <td><code class="code-font">{{ item.code }}</code></td>
              <td><strong>{{ item.name }}</strong></td>
              <!-- 所属板块 -->
              <td>
                <span class="badge" :class="getBoardBadgeClass(item.board)">
                  {{ item.board || '主板' }}
                </span>
              </td>
              <td><span class="badge badge-silver">{{ item.industry }}</span></td>
              <!-- 评级 -->
              <td>
                <span v-if="item.rating === 'A'" class="badge-rating-a">A 级</span>
                <span v-else-if="item.rating === 'B'" class="badge-rating-b">B 级</span>
                <span v-else class="badge-rating-c">C 级</span>
              </td>
              <!-- 预测跑赢候选池均值的概率估计 -->
              <td>
                <div class="prob-bar-container">
                  <strong>{{ (((item.probability ?? 0) * 100)).toFixed(1) }}%</strong>
                  <div class="prob-bar-bg">
                    <div 
                      class="prob-bar-fill" 
                      :style="{ 
                        width: Math.min(100, Math.max(0, ((item.probability ?? 0) * 100))) + '%',
                        background: item.rating === 'A' ? '#10b981' : (item.rating === 'B' ? '#f59e0b' : '#3b82f6')
                      }"
                    ></div>
                  </div>
                </div>
              </td>
              <td>
                <span v-if="item.is_limit_up === '是'" class="badge-limit-up">涨停</span>
                <span v-else style="color: #64748b;">否</span>
              </td>
              <td>¥{{ item.price ?? '--' }}</td>
              <td :class="(item.change_pct ?? 0) >= 0 ? 'text-pos' : 'text-neg'">
                {{ (item.change_pct ?? 0) >= 0 ? '+' : '' }}{{ item.change_pct ?? 0 }}%
              </td>
              <td>{{ item.rsi14 ?? 50.0 }}</td>
              <td :class="(item.macd ?? 0) >= 0 ? 'text-pos' : 'text-neg'">{{ item.macd ?? 0.0 }}</td>
              <!-- 操作联动 -->
              <td style="text-align: center;">
                <div style="display: flex; gap: 6px; justify-content: center;">
                  <button class="btn btn-primary btn-sm" @click="$emit('viewKline', item)">
                    查看K线
                  </button>
                  <button class="btn btn-outline btn-sm" @click="$emit('explain', item)">
                    归因诊断
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

defineEmits(['viewKline', 'explain'])

const searchKeyword = ref('')
const selectedBoard = ref('全部')
const selectedIndustry = ref('全部')
const selectedRating = ref('全部')
const onlyFavorite = ref(false)

const stocksList = ref([])
const totalCount = ref(0)
const favoriteCount = ref(0)
const loading = ref(false)

const boardList = ['全部', '主板', '创业板', '科创板', '北交所']

const industryList = [
  '食品饮料', '医药生物', '电子', '电力设备', '计算机', '非银金融', '银行', '汽车',
  '机械设备', '国防军工', '通信', '基础化工', '有色金属', '家用电器', '公用事业',
  '交通运输', '石油石化', '建筑装饰', '建筑材料', '商贸零售', '房地产', '传媒',
  '煤炭', '农林牧渔', '钢铁', '环保', '美容护理'
]

const handleSelectBoard = (b) => {
  selectedBoard.value = b
  fetchStocks()
}

const getBoardBadgeClass = (board) => {
  switch (board) {
    case '主板':
      return 'badge-board-main'
    case '创业板':
      return 'badge-board-chinext'
    case '科创板':
      return 'badge-board-star'
    case '北交所':
      return 'badge-board-bse'
    default:
      return 'badge-silver'
  }
}

const fetchStocks = async () => {
  loading.value = true
  try {
    const params = {
      only_favorite: onlyFavorite.value
    }
    if (searchKeyword.value.trim()) {
      params.keyword = searchKeyword.value.trim()
    }
    if (selectedBoard.value !== '全部') {
      params.board = selectedBoard.value
    }
    if (selectedIndustry.value !== '全部') {
      params.industry = selectedIndustry.value
    }
    if (selectedRating.value !== '全部') {
      params.rating = selectedRating.value
    }

    const res = await api.getStockManageList(params)
    stocksList.value = res.data.stocks
    totalCount.value = res.data.total
    favoriteCount.value = res.data.favorite_count
  } catch (err) {
    console.error('获取股票管理列表失败:', err)
  } finally {
    loading.value = false
  }
}

const handleToggleFavorite = async (item) => {
  try {
    const res = await api.toggleFavorite(item.code)
    item.is_favorite = res.data.is_favorite
    favoriteCount.value = res.data.total_favorites
    // 如果当前勾选了仅看自选且取消了关注，则重新拉取一次
    if (onlyFavorite.value && !item.is_favorite) {
      await fetchStocks()
    }
  } catch (err) {
    alert('切换自选关注失败: ' + err.message)
  }
}

const resetFilters = () => {
  searchKeyword.value = ''
  selectedBoard.value = '全部'
  selectedIndustry.value = '全部'
  selectedRating.value = '全部'
  onlyFavorite.value = false
  fetchStocks()
}

onMounted(() => {
  fetchStocks()
})
</script>

<style scoped>
.stock-manage-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.filter-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  border-bottom: 1px solid var(--slate-100);
  padding-bottom: 12px;
}

.filter-header h2 {
  font-size: 18px;
  font-weight: 700;
  color: var(--slate-900);
}

.sub-text {
  font-size: 13px;
  color: var(--slate-600);
  margin-top: 2px;
}

.stats-badge-box {
  display: flex;
  gap: 8px;
}

.filter-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

/* 板块切换按钮组样式 */
.board-segmented-control {
  display: inline-flex;
  background: #f1f5f9;
  padding: 3px;
  border-radius: 8px;
  border: 1px solid var(--slate-200);
  gap: 2px;
}

.board-btn {
  border: none;
  background: transparent;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--slate-600);
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.board-btn:hover {
  color: var(--slate-900);
  background: rgba(255, 255, 255, 0.6);
}

.board-btn.active {
  background: #ffffff;
  color: var(--primary);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.board-btn.active.is-main {
  color: #2563eb;
  border-bottom: 2px solid #2563eb;
}

.board-btn.active.is-chinext {
  color: #059669;
  border-bottom: 2px solid #059669;
}

.board-btn.active.is-star {
  color: #7c3aed;
  border-bottom: 2px solid #7c3aed;
}

.board-btn.active.is-bse {
  color: #ea580c;
  border-bottom: 2px solid #ea580c;
}

/* 板块专属标签色彩 */
.badge-board-main {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
  font-weight: 600;
}

.badge-board-chinext {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
  font-weight: 600;
}

.badge-board-star {
  background: #f5f3ff;
  color: #6d28d9;
  border: 1px solid #ddd6fe;
  font-weight: 600;
}

.badge-board-bse {
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fed7aa;
  font-weight: 600;
}

.input-control {
  padding: 8px 12px;
  border: 1px solid var(--slate-300);
  border-radius: var(--radius-md);
  font-size: 14px;
  outline: none;
  min-width: 220px;
}

.input-control:focus {
  border-color: var(--primary);
}

.select-control {
  padding: 8px 12px;
  border: 1px solid var(--slate-300);
  border-radius: var(--radius-md);
  font-size: 14px;
  outline: none;
  background: #ffffff;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-weight: 500;
  color: var(--slate-800);
}

.star-btn {
  background: transparent;
  border: none;
  font-size: 20px;
  color: #cbd5e1;
  cursor: pointer;
  transition: color 0.2s, transform 0.2s;
}

.star-btn:hover {
  transform: scale(1.2);
  color: #f59e0b;
}

.star-btn.active {
  color: #f59e0b;
}

.table-container {
  overflow-x: auto;
}

.btn-sm {
  padding: 5px 10px;
  font-size: 13px;
}

.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #e2e8f0;
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
