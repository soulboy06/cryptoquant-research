# 模型样本、训练与验证实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 在当前对话顺序实施。用任务复选框记录实际进度；用户要求减少不必要测试，未改动的既有模块不重复验证。当前没有Git，不建立worktree或提交；正式实验冻结源码、配置和SHA。

**Goal:** 把已核验行情转成无未来信息的九特征／四小时标签，训练三币逻辑回归，并用2025验证交易结果判断是否值得进入冻结与保留测试。

**Architecture:** 特征、训练标签、拟合／预测和交易执行分开。复用已有数据证据与共同账本；新策略只提供决策目标，订单／费用／风控沿用原引擎。先交付development训练样本，再实现模型和validation接口，保留测试需要额外冻结流程与预定筛选条件。

**Tech Stack:** 现有Python3.12、pandas、numpy、pyarrow、Decimal、pytest；拟合阶段才安装scikit-learn并锁定实际版本。当前不新增深度学习框架或GPU依赖。

---

日期：2026-10-04（Asia/Shanghai）。依据：[首轮有效方案](../specs/2026-10-04-first-experiment-design.md)、[停机补充v2](../specs/2026-10-04-halt-aware-data.md)、[用户测试偏好D-022](../../../DECISIONS.md)。本文是执行计划，不是训练或验证成绩。

## 实施批次与文件

本轮先实施任务1—2并实际生成训练样本；不为样本准备安装模型依赖、不读取validation/test Parquet、不运行收益实验。后续任务3—5分别交付模型训练与验证；冻结／保留测试只按任务5门槛继续，不能因本计划存在就自行打开测试。

| 文件 | 职责 |
| --- | --- |
| `src/cryptoquant/models/features.py` | 按已经可获得的收盘历史计算九特征／有效性，不构造未来答案 |
| `src/cryptoquant/models/samples.py` | 按UTC四小时决策取训练样本，构造五小时日历窗口标签，严格剔除跨界及停机 |
| `src/cryptoquant/models/workflow.py` | build-samples离线入口、独立编号／冻结来源与输出，不安装依赖或调用交易所 |
| `src/cryptoquant/models/training.py`（后续创建） | 三币分别拟合、模型与scaler保存、冻结预测与诊断 |
| `src/cryptoquant/models/selection.py`（后续创建） | 九候选完整比较、合格判断、预定排序与选择记录 |
| `src/cryptoquant/baselines/{engine,io,reporting}.py`（后续修改） | 共用执行与指标接口支持明确评价期间／决策目标；保持旧development行为 |
| `src/cryptoquant/cli.py` | 本轮新增build-samples；后续train／validate命令另按任务3—5加入 |
| `tests/test_training_samples.py` | 本轮四个核心行为检查：历史／数值、停机、标签边界、离线CLI |

旧EXP-003数据、EXP-004／005结果冻结；数据已核验，不重新下载、重复检查全部归档或重跑开发基准。当前源码变更后，旧临时脚本的“当前源码与旧快照相同”断言不适用，不能据此判定旧结果失效。

## 任务1：九特征与历史有效性

- [x] 创建models包及`features.py`，接口`build_features(frame)`，每币单独计算；输入是已核验连续日历分区，含744小时预热和仅开盘终点。顺序／唯一时间、交易对和状态不合法时失败。
- [x] 输出symbol、feature_open_time、decision_time、feature_available_time、history_count、feature_valid／invalid_reason和九个浮点特征。decision_time为该小时结束的下一整点；只有真实observed且available_time不晚于该决策时刻才有效。不能把终点开盘行当已收盘。
- [x] 每个连续observed片段独立计算；no_trade／halt重置，累计744个观察后才允许信号。仅用历史行的状态判断特征可用性，不用当前成交小时最终状态／成交量作预测特征。
- [x] 固定九特征：close/close.shift(h)-1，h=1/4/24/72；24个一小时收益的样本标准差ddof=1；(high-low)/close；quote_volume/前24根quote_volume均值-1（均值shift(1)排除当前）；close/EMA24-1与close/EMA72-1，EMA adjust=False。不搜索窗口、不静默填零，不跨片段shift或rolling。
- [x] 不足历史、零／无效分母及非有限值记录无效。未来信息检查修改输入末端以后行情，末端之前的特征必须不变；合成数值检查只验证一组有辨识度的预期值，避免逐函数机械测试。

