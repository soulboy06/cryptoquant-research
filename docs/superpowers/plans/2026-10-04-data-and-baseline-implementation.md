# 数据准备与最小基准回测实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 默认在当前对话按 executing-plans 顺序执行；文档审查不等于任务执行。

**Goal:** 准备可校验、可追溯的三币小时数据和公开规则快照，实现共同资金账本及买入持有／简单趋势基准，输出开发期结果。

**Architecture:** 数据准备与离线回测分开，公开网络访问只发生在数据准备和规则快照命令。回测按小时的开盘执行、收盘观察两个事件推进，订单、账户和风控各自有明确接口。数据质量检查覆盖全部下载范围，策略开发仅使用 2022—2024 年区间，后续模型计划才开启验证和保留测试评价。

**Tech Stack:** Python 3.12、pandas、numpy、pyarrow、requests、matplotlib、pytest；交易数量和账本使用标准库 Decimal，配置使用 TOML，日志与清单使用 JSON／JSONL。

---

日期：2026-10-04（Asia/Shanghai）。状态：数据阶段完成，91项检查与代码复查通过，EXP-003三币prepare／rules／check-data完成；EXP-001／002失败保留。停机与来源按[补充计划](2026-10-04-halt-aware-data-implementation.md)及v2方案执行，旧EXP-001示例只代表原流程，不可用当前配置复用。任务6—10账本／基准已完成，完整129项检查及独立复查通过，EXP-004／005实际开发回测完成；模型未训练。实际状态见STATUS.md。

方案依据：[第一轮实验方案](../specs/2026-10-04-first-experiment-design.md)。本计划只覆盖其中的数据、账本和两组基准；不训练逻辑回归、不运行 2025 年策略评价或 2026 年保留测试，不接账户、不部署服务器。

## 当前环境与执行约定

- 已只读确认 Python 3.12.10 和 pip 26.0；全局已有 numpy、pandas、pyarrow、requests、matplotlib，未发现 pytest 或 sklearn。本计划执行时使用独立 `.venv`，不依赖全局包。
- `D:\量化` 当前没有 `.git`。不为本任务创建 Git 仓库、worktree 或提交；用源码哈希与环境清单保存版本证据。若用户后续要求 Git，再调整。
- 下方 PowerShell 命令均在 `D:\量化` 执行。尚不存在的文件是计划产物，不计为已完成；实际任务进度只更新根目录 `STATUS.md`。
- 每个实现任务先编写列出的关键行为测试，运行确认失败，再实现最小功能、通过对应测试并更新状态。修复新问题时增加能复现问题的测试；不为简单文档或空初始化文件添加无意义测试。
- 网络／安装不可用时记录具体失败，不把空文件、缺包或残缺数据判定为成功。正常沙箱授权流程由执行 agent 处理，不要求用户提供交易密钥。

## 文件与职责

以下路径相对于 `D:\量化`；每项均在其任务中创建。

| 文件 | 职责 |
| --- | --- |
| `pyproject.toml`、`requirements-lock.txt` | 项目与依赖声明、实际解析版本锁定 |
| `.gitignore`、`README.md` | 产物目录约定、中文运行说明与修改入口 |
| `configs/first_experiment.toml` | 时间、资金、风险、费用与策略默认值 |
| `src/cryptoquant/__init__.py`、`__main__.py`、`cli.py` | 包入口、prepare／rules／check-data／backtest 子命令 |
| `src/cryptoquant/config.py` | 读取 TOML、拒绝非模拟模式、校验时间和参数 |
| `src/cryptoquant/data/archive.py` | 归档计划、公开下载、校验和缓存版本 |
| `src/cryptoquant/data/normalize.py` | ZIP 内 CSV 读取、单位转换和标准数据表 |
| `src/cryptoquant/data/quality.py` | 完整性检查、数据分区与质量报告 |
| `src/cryptoquant/data/rules.py` | 保存公开规则、解析市价适用过滤器 |
| `src/cryptoquant/data/workflow.py` | 数据流程的步骤产物、源码与环境快照、质量报告关联 |
| `src/cryptoquant/trading/ledger.py` | 现金、持仓、费用、平均成本与净值 |
| `src/cryptoquant/trading/orders.py` | 合规检查、量化取整、成交偏移和买卖分配 |
| `src/cryptoquant/trading/risk.py` | 底线锁定、单币退出、重试、冷却及周期计数 |
| `src/cryptoquant/baselines/strategies.py` | 买入持有与 EMA24／EMA72 目标仓位 |
| `src/cryptoquant/baselines/engine.py` | 开盘／收盘事件顺序、区间限制和期末清算 |
| `src/cryptoquant/reporting.py` | 结果表、净值图、中文结论与复现证据 |
| `tests/` | 下列行为测试和人工可验的合成行情 |

