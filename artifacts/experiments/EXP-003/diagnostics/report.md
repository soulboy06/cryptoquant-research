# EXP-003 来源与异常证据

本目录复制并重新核验六份官方日包、被排除SOL月包及先前全量原始审计。逐文件来源及SHA见[halt-daily-audit.json](halt-daily-audit.json)，旧月包异常及三币原始现象见[full-archive-audit.json](full-archive-audit.json)。源调查报告保留于[EXP-002](../../EXP-002/diagnostics/report.md)。

EXP-003 使用halt_aware_v2，SOL 2021-12全部用官方日包。三币12点精确无成交原始记录保留而不可用于成交／标签／新估值，13点是无价格的空停机。两种状态中断历史累计。来源选择与HTTP404月包未发布降级分开记录，所有未知异常仍失败。

正式三步运行UTC2026-10-04 07:44:21—07:46:23完成，真实报告见[质量检查](../check-data/attempt-001/report.md)。本次验证的是数据准备，不是策略／模型盈利。