## 任务2：训练标签、最小检查与真实样本

- [x] 创建`samples.py`，接口`build_training_samples(frame, start, end)`。只选decision_time位于[start,end)、UTC00/04/08/12/16/20且feature_valid的行；预热不计训练样本。
- [x] 标签在同币固定日历中读取entry=decision_time、exit=decision_time+4h的真实open：`label_return=open_exit/open_entry-1`，大于0为1，其余0。entry至exit的五个小时均observed且有open，不能压缩缺口后取后四行。比较方向用Decimal，特征／训练收益转换浮点。
- [x] 要求label_end严格早于end；训练截止2025-01-01 00:00 UTC，所以2024-12-31 20:00→终点00:00必须剔除。标签仅作为训练／事后预测诊断答案，不能成为同刻交易目标的可用输入。
- [x] 保留有效样本与被剔除决策的原因表；不对特征做标准化、不拟合或选择参数。样本按币保存Parquet，保留source_id、特征可获得时间、标签起止和数据／源码SHA。
- [x] 为任务1—2合并四项有意义的行为检查：已知数值＋未来不变性；停机／no_trade与744重启；真实四小时标签＋严格边界；离线CLI输出／编号拒绝及只读development。先确认缺实现失败，再最小实现后通过。命令：`.venv/Scripts/python.exe -m pytest tests/test_training_samples.py -q -W error`。CLI是改动接口，额外只运行既有离线CLI流程的相关检查，不运行全129项。
- [x] 新增`build-samples --config ... --data-experiment-id EXP-003 --experiment-id EXP-xxx`。复用development证据加载，不能读取另外两个分区；无网络／resume，既有目录拒绝，失败状态／日志保留。与backtest相同冻结代码、配置、环境与数据SHA；不覆盖任何旧实验。
- [x] 四项检查通过后，先在EXPERIMENTS登记下一真实编号（目前EXP-006）为“训练样本准备”，再实际运行：`python -m cryptoquant build-samples --config configs/first_experiment.toml --data-experiment-id EXP-003 --experiment-id EXP-006`。保存sample_manifest／report、每币training_samples与excluded_decisions、源码／配置。数量、标签比例、失效原因以实际计算填写，不捏造收益。

## 任务3：三个币的模型拟合／预测

- [x] 安装兼容现有环境的scikit-learn，锁定实际版本并运行pip check，不重复安装现有行情／绘图库。只在拟合阶段引入；版本不猜测，不加载不可信外部模型文件。
- [x] 核对样本SHA／边界／特征顺序；三个币各用独立`StandardScaler + LogisticRegression`。参数沿用L2、lbfgs、max_iter=1000、class_weight=None、random_state=42；C取0.1/1/10，全部币共享同一候选C，不能逐币择优组合。
- [x] 每个C只拟合一组3个模型，总计9个模型；0.55/0.60/0.65阈值共享该C的预测，不重复拟合。scaler只fit训练样本，不fit验证；样本单类或不收敛时该拟合失败，保留记录，不能静默增加迭代／更换算法。
- [x] 关键检查只保留训练／验证隔离（验证扰动不改变训练scaler／模型）、概率与同刻信号未来不变性。保存每币有效样本数、类别数量、特征顺序、模型／scaler、训练区间、依赖／参数／SHA及失败信息。
- [x] 正式训练前登记独立实验编号，关联EXP-006；不因“生成样本”已经完成就称为模型训练完成。阈值按验证交易成绩选择，训练分类准确率不作为盈利筛选。

## 任务4：共用执行引擎的validation接口

