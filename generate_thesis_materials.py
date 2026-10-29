import os
import shutil
import docx
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls
import copy

BASE_DIR = r"D:\Python_Project\Alpha"
OUTPUT_DIR = os.path.join(BASE_DIR, "论文材料输出")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TASK_SRC = r"D:\xwechat_files\wxid_zbz132llxvhi22_ee05\msg\file\2026-10\桂林旅游学院毕业论文（设计）任务书.docx"
PROPOSAL_SRC = r"D:\xwechat_files\wxid_zbz132llxvhi22_ee05\msg\file\2026-10\桂林旅游学院毕业论文（设计）开题报告.docx"

TASK_DST = os.path.join(OUTPUT_DIR, "毕业论文（设计）任务书_完成稿.docx")
PROPOSAL_DST = os.path.join(OUTPUT_DIR, "开题报告_完成稿.docx")

PURPOSE_AND_SIGNIFICANCE = [
    ("（一）研究目的", True, 12),
    "股票市场是现代宏观金融体系与资本资源配置的核心枢纽。股票推荐系统通过对海量股票标的进行定量分析与横截面优选，旨在辅助投资者在剧烈波动的市场中发掘具备相对超额收益潜力的优质资产，降低决策盲目性并提高资金配置效率。然而，股票二级市场受到宏观经济周期、货币流动性、行业结构轮动、公司微观基本面以及高频博弈情绪等多重异构因素交织作用，其数据序列具有显著的非平稳性、动态时变性、极高噪声与低信噪比特征，使得精准可靠的股票推荐极具学术挑战与实务难度。",
    "传统的量化选股与推荐模型多以资本资产定价模型（CAPM）及Fama-French多因子定价体系为理论基础，依赖横截面多元线性回归或静态IC加权打分法。这类线性模型假定因子与资产收益率之间存在恒定不变的单调线性映射关系，但在实际运行中，动量、估值、波动率等量价与财务因子往往在不同市场状态（牛市、熊市、震荡市）下呈现非线性拐点与复杂的交叉协同效应。例如高估值在流动性充裕阶段可能伴随高动量溢价，但在熊市退潮期则极易转为高回撤风险。传统线性方法难以动态识别并建模这种高阶交互特征，导致策略适应能力与预测稳健性不足。",
    "以梯度提升决策树（GBDT）、LightGBM为代表的集成机器学习算法，凭借强大的非线性拟合能力、天然支持高阶特征交叉交互以及对缺失值和异常值的优异容忍度，为量化股票推荐提供了前沿的方法论工具。然而，机器学习模型的强拟合能力在金融领域也是一把“双刃剑”：一方面，金融时序的强噪声极易诱发严重的样本内过拟合与“未来信息泄漏”（前视偏差），导致模型在训练期看似优秀、在样本外实盘中却迅速失效；另一方面，复杂的树集成模型通常被视为高度不可透视的“黑箱”，无法向投研人员清晰阐明具体推荐得分背后的特征驱动逻辑，极易引发审慎风控隐患与合规监管质询。",
    "因此，本毕业设计旨在以A股沪深300指数全成分股为候选标的池，设计并实现一套兼具“严格防前视数据工程、训练期因子诊断、LightGBM横截面排序、实盘级Top-K组合回测、Alpha/Beta业绩解耦归因、TreeSHAP全局与个股局部特征解释，以及FastAPI+Vue3可视化交互大屏”的股票推荐系统原型。本研究的核心目的并非预测股票的绝对上涨，而是精确学习个股在横截面上的相对排序能力（输出跑赢截面均值的估计倾向）；同时通过科学归因揭示策略收益中系统性Beta风险与选股Alpha的真实构成，打破量化神话，为量化投研与中小投资者提供一套规范、透明、可信且可落地的智能推荐解决方案。",
    ("（二）研究意义", True, 12),
    "理论意义：（1）丰富金融实证资产定价与机器学习交叉领域的方法论。系统性探索LightGBM在A股高噪声、低信噪比弱信号环境下的横截面排序性能边界，验证排序学习指标与传统分类损失在金融推荐中的有效性。（2）深化可解释人工智能（XAI）在量化金融风控中的应用理论。基于合作博弈论Shapley值体系，验证TreeSHAP在多项式时间内实现树集成模型全局重要性与局部样本分解的加和一致性，构建特征归因到投资逻辑验证的理论桥梁。（3）深化对A股市场有效性特征的实证认识。通过对回测净值进行严格的Jensen Alpha与Beta线性回归分解，实证检验超额收益在不同市场状态下的表现形态，揭示量化多因子收益中Beta风险补偿的本质，为理解A股半强式有效性提供扎实的微观实证证据。",
    "现实意义：（1）构建杜绝数据泄漏与兼顾交易摩擦的规范化量化工程范式。系统从特征向前填充、财报披露法定截止日滞后对齐、标签定义及5日时序隔离带等全流程阻断前视偏差，并在回测中严密核算印花税、过户费与佣金，为中小投资者与量化初创团队提供极具参考价值的合规工程模板。（2）提供直观透明的模型可解释性交互支持。系统通过FastAPI微服务与Vue 3前端组件化架构，将复杂的SHAP归因分解转化为多维可视化图表与个股归因弹窗，投研人员不仅能获取Top-K推荐列表，更能清晰洞察推动推荐的核心驱动因子与负向拖累因子，极大提升了人机协同决策效率与风控透明度。（3）揭示策略收益的Beta本质，倡导理性科学投资理念。研究如实报告超额收益主要来自承担高于市场的Beta系统性敞口、Jensen Alpha在统计上未达到显著水平的实证事实，客观揭示简单的技术指标难以持续获取超越市场的真实Alpha，引导投资者树立尊重市场规律、防范极端回撤的理性投资观。"
]

