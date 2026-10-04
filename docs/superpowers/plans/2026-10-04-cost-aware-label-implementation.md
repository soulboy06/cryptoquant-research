# 第五轮成本感知标签 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Inline execution is the default here; any review delegation follows the applicable skill and does not create a new chat.

**Goal:** 比较4小时毛方向标签与base扣费盈利标签，按时间训练和固定窗口评价，区分技术过线、相对改善和用户长期平均周净收益1.5%的目标。

**Architecture:** 保持原Config、数据验证与共用账本；新增研究配置、标签政策、已校验数据准备和三币模型产物适配。给原事件引擎增加受控窗口边界，交易信号使用从原连续历史计算的特征。独立研究入口管理有限候选、选择记录、周统计和失败证据，旧CLI行为与冻结实验保持可读。

**Tech Stack:** 既有Python 3.12独立环境、pandas、Decimal、scikit-learn、joblib、Parquet／TOML／JSON；不增加依赖。

---

日期：2026-10-04（Asia/Shanghai）。依据[第五轮方案](../specs/2026-10-04-cost-aware-label-design.md)，用户对方案回复“可以／继续”。本计划2026-10-04独立计划／源码审查Approved后开始实施；Task 1／2基础接口完成且检查／需求／质量审查通过；Task 3—6尚未完成，按实际完成勾选。当前无Git，不创建仓库／worktree，不执行提交；以实验源码快照与SHA保存版本。用户D-022精简检查优先于技能中的机械测试／重复全套检查要求。

## 实施前接口事实与安全边界

- `Config`固定开发2022—2024／验证2025／测试2026，`load_period`会核对EXP-003原配置时间与分区SHA。不要改Config日期绕过验证，不改原分区。
- `samples.py`与`evaluation_labels`目前只生成gross方向标签；`training.py`仅fit显式特征列，`load_training_samples`验证development边界；旧训练产物固定三币×三C共9模型。第五轮C固定0.1，不能将新3模型manifest塞入旧9模型加载器。
- `build_probabilities`默认从传入行情重算指标；仅截取窗口744小时再重算EMA会改变同时间特征。本轮须先在原分区完整连续历史计算特征，再按决策时间切片，交易引擎则使用窗口行情视图。
- `period_bounds`只接受development／validation；`validate_frames`与报告都调用它。增加受控window须覆盖引擎、验证、年度／季度／周统计全部调用点；未知窗口及2026仍拒绝。
- `decision_targets`与旧CLI阈值表不含0.40／0.50。本轮研究入口需要自己的有限阈值校验，不能误用旧全局THRESHOLDS扩大搜索范围。
- 以上描述是计划编写时的接口起点；已实现范围按任务勾选及STATUS核对。research命令仍不存在，实现且对应检查通过后才能执行。正式编号仍从EXP-063现场核对，不提前预占。

## 文件职责

下表定义实施目标；实际存在和可用的范围以任务勾选及STATUS为准，不能据此直接运行research命令。

| 文件 | 职责 |
| --- | --- |
| `configs/fifth_experiment.toml` | 研究配置，引用冻结执行配置、标签政策、C=0.1、有限阈值、周目标与预算 |
| `src/cryptoquant/models/research_config.py` | 读取并校验研究配置，固定W1／W2／R2025元数据；基础执行Config仍由原load_config读取 |
| `src/cryptoquant/models/labels.py` | 两种标签的Decimal公式、标签语义与成本元数据校验 |
| `src/cryptoquant/models/research_data.py` | 原数据与EXP-021 SHA核对、资金费率历史快照、连续特征与标签派生、研究样本加载 |
| `src/cryptoquant/models/research_models.py` | 每政策／每窗口三模型fit、scaler、模型卡、重载与语义校验 |
| `src/cryptoquant/baselines/windows.py` | 从已校验原分区构造744h历史与仅开盘终点的窗口视图，不修改原行情 |
| `src/cryptoquant/models/research_reporting.py` | 周指标、W1／W2选择、三层结论及比较报告 |
| `src/cryptoquant/models/research_workflow.py` | 准备／训练／评价／选择／比较五个阶段的实验生命周期和依赖检查 |
| `tests/test_cost_labels.py` | 盈亏平衡、旧／新标签兼容与语义拒绝 |
| `tests/test_research_windows.py` | 受控窗口、连续指标、资金／终点及未来信息隔离 |
| `tests/test_research_models.py` | fit边界、三模型持久化、来源／标签政策错配 |
| `tests/test_research_reporting.py` | 周端点、排序、预算／停止条件、目标未达时的正确报告 |

