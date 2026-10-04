# 共同账本与开发期基准代码检查

日期：2026-10-04（Asia/Shanghai）。检查不代替真实回测或盈利证明。

范围：trading/ledger.py、orders.py、risk.py；baselines/strategies.py、engine.py、io.py、reporting.py、workflow.py与CLI。对照首轮方案、停机补充及数据／基准计划任务6—10。

独立只读复查分两轮，未运行正式实验或网络。第一轮20项核心检查，发现MAX_POSITION净数量过滤过松，失败回归后改为毛提交数量。第二轮检查事件顺序、终点掩码、停机恢复底线、风险退出与冷却、共同预算、年度指标、只读development和编号防覆盖；发现旧止损尾差反复刷新冷却，补充失败回归并修复。冷却禁买币同步在买入预算分配前排除。

最终独立复查：无未解决Critical／Important；审查者实际运行23项相关离线检查。root随后补充EMA与pandas adjust=False一致、恢复开盘穿底线、止损跨停机、终点单次限量、冷却预算等检查，完整`python -m pytest -q -W error`：129 passed（6.42s），退出0。

程序只回测development。三份分区及质量、清单、公开规则和冻结数据配置沿SHA链核验；每次新独立账户，非空／既有编号拒绝；失败日志与状态保存。费用计一次，所有金额／数量保持Decimal，指标信号使用浮点。

实际EXP-004／005已完成，见EXPERIMENTS.md。每组逐笔重放及52,610净值检查点、源码／产物SHA与年度连续性核对通过，见各verification.json。无模型训练、验证／保留测试收益、实时模拟或真实交易。

最终补查：从CSV独立核对最大回撤通过；合成数据改变当前开盘价只改变成交数量，不改变同刻EMA信号，证据见[开盘独立性](../artifacts/baseline-open-independence.json)。pip check无冲突。15份当前文档UTF-8和96个本地链接检查通过，冻结旧实验文档未改。