LIT_REVIEW = [
    ("（一）国外研究现状", True, 12),
    "国外在量化资产定价、机器学习选股以及模型可解释性方面拥有深厚的理论积淀与成熟的工业实践体系。在资产定价与因子投资基石方面，Fama与French（1993）提出的三因子模型奠定了现代实证资产定价的基础，通过市场溢价、规模因子（SMB）与估值因子（HML）解释截面股票收益差异，随后扩展为五因子模型。然而随着学术界发掘的资产异象因子迅速膨胀至数百个，Harvey、Liu与Zhu（2016）在Review of Financial Studies上发表著名文献，尖锐指出大量声称显著的因子实际上是数据窥探（p-hacking）与假阳性结果，呼吁必须提高统计显著性门槛（t > 3.0）并引入更为严苛的样本外检验与经济学逻辑校验。",
    "在机器学习与资产定价融合方面，Gu、Kelly与Xiu（2020）在Review of Financial Studies发表了里程碑式的实证研究《Empirical Asset Pricing via Machine Learning》，系统评估了线性回归、样条回归、随机森林、梯度提升决策树（GBDT）及深层神经网络在美股横截面资产定价中的预测能力。研究证实，树集成模型（如GBRT/LightGBM）与神经网络由于能够灵活捕捉宏观状态变量与微观公司特征之间的高阶非线性交互效应，其样本外排序能力与预测表现显著优于传统线性计量模型，确立了机器学习在现代量化投资中的核心地位。Fischer与Krauss（2018）也将长短期记忆网络（LSTM）应用于标普500成分股收益预测，进一步证实了非线性模型在捕捉市场复杂时序动态中的优势。",
    "在金融机器学习的方法论规范与防过拟合机制方面，知名量化金融学家Marcos López de Prado（2018）在专著《Advances in Financial Machine Learning》中系统指出了金融时间序列与传统机器学习独立同分布（IID）假设的本质冲突。他特别强调，金融数据存在严重的自相关性与标签跨期重叠，传统K-Fold交叉验证必然导致严重的未来信息泄漏（Look-ahead Bias）；为此，他提出了Purged K-Fold CV（样本隔离交叉验证）与Embargo（冷冻期）机制，要求在训练段与检验段之间设置严格的成熟期隔离带，这一理论为现代金融机器学习提供了行业公认的防泄漏标准。",
    "在模型可解释性与特征归因理论方面，随着黑箱模型广泛应用于高风险决策场景，Caruana等（2015）在KDD大会上力倡可解释模型的重要性。Lundberg与Lee（2017）基于合作博弈论的Shapley值，提出了统一的SHAP（SHapley Additive exPlanations）可解释性计算框架，证明了SHAP值是唯一同时满足局部精确性、缺失性及一致性公理的加和归因方法。2020年，Lundberg等人在Nature Machine Intelligence发表TreeSHAP算法，将多层决策树集成的归因计算复杂度从指数级降至多项式时间，使得对GBDT与LightGBM等复杂集成树模型进行大规模横截面特征重要性排序（全局归因）与单样本贡献拆解（局部归因）成为可能，极大推动了XAI在现代量化风控中的落地应用。",
    ("（二）国内研究现状", True, 12),
    "国内量化选股与智能投资研究紧密贴合中国A股市场的本土化运行特征，经历了从传统多因子打分到机器学习建模的深刻演进。在传统量化选股层面，陈小悦与孙爱军（2000）基于实证检验了CAPM在中国股市的有效性；郑振龙与孙清泉（2013）在《经济研究》深入分析了A股市场的投资者交易行为与异象特征。杨博理与贾芳（2017）在《量化炼金术：中低频量化交易策略研发》中系统总结了A股中低频多因子研发流程、因子IC/IR诊断、行业中性化处理及推进分析（Walk-Forward Analysis）在防范策略过拟合中的实战价值。",
    "在机器学习多因子实证层面，顾明、廖理与许宪春（2021）在《经济研究》发表《机器学习与中国股票市场选股》，实证评估了多种机器学习模型在A股不同市场环境下的选股能力，表明非线性树模型在捕捉复杂交互模式上展现出更强的稳健性；姜富伟、孟令超与唐国豪（2022）在《系统工程理论与实践》发表《机器学习与中国股票市场收益预测》，指出机器学习能够有效整合宏观状态与微观公司特征，但由于A股散户占比较高、风格切换剧烈，短周期量价因子的预测信噪比往往高于低频财报数据，因子的时间非平稳性也更为显著。姜富伟、唐国豪与马甜（2024）在其专著《金融与财务机器学习》中系统梳理了金融特征工程、正则化决策树与可解释性建模的量化实战架构。",
    "在模型可解释性与量化系统工程探索方面，周志华（2016）在《机器学习》中系统论述了集成学习与决策树的理论机制。胡杰（2020）在北京交通大学完成了基于机器学习的股票预测及股票推荐系统的设计与实现，探讨了时序预测算法与个性化推荐系统的工程落地；曹志（2022）基于LightGBM算法与投资者情绪构建了多因子量化选股和择时方案；张宇（2023）对机器学习在A股多因子选股中的特征构建与组合优化进行了系统实证；余柏翱（2025）在贵州大学进一步拓展了基于机器学习的多因子量化选股策略研究；文晓婷（2025）在中央民族大学深入实证了基于LightGBM与XGBoost的ESG多因子选股与择时体系。然而，国内绝大多数已有研究主要停留在离线静态回测阶段，缺乏涵盖严格前视防泄漏时序管道、多轮Walk-Forward推进检验、Alpha/Beta风险严格解耦、微服务API封装与TreeSHAP可解释交互大屏的全链路闭环推荐系统原型交付。",
    ("（三）研究述评", True, 12),
    "综合对比国内外研究现状，现有文献与工程实践已在理论奠基、算法演进与归因探索上取得了丰硕成果，但面向实际量化投研与推荐应用，仍存在以下亟待解决的突出痛点：（1）数据前视偏差防范意识淡薄：大量研究在数据预处理阶段随意采用包含未来信息的向前填充（bfill）、直接使用未扣除发布时滞的原始财报公布日期，导致实证结论存在严重的未来函数造假；（2）普遍忽视幸存者偏差：多数研究直接以当前最新的指数成分股倒推历史十年回测，未能真实反映历史被剔除或退市股票的下行风险，回测超额存在系统性虚高；（3）跨周期评估与稳定性检验缺失：多数文献仅展示单次特定时间切分下的亮眼净值曲线，忽视了金融市场状态切换时因子预测方向的符号剧烈翻转，缺乏多窗口推进分析（Walk-Forward）的严苛检验；（4）业绩归因不严谨与因果误读：许多研究将组合超额收益笼统归功于模型的“高超选股能力”，未严格区分系统性高Beta风险敞口与真实超额Alpha；同时容易将SHAP模型特征依赖性错误阐释为经济学因果关系；（5）全链路工程化系统缺失：算法探索与工程系统脱节，缺乏集数据工程、模型训练、评测对比、回测归因与XAI交互于一体的完整软硬件系统原型。",
    "针对上述短板，本课题以沪深300成分股为基准池，建立覆盖2015年至2026年全周期的前视防泄漏数据管道；引入训练期Spearman IC与Newey-West HAC t值双重诊断机制，剔除冗余因子；采用Optuna时序分组交叉验证优化LightGBM超参数，通过13轮滚动窗口推进实验全面检验模型泛化能力；建立考虑真实交易费率的Top-K调仓回测与Alpha/Beta线性回归业绩解耦，如实揭示超额收益的Beta本质；基于TreeSHAP完成加和一致性校验与多维度特征解释，并基于FastAPI与Vue 3开发交付功能完备的交互式推荐系统原型，从而在严谨实证与工程落地两方面均形成清晰的研究创新与实践价值。"
]

