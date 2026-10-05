# 第七轮市场状态买入过滤实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 或 superpowers:executing-plans；逐项核对实际成果后勾选。

**Goal:** 用已收盘 BTC 状态控制三币买入，比较 R1 与现有 C2 的扣费收益、回撤和机会损失。

**Architecture:** 独立状态模块输出因果状态表，预测模型保持12特征；引擎仅在 BUY 执行许可处过滤，原 SELL 与风险逻辑沿用。独立第七轮配置及来源门禁绑定状态、模型和复用对照，预算最多9个新账户尝试。

**Tech Stack:** Python、pandas、现有模拟账户、SHA-256、pytest。

日期：2026-10-05（Asia/Shanghai）。依据：[第七轮方案](../specs/2026-10-05-market-regime-filter-design.md)。方案文档审查通过；用户“开始”后已完成实现与有限历史比较，R1基础失格因此条件压力不运行；勾选只标实际项，完整成绩见STATUS／EXPERIMENTS。[研究接口验收](2026-10-05-research-integrity-acceptance.md)已完成有限范围，本项目无Git，不执行提交或工作树操作。

## Task 1：闭合行情状态与冻结准备

文件：新增 `src/cryptoquant/models/regime.py`、`configs/seventh_experiment.toml`、`tests/test_market_regime.py`；按现有固定值模式修改 `research_config.py`，不改第五／六配置或哈希。

- [x] 先写一组因果检查：改变当前／未来 OHLC 不改变之前状态；已核验停机重置；未知缺口／坏价格直接失败。
- [x] 实现方案的 ADX14 与 EMA72／slope24，初值、零分母与744连续小时有效条件按方案，不调用定义不明的第三方默认指标。
- [x] 输出逐4h唯一UTC状态表与可获得时间；只接受明确行情列，不读标签或2026。无效预热与损坏数据分开处理。
- [x] 新配置固定 net／C.1／T.50／C2、BTC全局过滤条件、R0／R1和9账户预算；状态参数不能由任意CLI阈值绕过。
- [x] 状态准备函数先核验 EXP-003、EXP-063、三窗模型来源，保存状态表、输入／配置／源码SHA及环境；要求先登记，失败保留。仅在临时夹具运行准备，CLI在Task3接；尚无正式状态实验。

Task1证据：独立需求／质量审查通过；14项新检查与原固定配置1项实际15 passed，`.cache/market-regime-final.log`；源码／配置／日志SHA`.cache/market-regime-task1-20261005.json`。root真实9模型来源回读、实际分区重叠检查均通过，见STATUS与WORKLOG；不重跑已有无变化检查，不计正式训练或账户成绩。

## Task 2：引擎买单许可

文件：修改 `src/cryptoquant/baselines/engine.py`；新增 `tests/test_regime_execution.py`。

- [x] 先用小型合成行情查无许可参数时逐笔等价、受限时 BUY 被拒绝而 SELL 保留、已持仓不因状态变化强制退出。
- [x] 增加可选 `buy_permission` 表（decision_time、available_time、state_valid、allow_buy）；精确核对UTC4h网格、唯一性、布尔类型与 available_time≤decision_time，模型策略之外拒绝传入。传入表必须完整覆盖账户窗口全部4h决策点，缺行／多行／缺值直接失败，不默认放行或沿用上次许可；state_valid=False必须禁止BUY，若同时allow_buy=True则拒绝冲突输入。只有buy_permission=None关闭过滤并保持原C2。合成检查覆盖缺行与冲突状态。
- [x] 原先卖后买流程中的 BUY 若受限，记录 `regime_blocked` 后跳过执行。不要将目标权重直接改0；原 SELL、风险退出、费用、资金缩放与冷却不改。当前是三币同一许可，受限时全部买入均被拦截，不能另外套逐币许可而造成未计预算的变体。
- [x] 无许可参数继续兼容现有C2；只运行受影响执行检查，不重跑旧基准／18个第六轮收益账户。

Task2证据：独立需求修复后复审与质量审查Approved。7项新执行与7项受影响出场检查通过；补空表边界红灯1失败后3项针对检查通过，原日志保留。三成本16h合成None与保存旧C2、全True与None逐笔一致，证据`.cache/regime-execution-checks-20261005.json`与`regime-execution-equivalence-20261005.json`。未重跑旧年度账户。

## Task 3：研究入口、结果和有限对照

文件：修改 `src/cryptoquant/models/research_workflow.py`、`research_gates.py`、`research_reporting.py`、`cli.py`；新增 `tests/test_regime_research.py`。若现有函数过大，可新增同职责的 `regime_workflow.py`，保持旧入口不重构。

- [x] 检查预算／配置／状态来源错配在行情加载、预测和新目录创建前拒绝；登记／失败记录不删除。
- [x] 只读核验现有 R0 C2 三窗三成本9份账户；保证模型、数据、风险、时间与费用一致。不能以旧摘要直接冒充带新接口的已重跑结果。
- [x] 独立第七轮账户入口绑定状态准备、模型、R0来源和冻结配置，保存完整订单（含拒单）、成交、信号、状态、净值与周统计及SHA。每个新尝试占9账户预算，不覆盖编号。
- [x] 在EXPERIMENTS先登记3个R1 base账户，再逐个执行并补结果；三个窗口全部写明已查看研究数据。出现输入／资金错误先停止，不能继续批跑掩盖错误。
- [x] 选择入口按方案6.1的精确门槛核验来源并保存清单；R1不合格或样本不足就完整报告并停止，不跑压力。
- [ ] 若R1合格，先冻结资格再登记最多6个压力账户。**条件未满足，不执行：EXP-126四基础门槛失格；此为方案要求停止，不是漏跑。**旧strict W2失败保留，不能降低15%门槛。
- [x] 综合报告区分来源／接口验收、观察到的历史改善、周收益目标；三窗合成不称连续账户，未有实时或独立样本外证据不开启2026。

Task3代码证据：独立需求／质量及全轮集成最终审查Approved；实际14 passed与19文件SHA在`.cache/regime-research-task3-20261005.json`。正式EXP-122—127已执行且complete，四基础门槛失败；实际3／9账户及6／12总尝试，条件压力不启动，结果不代表盈利。

## Task 4：交接与后续选择

文件：README、STATUS、EXPERIMENTS、WORKLOG；重要路线变化才改 DECISIONS／PLAN。

- [x] 给出当前真实CLI完整参数及不可复用编号说明，解释状态表与模型概率分离、受限买单／机会损失。
- [x] 记录原始产物、精确失败项、实际有限检查日志、未运行项和下一步；核对文件链接和跨文档一致性。
- [x] 根据结果选择继续过滤研究或研究动态阈值／仓位；不因失败自动扩大参数网格，不自动部署或转实盘。

Task4交接：README实际六命令／不可复用ID，STATUS唯一当前摘要，EXPERIMENTS保留精确失格，WORKLOG记录证据，D-035下一行动为只读诊断再设计少量动态响应，不新增第七账户。最终文档链接检查见WORKLOG。

## 验证与完成标准

原预列范围参考（本轮没有联合重跑三文件；实际仅按改动选检查，见上方14项命令及WORKLOG）：

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_market_regime.py tests/test_regime_execution.py tests/test_regime_research.py -q -W error --basetemp .cache/regime-interface-tests
```

完成标准：无未来状态输入、开启／关闭许可语义清楚且关闭时兼容原C2、全部新尝试在预算内、精确按冻结门槛报告结果且旧实验未改。盈利不是实施完成的前提；失败与证据不足也是应完整交付的研究结果。