只按任务修改`samples.py`、`predictions.py`、`training.py`、`workflow.py`、`training_workflow.py`、`validation_workflow.py`的标签声明／兼容检查，及`baselines/periods.py`、`engine.py`、`reporting.py`的窗口参数，`cli.py`的新research入口。不重构资金／下单／风控算法，不改已有实验目录。

## Task 1：研究配置与精确标签政策

**Files:** 创建`configs/fifth_experiment.toml`、`models/research_config.py`、`models/labels.py`、`tests/test_cost_labels.py`；按需修改`samples.py`、`predictions.py`、旧工作流的manifest标签声明。

- [x] **Step 1：新增一个边界行为检查，先运行确认尚不支持。**检查净标签在精确盈亏平衡、其上下附近和负收益的结果；同时覆盖毛方向标签保持原值、未知政策／费用语义错配拒绝。测试数据为合成Decimal价格，不读市场。
- [x] **Step 2：实现单一标签函数与政策验证。**建议接口`label_values(entry, exit, policy, fee=None, adverse=None)`，返回`label_return`、`label_net_return_text`与`label`；gross政策不需要成本，net政策必须使用base f／s。精确判断采用下述价差代数形式，避免除法舍入将盈亏平衡分为正样本；净收益文本仍计算原公式。

```python
net_factor_numerator = exit * (Decimal('1') - fee) ** 2 * (Decimal('1') - adverse)
net_factor_denominator = entry * (Decimal('1') + adverse)
label = int(net_factor_numerator > net_factor_denominator)
net_return = net_factor_numerator / net_factor_denominator - Decimal('1')
```

Decimal精度必须覆盖原价格有效位与以上有限乘积，统一局部足够精度后再比较；不能用四舍五入0.30%或float比较。正价格、f／s有限且0<=值<1、政策已知，否则失败。净政策的成本卡须精确f=0.001、s=0.0005、horizon=4。

- [x] **Step 3：添加研究配置，不改变原Config时间。**配置示例：

```toml
execution_config = "second_experiment.toml"
label_policies = ["gross_direction_v1", "net_positive_base_v1"]
C = "0.1"
thresholds = ["0.40", "0.50", "0.60", "0.64"]
weekly_target = "0.015"
max_account_runs = 30
windows = ["W1", "W2", "R2025"]
```

引用路径相对研究配置目录，解析后限于项目`configs/`；校验无未知键、以上固定政策／候选／预算与顺序，模型为12特征LR，执行Config的100／50／30%／8%／4h与三档成本符合方案。新字段不能混入原`load_config`。记录原执行配置SHA和研究配置SHA，两者各自来源明确。

- [x] **Step 4：统一标签语义，不改旧冻结结果。**旧新生成sample／train／概率metadata明确gross政策；没有政策字段的旧自产`training_samples`／`model_training`产物，只能以明确的兼容分支解释为gross，未知类型／政策失败。旧加载器默认仅允许gross，新净模型需通过研究加载器，防止净样本进入旧训练接口后冒充上涨概率。`evaluation_labels`支持显式政策，但未来标签与概率交易表分开；原默认gross行为保持一致。
- [x] **Step 5：只跑Task 1相关检查。**命令：`.venv/Scripts/python.exe -m pytest tests/test_cost_labels.py -q -W error`，预期行为检查通过；如果触及旧加载器，追加现有样本／模型manifest兼容检查，按实际测试名称选择，不重跑全部训练实验。标签库无需模型训练。

## Task 2：受控窗口与连续特征接口

**Files:** 创建`baselines/windows.py`和`tests/test_research_windows.py`；修改`baselines/periods.py`、`engine.py`、`reporting.py`，为模型预测增加从已计算特征生成概率的受控函数（`research_models.py`或`predictions.py`）。