RESEARCH_CONTENT = [
    ("（一）主要研究内容", True, 12),
    "1. 研究对象：本研究选取中国A股市场最具代表性的核心蓝筹指数——沪深300指数（000300.SH）全部成分股作为候选股票池。数据跨越2015年1月16日至2026年10月21日共计2,856个交易日，构建包含744,372行样本的高维截面面板数据集，涵盖基础日K线量价数据、衍生技术指标、流动性特征以及财务报表估值指标。",
    "2. 拟解决的关键问题：（1）金融面板数据中的前视偏差（Look-ahead Bias）与幸存者偏差（Survivorship Bias）防控问题；（2）高噪声横截面环境中有效弱信号因子的科学诊断、中性化与冗余剔除问题；（3）基于LightGBM的股票横截面二分类排序模型构建与时序防泄漏调优问题；（4）贴合A股实盘交易摩擦成本（印花税、过户费、佣金）的Top-K等权调仓回测与滚动窗口连续验证问题；（5）策略超额收益的Jensen Alpha与系统性Beta风险暴露的严格解耦归因问题；（6）集成树模型黑箱决策在数学加和一致性保障下的TreeSHAP全局与个股局部特征归因问题；（7）微服务化REST API接口设计与现代组件化前端可视化大屏的高效交互集成问题。",
    "3. 关键技术：本课题采用的关键技术栈包括：以LightGBM为核心的梯度提升决策树排序学习算法；基于合作博弈论的TreeSHAP特征加和解释技术；横截面分行业去均值中性化与Z-score极值标准化；基于Optuna的贝叶斯超参数时序交叉验证寻优技术；基于Newey-West异方差自相关一致协方差矩阵（HAC）的因子t值诊断统计方法；Top-K等权组合模拟回测与资本资产定价市场回归归因分析；基于FastAPI的异步高性能后端RESTful服务架构；基于Vue 3 + Vite + ECharts的现代响应式数据可视化大屏技术。",
    "4. 拟采取的措施：（1）严格执行防前视数据工程规范：特征清洗杜绝bfill，缺失值向前填充并以个股历史中位数兜底；财务数据按法定披露截止日保守滞后（一季报4/30，年报次年4/30）；标签严格定义为t+1开盘买入至t+5收盘收益是否超越当日截面均值；训练/验证/测试集按时间严格先后切分，并设置5个交易日成熟期隔离带（purging）。（2）多层次因子筛选机制：训练期逐日计算截面Spearman IC与Newey-West HAC t值，设定|IC|>=0.015与|t|>=2.0硬性门槛，并按|r|>0.7执行相关性去冗余；同时如实开展技术因子与基本面因子在沪深300池上的有效性对比。（3）严谨的时序验证与推进分析：利用Optuna在训练集内部交叉验证确定固定迭代轮次，防止早停退化；在测试集上对比随机猜测、逻辑回归、随机森林等基准，计算AUC、NDCG@5、Precision@5；执行13轮步长为120交易日的Walk-Forward滚动检验，统计AUC分布与因子符号翻转频次。（4）真实交易场景回测与收益归因：模拟每5个交易日等权调仓，扣除0.03%佣金、0.001%过户费及0.05%印花税，对比全市场排序与行业中性口径；对13个窗口拼接而成的1,547期连续收益做市场OLS回归，检验Alpha显著性与Beta大小，并按市场涨跌五等分验证收益单调性。（5）精确特征归因与系统落地：在log-odds空间运行TreeSHAP，对200个测试样本进行绝对误差小于0.001的加和一致性数学校验，生成全局Beeswarm蜂群图与个股局部瀑布拆解；通过FastAPI实现推荐与归因接口，开发Vue 3交互界面。",
    "5. 预计解决问题的程度：通过上述研究与系统开发，预期构建起一套完全可复现、具备严密学术证据链的股票推荐系统原型。在实证层面，如实揭示LightGBM在5日预测周期上微弱但具备统计显著性的截面排序能力（滚动AUC均值0.5095），客观阐明策略收益本质为Beta系统性风险放大（Beta=1.1424，Alpha在统计上不显著），与A股半强式有效假说形成有力契合；在工程层面，提供界面美观、操作流畅、支持实时Top-K推荐与毫秒级特征解释的完整软件系统原型。",
    ("（二）论文提纲", True, 12),
    "第1章 绪论\n  1.1 研究背景与问题提出（股票市场复杂性、传统量化局限、机器学习应用契机）\n  1.2 研究目的与意义（理论意义、现实工程意义）\n  1.3 国内外研究现状与文献综述（多因子资产定价、金融机器学习、模型可解释性XAI）\n  1.4 现有研究不足与本课题切入点（前视防范、幸存者偏差、跨期稳定性、业绩解耦）\n  1.5 研究内容与技术路线（六阶段研发流程图、系统架构蓝图）\n  1.6 论文组织结构安排",
    "第2章 相关理论与核心技术\n  2.1 多因子选股理论与截面排序机制（截面IC/IR、Rank IC、多头排序逻辑）\n  2.2 LightGBM算法原理与时序优化机制（直方图算法、GOSS、EFB及目标函数）\n  2.3 基于合作博弈论的可解释AI与TreeSHAP方法（Shapley公理、TreeSHAP原理、加和一致性）\n  2.4 金融机器学习中的数据泄漏防范理论（前视偏差、Purging成熟期隔离、时序交叉验证）\n  2.5 本章小结",
    "第3章 股票推荐系统数据工程与因子诊断\n  3.1 样本选择与沪深300候选池构建（成分股覆盖、面板构建、幸存者偏差约束）\n  3.2 标签设计与前视防泄漏时序切分（5日前瞻收益、相对超额二值化、成熟期隔离带）\n  3.3 截面因子构建与行业中性化处理（技术、量价与基本面特征、缩尾、行业去均值、标准化）\n  3.4 训练期因子有效性诊断与筛选（Spearman IC、Newey-West HAC t值、相关性去冗余）\n  3.5 基本面因子在大样本中性化下的有效性反转分析（小样本与大样本A/B对比实证）\n  3.6 本章小结",
    "第4章 基于LightGBM的股票推荐模型构建与评价\n  4.1 模型架构设计与时序交叉验证（TimeSeriesSplit、折内因子筛选、防过拟合机制）\n  4.2 基于Optuna的超参数贝叶斯寻优（固定迭代轮数选择、超参数敏感性分析）\n  4.3 测试集预测性能与基线模型对比（LightGBM与随机猜测、逻辑回归、随机森林对比）\n  4.4 Walk-Forward推进分析与跨期稳定性检验（13个滚动窗口AUC分布、因子符号翻转检验）\n  4.5 训练收敛性与二分类Logloss演进分析\n  4.6 本章小结",
    "第5章 投资组合回测与Alpha/Beta业绩归因\n  5.1 Top-K组合构建与回测机制设置（5日调仓、印花税/佣金/过户费摩擦成本模型）\n  5.2 全市场排序与行业中性选股口径对比（收益率、夏普比率、最大回撤多维权衡）\n  5.3 滚动连续回测与净值表现分析（1,547期连续拼接净值曲线、最大回撤风险特征）\n  5.4 策略收益的Jensen Alpha与Beta线性回归归因（超额收益来源数学解耦与t检验）\n  5.5 分市场状态表现与选股能力本质剖析（五等分市场状态单调性、Beta中性化对照实证）\n  5.6 本章小结",
    "第6章 股票推荐与特征归因系统的设计与实现\n  6.1 系统总体架构设计与技术选型（FastAPI异步后端、Vue 3组件化前端架构）\n  6.2 核心业务流程与REST API接口实现（行情接口、训练接口、回测接口、归因接口）\n  6.3 TreeSHAP特征归因模块工程落地（加和一致性校验、全局Beeswarm图、个股局部归因弹窗）\n  6.4 前端可视化看板与交互模块实现（行情看盘、因子诊断、模型评测、滚动回测、业绩归因大屏）\n  6.5 系统测试与运行效果分析（响应延迟、归因计算时效性、系统鲁棒性）\n  6.6 本章小结",
    "第7章 总结与展望\n  7.1 研究工作总结（主要研究成果与核心发现梳理）\n  7.2 研究局限与反思（预测弱信号、幸存者偏差、成交假设理想化、归因非因果）\n  7.3 未来改进与研究展望（微观高频特征接入、历史动态成分股重构、因果推断框架引入）",
    ("（三）预期目标", True, 12),
    "本研究预期在学术实证与工程软件两个维度达成以下成果目标：（1）学术与实证目标：撰写一篇结构严密、数据详实、图表丰富、遵循学术规范的本科优秀毕业设计论文；如实呈现全部实验数据与统计检验结果，形成“弱预测力、无显著Alpha、超额源于高Beta风险”的完整客观证据链，经得起学术评审与答辩质询。（2）工程与系统目标：交付一套完全可复现的代码仓库（包含完整的特征工程、训练管道、回测框架与SHAP计算脚本），以及一套稳定运行、界面现代的股票推荐与特征归因前后端原型系统，提供高内聚的REST API服务与交互式可视化分析功能。"
]

