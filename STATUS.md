# 当前状态

最后更新：2026-10-05（Asia/Shanghai）。本文件是当前进度的唯一摘要，历史操作及旧结论见WORKLOG／EXPERIMENTS。

## 本轮任务

用户附件要求“先状态机修复→验证旧结果→重建baseline→冻结第十轮→有限实验→汇报并更新GitHub”。本轮全部完成，已上传GitHub分支codex/cycle-state-integrity并创建[PR #1](https://github.com/soulboy06/cryptoquant-research/pull/1)，尚未合并main；没有活跃账户回测或后台进程。第十轮3候选全部失格，无最终候选、未证明稳定盈利、未达到长期几何周收益1.5%目标。

## 已完成与证据

- min-notional拒卖不再关闭正持仓周期或清除风险；退出请求锁存，UTC时长延续，正常恢复退出后才冷却。真实全退出SELL后的sub-step零头按明确政策模拟核销，成本计损失、现金不变并审计；不是真实dust转换。独立修复提交3751f9d。
- Phase A EXP-160～175共15组R0/R3/R5/R6/R7三窗配对完成，全部旧成交／关键指标复现，新行为均变化。EXP-159报告快照失败保留，EXP-175同参数替代，共32核验账户。[结果](docs/cycle-state-repair-results-2026-10-05.md)、[总验收](artifacts/experiments/EXP-174/comparison.json)。
- 原第六～九轮交易成绩不再作新引擎baseline；旧失败和冻结文件不改写。EXP-158的0.53／3%、固定波动率、SOL七交易收益预测不是已验证结论。修复R5 W1/W2周期30/25，R6为30/27，不能仅在旧计数上加一两笔。
- 第十轮事前冻结提交33ca36e，父策略按修复R5/R6选择R6。R8 Top-1恢复30%，R9加24h正方向，R10自身既往预测80%分位数恢复30%。[方案](docs/tenth-experiment-design-2026-10-05.md)、configs/tenth_experiment.json。
- EXP-176～184九Base、EXP-185统一选择、EXP-192全景报告完成；EXP-186～191条件压力跳过，条件25%邻域未启动，没有追加候选／搜参。R8描述性最好但仍亏损，W2收益+0.2236%、28周期，2025收益-18.7838%、回撤20.5623%；合成周收益-0.108368%。相对父R6，2025净收益下降0.4373个百分点。
- 65项受影响执行／风险／账本检查、5项机制因果检查、2项预算／Phase A门禁检查实际通过，共72项。逐账户资金／费用守恒；汇总核对2813项产物／源码SHA、完整周期PnL、逐币dust及favorable目标保持。不代表全部模块重新测试。
- [最终12项答复](docs/cycle-repair-and-tenth-results-2026-10-05.md)、[统一归因](artifacts/research/cycle-repair-and-tenth-summary.json)。4452文件证据包46.47MiB，逐文件SHA及压缩后内容校验通过，见[说明](artifacts/research/README.md)和evidence_manifest.json；包括完整新旧流水／targets／源码，不含原始行情或2026测试。

## 当前限制与长期边界

- 2023、2024、2025均是已反复查看的研究开发数据，不是盲测或独立OOS。2026 test从未在本轮读取；仅复用用户明确授权的既有终点开盘报价清算。
- 100USDT初始虚拟资金、三币共用账户、固定50USDT底线、普通现货／无杠杆／无实盘不变。R0是模型固定30%目标仓位对照，不是买入持有。
- 净收益变化是状态修复与保守精度零头放弃的联合效果，未单独消融两者。小本金下BTC数量步长的零头核销累积损失很大；历史规则快照、费用方式和真实dust处理可行性未验证，不能把模拟核销当交易能力。
- 无合格候选，因此没有压力或条件邻域稳定性证据，不推荐打开2026或进入实时模拟。旧“已取得突破／W2将达16%～17%”说法撤回。
- using-superpowers技能已按用户要求删除并禁止使用，见D-041；研究失败仍保留。

## 下一行动与交接

GitHub上传与PR创建已完成。研究按用户附件到此停止，不能自动开展新候选或消耗2026。后续如用户继续授权，第一步只读核对历史数量步长、手续费和dust政策的执行可行性，先冻结下一阶段问题／政策／预算再运行，不放宽本金或收益门槛。

复核入口：README命令、scripts/verify_cycle_repair.py、run_tenth_research.py、summarize_cycle_research.py。已完成编号不得覆盖，登记已至EXP-192（条件跳过编号保留），下一编号现场核对EXPERIMENTS后分配。
