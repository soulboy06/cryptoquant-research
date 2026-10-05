# 第八轮动态阈值调节与自适应仓位缩放实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 或 superpowers:executing-plans；逐项核对实际成果后勾选。

**Goal:** 基于 EXP-128 诊断结论，实现并验证状态感知响应（动态阈值与自适应仓位变体 R2/R3/R4），与基线 R0 及二元过滤 R1 对比，检验能否在保留 2024 牛市独立动量收益的同时，有效削减 2025 震荡市回撤。

**Architecture:** 
1. 状态与响应解耦：复用 EXP-122 状态数据（只读核验），在决策目标生成阶段（`dynamic_regime.py`）将预测概率与 BTC 状态对齐，输出每 4h 包含动态阈值与自适应目标权重的决策目标表；
2. 交易引擎支持多档仓位权重：调整 `engine.py` 目标仓位有效性校验，支持 0.10、0.15、0.30 多档合法非零权重，严格保持现金同比缩放、单币止损与 C2 动态保本逻辑不变；
3. 专用工作流与 CLI：实现 `dynamic_workflow.py` 与独立 CLI（`dynamic-evaluate`、`dynamic-select`、`dynamic-compare`），绑定只读来源门禁与 15 个账户预算上限。

**Tech Stack:** Python 3.12、pandas、numpy、现有事件驱动账本引擎、SHA-256 数据门禁、pytest。

日期：2026-10-05（Asia/Shanghai）。依据：[第八轮方案](../specs/2026-10-05-dynamic-threshold-and-position-scaling-design.md)。方案已冻结；勾选只标记实际完成项，2026 测试集坚决封存，无真实下单。

---

## Task 1：动态决策目标逻辑与第八轮冻结配置

文件：新增 `src/cryptoquant/models/dynamic_regime.py`、`configs/eighth_experiment.toml`、`tests/test_dynamic_regime.py`。

- [x] 实现 `build_dynamic_decision_targets(probabilities, regime_states, variant)` 函数：
  - 严格校验两表时间戳对齐（UTC 4h 网格，无缺失、无未来泄露）；
  - `Favorable` 判定：`state_valid == True` 且 `adx14 >= 20` 且 `slope24 > 0`；
  - 针对变体 R2、R3、R4，精确应用预设阈值 $T$ 与仓位权重 $W$：
    - R2：Favorable ($T=0.50, W=0.30$) / Weak ($T=0.60, W=0.30$)；
    - R3：Favorable ($T=0.50, W=0.30$) / Weak ($T=0.50, W=0.10$)；
    - R4：Favorable ($T=0.50, W=0.30$) / Weak ($T=0.60, W=0.15$)；
  - 输出格式必须包含：`symbol`, `decision_time`, `probability`, `target_weight`, `market_regime`, `applied_threshold`, `applied_weight`。
- [x] 编写配置文件 `configs/eighth_experiment.toml`：
  - 冻结底层模型配置（复用 EXP-065/067/094，C=0.1，net 政策）；
  - 冻结 R2、R3、R4 变体参数与候选清单；
  - 冻结来源门禁路径与实验预算（最多 9 个 Base 账户、6 个压力账户）。
- [x] 编写针对性测试 `tests/test_dynamic_regime.py`：
  - 测试因果完整性：修改未来行情不改变当前动态决策；
  - 测试边界对齐：缺少状态行或时间冲突必须报错；
  - 测试规则精确性：单点验证弱势状态下提阈值与降仓的逻辑一致性。

Task 1 证据：`tests/test_dynamic_regime.py` 5 passed (0.48s)，配置加载与变体参数完全一致。

---

## Task 2：交易引擎多档目标仓位支持与出场风控等价性

文件：修改 `src/cryptoquant/baselines/engine.py`；新增 `tests/test_dynamic_execution.py`。

- [x] 调整 `engine.py` 中的决策目标权重合法性校验：
  - 将原先单一的 `amount(weight) not in {ZERO, config.weight_per_symbol}` 泛化为支持多档合法权重：允许 `weight == ZERO` 或 `weight in {0.10, 0.15, 0.30}`（且不超过 `config.weight_per_symbol`）；
  - 严禁输入负权重或超过 0.30 的非法权重；
- [x] 验证现有执行逻辑对降仓的完全兼容性：
  - 验证弱势期 $W=0.10$ 下单时的名义金额检查（$\ge 10\text{ USDT}$）；
  - 验证现金不足时的同比缩放逻辑正常运作；
  - 验证当状态由顺势变为弱势时，若策略目标由 0.30 降至 0.10，引擎按原计划重平衡（plan_rebalance）执行有序减仓，且不影响已有持仓的 C2 动态保本止损与硬止损；
- [x] 编写并执行针对性测试 `tests/test_dynamic_execution.py`：
  - 测试合成行情下多档仓位的买入与平仓流程；
  - 验证若传入恒定 0.30 目标权重，其执行轨迹与原 C2 逐笔完全等价。

Task 2 证据：`tests/test_dynamic_execution.py` 3 passed (0.68s)，资金守恒与 C2 兼容性通过。

---

## Task 3：第八轮研究工作流与 CLI 入口实现

文件：新增 `src/cryptoquant/models/dynamic_workflow.py`；修改 `src/cryptoquant/cli.py`；新增 `tests/test_dynamic_research.py`。

