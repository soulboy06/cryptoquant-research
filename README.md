# 加密货币离线研究

新对话／新agent先读[AGENTS.md](AGENTS.md)，再按其中顺序恢复状态与决策；[STATUS.md](STATUS.md)给出具体下一行动，[WORKLOG.md](WORKLOG.md)保存每轮重要工作的历史与证据。无需依赖旧聊天才能接手。

当前已实现公开现货数据准备：配置校验、官方 ZIP 与 SHA-256 校验、小时行情标准化、质量检查、评价分区及公开规则快照。研究 BTCUSDT、ETHUSDT、SOLUSDT，不需要账户或密钥。

三币归档127,149条，其中127,146条可用观察；日历127,152行。真实质量报告见[EXP-003](artifacts/experiments/EXP-003/check-data/attempt-001/report.md)。共同账本与基准见[开发期比较](docs/development-baseline-results-2026-10-04.md)。[EXP-006](artifacts/experiments/EXP-006/report.md)保存每币6,387训练样本；[EXP-007](artifacts/experiments/EXP-007/report.md)保存首版9个逻辑回归与scaler。后续12特征、LightGBM、四轮2025验证与成本评价已完成；[EXP-062](artifacts/experiments/EXP-062/report.md)为最新既有结果诊断，2026保留测试尚未评价。最新进度以STATUS为准，下方早期命令说明保留其历史配置，不能据此判断最新阶段未实现。

EXP-001／002 的失败记录保留。新版 halt_aware_v2 已通过91项行为检查及代码复查，EXP-003三步真实流程完成；[停机补充方案](docs/superpowers/specs/2026-10-04-halt-aware-data.md) 明确日历状态和来源，[EXP-002 调查](artifacts/experiments/EXP-002/diagnostics/report.md) 记录月包／日包差异及零成交记录。

## 环境与检查