METHOD_AND_MEASURES = [
    ("（一）研究方法", True, 12),
    "根据本毕业设计的跨学科研究内容与工程落地要求，研究主要采用文献研究法、实证分析法、定量诊断法、推进分析法与系统原型开发法相结合的综合研究路径：",
    "1. 文献研究法：广泛搜集并系统梳理实证资产定价、金融机器学习（GBDT/LightGBM）、数据泄漏防范（Purging/Embargo）以及模型可解释性（TreeSHAP）等领域的国内外权威文献，明确技术路线与研究边界，奠定严谨扎实的理论基础。",
    "2. 实证分析法：立足中国A股沪深300指数真实历史日线行情与财务面板数据（2015-2026年，74.4万余条样本），严格遵照统计学规范执行前瞻防泄漏切分、缩尾中性化与标准化处理，构建客观公正的实证数据集。",
    "3. 定量诊断与特征筛选法：在训练集内部对每个交易日截面计算Spearman秩相关（IC）与Newey-West HAC t统计量，通过硬性门槛与相关性去冗余筛选有效特征，并严谨开展技术与基本面因子的截面有效性对比分析。",
    "4. 推进分析法（Walk-Forward Analysis）：针对金融数据非平稳性，摒弃单一时间切分的乐观偏差，构建13个步长为120交易日的滚动窗口推进实验，全面评估模型排序指标的分布特征与因子跨期方向稳定性。",
    "5. 模拟交易回测与业绩归因法：构建贴合真实A股交易规则的Top-K等权调仓回测，计入印花税、佣金与过户费；对滚动回测净值建立资本资产定价OLS回归模型，数学解耦Jensen Alpha与Beta风险暴露，并按市场状态五等分严密验证收益单调性。",
    "6. 原型系统开发法：遵循软件工程规范，采用FastAPI设计高内聚微服务接口，采用Vue 3 + Vite + ECharts开发组件化前端，将量化推荐、实证回测与TreeSHAP特征归因集成于可视化交互系统中，实现原型交付。",
    ("（二）准备工作情况", True, 12),
    "截至目前，本项目已在理论准备、数据管线、模型实验及系统开发各环节取得实质性进展，具备完备的开题与系统深化条件：（1）理论与文献准备充分：已系统精读Gu et al. (2020)、Lundberg et al. (2020)、López de Prado (2018)等核心文献，完成了详细的文献综述与方法论推演；（2）数据管道与防泄漏设计就绪：已成功接入沪深300成分股自2015年至今的量价行情与财务估值数据，编写完成了ffill填充、自身历史中位数补缺、财报披露截止日保守滞后及5日成熟期隔离的代码逻辑；（3）全流程模型训练与产物固化：已基于Optuna完成LightGBM模型调优与13轮Walk-Forward推进实验，成功导出包含training_report.json、evaluation_metrics.json、walk_forward.json、attribution.json及shap_summary.json在内的全套真实实验数据，并绘制了8张高质量学术论文图表；（4）前后端原型系统初具雏形：已利用FastAPI搭建起覆盖因子诊断、模型评测、组合回测、业绩归因及SHAP解释的完整API路由，Vue 3前端实现了看板、图表展示与个股归因弹窗等交互界面，系统整体运行稳定流畅。",
    ("（三）主要措施", True, 12),
    "为确保毕业设计高质量如期完成，研究将严格执行以下四项关键保障措施：（1）严格执行金融数据时序防泄漏规程：全流程严格把控特征工程时间戳，杜绝任何形式的向后回填；确保验证集与测试集标签不参与特征筛选与参数调优，保障实证结论绝对真实可信；（2）坚持客观严谨的学术求真态度：在论文中如实阐明模型AUC处于0.51弱预测水平、超额收益本质为高Beta敞口、缺乏动态成分股所伴随的幸存者偏差等已知局限，坚决杜绝编造造假、虚饰指标或做出收益保证等不良学风；（3）确保特征归因与工程实现的规范性：TreeSHAP计算严格执行加和误差小于0.001的数学校验，API接口与前端代码采用模块化分层架构设计，确保系统具备良好的可读性、可测试性与扩展性；（4）紧密保持与指导教师的沟通汇报：严格遵循学校与学院制定的毕业设计时间进度节点，定期向刘尧指导老师汇报研究进展，根据导师指导意见积极迭代优化论文框架、实证图表与系统原型。"
]

SCHEDULE_ITEMS = [
    ("序号\t各阶段工作内容\t                                             起讫日期", True, 10.5),
    " 1\t明确论文任务与选题确认\t                                     2025年12月01日—2025年12月16日",
    " 2\t开展文献调研与撰写开题报告\t                                 2025年12月17日—2025年12月25日",
    " 3\t完成开题答辩与方案论证\t                                     2025年12月26日—2025年12月28日",
    " 4\t系统核心算法研发、实验验证与论文初稿撰写\t                   2025年12月29日—2026年02月28日",
    " 5\t论文中期检查与系统原型联调\t                                 2026年02月29日—2026年03月15日",
    " 6\t完成系统优化与论文多轮修改完善\t                             2026年03月16日—2026年04月05日",
    " 7\t完成论文复制比检测与定稿验收\t                               2026年04月06日—2026年04月15日",
    " 8\t参加毕业论文（设计）答辩\t                                   2026年04月16日—2026年04月30日",
    " 9\t答辩后材料整理、归档与总结\t                                 2026年05月01日—2026年05月25日"
]