- [x] **Step 1：写合成窗口检查并确认未实现时失败。**一个组合测试覆盖窗口日期、744h日历、终点未来字段屏蔽、旧default行为、未知window与跨2026拒绝；另一个测试用长EMA历史／停机恢复比较切窗前后同时间特征，并扰动后续行情确认过去特征不变。不得为窗口剪裁重新初始化EMA或停机计数。
- [x] **Step 2：定义仅允许的window参数。**`period_bounds(config, period, *, window=None)`：None保持旧行为；development/W1=UTC2023-01-01至2024-01-01，development/W2=2024-01-01至2025-01-01，validation/R2025=原2025验证边界。各边界须包含于相应原分区，其他组合拒绝，不能自由输入datetime或test。原`load_period`仍用None验证和加载原分区，不用window改原Config。
- [x] **Step 3：建立行情视图与预测特征的两条明确路径。**`window_frames(verified_frames, config, period, window)`只在已核对原分区上拷贝`[start-744h,end]`，重写row_role并将最后一行除symbol、open_time、open、source_id、row_role、market_state外全设空，保留停机行空价格。预测用原分区连续历史预先算出的特征，只截决策`[start,end)`，每行feature_available_time<=decision_time；不把行情视图重算的EMA当模型输入。明确完整特征历史以原分区及特征版本为依据，W1／W2同时间输出须匹配EXP-021有对应样本的历史特征。
- [x] **Step 4：让引擎、摘要与报告传递同一个window。**`BacktestResult`新增可选window字段；`validate_frames`、`run_backtest`与reporting调用`period_bounds(...,window=result.window)`。报告start/end、年度／季度清算、净值和所有预测目标必须同一窗口。旧默认None结果不改。成交、费用、风控、公共资金预算与四列decision_targets校验不变。
- [x] **Step 5：核对窗口资金与端点。**合成账户检查起点独立100、先卖后买共享资金、末端退出与双边费用及尾差守恒；用同一窗口人工目标与模型目标验证相同账本结果。只运行本轮window测试和原`test_period_interface_preserves_execution_and_terminal_fees`这个受影响行为检查，旧完整引擎检查未受影响时不重复。

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_research_windows.py tests/test_validation.py::test_period_interface_preserves_execution_and_terminal_fees -q -W error
```

## Task 3：准备两种标签数据与历史资金费率快照

**Files:** 创建`models/research_data.py`，补Task 1／2必要的真实来源校验；不改EXP-021样本或原分区。

- [x] **Step 1：实现准备阶段依赖检查。**通过原`load_period(root,EXP-003,execution_config,'development')`验证配置、政策、规则与Parquet SHA，再验证EXP-021 sample_manifest／各币sample SHA、12项特征、原样本边界和来源。拒绝任意外部路径、同币重复时间、未来输入列冒充特征与不一致价格方向。这里只读development；R2025行情等选择后才加载。
- [x] **Step 2：制作资金费率快照并核对连续特征。**核对EXP-021记录的资金费率源SHA；读取归档后截断到UTC2025-12-31 20:00并保存各币不可变副本及SHA、数量、最早／最晚时间，明确源完整文件含2026且为“读取后截断”。W1／W2特征仍仅按当时已结算时间向后asof匹配；拟合不得接触快照后期记录。development特征从原连续历史生成并核对EXP-021相同决策的12列；若不一致，停止并诊断版本，不将新旧标签混在不同特征上比较。
- [x] **Step 3：生成研究样本，不覆盖旧标签。**以EXP-021同一批有效时间／特征为基准，从development十进制开盘价重算gross与net标签；保留两者、净收益精确文本、entry／exit／label_end、剔除原因和政策成本卡，两政策的行集合一致。构造各窗fit视图时只取`decision_time>=2022-01-01`且`label_end<train_end`；未来列不能送入feature_matrix。评价的全部决策特征另存，包括特征无效但标签到期等情况，不能拿仅有效训练样本替代完整账户决策网格。
- [x] **Step 4：保存准备实验。**事先登记新EXP（当前预计EXP-063，现场核对），生成`prepared_manifest.json`、`samples/{policy}/{symbol}.parquet`、`features/{symbol}.parquet`、`funding_snapshot/{symbol}.parquet`、来源／配置／环境／源码SHA、类别诊断和report。训练数据type为`research_samples`，不伪装旧training_samples；状态running→complete或failed，失败保留且不能覆盖，源码快照记录原执行config并额外保存研究config。
- [x] **Step 5：执行前必要核对。**复用前两任务行为检查，仅新增一项准备流程集成检查：来源SHA、政策错配、完整目标网格、未来分区禁止读取与重复ID拒绝。通过后再运行实际准备一次，不拟合模型、不做账户评价；记录真实样本数与类比例，不能照抄EXP-021数量当新结果。

## Task 4：三币按时间fit与模型语义持久化

**Files:** 创建`models/research_models.py`与`tests/test_research_models.py`；复用`fit_model`和`predict_probabilities`，不改变原C_VALUES或训练求解器。

- [x] **Step 1：写两个关键模型检查。**一个验证只fit相应窗的样本、scaler只见训练行、label_end跨界剔除、模型输入没有gross／net答案；一个验证三模型重载概率一致，未知／错配政策、配置／数据SHA／窗口边界错误、标签单类及源码依赖不兼容拒绝。
- [x] **Step 2：实现显式三模型训练器。**`train_research_models(prepared_id,window,label_policy)`只接受固定C=0.1、12特征LR；W1 train_end=2023-01-01，W2=2024-01-01，R2025=2025-01-01。每币一模型，固定random_state42，fit遵守方案参数；不收敛／单类写失败，不换算法、不自动扩大年份。
- [x] **Step 3：实现研究模型加载器。**manifest type=`research_training`，恰好三个币，无缺漏／重复；核对prepared来源和政策成本卡、12特征顺序、C、scaler行数、训练起止／最晚label_end、Python／必要库版本和joblibSHA，重载核验一致。概率表附带独立manifest语义，CSV只保存symbol／decision_time／probability；净模型的probability含义为覆盖base理想成本的概率。旧EXP-022不能预测W1／W2；R2025旧标签只有全量训练、特征、配置、版本完全相同时才能复用其C=0.1模型，并记录来源，不把复用算新fit。
- [x] **Step 4：仅运行本轮模型检查。**命令`.venv/Scripts/python.exe -m pytest tests/test_research_models.py -q -W error`；按改动追加旧manifest政策兼容检查。没有修改旧求解器／账本，不跑全套旧训练测试。
- [x] **Step 5：真实fit分阶段登记。**准备成功后，W1／W2×两标签分别登记训练实验，每实验三个模型，总计12个币种模型。只有选择阶段新标签通过时，才登记R2025的两政策训练（最多另6个模型）；未通过则不运行R2025。报告训练诊断不能写成盈利成绩。

## Task 5：有限候选、周统计、冻结选择与研究比较

**Files:** 创建`models/research_reporting.py`、`tests/test_research_reporting.py`；必要窗口报告修改已在Task 2完成。

- [x] **Step 1：明确研究阈值与目标生成。**研究模块校验阈值仅为0.40／0.50／0.60／0.64，共用三币；使用预测概率生成0／30%或缺省保留目标，目标表严格只有symbol、decision_time、probability、target_weight。不可通过修改旧THRESHOLDS让旧CLI自动参与第五轮，也不得把事后net_return当probability。
- [x] **Step 2：实现周统计，写一个端点行为测试。**起点initial，内部每7天边界close，清算终点terminal；若缺少或重复相应phase，失败，不能选open替代。末段不足168h单列。准确使用实际窗口小时计算`g_week=(E1/E0)^(168/H)-1`；两个独立窗口合成排序值采用方案sum(log增长)/sum小时，输出“合成”标签，不伪装连续账户。测试用不同open／close／terminal值和残段验证口径，报告亏损完整周比例、最差完整周、陈旧估值与小时回撤限制。
- [x] **Step 3：实现选择规则，写一个边界／失败测试。**只接受两政策×两窗×四阈值共16个base账户实验的完整索引与对应失败记录；校验每次模型／prepared／窗口／标签／成本／阈值及完整SHA。每政策先按每窗base收益>0、回撤<=25%、周期>=30、底线0筛选，再按合成周收益降序、最差窗回撤升序、阈值降序。没有合格项就failed资格；旧标签可以固定0.64作失败对照，不替它恢复资格。冻结所选阈值与引用实验，higher／strict不重新选参。新政策不合格，selection须`do_not_run_R2025`，后续入口强制拒绝，不只是报告一句停止。
- [x] **Step 4：补比较报告。**先完成W1／W2选择，再对两政策选中策略运行每窗higher_execution／strict（最多8个账户）；旧政策无合格项时按0.64对照记录。严格情景亏损注明脆弱，仍可作已查看R2025研究比较但不能宣称达目标。新标签合格才训练／评价R2025，每政策所选阈值三档成本，共最多6个账户；不依据2025重选。EXP-049／059／060能精确匹配则复用，否则新登记；不能只因参数相同忽略特征来源／模型差异。
- [x] **Step 5：三层结论测试与实际报告。**方法有效、相对改善、达到每周1.5%分别计算。达到目标要求新模型三个窗口各base g_week>=0.015、strict收益>0、baseDD<=25%、>=30周期和底线0；相对改善逐窗比较base收益与回撤，不能只合并胜率。缺窗／未运行／无交易用明确状态，不填虚构0或True；一窗未达目标即未达。最大盈利集中与单币／月贡献取真实周期／尾差账本，沿用EXP-062核对口径，不用独立信号公式替代真实利润。
- [x] **Step 6：只跑报告相关检查。**`.venv/Scripts/python.exe -m pytest tests/test_research_reporting.py -q -W error`。选择／周端点／状态语义约3项综合行为检查足够，不给每个字段写机械测试。真实实验前校验索引和预算：最多16+8+6=30次账户模拟／18币种模型；候选失败或缓存复用减少实际次数，不为凑预算运行。

## Task 6：研究入口、实验执行和交接

**Files:** 创建`models/research_workflow.py`；修改`cli.py`与`tests/test_cli.py`；完成后更新README、STATUS、EXPERIMENTS、WORKLOG，决策变化再更新DECISIONS。

- [x] **Step 1：提供阶段明确的命令。**建议新入口`research-prepare`、`research-train`、`research-evaluate`、`research-select`、`research-compare`，分别调用上述模块。每命令需`--research-config`和唯一`--experiment-id`；prepared／training／selection等来源用明确experiment-id参数；不自动挑最新目录，不自动继续到下阶段。仅window W1／W2／R2025，不提供test／live参数。
- [x] **Step 2：确保执行有门槛。**W1／W2 base只能四个阈值；任何压力账户须complete selection且阈值等于该政策冻结值（旧失败对照0.64有独立标识）；R2025训练和账户都要求新政策通过滚动选择。prepared、training、selection、report相互校验来源配置／SHA与标签政策；不允许用外来账户成绩混入索引。合成／单类训练失败对应候选是失败／未运行，不假装16账户全完成。
- [x] **Step 3：生命周期与中断。**每实际命令运行前在EXPERIMENTS登记编号。新目录拒绝覆盖，running manifest包含命令、数据／配置／源代码／环境、label_cost卡、窗口、父子实验ID及SHA，完成后记录产物SHA；异常保留failure.json和failed。批次索引记录各训练／账户ID及状态，阶段成功后冻结一份索引及SHA，后续选择依冻结副本。无自动追加候选，无重用前次现金，后台任务标识与最后状态写STATUS。
- [x] **Step 4：最小入口集成检查。**新增一个合成端到端研究检查覆盖prepare→train→base→select→pressure的语义流和失败停止；不读取真实市场。追加现有无账户／live命令检查，确认旧CLI仍拒绝未知参数与test。只按已修改模块跑前述必要集合，不重复旧全套测试或61个收益实验。若改变资金／费用接口或出现新失败，再扩大受影响检查。
- [x] **Step 5：按顺序实际执行，不能现在运行以下计划命令。**编号须现场分配，以下变量不是已完成实验；每阶段完成即维护STATUS检查点：

```powershell
# 仅实现并检查通过后，登记新编号再运行。不要把变量示例当现有实验。
$researchPreparedId = 'EXP-063' # 现场核对；如被占用，使用登记表下一个编号
& .\.venv\Scripts\python.exe -m cryptoquant research-prepare --research-config configs/fifth_experiment.toml --data-experiment-id EXP-003 --source-sample-experiment-id EXP-021 --experiment-id $researchPreparedId
# training／evaluation／selection编号随后逐个登记，分别用显式父实验ID调用对应命令。
```

实现时在README写完五个入口真实参数与示例；任务未完成时不要发布不存在的命令。执行顺序严格为prepare→W1/W2两政策训练→16个base或失败记录→select→最多8压力→若新标签合格才R2025训练／最多6账户→compare。每个账户依同C／同政策模型共用一次概率预测，不重复fit，不按压力成本重算训练标签。

- [x] **Step 6：文档与完成证据。**登记真实样本／拟合／账户数、所有候选／失败／未运行与源码版本、基础配置与研究配置、fit标签边界、成本与周收益口径；补本计划已实际完成的勾选。说明每周1.5%只是用户目标，研究改善／目标达到／未来能力分别表述。下一步看真实成绩，2026仍封存；正式test冻结、重新拟合及入口是另一个工作包，不能在本轮默认开启。

## 完成标准与交接

实现完成须有新政策／旧政策语义隔离、精确标签、同时间特征一致、两窗fit边界、账本／费用／周端点检查及实际产物SHA证据。实验阶段完成须有所有已运行／失败／未运行的明确登记与按方案的三层结论；即使新标签失败，也算本轮实验流程完成，不算盈利目标完成。

本计划Task 1至Task 6全部任务均已实现并执行完成。EXP-063~EXP-101实验已完整运行生成产物与报告。2026测试分区继续严格封存，未接入真实交易。详细结论见[EXP-101报告](../../../artifacts/experiments/EXP-101/report.md)。