在项目根目录使用 Python 3.12。无需激活环境，直接调用环境中的 Python：

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
& .\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m cryptoquant --help
```

开发首次安装也可使用 `pip install -e '.[dev]'`。锁文件记录本次环境实际解析的版本；其中包含构建工具，以支持离线构建入口。当前目录没有 Git，实验保存源码快照及哈希。

## 数据流程

配置入口是 [configs/first_experiment.toml](configs/first_experiment.toml)：三个币共用 100 USDT，本金底线固定 50 USDT。费用、仓位等是固定研究假设，不是已验证最优参数。修改配置需要重新校验；资金必须写成十进制字符串，例如 `"100"`。

正式运行前先在 [EXPERIMENTS.md](EXPERIMENTS.md) 登记新编号。下方记录EXP-003实际运行的三个步骤。该编号已完成，复跑须先登记新编号再替换命令中的编号；不能覆盖旧实验：

```powershell
& .\.venv\Scripts\python.exe -m cryptoquant prepare --config configs/first_experiment.toml --experiment-id EXP-003
& .\.venv\Scripts\python.exe -m cryptoquant rules --config configs/first_experiment.toml --experiment-id EXP-003
& .\.venv\Scripts\python.exe -m cryptoquant check-data --config configs/first_experiment.toml --experiment-id EXP-003
```

`prepare` 下载并标准化数据；`rules` 保存当前公开交易规则；`check-data` 核对全部校验、时间和数值，生成分区及质量报告。所有日期均为 UTC，下载范围为 2021-12-01 至 2026-10-02，右端不含。

同一步骤成功后重复执行会拒绝；失败或中断时，在同样的命令后添加 `--resume` 才能建立新的尝试目录。配置必须相同，旧日志保留。方法或配置改变须登记新编号；完成后复跑不能覆盖。

已核实的空停机行无价格和成交量；已核验的零成交重复价格行保留原文、标 no_trade，不可成交或用作新价格。报告区分实际归档条目、可用观察和日历行，其他不明缺口仍失败。五组非标准结束时间只接受逐币精确白名单，原始值保留。SOL 2021-12 明确选官方日包，来源选择单独记录；其余月包只在真实404时降级。政策 JSON 随源码快照保存，跨步骤变更会停止质量检查。旧配置省略政策时采用 strict_v0。

## 文件在哪里

- `data/raw/`：按原始文件名与 SHA-256 保存 ZIP 版本及官方校验值。
- `data/manifests/`：来源、获取时间、校验值和实际环境。
- `data/rules/`：不可变公开规则快照。
- `data/processed/normalized/`：保留十进制文本的 UTC 行情。
- `data/processed/development/`、`validation/`、`test/`：分区文件，包含已标记的预热和终点行。
- `artifacts/experiments/EXP-xxx/`：步骤状态、每次尝试、源码与配置快照、质量报告；失败也保留。

整根小时线到下一小时才可用于信号。不可用小时中断历史累计，恢复后须有744个连续可用观察小时；标签检查入口到四小时后出口的五个日历小时。终点仅保留真实开盘、来源与市场状态，未来行情和历史状态掩码。no_trade 终点也不成交。离线执行掩码不能作为在线预测信号。数据检查读取全部区间只为检查完整性；后续策略开发先限于2022—2024，尚未评价验证／保留测试的策略收益。

## 离线基准回测

以下是已经完成的EXP-004／005命令，重复编号会拒绝。重跑前登记新编号并替换编号，程序从独立100 USDT账户开始。只有development可运行；无需HTTP、账户或密钥。

```powershell
$env:MPLCONFIGDIR = 'D:\量化\.cache\matplotlib'
& .\.venv\Scripts\python.exe -m cryptoquant backtest --config configs/first_experiment.toml --data-experiment-id EXP-003 --strategy buy_hold --period development --cost base --experiment-id EXP-004
& .\.venv\Scripts\python.exe -m cryptoquant backtest --config configs/first_experiment.toml --data-experiment-id EXP-003 --strategy ema_trend --period development --cost base --experiment-id EXP-005
```

`--strategy buy_hold`仅起点各币30%，不主动调仓；`ema_trend`每四小时按已收盘EMA24/72给0或30%目标。三币共同分配现金，先卖后买；买入手续费从收到币扣，卖出从收到USDT扣。`--cost`还可选择higher_execution或strict；正式压力实验尚未运行，新实验需独立登记，不为提高开发收益选参。

策略停止买入后，仍记录持仓、退出和净值；固定底线永久禁买，单币止损完成冷却4小时且只能在正常四小时决策点恢复。完整退出尾差不再反复触发同一止损；尾差仍计入资产与底线。停机无真实报价不成交，恢复首个开盘补查底线；8%单币止损只在真实收盘观察。

结果目录包含manifest／源码与配置、signals／orders／fills／equity／annual CSV、风险事件JSONL、summary、净值PNG及中文报告；所有金额保留Decimal文本。运行失败保留failure.json与failed状态，不能覆盖原编号或续用账户。修改资金／成本／风险参数需新编号；改变数据时间／币种／政策则需先匹配新数据检查。

## 生成训练样本

以下是已完成EXP-006的命令；重复编号拒绝。需要重跑时先登记新编号，不覆盖旧输出，不重新下载行情。

```powershell
& .\.venv\Scripts\python.exe -m cryptoquant build-samples --config configs/first_experiment.toml --data-experiment-id EXP-003 --experiment-id EXP-006
```

只读取development三份Parquet，2021-12仅预热，2022—2024决策生成九特征和四小时方向标签；停机、历史不足、答案跨界等明确剔除。样本未标准化，未来scaler只在训练样本fit；验证／测试文件不会加载。

输出见实验目录：training_samples／excluded_decisions分币Parquet，sample_manifest包含数量／时间／来源／SHA，source_snapshot、source_manifest、config保存版本，report为中文说明。九特征定义在[features.py](src/cryptoquant/models/features.py)，标签与剔除在[samples.py](src/cryptoquant/models/samples.py)，运行在[workflow.py](src/cryptoquant/models/workflow.py)。EXP-006只准备样本；模型拟合另用下面的train入口，没有validate命令或模型收益成绩。

本轮针对性检查：`.venv/Scripts/python.exe -m pytest tests/test_training_samples.py -q -W error`；与受影响CLI两项合计6 passed。遵循用户偏好，只按实际改动选择检查，不反复跑未改动模块或基准。

## 训练模型

train已实现，正式实验编号需先登记。下面是已完成EXP-007的命令，重复使用会拒绝；重跑需新编号，实际结果见[训练报告](artifacts/experiments/EXP-007/report.md)、[核对记录](artifacts/experiments/EXP-007/verification.json)与[实验登记](EXPERIMENTS.md)。

```powershell
& .\.venv\Scripts\python.exe -m cryptoquant train --config configs/first_experiment.toml --sample-experiment-id EXP-006 --experiment-id EXP-007
```

只读取源实验training_samples三份文件，核对SHA、特征顺序、类别和严格UTC时间边界。每个币独立fit标准化与逻辑回归，C=0.1／1／10，共9个候选模型；训练只使用九个历史特征，不将未来label／label_return混入输入，不读取validation/test分区。

模型参数L2、lbfgs、max_iter=1000、class_weight=None、random_state=42固定；scikit-learn1.9.1使用l1_ratio=0表达L2，依据[官方参数文档](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)。单类或不收敛记录失败，不自动换算法或增加迭代。阈值0.55／0.60／0.65之后复用同C预测，不在训练集选择赢家。

输出train_manifest、models/*.joblib（包含对应scaler）、同名JSON参数与系数、training_probabilities和training_diagnostics、源码／环境／配置快照及中文report。训练集诊断不表示预测未见行情的能力，也不表示交易盈利。概率诊断文件带有事后标签，不能整表作为交易目标输入。

使用自己生成的可信本地模型，在同一锁定环境中调用预测接口；features必须是已经收盘且历史有效的九特征：

```python
import joblib
from cryptoquant.models.training import predict_probabilities