REFERENCES = [
    "Ke G, Meng Q, Finley T, et al. LightGBM: A highly efficient gradient boosting decision tree[C]//Advances in Neural Information Processing Systems (NeurIPS 2017). Long Beach: Curran Associates, Inc., 2017, 30: 3146-3154.",
    "Lundberg S M, Lee S I. A unified approach to interpreting model predictions[C]//Advances in Neural Information Processing Systems (NeurIPS 2017). Long Beach: Curran Associates, Inc., 2017, 30: 4765-4774.",
    "Lundberg S M, Erion G, Chen H, et al. From local explanations to global understanding with explainable AI for trees[J]. Nature Machine Intelligence, 2020, 2(1): 56-67. DOI: 10.1038/s42256-019-0138-9.",
    "Gu S, Kelly B, Xiu D. Empirical asset pricing via machine learning[J]. The Review of Financial Studies, 2020, 33(5): 2223-2273. DOI: 10.1093/rfs/hhaa009.",
    "Fama E F, French K R. Common risk factors in the returns on stocks and bonds[J]. Journal of Financial Economics, 1993, 33(1): 3-56. DOI: 10.1016/0304-405X(93)90023-5.",
    "Harvey C R, Liu Y, Zhu H. … and the cross-section of expected returns[J]. The Review of Financial Studies, 2016, 29(1): 5-68. DOI: 10.1093/rfs/hhv059.",
    "Akiba T, Sano S, Yanase T, et al. Optuna: A next-generation hyperparameter optimization framework[C]//Proceedings of the 25th ACM SIGKDD International Conference on Knowledge Discovery & Data Mining. Anchorage: ACM, 2019: 2623-2631. DOI: 10.1145/3292500.3330701.",
    "López de Prado M. Advances in financial machine learning[M]. Hoboken: John Wiley & Sons, 2018.",
    "Newey W K, West K D. A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix[J]. Econometrica, 1987, 55(3): 703-708. DOI: 10.2307/1913610.",
    "Järvelin K, Kekäläinen J. Cumulated gain-based evaluation of IR techniques[J]. ACM Transactions on Information Systems, 2002, 20(4): 422-446. DOI: 10.1145/582415.582418.",
    "Caruana R, Lou Y, Gehrke J, et al. Intelligible models for healthcare: Predicting pneumonia risk and 30-day hospital readmission[C]//Proceedings of the 21st ACM SIGKDD International Conference on Knowledge Discovery and Data Mining. Sydney: ACM, 2015: 1721-1730. DOI: 10.1145/2783258.2788613.",
    "Fischer T, Krauss C. Deep learning with long short-term memory networks for financial market predictions[J]. European Journal of Operational Research, 2018, 270(2): 654-669. DOI: 10.1016/j.ejor.2017.11.054.",
    "Burges C, Shaked T, Renshaw E, et al. Learning to rank using gradient descent[C]//Proceedings of the 22nd International Conference on Machine Learning. Bonn: ACM, 2005: 89-96. DOI: 10.1145/1102351.1102363.",
    "周志华. 机器学习[M]. 北京: 清华大学出版社, 2016.",
    "顾明, 廖理, 许宪春. 机器学习与中国股票市场选股[J]. 经济研究, 2021, 56(07): 120-136.",
    "姜富伟, 孟令超, 唐国豪. 机器学习与中国股票市场收益预测[J]. 系统工程理论与实践, 2022, 42(05): 1145-1162.",
    "姜富伟, 唐国豪, 马甜. 金融与财务机器学习[M]. 北京: 机械工业出版社, 2024.",
    "郑振龙, 孙清泉. 彩票类股票交易行为分析: 来自中国A股市场的证据[J]. 经济研究, 2013, 48(05): 128-140.",
    "陈小悦, 孙爱军. CAPM在中国股市的有效性检验[J]. 北京大学学报(哲学社会科学版), 2000(04): 28-37.",
    "杨博理, 贾芳. 量化炼金术: 中低频量化交易策略研发[M]. 北京: 机械工业出版社, 2017.",
    "胡杰. 基于机器学习的股票预测及股票推荐系统的设计与实现[D]. 北京: 北京交通大学, 2020.",
    "曹志. 基于LightGBM算法和投资者情绪的多因子量化选股和择时方案[D]. 长沙: 湖南大学, 2022.",
    "张宇. 基于机器学习的A股多因子量化选股策略实证研究[D]. 北京: 首都经济贸易大学, 2023.",
    "余柏翱. 基于机器学习的多因子量化选股策略研究[D]. 贵阳: 贵州大学, 2025.",
    "文晓婷. 基于LightGBM与XGBoost的ESG多因子选股择时策略实证研究[D]. 北京: 中央民族大学, 2025."
]

def format_run(run, font_name="宋体", size_pt=12, bold=False, color="000000"):
    run.font.name = font_name
    run.font.size = docx.shared.Pt(size_pt)
    run.font.bold = bold
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:ascii'), 'Times New Roman' if not bold else '黑体')
    rFonts.set(qn('w:hAnsi'), 'Times New Roman' if not bold else '黑体')
    rFonts.set(qn('w:eastAsia'), font_name)

