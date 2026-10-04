# 停机数据与三币准备实施计划

> For agentic workers: 使用 superpowers:executing-plans 在本会话顺序实施；按 superpowers:test-driven-development 先失败再实现。用户已授权继续，沿用当前会话执行方式。

**Goal:** 在保留未知异常硬失败的前提下处理已核验停机，完成三币真实数据准备。

**Architecture:** 版本化 market_calendar.json 保存有限例外；calendar.py 校验结束时间、增加空行情日历行并提供样本与成交可用接口。现有三步工作流保留不可覆盖的尝试与来源快照。

**Tech Stack:** Python 3.12、pandas、Parquet、Decimal 字符串、pytest、requests。当前没有 Git，不创建工作树或提交，继续使用源码快照和 SHA。

依据：[停机补充方案](../specs/2026-10-04-halt-aware-data.md)。本批不实现账本、策略或模型。

## 1. 精确例外与配置

文件：新增 `src/cryptoquant/data/calendar.py`、`market_calendar.json`、`tests/test_calendar.py`；修改 `config.py`、`normalize.py`、`pyproject.toml`、配置和对应测试。

- [x] 先写测试：精确白名单结束时间保留、未知提前结束失败、旧配置严格拒绝、新配置识别、非法政策拒绝。
- [x] 执行 `.\.venv\Scripts\python.exe -m pytest tests/test_calendar.py tests/test_config.py tests/test_normalize.py -q -W error`，确认新接口缺失或尚不支持政策导致失败。
- [x] 实现 policy_info(policy) 返回内置 JSON 与 SHA；valid_close(symbol, opened, closed, policy) 先允许标准毫秒／微秒末端，再只允许白名单精确三元组。read_archive 增加默认 strict_v0 政策参数。load_config 新字段默认 strict_v0，支持仅这两种版本。JSON 由六份已核验日包生成证据字段，包设置包含 JSON。
- [x] 重跑目标检查通过，原有解析边界仍通过。

## 2. 空日历、因果历史与标签接口

文件：修改 `quality.py`、`calendar.py`；新增关键行为测试。

- [x] 先写测试：已知停机补一条全空行情、未知缺口失败、停机有实际记录失败、恢复后第 744 个已收盘观察小时才 ready、跨缺口及缺出口标签失败、正常五小时标签通过、缺真实开盘不成交、终点保持状态但掩码未来历史信息、Parquet 保持空价格／UTC。
- [x] 执行 `.\.venv\Scripts\python.exe -m pytest tests/test_calendar.py tests/test_quality.py -q -W error`，确认这些行为失败。
- [x] audit 增加 policy 默认 strict_v0，仍先检查数值和重复。missing 集合必须等于该区间白名单停机小时，extras 必须为空。在校验成功后 reindex 生成日历，保持原始价格字符串；停机行情与来源为 null，状态 halt。逐行计算 segment_id 和连续观察数，history_ready 为计数≥744。新增行字段 is_nonstandard_close，实际标准行 false、白名单提前结束行 true、停机 null，报告 nonstandard_close_count 与明细一致；测试五组精确例外、普通行和原始 close_time/source_id，分区终点掩码该标记。
- [x] can_execute(row) 仅判断 observed 且真实非空开盘；label_window_is_observed(frame, entry_time, horizon=4) 按精确 UTC 整点五小时检查，未知／重复／缺失时返回 false。这是标签构造辅助，不能用于在线信号。partition_data 终点仅保留既有允许字段及 market_state；历史字段掩码。
- [x] 重跑目标检查并回归全部旧检查；缺口默认仍严格失败。

## 3. 证据工作流

文件：修改 `workflow.py`、`tests/test_data_integration.py`，补充端到端 fixture。

- [x] 先写集成检查：原三步仍通过且 manifest/报告政策 SHA 相等；JSON 包含在源码快照；prepare 后政策 SHA 变化被 check-data 拒绝；使用真实停机日期的合成归档三步生成空停机行，报告实际与日历数量分开。
- [x] 跑目标集成检查确认失败。固定合成 ZIP 的 ZipInfo 时间，避免 checksum 与 ZIP 两次生成相差两秒导致偶发失败。
- [x] snapshot_source 包含政策 JSON；prepare 传入政策、记政策 SHA；check_data 核对 prepare 政策与当前版本，传入 audit。保持 total_rows 表示日历，增加 total_observed_rows 和 total_halt_hours，中文报告明确不是全部实际 K 线。不改下载、规则和恢复协议。
- [x] 执行 `.\.venv\Scripts\python.exe -m pytest -q -W error` 和 `.\.venv\Scripts\python.exe -m pip check`。按 requesting-code-review 技能独立审查修改后代码；修复实际问题后复验。