model = joblib.load('artifacts/experiments/EXP-007/models/BTCUSDT_C-1.joblib')
# features是已计算的有效特征DataFrame；此处只predict，不重新fit。
probability = predict_probabilities(model, features)
```

训练实现见[training.py](src/cryptoquant/models/training.py)与[training_workflow.py](src/cryptoquant/models/training_workflow.py)。针对性检查：`.venv/Scripts/python.exe -m pytest tests/test_model_training.py tests/test_cli.py::test_no_account_or_live_commands_exist -q -W error`，已实际5 passed；未重跑旧账本或基准。

## 资金费率与第二轮12特征实验

第二轮改进配置位于 [configs/second_experiment.toml](configs/second_experiment.toml)（`feature_policy = "kline_and_funding"`）。

1. 资金费率获取与校验：
```powershell
& .\.venv\Scripts\python.exe -m cryptoquant fetch-funding --config configs/second_experiment.toml
```
覆盖2021-12至2026-10，下载官方月度ZIP归档，核验SHA-256，生成Parquet于 `data/processed/funding_rate/`。

2. 12特征样本构建（EXP-021）与模型训练（EXP-022）：
```powershell
& .\.venv\Scripts\python.exe -m cryptoquant build-samples --config configs/second_experiment.toml --data-experiment-id EXP-003 --experiment-id EXP-021
& .\.venv\Scripts\python.exe -m cryptoquant train --config configs/second_experiment.toml --sample-experiment-id EXP-021 --experiment-id EXP-022
```

3. 2025验证模拟（EXP-023至EXP-033）与筛选汇总（EXP-034）：
```powershell
& .\.venv\Scripts\python.exe -m cryptoquant backtest --config configs/second_experiment.toml --data-experiment-id EXP-003 --strategy buy_hold --period validation --cost base --experiment-id EXP-023
& .\.venv\Scripts\python.exe -m cryptoquant backtest --config configs/second_experiment.toml --data-experiment-id EXP-003 --strategy ema_trend --period validation --cost base --experiment-id EXP-024
& .\.venv\Scripts\python.exe -m cryptoquant validate --config configs/second_experiment.toml --data-experiment-id EXP-003 --training-experiment-id EXP-022 --C 0.1 --threshold 0.65 --cost base --experiment-id EXP-027
& .\.venv\Scripts\python.exe artifacts/experiments/EXP-034/compare_validation.py
```

详见[EXP-034报告](artifacts/experiments/EXP-034/report.md)。

## 第五轮成本感知标签与受控窗口研究

第五轮[成本感知标签方案](docs/superpowers/specs/2026-10-04-cost-aware-label-design.md)与[实施计划](docs/superpowers/plans/2026-10-04-cost-aware-label-implementation.md)已全部完成（EXP-063~EXP-101）。配置位于 [configs/fifth_experiment.toml](configs/fifth_experiment.toml)。

### 1. 研究样本准备与资金费率截断快照
```powershell
& .\.venv\Scripts\python.exe -m cryptoquant research-prepare --research-config configs/fifth_experiment.toml --data-experiment-id EXP-003 --source-sample-experiment-id EXP-021 --experiment-id EXP-063
```
核验EXP-003与EXP-021数据源，截断资金费率至2025-12-31 20:00:00，从连续历史重算12特征并校验一致性，生成 `gross_direction_v1`（上涨方向）与 `net_positive_base_v1`（覆盖基础摩擦净盈利）两套样本及决策特征库。

### 2. 受控窗口模型训练
```powershell
& .\.venv\Scripts\python.exe -m cryptoquant research-train --research-config configs/fifth_experiment.toml --prepared-experiment-id EXP-063 --window W1 --label-policy gross_direction_v1 --experiment-id EXP-064
```
按时间截取训练样本，拟合三币独立逻辑回归（C=0.1），持久化模型、参数卡、三列独立概率表及分表标签。

### 3. 受控窗口账户回测与周统计
```powershell
& .\.venv\Scripts\python.exe -m cryptoquant research-evaluate --research-config configs/fifth_experiment.toml --training-experiment-id EXP-064 --window W1 --threshold 0.40 --cost base --experiment-id EXP-068
```
基于受控历史窗口执行独立100 USDT账户回测，并严格按照 initial->close->terminal 口径计算周收益与几何周复合增长率 $g_{week}$。

### 4. 滚动选择与参数冻结
```powershell
& .\.venv\Scripts\python.exe -m cryptoquant research-select --research-config configs/fifth_experiment.toml --experiment-id EXP-084
```
聚合两窗16组base候选，执行四项硬性门槛过滤与排序，冻结胜出参数并判定R2025盲测执行资格。

### 5. 多窗口多成本综合对比评估
```powershell
& .\.venv\Scripts\python.exe -m cryptoquant research-compare --research-config configs/fifth_experiment.toml --selection-experiment-id EXP-084 --experiment-id EXP-101
```
对比双政策在三窗口、三档摩擦成本下的表现，生成综合对账表与三层结论最终评定。详细结果见[EXP-101报告](artifacts/experiments/EXP-101/report.md)。

### 修改入口与模块说明

- [研究配置](configs/fifth_experiment.toml)由[research_config.py](src/cryptoquant/models/research_config.py)读取，固定原执行配置、两种标签、C=0.1、四阈值与窗口；不改原时间分区。
- [labels.py](src/cryptoquant/models/labels.py)的`label_values`输入十进制入口／出口价格，返回毛收益、净收益文本及0／1标签。`gross_direction_v1`判断上涨，`net_positive_base_v1`判断是否覆盖固定base理想成本；实际账户仍按原账本扣费。
- [windows.py](src/cryptoquant/baselines/windows.py)的`window_frames`构造固定W1／W2／R2025执行视图；`select_window_features`截取原连续历史预计算特征。[predictions.py](src/cryptoquant/models/predictions.py)的`build_window_probabilities`据此生成完整4小时概率表。
- [research_data.py](src/cryptoquant/models/research_data.py)、[research_models.py](src/cryptoquant/models/research_models.py)、[research_reporting.py](src/cryptoquant/models/research_reporting.py)与[research_workflow.py](src/cryptoquant/models/research_workflow.py)实现了第五轮完整的研究管道。

### 已有结果交易诊断


EXP-062只分析EXP-049的冻结2025产物，不读行情分区、拟合模型或生成新交易。报告见[诊断](artifacts/experiments/EXP-062/report.md)，尾差与独立信号收益口径见[补充解释](artifacts/experiments/EXP-062/interpretation.md)。主要修改入口为实验内的 `diagnose.py`；已经冻结，后续修改需新编号／新脚本，不能覆盖该目录旧结果。

本轮已经实际执行以下命令，重复运行拒绝覆盖：

```powershell
& .\.venv\Scripts\python.exe artifacts/experiments/EXP-062/diagnose.py
& .\.venv\Scripts\python.exe artifacts/experiments/EXP-062/verify_diagnostics.py
```

逐周期 `cycles.csv` 与概率分组 `signal_buckets.csv` 支持复核；冻结来源／输出SHA见run_manifest，独立对账见independent_verification。盈利信号比例是理想定额交易口径，实际账本保留尾差、数量取整和资金限制，两者不能混用。

- 时间和研究参数：[首轮配置](configs/first_experiment.toml) / [第二轮配置](configs/second_experiment.toml)，加载时由 [config.py](src/cryptoquant/config.py) 校验。
- 资金费率下载与对齐：[funding.py](src/cryptoquant/data/funding.py)、[funding_workflow.py](src/cryptoquant/data/funding_workflow.py)。
- 下载与缓存：[archive.py](src/cryptoquant/data/archive.py)。完整月份优先月包，仅月包 HTTP 404 才改取日包。
- 时间及字段：[normalize.py](src/cryptoquant/data/normalize.py)；质量和边界：[quality.py](src/cryptoquant/data/quality.py)。
- 订单规则：[rules.py](src/cryptoquant/data/rules.py)。数量步长取适用网格交集，市场标志决定名义金额过滤器是否适用。
- 流程与证据：[workflow.py](src/cryptoquant/data/workflow.py)、[cli.py](src/cryptoquant/cli.py)。
- 资金与成本：[ledger.py](src/cryptoquant/trading/ledger.py)、订单与预算：[orders.py](src/cryptoquant/trading/orders.py)、风险：[risk.py](src/cryptoquant/trading/risk.py)。
- 趋势指标：[strategies.py](src/cryptoquant/baselines/strategies.py)、事件引擎：[engine.py](src/cryptoquant/baselines/engine.py)、数据加载：[io.py](src/cryptoquant/baselines/io.py)、报告：[reporting.py](src/cryptoquant/baselines/reporting.py)。
- 特征工程：[features.py](src/cryptoquant/models/features.py)；模型拟合与预测：[training.py](src/cryptoquant/models/training.py)、[predictions.py](src/cryptoquant/models/predictions.py)。

当前规则快照用于历史模拟，不能还原每天的规则；市价名义金额只能以模拟成交价近似，不能恢复交易所参考价或分钟加权均价。完整实施顺序见 [实施计划](docs/superpowers/plans/2026-10-04-data-and-baseline-implementation.md)，实际进度见 [STATUS.md](STATUS.md)。

数据依据：[币安公开归档](https://github.com/binance/binance-public-data#readme)、[公开行情接口](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md)、[交易过滤器](https://github.com/binance/binance-spot-api-docs/blob/master/filters.md)。