def update_single_cell_text(cell, text, font_name="宋体", size_pt=12, bold=False, align="left"):
    for p in list(cell.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    p = cell.paragraphs[0]
    p.text = ""
    if align == "center":
        p.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
    elif align == "left":
        p.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.LEFT
    elif align == "right":
        p.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.RIGHT
    r = p.add_run(text)
    format_run(r, font_name=font_name, size_pt=size_pt, bold=bold)

def populate_cell_paragraphs(cell, items, pPr_template, is_numbered=False, num_id=None, default_size=12, line_spacing=None, before_pt=None):
    for p in list(cell.paragraphs):
        p._p.getparent().remove(p._p)
        
    for item in items:
        new_p = OxmlElement('w:p')
        new_pPr = copy.deepcopy(pPr_template)
        
        if line_spacing is not None:
            spacing = new_pPr.find(qn('w:spacing'))
            if spacing is not None:
                spacing.set(qn('w:line'), str(line_spacing))
                spacing.set(qn('w:lineRule'), 'exact')
        if before_pt is not None:
            spacing = new_pPr.find(qn('w:spacing'))
            if spacing is not None:
                spacing.set(qn('w:before'), str(before_pt))
                spacing.set(qn('w:beforeLines'), '0')
        
        if is_numbered and num_id is not None:
            numPr = new_pPr.find(qn('w:numPr'))
            if numPr is None:
                numPr = OxmlElement('w:numPr')
                new_pPr.insert(0, numPr)
            ilvl = numPr.find(qn('w:ilvl'))
            if ilvl is None:
                ilvl = OxmlElement('w:ilvl')
                numPr.append(ilvl)
            ilvl.set(qn('w:val'), '0')
            numId_elem = numPr.find(qn('w:numId'))
            if numId_elem is None:
                numId_elem = OxmlElement('w:numId')
                numPr.append(numId_elem)
            numId_elem.set(qn('w:val'), str(num_id))
            
            # compact references
            spacing = new_pPr.find(qn('w:spacing'))
            if spacing is not None:
                spacing.set(qn('w:before'), '40')
                spacing.set(qn('w:after'), '40')
                spacing.set(qn('w:line'), '300')
                spacing.set(qn('w:lineRule'), 'exact')
            
            sz = new_pPr.find(qn('w:rPr'))
            if sz is not None:
                sz_elem = sz.find(qn('w:sz'))
                if sz_elem is not None:
                    sz_elem.set(qn('w:val'), '21')
        else:
            numPr = new_pPr.find(qn('w:numPr'))
            if numPr is not None:
                new_pPr.remove(numPr)
                
        new_p.append(new_pPr)
        cell._tc.append(new_p)
        p_obj = docx.text.paragraph.Paragraph(new_p, cell)
        
        if isinstance(item, tuple):
            text, bold, size = item
        else:
            text = item
            bold = False
            size = default_size
            
        r = p_obj.add_run(text)
        format_run(r, font_name="宋体", size_pt=size, bold=bold)

def fix_table_widths(doc, doc_type="task"):
    # Fix Table 1 (remove 3rd cell & 3rd gridCol)
    t1 = doc.tables[1]
    if len(t1.rows[0].cells) > 2 and t1.rows[0].cells[2].text.strip() == '':
        cell2 = t1.rows[0].cells[2]._tc
        cell2.getparent().remove(cell2)
    grid = t1._tbl.tblGrid
    gridCols = grid.findall(qn('w:gridCol'))
    if len(gridCols) > 2:
        grid.remove(gridCols[2])
    
    # Adjust widths to exact usable width
    if doc_type == "task":
        # Task section 0 usable: 9070 dxa. Table 1: col 0 = 1701 dxa (85 pt), col 1 = 7369 dxa (368.4 pt)
        gridCols[0].set(qn('w:w'), '1701')
        gridCols[1].set(qn('w:w'), '7369')
        t1.rows[0].cells[0]._tc.tcPr.tcW.set(qn('w:w'), '1701')
        t1.rows[0].cells[1]._tc.tcPr.tcW.set(qn('w:w'), '7369')
        
        # Table 2 (main table in task doc): usable width is 9070 dxa (453.5 pt)
        # Original grid was: 1228, 752, 2087, 1740, 3686 (sum 9493 dxa)
        # Scaled to sum 9070: 1173, 718, 1994, 1663, 3522
        t2 = doc.tables[2]
        t2_grid = t2._tbl.tblGrid.findall(qn('w:gridCol'))
        new_widths = [1173, 718, 1994, 1663, 3522]
        for idx, w in enumerate(new_widths):
            t2_grid[idx].set(qn('w:w'), str(w))
        # Update row cells tcW
        for r in t2.rows:
            # check merged cells
            seen = set()
            for c in r.cells:
                if c._tc not in seen:
                    seen.add(c._tc)
                    # if single cell row (spans all columns)
                    if len(seen) == 1 and len(r.cells) == 5:
                        c._tc.tcPr.tcW.set(qn('w:w'), '9070')
    elif doc_type == "proposal":
        # Proposal Section 0 usable: 8306 dxa. Table 1: col 0 = 1700, col 1 = 6606
        gridCols[0].set(qn('w:w'), '1700')
        gridCols[1].set(qn('w:w'), '6606')
        t1.rows[0].cells[0]._tc.tcPr.tcW.set(qn('w:w'), '1700')
        t1.rows[0].cells[1]._tc.tcPr.tcW.set(qn('w:w'), '6606')
        
        # Table 2 in proposal: 1 column, Section 2 usable width is 8121 dxa (406.05 pt)
        t2 = doc.tables[2]
        t2_grid = t2._tbl.tblGrid.findall(qn('w:gridCol'))
        t2_grid[0].set(qn('w:w'), '8121')
        for r in t2.rows:
            r.cells[0]._tc.tcPr.tcW.set(qn('w:w'), '8121')

# ----------------- BUILD 任务书 -----------------
print("Generating 毕业论文（设计）任务书_完成稿.docx...")
shutil.copyfile(TASK_SRC, TASK_DST)
doc_task = docx.Document(TASK_DST)

# Table 0: Cover
t0 = doc_task.tables[0]
update_single_cell_text(t0.rows[0].cells[1], "基于LightGBM与特征归因的股票推荐系统", size_pt=12, bold=False, align="left")
update_single_cell_text(t0.rows[1].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(t0.rows[2].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(t0.rows[3].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(t0.rows[4].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(t0.rows[5].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(t0.rows[6].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(t0.rows[7].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(t0.rows[7].cells[3], "[待填写]", size_pt=12, bold=False, align="left")

# Table 1: Category
t1 = doc_task.tables[1]
update_single_cell_text(t1.rows[0].cells[1], "毕业论文 毕业设计（√） 社会调查报告 作品展示 毕业汇报演出 专业外文翻译 （在选定的类型上打√）", size_pt=12, bold=False, align="left")

# Table 2: Main Table
t2 = doc_task.tables[2]
update_single_cell_text(t2.rows[0].cells[1], "基于LightGBM与特征归因的股票推荐系统", size_pt=12, bold=False, align="left")
update_single_cell_text(t2.rows[1].cells[1], "科研课题 生产实际或经济建设（√） 其他 （在选定的类型上打√）", size_pt=12, bold=False, align="left")

pPr_task_std = copy.deepcopy(t2.rows[3].cells[0].paragraphs[0]._p.pPr)

TASK_CONTENT_PARAS = [
    "股票市场受宏观经济波动、产业政策调整、多方投资者博弈及非理性情绪等多重因素影响，呈现出强烈的非线性、高噪声与低信噪比特征。传统的量化多因子选股方法多依托线性多元回归或静态打分机制，难以自适应捕捉因子间的高阶非线性交互与市场状态跃迁；而深度神经网络等复杂黑箱模型虽具备较强的特征拟合能力，但极易在金融时序数据上发生过拟合，更缺乏模型决策的透明度与可解释性，难以满足投资决策审慎风控与金融合规监管的要求。此外，诸多学术与工程实践常因未来数据泄露（前视偏差）、忽视幸存者偏差或缺乏跨周期稳定性检验，导致样本外预测与回测效果严重失真。因此，如何构建一套兼具严密防前视设计、有效截面排序能力、透明特征归因与严谨业绩分解的股票推荐系统，是现代智能金融工程领域亟待解决的核心课题。",
    "针对上述痛点，本毕业设计以A股沪深300指数成分股为候选标的池，设计并实现一套“特征工程及行业中性化 → 训练期因子诊断 → LightGBM横截面排序推荐 → 贴合实盘回测与Alpha/Beta业绩归因 → TreeSHAP全局与个股特征归因 → FastAPI与Vue3全栈可视化交互”的全链路股票推荐系统原型。系统的核心任务是实现候选股票的横截面相对排序与Top-K推荐，而非预测股票的绝对上涨走势；模型输出二分类打分表示个股未来5个交易日收益跑赢当日截面均值的估计倾向，为量化投研人员与投资者提供兼具量化排序支撑与归因解释依据的决策参考。",
    "系统重点围绕以下五个核心模块展开设计与实证研究：（1）数据工程与防泄漏设计：采集沪深300成分股自2015年1月至2026年10月的日频量价与财务估值数据（共744,372条面板样本），特征清洗严格采用向前填充（ffill）并以个股自身历史中位数填补缺失值；财务报表数据严格按照法定披露截止日进行保守滞后对齐（一季报滞后至4月30日，年报滞后至次年4月30日）；标签定义为未来5个交易日个股收益（t+1开盘买入至t+5收盘）是否跑赢当日截面均值；按时间先后切分训练集、验证集与测试集，并在集合边界设置5个交易日的标签成熟期隔离（purging），彻底阻断前视偏差。（2）截面中性化与因子有效性检验：对技术指标、量价衍生指标与基本面因子在每个交易日截面上进行缩尾、行业去均值（行业缺失时退回全市场去均值）与Z-score标准化；在训练集内部通过截面Spearman秩相关（IC）、Newey-West HAC t统计量（ICIR×√截面数）及相关性分析（去冗余阈值|r|>0.7）进行因子诊断与筛选，选定ATR_ratio、MACD_norm、momentum_60d、OBV_zscore等有效因子；同时如实记录并分析基本面因子在大样本中性化后未能提供增量的实证现象。（3）LightGBM排序模型构建与时序验证：基于Optuna在训练集内部通过时序交叉验证（TimeSeriesSplit）开展超参数贝叶斯寻优；在测试集上评估AUC、NDCG@K与Precision@K，并与随机猜测、逻辑回归及随机森林基线进行对比；开展13轮步长为120交易日的推进分析（Walk-Forward滚动窗口验证），检验模型在不同市场周期下的稳定度。（4）Top-K组合回测与Alpha/Beta业绩归因：构建Top-K（K=10）等权持仓策略，每5个交易日调仓，按下一交易日开盘买入至第5交易日收盘卖出收益核算，扣除印花税、佣金及过户费，对比全市场排序与行业中性两种选股口径；将13个滚动窗口的预测信号按时间拼接为连续净值序列，对基准收益进行OLS线性回归归因，测算Jensen Alpha与Beta暴露，并分五等分市场状态检验超额收益来源。（5）TreeSHAP特征归因与原型系统开发：基于TreeSHAP算法在LightGBM原始log-odds空间进行全局特征重要性（Mean |SHAP|）与个股局部归因分解，严格进行加和一致性容差校验；基于FastAPI构建后端高性能REST API接口，基于Vue 3 + Vite + ECharts开发涵盖行情看板、数据工程、因子诊断、模型评测、滚动回测、业绩归因、全局解释与个股SHAP归因弹窗的前端交互界面，实现系统原型的完整交付。",
    "本研究秉持实事求是的科学态度，在设计与论文撰写中严格恪守以下规范与局限说明：一是如实报告实验结果，模型滚动AUC均值约为0.5095（38.5%的窗口低于0.5随机基线），LightGBM在排序指标上与随机森林处于统计不可区分的水平，论文不虚夸模型表现；二是深刻揭示业绩归因本质，策略Beta为1.1424（显著大于1），收益中约74%由市场Beta驱动，Jensen Alpha年化2.99%在统计上不显著（p=0.1904），分市场状态下超额随行情严格单调，确认超额源于高Beta风险敞口而非纯选股能力，结论符合A股半强式有效特征；三是明确数据与回测局限，历史成分股若缺乏动态调整生效期文件则存在幸存者偏差，回测成交未考虑滑点、冲击成本、涨跌停及停牌限制；四是严谨界定特征归因边界，SHAP值仅反映模型内部对特征的利用权重与边际贡献，不构成经济学因果解释或未来投资收益保证。"
]
populate_cell_paragraphs(t2.rows[3].cells[0], TASK_CONTENT_PARAS, pPr_task_std)

TASK_PLAN_PARAS = [
    "本项目遵循“理论探究与实证研究相融合、算法建模与系统工程相结合”的研究方案，总体技术路线划分为六个阶段：第一阶段（需求分析与方案设计）：调研量化选股与可解释人工智能（XAI）前沿文献，明确沪深300股票池截面推荐的业务定位与功能边界，制定全链路技术方案与数据防泄漏规范。第二阶段（数据工程与因子中性化）：构建面板数据预处理管道，完成缺失值向前填充、财报法定披露截止日保守滞后对齐、标签定义及5日时序隔离；实现逐日横截面缩尾、行业去均值中性化与标准化。第三阶段（训练期因子诊断与特征筛选）：在训练期计算候选因子的截面Spearman IC与Newey-West HAC t值，执行阈值过滤与相关性去冗余，深入剖析技术因子与基本面因子在截面上的表现差异。第四阶段（LightGBM建模与滚动时序验证）：运用Optuna结合时序交叉验证完成超参数调优，在测试集上开展多模型对比；设计并执行13轮Walk-Forward滚动窗口推进实验，统计跨期AUC分布与因子符号翻转情况。第五阶段（实盘级回测与业绩归因实证）：设计考虑交易摩擦成本的Top-K等权调仓回测机制，对比全市场排序与行业中性选股表现；对滚动拼接净值开展市场基准回归，解耦Jensen Alpha与Beta风险暴露，并按市场状态五等分检验收益单调性。第六阶段（TreeSHAP特征归因与系统原型交付）：在log-odds空间实现TreeSHAP全局与个股局部解释，严格执行加和一致性校验；采用FastAPI与Vue 3构建RESTful微服务与组件化前端，完成系统集成、联调与毕业论文撰写。",
    "本研究预期达成以下四项核心目标：（1）理论与方法目标：建立一套规范严密、杜绝前视偏差的A股量化排序建模范式，通过因子诊断、时序切分、滚动验证与Alpha/Beta业绩解耦，揭示机器学习在A股弱信号环境下的真实预测边界与市场有效性特征。（2）算法与模型目标：构建收敛稳定、支持时序交叉验证的LightGBM股票推荐模型，客观对比基线指标，完成13轮Walk-Forward推进实验，全面评估模型排序能力与跨周期平稳性。（3）可解释性与归因目标：实现基于TreeSHAP的特征归因模块，全局明确主要影响因子的贡献占比，局部实现个股推荐打分的透明化拆解，并通过加和性数学校验确保解释可信度。（4）工程系统与交付目标：完成一套功能完备、前后端分离的股票推荐与特征归因原型系统开发，输出规范的API接口与交互界面，提交包含真实可复现实验产物的高质量毕业设计论文。"
]
populate_cell_paragraphs(t2.rows[5].cells[0], TASK_PLAN_PARAS, pPr_task_std)

# References
pPr_task_ref = copy.deepcopy(t2.rows[17].cells[0].paragraphs[0]._p.pPr)
populate_cell_paragraphs(t2.rows[17].cells[0], REFERENCES, pPr_task_ref, is_numbered=True, num_id=1, default_size=10.5)

# Signature blocks
update_single_cell_text(t2.rows[20].cells[2], "\n\n\n\n教研室主任签字：                [待填写]年[待填写]月[待填写]日", size_pt=12, align="left")
update_single_cell_text(t2.rows[21].cells[2], " \n\n\n学院领导签字：                [待填写]年[待填写]月[待填写]日", size_pt=12, align="left")
update_single_cell_text(t2.rows[22].cells[2], "[待填写]年[待填写]月[待填写]日", size_pt=12, align="center")
update_single_cell_text(t2.rows[22].cells[4], "  [待填写]年[待填写]月[待填写]日", size_pt=12, align="center")

# Fix table widths & eliminate overflow
fix_table_widths(doc_task, doc_type="task")

doc_task.save(TASK_DST)
print(f"Saved & Formatted: {TASK_DST}")

# ----------------- BUILD 开题报告 -----------------
print("Generating 开题报告_完成稿.docx...")
shutil.copyfile(PROPOSAL_SRC, PROPOSAL_DST)
doc_prop = docx.Document(PROPOSAL_DST)

# Table 0: Cover
pt0 = doc_prop.tables[0]
update_single_cell_text(pt0.rows[0].cells[1], "基于LightGBM与特征归因的股票推荐系统", size_pt=12, bold=False, align="left")
update_single_cell_text(pt0.rows[1].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(pt0.rows[2].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(pt0.rows[3].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(pt0.rows[4].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(pt0.rows[5].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(pt0.rows[6].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(pt0.rows[7].cells[1], "[待填写]", size_pt=12, bold=False, align="left")
update_single_cell_text(pt0.rows[7].cells[3], "[待填写]", size_pt=12, bold=False, align="left")

# Table 1: Category
pt1 = doc_prop.tables[1]
update_single_cell_text(pt1.rows[0].cells[1], "毕业论文 毕业设计（√） 社会调查报告 作品展示 毕业汇报演出 专业外文翻译 （在选定的类型上打√）", size_pt=12, bold=False, align="left")

# Table 2: Main Table
pt2 = doc_prop.tables[2]
pPr_prop_body = copy.deepcopy(pt2.rows[1].cells[0].paragraphs[1]._p.pPr)

# Optimize spacing for balanced pagination: line=310 dxa (exact 15.5pt), before=120 dxa (6pt)
populate_cell_paragraphs(pt2.rows[1].cells[0], PURPOSE_AND_SIGNIFICANCE, pPr_prop_body, line_spacing=310, before_pt=120)
populate_cell_paragraphs(pt2.rows[3].cells[0], LIT_REVIEW, pPr_prop_body, line_spacing=310, before_pt=120)
populate_cell_paragraphs(pt2.rows[5].cells[0], RESEARCH_CONTENT, pPr_prop_body, line_spacing=310, before_pt=120)
populate_cell_paragraphs(pt2.rows[7].cells[0], METHOD_AND_MEASURES, pPr_prop_body, line_spacing=310, before_pt=120)
populate_cell_paragraphs(pt2.rows[9].cells[0], SCHEDULE_ITEMS, pPr_prop_body, line_spacing=310, before_pt=120)

# References
pPr_prop_ref = copy.deepcopy(pt2.rows[11].cells[0].paragraphs[0]._p.pPr)
populate_cell_paragraphs(pt2.rows[11].cells[0], REFERENCES, pPr_prop_ref, is_numbered=True, num_id=3, default_size=10.5)

# Signature blocks - elegant spacing
update_single_cell_text(pt2.rows[13].cells[0], "指导教师签名：\n[待填写]年[待填写]月[待填写]日", size_pt=12, align="left")
update_single_cell_text(pt2.rows[15].cells[0], "组长签名：\n[待填写]年[待填写]月[待填写]日", size_pt=12, align="left")

# Fix table widths & eliminate overflow
fix_table_widths(doc_prop, doc_type="proposal")

doc_prop.save(PROPOSAL_DST)
print(f"Saved & Formatted: {PROPOSAL_DST}")

# ----------------- PRECISION FORMATTING -----------------
print("Applying precision post-formatting to Task and Proposal...")
import subprocess

def apply_post_formatting():
    # 1. Format Task Doc
    doc_t = docx.Document(TASK_DST)
    t1 = doc_t.tables[1]
    grid = t1._tbl.tblGrid
    gridCols = grid.findall(qn('w:gridCol'))
    for col in gridCols[2:]:
        grid.remove(col)
    tblW1 = t1._tbl.tblPr.find(qn('w:tblW'))
    if tblW1 is not None:
        tblW1.set(qn('w:w'), '9070')
    t1.rows[0].cells[0]._tc.tcPr.tcW.set(qn('w:w'), '1701')
    t1.rows[0].cells[1]._tc.tcPr.tcW.set(qn('w:w'), '7369')
    grid.findall(qn('w:gridCol'))[0].set(qn('w:w'), '1701')
    grid.findall(qn('w:gridCol'))[1].set(qn('w:w'), '7369')
    
    t2 = doc_t.tables[2]
    tblW2 = t2._tbl.tblPr.find(qn('w:tblW'))
    if tblW2 is not None:
        tblW2.set(qn('w:w'), '9070')
    t2_grid = t2._tbl.tblGrid.findall(qn('w:gridCol'))
    new_grid_widths = [1173, 718, 1994, 1663, 3522]
    for idx, w in enumerate(new_grid_widths):
        t2_grid[idx].set(qn('w:w'), str(w))
    w_map = {
        '1228': '1173', '8265': '7897', '9493': '9070', '4579': '4375',
        '3686': '3522', '1980': '1891', '7513': '7179', '2087': '1994', '1740': '1663'
    }
    for r in t2.rows:
        for c in r.cells:
            tcW = c._tc.tcPr.find(qn('w:tcW'))
            if tcW is not None:
                old_w = tcW.attrib.get(qn('w:w'))
                if old_w in w_map:
                    tcW.set(qn('w:w'), w_map[old_w])
    doc_t.save(TASK_DST)

    # 2. Format Proposal Doc
    doc_p = docx.Document(PROPOSAL_DST)
    pt1 = doc_p.tables[1]
    p_grid = pt1._tbl.tblGrid
    p_gridCols = p_grid.findall(qn('w:gridCol'))
    for col in p_gridCols[2:]:
        p_grid.remove(col)
    tblW1_p = pt1._tbl.tblPr.find(qn('w:tblW'))
    if tblW1_p is not None:
        tblW1_p.set(qn('w:w'), '8306')
    pt1.rows[0].cells[0]._tc.tcPr.tcW.set(qn('w:w'), '1700')
    pt1.rows[0].cells[1]._tc.tcPr.tcW.set(qn('w:w'), '6606')
    p_grid.findall(qn('w:gridCol'))[0].set(qn('w:w'), '1700')
    p_grid.findall(qn('w:gridCol'))[1].set(qn('w:w'), '6606')
    
    pt2 = doc_p.tables[2]
    tblW2_p = pt2._tbl.tblPr.find(qn('w:tblW'))
    if tblW2_p is not None:
        tblW2_p.set(qn('w:w'), '8121')
    pt2_grid = pt2._tbl.tblGrid.findall(qn('w:gridCol'))
    pt2_grid[0].set(qn('w:w'), '8121')
    for r in pt2.rows:
        for c in r.cells:
            tcW = c._tc.tcPr.find(qn('w:tcW'))
            if tcW is not None:
                tcW.set(qn('w:w'), '8121')
                
    for row_idx in [1, 3, 5, 7, 9]:
        for p in pt2.rows[row_idx].cells[0].paragraphs:
            sp = p._p.pPr.find(qn('w:spacing'))
            if sp is not None:
                sp.set(qn('w:before'), '0')
                if qn('w:beforeLines') in sp.attrib:
                    del sp.attrib[qn('w:beforeLines')]
                sp.set(qn('w:after'), '40')
                sp.set(qn('w:line'), '310')
                sp.set(qn('w:lineRule'), 'auto')

    for p in pt2.rows[11].cells[0].paragraphs:
        sp = p._p.pPr.find(qn('w:spacing'))
        if sp is not None:
            sp.set(qn('w:before'), '0')
            if qn('w:beforeLines') in sp.attrib:
                del sp.attrib[qn('w:beforeLines')]
            sp.set(qn('w:after'), '20')
            sp.set(qn('w:line'), '250')
            sp.set(qn('w:lineRule'), 'auto')
            
    doc_p.save(PROPOSAL_DST)
    print("Precision post-formatting applied successfully.")

apply_post_formatting()

# ----------------- PDF CONVERSION -----------------
def convert_docx_to_pdf(src_docx, dst_pdf):
    print(f"Converting: {src_docx} -> {dst_pdf}")
    ps_script = os.path.join(BASE_DIR, "scripts", "convert_to_pdf.ps1")
    cmd = [
        "powershell",
        "-ExecutionPolicy", "Bypass",
        "-File", ps_script,
        "-src", src_docx,
        "-dst", dst_pdf
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    print("PDF Output:", res.stdout.strip())

TASK_PDF = os.path.join(OUTPUT_DIR, "毕业论文（设计）任务书_完成稿.pdf")
PROPOSAL_PDF = os.path.join(OUTPUT_DIR, "开题报告_完成稿.pdf")

convert_docx_to_pdf(TASK_DST, TASK_PDF)
convert_docx_to_pdf(PROPOSAL_DST, PROPOSAL_PDF)
print("All files generated and converted to PDF successfully!")