各子包只需最小 `__init__.py`；不建立数据库、Web 服务、交易所下单 SDK 或并发交易服务。

数据产物：`data/raw/` 保留归档版本；`data/manifests/` 保存来源与校验；`data/rules/` 保存原始规则快照；`data/processed/development/`、`validation/`、`test/` 保存对应分区及预热／边界行。实验产物写入 `artifacts/experiments/<实际 EXP 编号>/`，测试临时产物只写 pytest 的临时目录。

## 任务 1：建立独立环境与配置入口

创建：`pyproject.toml`、`.gitignore`、`configs/first_experiment.toml`、包初始化、`config.py`；测试：`tests/test_config.py`。

- [x] 创建 Python 3.12 项目、src 布局，声明 numpy、pandas、pyarrow、requests、matplotlib，dev 依赖 pytest。先不安装 sklearn；模型任务再加入。
- [x] 运行 `python -m venv .venv`，然后 `& .\.venv\Scripts\python.exe -m pip install -e '.[dev]'`。记录成功解析的版本，不改变全局环境。
- [x] 写配置行为测试：拒绝 `mode=live`、负资金／费用、无效时区、倒置日期、总目标超过 100%；固定底线必须小于初始资金。
- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_config.py -q`，确认配置校验未实现时失败，再实现并运行通过。
- [x] 用 `& .\.venv\Scripts\python.exe -m pip list --format=freeze --exclude cryptoquant-research | Set-Content -Encoding utf8 requirements-lock.txt` 保存实际版本；editable 项目源码另行哈希。使用 list 避免从核验本地 wheel 安装时，freeze 写入仅适用于本机的文件 URL。

配置采用如下明确值，加载时将时间解析成带 UTC 时区的对象，金额与比例从 TOML 字符串转换为 Decimal：

```toml
mode = "simulation"
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
interval = "1h"
download_start = "2021-12-01T00:00:00Z"
download_end = "2026-10-02T00:00:00Z"
development_start = "2022-01-01T00:00:00Z"
development_end = "2025-01-01T00:00:00Z"
validation_start = "2025-01-01T00:00:00Z"
validation_end = "2025-12-31T20:00:00Z"
test_start = "2026-01-01T00:00:00Z"
test_end = "2026-10-01T00:00:00Z"
initial_cash = "100"
equity_floor = "50"
weight_per_symbol = "0.30"
stop_loss = "0.08"
cooldown_hours = 4
minimum_order_notional = "10"

[costs.base]
fee = "0.001"
adverse_price = "0.0005"
[costs.higher_execution]
fee = "0.001"
adverse_price = "0.001"
[costs.strict]
fee = "0.002"
adverse_price = "0.001"
```

配置中保留后续区间供数据分区，但当前 CLI 不提供执行这些区间的能力。

## 任务 2：归档下载、SHA-256 与不可变缓存

创建：`data/archive.py`；测试：`tests/test_archive.py`，用内存 ZIP 与假 HTTP 响应，测试不得访问网络。

接口：`plan_archives(symbol, start, end)` 返回按 UTC 时间排序的来源请求；`fetch_verified(request, cache_root, session)` 返回已验证路径、来源、文件名、SHA-256、字节数和获取时间。

- [x] 测试完整月份优先月包、首尾不完整月份按日；月包 404 才回退日包，403／其他错误不能伪装成缺月。日包缺失必须停止并报告。
- [x] 测试 checksum 格式、SHA 不符、HTML 错误响应、超时／429／5xx、已有缓存版本改变；下载失败不得留下被认作成功的 ZIP。
- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_archive.py -q`，确认失败后实现。
- [x] HTTP 使用 HTTPS、明确超时和有限重试；429 尊重可用的 Retry-After，单次等待过长时向 agent 返回待重试状态；其他重试采用短退避。禁止无限循环。
- [x] 下载到同目录临时文件，流式计算 SHA-256，核对官方 `.CHECKSUM` 内的预期 ZIP 名和 64 位十六进制哈希，通过后原子发布。
- [x] 原始文件按 `data/raw/<symbol>/1h/<官方文件名>/<sha256>.zip` 保存；远端校验值变化时保存新版本，不覆盖旧实验引用的内容。缓存可复用，但新的数据准备需要核对远端校验值。
- [x] 运行对应测试通过，并用 manifest 记录每个请求的状态与来源；此阶段只用假网络测试，不启动正式下载。