- [x] 实现 `dynamic_workflow.py`：
  - 严格来源门禁：只读核验 EXP-003 数据、EXP-063 特征与 EXP-122 状态数据 SHA-256；
  - 预算控制门禁：记录并限制新账户尝试次数，拒绝重复编号与超出预算（>15）的启动；
  - 导出标准化产物：`summary.json`, `equity.csv`, `orders.csv`, `fills.csv`, `signals.csv`, `weekly.csv`, `run_manifest.json` 与中文 `report.md`。
- [x] 注册 CLI 命令：
  - `dynamic-evaluate`：支持 `--variant R2/R3/R4 --window W1/W2/R2025 --cost base/higher_execution/strict`；
  - `dynamic-select`：执行第 5.1 节基础门槛筛选并输出决选清单 `selection.json`；
  - `dynamic-compare`：汇总基线 R0、R1 与 R2~R4，生成全景对比报告。
- [x] 编写针对性测试 `tests/test_dynamic_research.py`：
  - 验证来源篡改与预算超额时的即时拒绝；
  - 验证 CLI help 与离线参数解析正常。

Task 3 证据：`tests/test_dynamic_research.py` 3 passed (1.91s)，CLI help 与预算审计通过；34 项回归检查全部通过（8.31s）。

---

## Task 4：执行 9 组 Base 基础回测与综合筛选

文件：执行 CLI；更新 `EXPERIMENTS.md`、`STATUS.md`。

- [x] 在 `EXPERIMENTS.md` 事前登记 EXP-129 ~ EXP-138 共 9 组 Base 实验（含 1 组启动格式异常保留）与 EXP-139 选择实验；
- [x] 依次运行 9 组 Base 基础回测：
  - R2（动态提阈值）：EXP-130（W1, +0.17%/4.02%/18笔）、EXP-131（W2, +12.28%/3.38%/26笔）、EXP-132（R2025, -9.09%/11.14%/67笔）；
  - R3（自适应降仓）：EXP-133（W1, +2.46%/3.72%/29笔）、EXP-134（W2, +13.66%/2.79%/55笔）、EXP-135（R2025, -7.68%/11.92%/50笔）；
  - R4（双重协同）：EXP-136（W1, +0.17%/4.02%/18笔）、EXP-137（W2, +9.35%/2.86%/26笔）、EXP-138（R2025, -7.80%/10.15%/67笔）；
- [x] 执行 EXP-139 基础筛选：
  - 按方案第 5.1 节门槛对 9 组回测执行严格筛选；
  - 判定全变体失格（`eligible = False`, `winner = None`），R3 表现最优（牛市捕获 55 笔主升浪、2025 减亏 +5.24U），但因 W1 缺 1 笔达标 30 笔门槛、W2 净收益 13.66% 缺 1.34% 达标 15% 门槛而失格；
  - 如实记录全候选失格，完整保存数据并坚决停止压力测试。

Task 4 证据：EXP-130~138 均生成完整 summary/orders/fills/equity/report/run_manifest；EXP-139 生成 selection.json 与 report.md。

---

## Task 5：执行条件压力测试与全景综合对比评估

文件：执行 CLI；生成 `artifacts/experiments/EXP-140/report.md`。

- [x] （按规则终止压力）因 EXP-139 判定全候选失格，严格执行方案门禁：坚决停止 6 组压力测试（EXP-139~EXP-144 压力账户未被创建），避免浪费回测预算；
- [x] 运行 EXP-140 全景对比评估：
  - 汇总 R0、R1 与 R2~R4 全量数据；
  - 横向对比净收益、最大回撤、交易周期、摩擦费用与动量保留；
  - 给出因果性（通过）、相对改善（R3 局部显著改善但未达硬标）与周 1.5% 目标（未达）的三层结论，生成综合报告 `report.md` 与 `comparison.json`。

Task 5 证据：EXP-140 生成完整 comparison.json 与 report.md；预算审计记录 12 项尝试（10 个账户），无超出预算行为。

---

## Task 6：终审验收、文档归档与安全交接

文件：`README.md`、`STATUS.md`、`DECISIONS.md`、`EXPERIMENTS.md`、`WORKLOG.md`。

- [x] 更新 `DECISIONS.md`：记录 D-037（第八轮动态响应全候选筛选失格判定、停止压力测试与后续路线）；
- [x] 更新 `EXPERIMENTS.md`：补齐 EXP-129 ~ EXP-140 的实际运行结果、全矩阵对比表与产物链接；
- [x] 更新 `README.md`：补充第八轮 CLI 命令与参数说明；
- [x] 更新 `WORKLOG.md`：详细记录本轮操作、检查日志与数据证据；
- [x] 更新 `STATUS.md`：反映第八轮最终状态、核心结论与下一步行动。

---

## 验证与完成标准

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_dynamic_regime.py tests/test_dynamic_execution.py tests/test_dynamic_research.py -q -W error
```

完成标准：
1. 动态目标与状态因果对齐无泄露；
2. 交易引擎支持 0.10/0.15/0.30 仓位且风控与记账守恒；
3. 全部实验在 15 账户预算内严格按序执行，失败亦如实记录；
4. 明确给出是否解决 2024 牛市错杀与 2025 假突破大回撤的量化结论；
5. 2026 测试集未受触碰，无实盘风险。