- [ ] 给engine／io／reporting引入明确`period`与外部决策目标接口，不复制一套账本。旧development默认、买入持有／EMA行为保持一致。先用一组短合成周期检查旧默认与新接口一致、终点费用／清算和UTC时间；只有接口变更引发疑问才重跑旧模块或真实基准。
- [ ] validation只加载EXP-003三份validation Parquet及所需预热，不加载test。训练样本不从该数据拟合；终点严格为2025-12-31 20:00 UTC，终点仅开盘清算，不能改成2026-01-01或用那里的价格评价。
- [ ] 概率预先按当时已可获得历史生成，决策表只含symbol、decision_time、probability和target_weight，不含未来标签；未预热／无效特征目标None以保持持仓，风险退出独立生效。模型按阈值≥给30%否则0，与EMA共用8%止损／4h冷却，独立100账户。
- [ ] 报告按评价期输出年度或季度分段，复用既有费用／回撤／周期指标，不硬编码开发期年份。只为新时间接口做必要检查，不重测未改动的Decimal账本。

## 任务5：完整验证与筛选；保留测试继续受控

- [ ] 所有九配置按C／阈值完整列出，每个候选／成本／期间用独立100账户和已登记编号保存结果（编号正式运行前分配，不能提前登记为完成）。基准验证两组也分别登记，不能把2022—2024成绩替代2025比较。
- [ ] 选参仅看base成本验证：净收益>0、最大回撤≤25%、底线次数0、闭合周期≥30。合格中期末净值最高，再依次较小回撤、较低成交额、较小C、较高阈值；排序关键检查用一次明确的平局例子即可。九候选失败／不合格也完整保留。
- [ ] 固定同一参数后记录三个成本情景，不按压力成绩重新选C／阈值。按首轮规则报告ROC-AUC、Brier、准确率，仅使用该评价期内到期有效标签；不完整诊断不能用来改交易结果。
- [ ] EMA独立判断同样验证门槛。全部主动策略不合格时结论“验证未通过”，不打开test。模型不合格而EMA合格，只安排EMA／买入持有测试。模型合格时安排模型、EMA和持有同一测试期，EMA不合格也保留为对照但无候选资格。
- [ ] 先生成冻结记录：选定参数、验证全部结果、数据／代码／环境SHA、拟合截止、测试范围／成本及是否获准按既定协议进入测试。重新拟合只用2022起且label_end严格早于2025-12-31 20:00的样本，冻结后才加载test；初次选择时不能借用2026任何特征拟合或标签。
- [ ] 2026测试按首轮方案只评价一次同一冻结模型／规则，各独立100账户；不再训练、不依测试调参。当前这批计划与样本实施不创建test命令或开启其收益评价。若后续实现冻结／测试模块，另补明确实施步骤与检查，不从CLI参数自行绕过。

## 验证工作量与交付

每批围绕真实风险选择少量综合行为检查；新修改后只跑受影响项，通过即继续。文档只检查链接与当前状态，不另写文档测试。没有用户要求或实际疑问，不新增基准性能测量、重复哈希扫描、逐行数学镜像测试或连续多轮审查。正式实验本身的有限一致性检查随运行完成，不与同一数据的大规模重新核验重复。

每个批次完成后同步AGENTS索引、STATUS实际事实与下一行动、EXPERIMENTS真实登记、WORKLOG，以及README已可用命令；决策变化追加DECISIONS。尚未训练／验证、失败、未合格和盈利要分别表述。

## 2026-10-04首批完成记录

任务1—2已实现并运行EXP-006；新样本4项＋受影响CLI2项共6 passed（2.71s），未重复旧基准／全套测试。一次精简计划复查与静态代码复查均无Critical／Important。三币各6,387有效样本、189剔除；模型未拟合，validation/test未读取。实际结果见[EXP-006报告](../../../artifacts/experiments/EXP-006/report.md)，下一工作为任务3，不重复生成样本。

## 2026-10-04模型训练完成记录

任务3已实现并实际运行EXP-007；三个币各三组C，共9份模型与scaler，均正常收敛并保存／重载核对。sklearn1.9.1等实际版本已锁，pip check无冲突；训练核心4项＋受影响CLI1项共5 passed（3.42s），一次静态复查无Critical／Important。未重复旧基准或全套。训练准确率52.25%—53.58%只是训练内诊断，不选择C／阈值。实际证据见[训练报告](../../../artifacts/experiments/EXP-007/report.md)与[核对](../../../artifacts/experiments/EXP-007/verification.json)。下一步任务4，validation交易接口尚未实现；当前没有读取评价分区或开启test。