不得使用 `extractall` 解压任意路径；下一任务只通过 `ZipFile.open` 读取预期 CSV 成员。不是 ZIP、包含不符成员或校验失败时停止。

## 任务 3：精确时间转换与标准行情

创建：`data/normalize.py`；测试：`tests/test_normalize.py`。

输出 schema：`symbol`、`open_time`、`close_time`、`available_time`、`open/high/low/close`、`volume`、`quote_volume`、`trade_count`、`source_id`。时间统一 UTC；价格与成交量保留十进制文本，指标计算时才转浮点。`available_time=open_time+1h` 表示整根 K 线已经可用。

- [x] 编写测试：毫秒／微秒混合、UTC 年界、无效秒单位、12 列字段、识别的可选表头、损坏字段、ZIP 成员路径。
- [x] 用一个已知时刻同时检查两种输入，避免测试只重复实现公式：

```python
def test_ms_and_us_resolve_to_same_utc_boundary():
    from datetime import datetime, timezone
    from cryptoquant.data.normalize import parse_archive_timestamp
    expected = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert parse_archive_timestamp("1735689600000") == expected
    assert parse_archive_timestamp("1735689600000000") == expected
```

- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_normalize.py -q`，确认失败后实现。
- [x] 将 13 位毫秒乘 1000 变成整数微秒，16 位按微秒处理，其他位数明确报错。用 UTC epoch 加整数 timedelta，避免浮点 timestamp 丢失微秒。
- [x] 对照官方文件日期核查归属；原始 close_time 必须在该小时内并接近右端，不把原始 close_time 当作提前可获得完整 K 线的时间。
- [x] 检查严格数字格式、正价格、非负成交量、整数交易次数；读取 CSV 时只跳过明确识别的表头，不能任意丢弃首行。
- [x] 运行测试通过，保存规范化 Parquet；来源标识关联归档清单与哈希。

## 任务 4：数据质量、重叠与评价分区

创建：`data/quality.py`；测试：`tests/test_quality.py`。

- [x] 测试同一时刻的相同记录可按固定来源优先级合并并记录数量；不同来源数值冲突必须停止，不能随意取最后一条。
- [x] 测试缺小时、重复、乱序、OHLC 不满足 `low<=open/close<=high`、负量、未收盘与跨区间；禁止前向填价。
- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_quality.py -q`，确认失败后实现完整检查报告。
- [x] 日历区间每币42,384行，共127,152行；实际归档每币42,383、可用观察42,382，分别报告；用时间边界程序计算再核对，不把预期数量作为真实已获取数量。质量报告只输出数量、日期、问题及校验标识，不输出验证／测试价格走势或策略收益。
- [x] 建立 development、validation、test 分区。每区间附上此前 744 小时可用历史作预热（2022 初期从 2021-12-01 起），另保留右边界开盘行供清算；附加历史与边界行标记用途，不能计入正常收益或当作已收盘特征。
- [x] 数据准备可读取未来分区作字段和时间完整性检查；本阶段回测入口只加载 development 分区，不加载验证／测试行情作策略决策。
- [x] 跨界标签剔除留给模型计划；当前记录 `available_time` 与分区边界，禁止提前构造任何用作调参的验证／测试标签或收益报告。
- [x] 运行对应测试通过，生成每币完整性报告与全局数据清单。数据不合格则不得进入回测。

## 任务 5：公开规则快照与订单过滤器

创建：`data/rules.py`；测试：`tests/test_rules.py`。只使用公开 `GET /api/v3/exchangeInfo`，请求 BTCUSDT、ETHUSDT、SOLUSDT；保留完整 JSON、获取时刻、来源和 SHA-256。