## 4. 真实运行与文档

文件：`EXPERIMENTS.md`、`STATUS.md`、`DECISIONS.md`、`AGENTS.md`、`README.md`、旧方案与计划索引、EXP-002 产物。

- [ ] 追加 D-018，新配置 data_policy=halt_aware_v1，替代严格无缺口假设；登记 EXP-002 运行中，保留 EXP-001 失败并链接冻结旧配置。
- [ ] 固定源码后执行三步：`.\.venv\Scripts\python.exe -m cryptoquant prepare --config configs/first_experiment.toml --experiment-id EXP-002`，再 rules，再 check-data；只有前置完成才能继续。公开 HTTPS 使用已授权的网络权限，不使用账户密钥。
- [ ] 复制六份日包及调查 JSON 到 EXP-002 diagnostics，核对 SHA 与内置政策一致。检查真实三币数量、实际缺口与精确异常，若出现新未知问题停止并保留证据，不随意新增例外。
- [ ] 同步实际结果、测试数、当前规则快照的历史近似限制。检查 Markdown 本地文件链接和每步源码文件哈希。数据完成后下一步共同账本和开发期两组基准；本批不声称有收益。

## 审查与执行记录

补充方案审查 Approved；计划首轮指出异常 flag／计数遗漏，已补齐并复查Approved。新行为测试首次运行按预期失败于缺少 calendar 模块。此段不计正式实验结果。

## 5. EXP-002 失败后的来源选择修订

范围仅修正已核验的月／日来源差异，不放宽 close_time。遵循 systematic-debugging：完整原始审计与对应日包比对已定位 SOL 2021-12 月包异常，其余字段一致。

- [x] 新增先失败检查：plan_archives/download_range 接收 force_daily_months，指定 SOL 的 2021-12 时只计划 31 日包，其他月份／币种仍月包优先；月底与局部日期保持原边界。
- [x] 新建 market_calendar_v2.json，继承 v1 并新增 source_preferences 的 SOL/2021-12 及已排除月包 SHA／日包证据。policy_info 支持 v2；配置切换 v2，v1 文件不改。src JSON 已包含在快照／package-data 的声明改为 *.json。
- [x] 同一 v2 JSON 写入已核验的三币 2023-03-24 12:00 no_trade_bars。先检查失败：12 点不成交、08→12 标签无效、原始价格保留、历史清零、终点 no_trade 不成交、记录矛盾失败。audit 核对零成交和 OHLC 相等／前一收盘；add_calendar 将精确行标 no_trade，只有 observed 计入连续历史。不得使用当前行最终成交量作为通用开盘执行开关。
- [x] 在 archive.py 的 plan_archives 增加 force_daily_months=()，use_month 条件排除明确月份；download_range 传入参数。workflow.prepare 从政策按币种取得该集合，manifest 记录 source_preferences；monthly_fallbacks 只使用带此集合的计划判断真实 404，不将主动日包选择伪造为 HTTP 404。
- [x] 更新配置与集成检查支持默认 v2，保留 v1 和省略政策的 strict_v0；正常三步／政策变化／停机检查继续通过。新集成检查要求 SOL 2021-12 日包来源选择有记录且不出现在 monthly_fallbacks。
- [x] 合成停机 fixture 的三币12点行按真实零成交／OHLC重复上一收盘构造；检查 no_trade/halt 两种不可用状态。报告增加 archive_rows/total_archive_rows、no_trade_rows/total_no_trade_rows，observed_rows 只统计 usable observed；actual归档行、可用观察、日历分别报告，预计127149／127146／127152。未运行账本的规则只写文档，不假称已测试。
- [x] `.\.venv\Scripts\python.exe -m pytest -q -W error` 与 pip check 通过，独立复查 v2 来源调整后冻结源码。
- [x] EXP-002 登记失败（264 归档、BTC/ETH 已标准化、SOL 失败）；新配置与政策登记 EXP-003，执行 prepare→rules→check-data。复制六份日包、排除月包及全量审计，保存原始与新方法。完成真实数据后同步文档，不开始模型评价。

执行结果：v1的EXP-002真实prepare失败，已保留，故第4节原EXP-002三步完成项保持未勾选。第5节v2与no_trade方案复查Approved，91项检查及代码复查通过，EXP-003三步完成；详见根实验登记和质量报告。
