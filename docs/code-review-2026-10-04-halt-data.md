# 停机处理实现与检查记录

日期：2026-10-04，Asia/Shanghai。本记录区分代码验证与真实数据实验。

- [补充方案](superpowers/specs/2026-10-04-halt-aware-data.md) 独立审查 Approved；[实施计划](superpowers/plans/2026-10-04-halt-aware-data-implementation.md) 补齐异常标记／数量要求后 Approved。
- 新行为检查先失败于缺少 calendar 模块；工作流随后按预期失败于缺政策字段、未传政策与政策变更未阻止。实现后 v1 全套 87 项通过，独立代码复查关闭缓存重跑也为 87 passed，pip check 无冲突。
- 终点对 bool 赋 null 曾产生 pandas FutureWarning；改用可空 Boolean／Int64 后通过，没有放松检查。
- EXP-002 真实检查停止于 SOL 月包越界结束时间，证明合成检查不能替代完整行情验证。全范围原始审计及对应日包比对定位根因，未手工修正价格／时间。
- v2 增加指定月份日包来源选择；独立方案／计划复查进一步发现三币12点零成交记录不能用于成交，已明确精确 no_trade 日历及因果约束。新检查先失败，再实现来源选择与不可用观察处理。
- v2 独立 Python 3.12 环境 `python -m pytest -q -W error`：91 passed；独立代码审查重跑91项和pip check通过，没有Critical／Important问题，可以启动EXP-003。额外只读检查覆盖三币no_trade终点掩码、08→12标签和原始记录矛盾拒绝。
- v1/v2 离线 wheel 构建成功，实际检查包含两个政策 JSON；v1政策与EXP-002源码快照逐字节一致。项目无 Git，保存源码快照及 SHA，不创建提交／工作树。

补充执行证据：两次pip wheel已输出Successfully built及有效wheel文件，但外层进程在输出完成后长时间未退出，最终中断剩余进程，退出码为1。因此这里的构建结论来自已生成ZIP包的实际读取和两个JSON成员检查，不把pip退出码当成功证据。中断不涉及项目环境、源码或实验流程；本次没有继续诊断退出等待原因。

真实EXP-003三步完成后，额外核对294个归档、9份Parquet、69份快照文件、同一源码版本及旧失败保留；17份Markdown／80个本地链接通过。结果保存于[最终产物核对](../artifacts/experiments/EXP-003/verification.json)。这仍不是策略收益验证。

以上不证明策略盈利，也不表示共同账本、EMA、模型或真实交易已经实现。真实全范围状态见 [实验登记](../EXPERIMENTS.md)。
