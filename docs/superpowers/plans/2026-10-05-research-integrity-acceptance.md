# 研究来源校验与入口验收实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 或 superpowers:executing-plans 逐项执行；先核对实际文件与检查日志再勾选。

**Goal:** 修复第五／六轮研究接口中缺失的来源绑定、选择资格和预算约束，使错误来源在训练、预测或汇总前被拒绝。

**Architecture:** 来源校验集中到 `research_integrity.py`，研究资格与预算集中到 `research_gates.py`；已有加载器、CLI 和工作流调用这些入口。旧实验只读，历史模型允许有依据的第五至第六轮训练复用，不重新拟合，也不修改旧清单。

**Tech Stack:** Python 3.12、pandas、scikit-learn、joblib、SHA-256、pytest。

日期：2026-10-05（Asia/Shanghai）。依据：AGENTS、D-033、第五轮方案及第六轮方案；用户“按你的来”授权。普通实现无需再次确认。本项目没有 Git 仓库，不执行提交或创建工作树。

## 范围与验收口径

- 2026 保留行情／测试分区不读取；资金费率仅使用 EXP-063 已截断快照。风险与账户算法本轮保持原配置。
- 修复来源检查不代表旧策略盈利或全部方法有效。EXP-119 的 +14.9816541437466% 低于原 +15.00% 门槛，原失败继续保留。
- 不重跑已有18次账户回测。检查使用临时目录合成损坏／错配产物，以及只读加载现有模型；不得使用正式实验编号做测试或删除原实验。
- 文件完整性、输入语义、研究资格、账户行为、收益评价分别记录；不能因为 SHA 一致就宣称无未来泄漏、资金守恒或盈利已证实。

## Task 1：样本、特征与模型加载来源

文件：新增 `src/cryptoquant/models/research_integrity.py`；修改 `research_data.py`、`research_models.py`；检查 `tests/test_research_integrity.py`、`tests/test_research_models.py`。

- [x] 先写关键失败检查：缺失／失败清单、SHA 变动、越界路径、prepared 来源错配、特征顺序或训练边界错配；损坏模型在 `joblib.load` 前拒绝。
- [x] 实现 `verify_completed_experiment(root, id, expected_type=None) -> (directory, run_manifest)`：核对编号、类型、complete、清单绑定、产物 SHA、源码快照清单及文件，拒绝目录逃逸。仅对已知旧消融选择／报告允许没有源码与环境的受限结构，明确标记缺证；是否可作资格依据另由12输入矩阵复核决定，不对模型／数据／账户允许同类豁免。
- [x] 实现 `verify_prepared(root, id, cfg=None)` 和配置绑定：核对两政策、三币、12特征、资金费率截断来源。第五至第六训练复用仅限相同执行配置、政策语义、C 与时间窗口；不能任意忽略 research hash。
- [x] 加载样本／特征前查 SHA，加载后检查符号、行数、唯一 UTC 时钟和可获得时间。4h决策网格、标签政策及 label_end 严格小于 fit_end 仅用于选中训练样本；EXP-063连续小时特征按自身小时网格和无效／预热标志检查，不能删除或错误要求4h。不得将未来列传入模型。
- [x] 加载模型前查模型／参数／概率／标签文件和依赖；回读核对参数、scaler 样本数、训练范围及原训练概率，不重新 fit。新训练记录 prepared 清单 SHA。
- [x] 运行受影响检查并只读加载6个现有训练实验共18个模型，核对第五和第六配置兼容。需求与质量审查均通过；日志与最终源码版本证据见STATUS／WORKLOG，本条不表示全套测试或Task2完成。

Task1证据：`.cache/research-loaders-final5.log` 28 passed、`.cache/research-archived-load-verification-final.log` 第五18模型／第六net9回读（gross按范围拒绝）。随后独立审查小修的4项配置／prepared／缺证契约检查及5项特征原因／小时网格检查分别通过，日志`.cache/research-review-contract-green.log`、`.cache/research-feature-quality-final.log`；旧出场与新三成本执行检查另记Task3。2026未读、没有正式训练／账户实验。后续Task2变更不能自动沿用这些通过记录。

## Task 2：研究资格、完整矩阵与有限预算

