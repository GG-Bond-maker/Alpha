# 基于 LightGBM 与特征归因的 A 股智能选股与可解释推荐系统 v2.0
> **毕业设计 / 量化投资全栈工程落地实现 (Full-Stack Implementation)**
> 
> 技术栈：**Python 3.11/3.12 + LightGBM + Optuna (贝叶斯调优) + akshare (真实行情) + TreeSHAP (XAI) + FastAPI + Vue 3 + Vite + ECharts**
> 
> 参考并重构融合项目：[AShare-AI-Stock-Picker](https://github.com/stlin256/AShare-AI-Stock-Picker)

---

## 1. 项目概述与重构创新亮点

本项目针对传统量化选股中“黑盒模型不可信”、“超参数调优繁琐”、“缺乏全栈工程可视化”以及“实盘真实数据断层”等痛点，参考开源优质项目 **[AShare-AI-Stock-Picker](https://github.com/stlin256/AShare-AI-Stock-Picker)** 进行系统级架构重构。

将真实的 A 股日线/实时数据流、全套经典技术指标体系、Optuna 贝叶斯超参数寻优、A/B/C 推荐评级与 Excel 报表导出，与先进的 **TreeSHAP 博弈论可解释性归因**、**FastAPI 异步微服务** 和 **Vue 3 + ECharts 交互大屏** 深度融合。

### 核心亮点：
1. **真实 A 股数据源与本地增量缓存 (`akshare`)**：
   - 支持全市场 A 股及核心行业龙头股票池实时行情与前复权日线拉取；
   - 内置智能本地磁盘缓存机制（`data/cache/`），同日重复计算秒级完成，具备离线兜底抗断网能力。
2. **双引擎经典技术指标特征工程 (`features/`)**：
   - 涵盖 **EMA20比率、RSI14、MACD、OBV能量潮、CCI顺势指标、ATR真实波幅、ADX平均趋向指标** 等全维度技术面因子；
   - 具备 **TA-Lib + 纯 NumPy/Pandas 向量化双计算引擎**，无缝兼容各类运行环境，零 C 编译依赖阻碍。
3. **股票范围严格限定为主板（沪深主板）**：
   - 包含上海主板（600/601/603/605）与深圳主板（000/001/002/003）；
   - 严格排除创业板（300/301）、科创板（688/689）及北交所（8/4/9）高投机性标的，过滤 ST 及退市标的，专注主板核心蓝筹资产。
4. **专业级股票 K 线走势与数据可视化大屏 (`StockKlineView.vue`)**：
   - 参考专业股票可视化推荐系统设计，集成高交互性 **日K线蜡烛图 (Candlestick)** 与 **MA5/MA10/MA20/MA30 多周期均线系统**；
   - 标注历史区间最高点与最低点水平支撑/阻力虚线及对角趋势辅助线；
   - 结构化悬浮 Tooltip 详尽展示开高低收与均线数据；
   - 下方无缝联动 **成交量 (Volume) 量能柱状图** 与均量线，支持 `DataZoom` 滑块双向自由缩放。
5. **Optuna 贝叶斯超参数自动寻优 (`optuna`)**：
   - 基于时间序列交叉验证（`TimeSeriesSplit`）优化 ROC-AUC / NDCG，杜绝未来信息穿越；
   - 自动搜索最优树深、学习率、采样率及正则项，相比固定超参具有更强泛化能力。
6. **多维推荐评级与自动化 Excel 报表生成**：
   - **A 级推荐**：预测看涨概率 $\ge 75\%$（高置信度多头动能标的）；
   - **B 级推荐**：$60\% \le$ 预测看涨概率 $< 75\%$（中等置信度关注标的）；
   - **C 级推荐**：预测看涨概率 $< 60\%$（中低置信度防守标的）；
   - 涨停检测警示（当日涨幅 $\ge 9.9\%$ 自动标注）；
   - 命令行 CLI 与 Web 界面均支持一键生成带有日期戳的专业格式 Excel 推荐报表（`stock_recommend_YYYYMMDD.xlsx`）。
7. **细粒度特征归因（TreeSHAP 局部瀑布图与全局透视）**：
   - **个股局部归因**：基于 Shapley 公理体系，将每只推荐标的的预测打分拆解为各技术指标的正负贡献，并生成自然语言诊断报告；
   - **全市场全局重要性**：透明化展示全市场宏观技术指标权重。
8. **现代化前后端分离落地**：
   - **FastAPI**：异步 ASGI 接口，支持 Swagger UI 交互式在线调试及 Excel 文件流下载；
   - **Vue 3 + Vite + ECharts**：响应式仪表盘，支持实时刷新、动态筛选、评级高亮、看涨概率条、K 线联动及瀑布图模态窗。

---

## 2. 系统快速启动指南

### 方式一：一键启动全栈服务（推荐）
双击根目录下的 `start_all.bat`，或者在终端运行：
```powershell
python backend/run_server.py
```
启动后直接打开浏览器访问：
- **系统前端交互主界面**：[http://127.0.0.1:8008](http://127.0.0.1:8008)
- **FastAPI 交互式接口文档 (Swagger UI)**：[http://127.0.0.1:8008/docs](http://127.0.0.1:8008/docs)
- **ReDoc 接口文档**：[http://127.0.0.1:8008/redoc](http://127.0.0.1:8008/redoc)

### 方式二：命令行 CLI 智能选股与导出 Excel
参考原项目控制台操作习惯，系统提供交互式与参数化 CLI 选股工具：
```powershell
# 1. 快速选股（扫描代表性核心标的，秒级导出 Excel）
python main.py --limit 20

# 2. 启用 Optuna 贝叶斯超参数自动调优并重训
python main.py --optuna --limit 20

# 3. 强制重训并忽略缓存
python main.py --no-cache
```
执行完毕后，根目录将自动产出带日期戳的报表：`stock_recommend_YYYYMMDD.xlsx`。

### 方式三：前端独立热更新开发模式 (Dev Mode)
若需二次定制前端页面与交互组件：
```powershell
# 终端 1：启动后端服务 (8008 端口)
python backend/run_server.py

# 终端 2：启动前端 Vite 开发服务器 (5174 端口，自动反向代理 8008)
cd frontend
npm run dev
```
访问开发服务器：[http://127.0.0.1:5174](http://127.0.0.1:5174)

---

## 3. 项目工程目录结构

```text
Alpha/
├── config/                      # 全局配置中心
│   ├── __init__.py
│   └── config.py                # 特征列定义、评级阈值、核心股票池及路径配置
│
├── data/                        # 数据管理与持久化
│   ├── cache/                   # 真实 A 股数据本地增量缓存
│   ├── stock_models/            # 单股 LightGBM 模型持久化目录
│   └── processed/               # 选股推荐结果缓存与评估样本
│
├── features/                    # 特征工程模块
│   ├── __init__.py
│   └── feature_engineering.py   # 双引擎技术指标计算（EMA, RSI, MACD, OBV, CCI, ATR, ADX）
│
├── models/                      # 核心算法与建模模块
│   ├── __init__.py
│   └── model_trainer.py         # Optuna 贝叶斯调优、LightGBM 训练与预测推理引擎
│
├── ml_pipeline/                 # 可解释性与评测流水线
│   ├── train_explainer.py       # TreeSHAP 解释器与自然语言推荐理由生成
│   └── evaluate_metrics.py      # NDCG@K, Precision@K, AUC 基线对比评测
│
├── saved_models/                # 序列化模型与预计算缓存
│   ├── lgbm_market_classifier.pkl # 训练好的市场通用 LightGBM 模型
│   ├── shap_explainer.pkl       # TreeSHAP 解释器实例
│   ├── global_importance.json   # 全局技术指标重要性数据
│   └── evaluation_metrics.json  # 对比模型评测指标数据
│
├── backend/                     # 后端工程 (FastAPI)
│   ├── app/
│   │   ├── api/                 # API 路由 (/recommend, /explain, /evaluation)
│   │   ├── schemas/             # Pydantic 响应数据模型规范
│   │   ├── services/            # 选股推荐、SHAP 计算与 Excel 导出服务
│   │   └── main.py              # FastAPI 入口 (自动挂载前端静态包)
│   └── run_server.py            # 后端启动脚本
│
├── frontend/                    # 前端工程 (Vue 3 + Vite + ECharts)
│   ├── src/
│   │   ├── api/                 # Axios 接口封装 (含 Excel 导出)
│   │   ├── components/
│   │   │   ├── ExplainModal.vue # 个股 SHAP 瀑布图与诊断模态窗
│   │   │   ├── GlobalExplainView.vue # 全局特征重要性分析大屏
│   │   │   └── MetricsView.vue  # 算法评测指标对比大屏
│   │   ├── App.vue              # 主应用视图、评级排行榜与 Excel 导出
│   │   └── style.css            # 现代响应式主题与评级徽章样式
│   └── dist/                    # 生产构建静态包 (自动被后端托管)
│
├── main.py                      # CLI 选股命令行主入口 (支持 Banner, 进度条, 导出 Excel)
├── requirements.txt             # 完整运行依赖清单
├── start_all.bat                # Windows 一键全栈启动脚本
└── README.md                    # 项目说明文档
```

---

## 4. 算法性能与基线对比实验结果

在时序测试集样本上的对比评测实验结果如下：

| 对比模型 | 建模范式 | NDCG@5 | NDCG@10 | Precision@5 | Precision@10 | HitRate@5 | AUC |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Random Guess** | 随机基线 | 0.3099 | 0.3467 | 0.3667 | 0.3500 | 1.0000 | 0.5000 |
| **Ridge Classifier** | 线性判别 | 0.6504 | 0.6981 | 0.6000 | 0.5500 | 1.0000 | 0.6120 |
| **Random Forest** | 随机森林 | 0.6720 | 0.7130 | 0.6667 | 0.5800 | 1.0000 | 0.6450 |
| **LightGBM + Optuna** | **梯度提升树 (本文系统)** | **0.7410** | **0.7830** | **0.7333** | **0.6667** | **1.0000** | **0.7150** |

---

## 5. 核心 API 接口速查

| 请求方法 | 路由地址 | 接口描述 |
| :--- | :--- | :--- |
| `GET` | `/api/health` | 后端服务健康状态检查 |
| `GET` | `/api/v1/recommend/dates` | 获取所有可选的推荐截面日期列表 |
| `GET` | `/api/v1/recommend/topk` | 获取指定截面与行业过滤的 Top-K 推荐股票及评级 |
| `GET` | `/api/v1/recommend/export_excel` | **导出并下载推荐结果为 Excel 文件 (`.xlsx`)** |
| `GET` | `/api/v1/explain/local/{stock_code}` | 获取指定股票的 TreeSHAP 瀑布图归因与自然语言诊断 |
| `GET` | `/api/v1/explain/global` | 获取全市场全局特征重要性排序 (Mean \|SHAP\|) |
| `GET` | `/api/v1/evaluation/metrics` | 获取算法评测指标与基线模型对比实验数据 |

---

## 6. 许可证与免责声明

- 本项目遵循开源许可协议；
- **免责声明**：本项目产出的模型预测、技术指标与推荐评级仅供学术研究、毕业设计与量化技术探讨，不构成任何实质性投资建议。股市有风险，入市需谨慎。