- [x] 用离线规则样本测试 `LOT_SIZE`、`MARKET_LOT_SIZE`、`MIN_NOTIONAL`、`NOTIONAL`、市价 apply 标志、0 禁用值、未知过滤器和非 TRADING 状态。
- [x] 实现 `parse_market_rules(symbol_info)` 和 `round_market_quantity(qty, rules)`；未解释且会影响市价合法性的过滤器不能静默忽略，需拒绝该快照并说明。
- [x] 有效最小数量取所有适用下限的最大值，最大数量取适用上限的最小值；LOT 与 MARKET 的非零 step 必须同时满足，不能仅取两者最大值。转换成统一整数单位后用最小公倍数处理步长交集。
- [x] 编写非整除步长测试：step 为 0.002 与 0.003 时，有效网格是 0.006；正数量向下取整，从不向上凑最低订单。
- [x] 市价适用的 min/max notional 都保留，最低金额取实验 10 USDT 与适用下限的较大者。`avgPriceMins` 保存原值；官方检查可能使用参考价、分钟成交量加权均价或最新价，小时数据无法恢复这些订单时点的价格。本轮使用模拟成交价近似名义金额检查，报告注明这个执行限制，不称为交易所精确复现。
- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_rules.py -q`，先失败、实现后通过；实际 HTTP 快照留到任务 10。

回测只读取已保存快照，不在历史事件循环中查询当前接口。此快照用于统一历史模拟，不包含历史逐日交易规则。

## 任务 6：共同账本、费用与平均成本

创建：`trading/ledger.py`；测试：`tests/test_ledger.py`。

接口：`Portfolio(initial_cash, symbols)`、`apply_fill(side, symbol, gross_quantity, execution_price, fee_rate)`、`equity(mark_prices)`。金额使用 Decimal，精度至少 28；接收十进制字符串／Decimal，不以二进制浮点直接构造金额。

- [x] 先写资金守恒测试、买入基础币费用、卖出 USDT 费用、加权成本、减仓成本、负余额拒绝及三币共享现金测试。
- [x] 已合规成交的账本例子：初始 100，成交价 10、买入毛数量 2、费率 0.001，现金应为 80，净持仓 1.998；同价卖出全部后现金为 99.96002，费用合计 0.03998，持仓为 0。

```python
def test_round_trip_fees_are_charged_once():
    from decimal import Decimal as D
    from cryptoquant.trading.ledger import Portfolio
    book = Portfolio(D("100"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    book.apply_fill("BUY", "ETHUSDT", D("2"), D("10"), D("0.001"))
    assert book.cash == D("80")
    assert book.positions["ETHUSDT"].quantity == D("1.998")
    book.apply_fill("SELL", "ETHUSDT", D("1.998"), D("10"), D("0.001"))
    assert book.cash == D("99.96002")
    assert book.fees_usdt == D("0.03998")
    assert book.positions["ETHUSDT"].quantity == 0
```

- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_ledger.py -q`，确认失败后实现。
- [x] 买入：现金减少毛成交金额，持仓增加毛量乘 `1-fee`；买入单位成本为实际花费除净收到数量。卖出：持仓减少毛卖量，现金增加成交金额乘 `1-fee`。费用换算为 USDT 仅用于累计报告，不再次扣现金。
- [x] 加仓加权平均，减仓保留平均，交易闭合与尾差状态由下一任务管理；现金与全部持仓市值始终组成同一净值。
- [x] 运行对应测试通过；账本不负责网络、预测或订单过滤，只有订单模块校验后的成交可进入正式引擎。

## 任务 7：模拟订单、取整与共同资金分配

创建：`trading/orders.py`；测试：`tests/test_orders.py`。

接口：`simulate_fill(intent, open_quote, rules, cost)` 返回成交或带原因拒单；`plan_rebalance(target_weights, portfolio, all_open_quotes, rules, cost)` 返回先减仓后买入的批次。

- [x] 测试买入使用 `open*(1+adverse)`、卖出使用 `open*(1-adverse)`，不得再扣一份价差；最低金额边界、最大金额、数量交集、持仓不足、资金不足、零量和尾差。
- [x] 用同一个开盘净值与三币开盘参考价计算目标净持仓。买入差额需要考虑收到币的手续费，即所需毛量为目标净增量除 `1-fee`，之后按网格向下取整。
- [x] 先风险卖单、普通减仓，再统一买入资金。超过可用现金时所有合规买单按名义金额同比缩小、重新取整和检查；余钱保留。测试交换币种输入顺序，不应改变共同资金分配结果。
- [x] 检查卖出与买入都使用实际模拟成交价近似 notional；风险卖出允许按最大合法量截取，普通策略超限拒单。拒单不扣费、不改变账本，原因写入日志。
- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_orders.py -q`，先失败、实现后通过；组合测试验证合法 fills 才进入 Portfolio。

不得以未四舍五入的理想目标代替实际成交，也不能忽略手续费导致现金变负。

## 任务 8：风险状态机与持仓周期

创建：`trading/risk.py`；测试：`tests/test_risk.py`。

状态分开维护：账户永久停止开仓标志、每币待退出原因／首次触发时刻、冷却截止、是否有可交易持仓、周期是否产生过退出成交。尾差继续在 Portfolio 内。

- [x] 测试净值先涨到 200、降到 150 不触发固定底线；降到 50 触发，之后价格恢复仍禁止所有新买单。
- [x] 测试收盘触发、下一开盘执行，禁止同根 K 线提前卖；单币含费用均价下跌 8% 触发，买入持有不使用单币止损。
- [x] 测试拒单仍保留待退出，每小时开盘重试；最大单笔限量造成剩余可交易持仓时继续待退出；价格恢复不取消；同币不能反向买入。
- [x] 测试退出至零或尾差时从完成时刻开始 4 小时冷却，只在正常四小时决策点恢复；纯拒单若全仓已不可交易，可结束退出意图并冷却，但不记闭合周期。
- [x] 测试完整退出至少一笔成交、仅剩不可交易尾差时闭合一次；部分调仓或纯拒单不增加；重新建立可交易持仓才开启下一周期。
- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_risk.py -q`，先失败、实现后通过。触发／完成／冷却记录进入events.jsonl，逐次退出重试与成交／拒绝原因进入orders.csv；两者按UTC关联。

## 任务 9：两组基准、事件引擎与无未来信息检查

创建：`baselines/strategies.py`、`baselines/engine.py`；测试：`tests/test_baseline_engine.py`。

买入持有只在区间起点给三个币各 30% 目标，之后不主动调仓。趋势在 UTC 四小时决策点，按上一根已收盘行情的 EMA24／EMA72 给每币 0 或 30%；使用 `adjust=False`，连续预热来自该区间前已有数据。目标函数只能看到截止决策时已可用的历史。

- [x] 先用合成三币数据测试开盘与收盘顺序、共同净值、止损优先、冷却、拒单、最后清算和无条件反复买卖的禁止。
- [x] 加入未来信息不变性测试：改变当前未收盘 K 线的 high/low/close 及之后所有价格，当前开盘目标和当前订单必须不变；改变当前开盘价可以改变合法成交数量，不能改变预测／趋势方向。
- [x] 引擎每个开盘先确认上一小时收盘事件已观察，处理待执行风控；终点则仅清算、不买入、不读取终点 K 线的未来高低收。正常时再处理减仓与统一买入。开盘执行后记一次净值，小时收盘观察后记一次净值并生成下小时风控。
- [x] 风险卖单每币每小时最多一笔；期末每币只尝试一次合法量，剩余持仓记录，不延长区间；期末成本归属结束的评价区间。
- [x] 开发期从 2022-01-01 00:00 开始，到 2025-01-01 00:00 边界清算；终点仅使用已保留的开盘字段，该根后续字段不参与开发期判断。
- [x] `backtest` 目前仅接受 `period=development`，指定 validation/test 或任何自定义越界期间都明确拒绝；配置有这些日期不等于本阶段开放评价。后续阶段依据模型冻结协议扩展入口。
- [x] 运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_baseline_engine.py -q`，先失败、实现后通过。
- [x] 重复运行同一固定输入得到相同净值和交易记录；引擎使用新的独立账户，不从前次结果续账或追加成交。

开发数据和合成数据可用于查错；修复账本／时间错误必须记录并重跑受影响开发结果，不把错误修复伪装成策略优化。

## 任务 10：CLI、正式数据检查与开发期结果

创建：`cli.py`、`baselines/io.py`、`baselines/workflow.py`、`baselines/reporting.py`、`README.md`；测试：`tests/test_cli.py`、`tests/test_baseline_workflow.py`。

- [x] CLI 通过 `python -m cryptoquant` 运行。子命令为 prepare、rules、check-data、backtest；无 live、下单、账户密钥或交易所签名参数。离线回测不创建 HTTP session。
- [x] `--experiment-id` 只接受 EXP 编号；执行真实数据检查或基准前，由 agent 在根 `EXPERIMENTS.md` 登记新的编号与配置。文档计划中的未来任务不提前计入正式实验。
- [x] 非空实验输出目录拒绝覆盖和追加，重复编号报错；新编号重跑从同样 100 USDT 开始。失败保留日志和状态，不复用为成功实验。源码哈希、配置哈希、数据清单与规则哈希进入各实验 manifest。
- [x] 先运行 `& .\.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_baseline_workflow.py -q`，失败后实现离线合成端到端流程，再通过测试。
- [x] 中文 README 写明环境创建、配置入口、公开数据、开发期限制、净值与风险语义、关闭策略／修改参数的方法；不声称模型已训练。
- [x] 核对根实验登记表：若仍为空，下一编号为 EXP-001，登记一次“数据检查”；随后执行下方命令。若已存在其他真实任务，使用实际下一个编号并同步命令／路径，不复用已登记编号。

```powershell
& .\.venv\Scripts\python.exe -m cryptoquant prepare --config configs/first_experiment.toml --experiment-id EXP-001
& .\.venv\Scripts\python.exe -m cryptoquant rules --config configs/first_experiment.toml --experiment-id EXP-001
& .\.venv\Scripts\python.exe -m cryptoquant check-data --config configs/first_experiment.toml --experiment-id EXP-001
```

上述三条是同一数据检查流程的不同步骤，必须有步骤状态与各自产物目录；第二／三步只能打开处于数据准备状态、且配置相同的 EXP-001，不能覆盖已有步骤结果。重复执行已完成的步骤拒绝；失败步骤经显式恢复且配置不变才可重试，保留失败日志。与新基准运行的“非空目录拒绝”规则分开实现。

- [x] 全部真实数据与规则检查成功后，将该实验记为完成。存在缺失或失败时记为失败／阻塞，停止真实回测，不生成虚构收益。保存完整报告而非仅一行“数据正常”。
- [x] 再运行 `& .\.venv\Scripts\python.exe -m pytest -q`；通过后分别登记买入持有与趋势的基准成本开发回测。数据检查现已占用EXP-001／002／003；EXP-004、EXP-005已事前登记并实际完成，以下为已执行命令（重复编号拒绝）：

```powershell
& .\.venv\Scripts\python.exe -m cryptoquant backtest --config configs/first_experiment.toml --strategy buy_hold --period development --cost base --experiment-id EXP-004
& .\.venv\Scripts\python.exe -m cryptoquant backtest --config configs/first_experiment.toml --strategy ema_trend --period development --cost base --experiment-id EXP-005
```

- [x] 每个开发回测保存 `run_manifest.json`、`events.jsonl`、`orders.csv`、`fills.csv`、`equity.csv`、`summary.json`、`equity.png`、`report.md`。无交易／触发底线／尾差／拒单均正常报告，不能强迫策略盈利。
- [x] 报告净收益、最终清算现金与尾差、最大回撤和未恢复回撤、周期与成交次数、费用、换手、暴露及风险次数。回撤基于小时收盘与成交后检查点，不声称小时内最大回撤。闭合次数沿用任务 8 语义。
- [x] 年度分段基于连续同一账户净值，不按年重置本金；总账户固定 50 底线。压力情景的配置与计算接口先可用，真实开发压力回测后续按实际需要另登记；当前不按这些开发结果重新挑选固定策略参数。
- [x] 最后更新根 `STATUS.md`、`EXPERIMENTS.md`、必要的 `DECISIONS.md`：记录真实命令、通过的检查、产物和限制；下一步是模型特征／训练与验证实施计划，保留测试仍未开启。

## 报告与实现完成标准

本计划实施完成时应具备：独立环境和锁定版本；完整数据清单与质量报告；公开规则快照；关键行为测试通过；两组基准的可复现开发结果；文档状态真实一致。策略亏损不等于实现失败，发现数据、账本或时间错误则使相关收益结果无效。

没有训练模型、没有验证或测试期策略结果、没有实时模拟、没有真实下单均须明确记录。不得因完成基础设施就宣布具备盈利能力。

## 文档审查记录

2026-10-04：单独的计划审查 agent 只读核对本计划与首轮方案，结论为 Approved，没有阻碍实施的缺口。审查覆盖任务完整性、数据与时间边界、共同账本、订单过滤、风险重试和实验复现。此结论只表示计划可供实施，不表示已实现、测试通过或取得收益。

## 实施时的参考

- [首轮方案](../specs/2026-10-04-first-experiment-design.md)、[数据源目录核查](../../data-source-check-2026-10-04.md)。
- [币安公开归档说明](https://github.com/binance/binance-public-data#readme)。
- [币安市价过滤器](https://github.com/binance/binance-spot-api-docs/blob/master/filters.md)、[仅公开行情接口](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md)。
- [Python Decimal](https://docs.python.org/3.12/library/decimal.html)：金额与向下取整。

执行时使用 `superpowers:executing-plans`、关键账本／数据功能按 `superpowers:test-driven-development` 实施、失败按 `superpowers:systematic-debugging` 查因、完成前按 `superpowers:verification-before-completion` 核对。无 Git 的当前目录使用源码与产物哈希代替提交证据。

## 首批执行检查点

2026-10-04：任务 1、2、5 的环境／下载器／规则解析实现与检查完成；任务 3、4 的标准化、质量与分区代码已通过合成检查，任务 10 的数据 CLI 已实现。真实 EXP-001 在 BTC 读取时失败：42,383 条，缺 2023-03-24 13:00 UTC，另有两条非标准结束时间。完整三币数据尚未生成，不能勾选真实数据完成项或进入任务 6—9 的真实回测。调查报告见 [EXP-001](../../../artifacts/experiments/EXP-001/diagnostics/report.md)。

2026-10-04后续检查点：v2停机与来源方法91项检查通过，EXP-003真实三币数据／规则／分区通过。下一步任务6—9共同账本和开发期基准；不直接跳入模型。

## 本次账本／基准执行细节（用户已同意继续）

- 沿用首轮参数，不重做策略选型。新交易核心、引擎／端到端合计38项新增检查通过（全套129项），独立复查通过；实际完成数以STATUS为准。
- 每个UTC整点先观察上一行已可用的真实收盘并更新EMA／风险，再按当前真实开盘执行。交易后净值与收盘净值分别记录，起点交易前记录100。终点只观察上一收盘和执行一次清算，绝不读取终点未来字段。
- no_trade／halt均重置指标历史；不产生真实价格更新或新单币止损观察。持仓估值沿用最后真实mark，记录价格年龄／陈旧币种，行情文件不改。恢复首个真实开盘使用新估值补查固定底线，避免陈旧价格使账户仍可开仓；单币8%止损仍只按真实收盘观察。此恢复检查来自停机方案“恢复后更新估值和风控”的明确实现。
- EMA分币递推adjust=False，只消费已可获得收盘；累计744个连续观察才发趋势信号。未预热时保持原持仓，不产生买卖目标；风险退出不受预热限制。买入持有仅起点尝试，不因缺价补买。
- 只有风险退出保留每小时待执行；普通减仓不计闭合周期。策略完整退出与终点退出可记闭合，但不引入单币止损冷却；4小时冷却只用于stop_loss退出完成。尾差保留估值，不能假装清仓。
- 新增baselines/io.py只校验并加载development三份Parquet及其证据，禁止回测入口读取其他分区。backtest新增--data-experiment-id（默认EXP-003），无网络、账户或resume。独立非空输出编号拒绝，失败状态保留；当前仅period=development。
- 输出manifest、事件、信号、订单、成交、持仓／陈旧净值、汇总、年度表现、净值PNG和中文说明；所有金额CSV保留Decimal字符串。开发结果用于建立基准，不选EMA参数、不评价封存测试或承诺盈利。

## 本轮最终执行检查点

2026-10-04：任务6—10完成，测试文件按模块合并为test_baseline_engine.py及test_baseline_workflow.py，没有遗漏原时间／账本／报告边界。风险重试明细保存在orders.csv，风险状态事件保存在events.jsonl，避免重复记录相同订单。129项自动检查通过，EXP-004／005冻结同一配置与源码并实际运行完成；各52,610净值点及成交重放和哈希通过。结果见[开发期比较](../../development-baseline-results-2026-10-04.md)。模型、验证／保留测试、实时模拟仍未开展。