文件：新增 `src/cryptoquant/models/research_gates.py`；修改 `research_workflow.py`、`research_models.py` 的训练入口、`research_reporting.py`、`cli.py`；检查 `tests/test_research_gates.py` 及受影响 CLI／研究报告检查。

- [x] 用临时产物复现未经选择的 R2025 训练／回测、错误 threshold 或政策、重复候选覆盖、缺失候选被跳过、预算超额；确认在 fit／行情加载前失败。
- [x] 第五轮选择必须索引完整16个唯一候选（2政策×2窗×4阈值），核验状态、配置、prepared／training 和摘要 SHA；登记的失败候选保留并判不合格，缺失记录不得静默略过。
- [x] 为 R2025 训练以及压力／R2025 回测提供 `--selection-experiment-id`。复核原选择的来源与资格；net 无合格候选时拒绝 R2025，旧 gross .64 仅允许明确失败对照。第六轮 base 消融绑定第五轮选定 net .50，压力只允许经过12组消融核验的冻结候选。EXP-114仅有evaluation／report／run_manifest，按受限历史适配核对全部12输入的唯一矩阵、SHA、配置、prepared／training及冻结参数，并保留其源码／环境缺证，不能伪称原选择已具备完整 provenance。
- [x] 预算按固定研究配置和 prepared 来源计数，失败账户尝试也计入；第五轮不超过30个，第六轮不超过18个。拒绝重复候选与改变配置逃避预算；已有超额／失败历史如实报出，不删除或重复使用编号。
- [x] 比较入口核对输入唯一键及所需矩阵，不能忽略缺失摘要；保存选择／输入清单 SHA。R2025 使用已核验的 EXP-063 funding_snapshot，不读取原始2026资金费率。
- [x] 方法评价默认“未验收”，只有独立证据支持时才明确通过；移除无条件 `method_valid=True`，研究报告用“已查看2025研究比较”。
- [x] 跑关键接口检查并只读审计 EXP-084 与 EXP-114 来源。不新建正式训练／账户实验，不重写历史选择报告。

## Task 3：有限出场检查与交接

Task2最终证据：独立需求／质量审查通过。四接口联合检查61 passed（`.cache/research-acceptance-final.log`）；最后仅补运行命令的实际选择／出场／数据参数后，对应3项检查通过（`.cache/research-command-record-green.log`）。`.cache/research-gates-readonly-current-20261005.json`核EXP-084／114完整输入及18项比较，保留账户预算30／30、18／18均拒绝新增。EXP-114历史缺自身配置、源码／环境仍明示，只具base资格；预算审计不能证明所有历史失败尝试从未丢失。最终源码与证据SHA见`.cache/research-acceptance-final-20261005.json`，细节见WL-031；不表示策略盈利或全项目检查通过。

文件：必要时新增 `tests/test_exit_execution_acceptance.py`；更新 README、STATUS、WORKLOG 及本计划。

- [x] 阅读现有出场检查，针对未覆盖的实际执行路径补足一组小型合成检查：收盘触发、次小时跳空开盘可亏损成交、费用计入、成交后冷却和同根禁止重买。原4项与新增三成本3项实际通过，未改风险／账户算法。
- [x] 按原第六轮量化标准对既有摘要只读核对，记录 strict W2 未过线；证据`.cache/sixth-stress-acceptance-20261005.json`。接口检查与收益评价分开写。
- [x] 更新 README 为真实存在的参数与明确不可重用的编号示例；STATUS 写已修复、仍未验收与下一步，WORKLOG 追加本轮实际证据。
- [x] 完成后准备第七轮市场状态过滤的具体 Spec／Plan，冻结少量候选与无未来状态输入。第七轮实施／收益回测不计作本修复计划已完成工作。

## 运行与完成标准

针对性命令（文件存在且实现后执行，不假定预先通过）：

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_research_integrity.py tests/test_research_models.py tests/test_research_gates.py tests/test_research_reporting.py -q -W error --basetemp .cache/research-acceptance-tests
```

独立检查应使用独立 basetemp，不能并发清理同一目录。若新增执行检查，单独运行其文件；已有无关模块不重测。pytest 通过仅证明被测行为，不代表全项目套件、独立样本外或收益目标通过。

完成标准：实际拒绝以上错误路径，现有合法训练可回读且训练语义一致，选择与预算门禁接入真实入口，旧产物保持不变；证据、未解决历史缺失和下一行动足够供新 agent 接手。
