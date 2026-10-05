# 第九轮：多币种相对强弱解耦与自适应配仓实施计划

日期：2026-10-05（Asia/Shanghai）；版本 v0.1。

状态：计划已编制，待逐步执行。依据[第九轮方案](../specs/2026-10-05-relative-strength-and-adaptive-allocation-design.md)设计推进，任务复选框仅在实际完成并经过针对性检查后勾选。

---

## 阶段与依赖

- 依赖：第七轮状态准备（EXP-122）、第八轮动态仓位经验（EXP-129~140）、C2 动态保本规则（EXP-114）及 12 特征逻辑回归模型（EXP-065/067/094）。
- 本轮核心：在弱势大盘中解耦独立强势币种（如 SOL），按相对超额收益 $\Delta R_{72h} > 0$ 赋予 20%~25% 优势仓位，验证能否在守住 2025 减亏的同时突破 2024 牛市 15% 收益线。
- 预算：最多 9 个 Base 账户（EXP-141~149）、1 项筛选决策（EXP-150）、最多 6 个条件压力账户（EXP-151~156）及 1 项综合报告（EXP-157）。2026 保留测试集继续严格封存。

---

## Task 1：相对强弱（Alpha）计算与多档目标构建

文件：新建 `src/cryptoquant/models/relative_strength.py`、`configs/ninth_experiment.toml`；新建 `tests/test_relative_strength.py`。

- [x] 实现 `compute_relative_strength_features(features_dict)`：
  - 提取各币种截至 $t-1\text{h}$ 的闭合 72 小时收益率 $R_{72h}$；
  - 计算对 BTC 的超额收益 $\Delta R_{72h} = R_{72h}(s) - R_{72h}(\text{BTC})$；
  - 判定 `is_alpha_leader = (Delta_R72h > 0) and (R72h > 0)`；
- [x] 实现 `build_alpha_decision_targets(probabilities, states, features_dict, variant)`：
  - 严格根据 R5/R6/R7 矩阵规则，对顺势期映射 30% 仓位；对弱势期根据 `is_alpha_leader` 映射 20%/25% 或 10% 仓位；
- [x] 创建并冻结 `configs/ninth_experiment.toml`，在 `research_config.py` 增加 V9 配置字典支持；
- [x] 编写针对性测试 `tests/test_relative_strength.py`：
  - 检验 $t-1\text{h}$ 因果边界；
  - 检验 R5/R6/R7 仓位映射逻辑的精确性与边界值。

---

## Task 2：交易引擎多档目标权重支持（扩展 0.20 与 0.25）

文件：修改 `src/cryptoquant/baselines/engine.py`；新建 `tests/test_alpha_execution.py`。

- [x] 调整 `engine.py` 目标仓位合法性检查，支持 `{ZERO, Decimal('0.10'), Decimal('0.15'), Decimal('0.20'), Decimal('0.25'), Decimal('0.30')}`；
- [x] 验证现金缩放比例、名义金额过滤器（10 USDT）与数量精度控制无截断；
- [x] 编写针对性测试 `tests/test_alpha_execution.py`：
  - 验证多币种同时持仓时的资金分配守恒；
  - 验证动态保本止损线（C2）在 0.20 / 0.25 仓位下的逐笔撮合一致性。

---

## Task 3：研究工作流与 CLI 子命令接入

文件：新建 `src/cryptoquant/models/alpha_workflow.py`；修改 `src/cryptoquant/cli.py`；新建 `tests/test_alpha_research.py`。

- [x] 实现工作流 `alpha_workflow.py`：
  - `execute_alpha_evaluate`：执行 R5/R6/R7 单账户回测与周统计；
  - `execute_alpha_select`：执行基础门槛筛选与最优变体决选；
  - `execute_alpha_compare`：汇总基线 R0、R1、R3 与 R5~R7 全量对账；
- [x] 在 `cli.py` 注册子命令：
  - `alpha-evaluate`
  - `alpha-select`
  - `alpha-compare`
- [x] 编写针对性测试 `tests/test_alpha_research.py`：
  - 验证预算审计、命令调度与篡改检测；
  - 验证 45 项既有回归测试全绿。

---

## Task 4：执行 9 组 Base 基础回测与综合筛选

文件：执行 CLI；更新 `EXPERIMENTS.md`、`STATUS.md`。

- [x] 在 `EXPERIMENTS.md` 事前登记 EXP-141 ~ EXP-149（9 组 Base 实验）与 EXP-150（基础筛选）；
- [x] 依次运行 9 组 Base 基础回测：
  - R5（Alpha 20%）：EXP-141（W1）、EXP-142（W2）、EXP-143（R2025）；
  - R6（Alpha 25%）：EXP-144（W1）、EXP-145（W2）、EXP-146（R2025）；
  - R7（Alpha 波动率）：EXP-147（W1）、EXP-148（W2）、EXP-149（R2025）；
- [x] 执行 EXP-150 基础筛选：
  - 严格按方案第 5.1 节门槛筛选，判定候选资格并决选出胜出变体；
  - 若无候选过线，如实记录失格事实，完整保存数据并坚决停止压力测试。

---

## Task 5：执行条件压力测试与全景综合对比评估

文件：执行 CLI；生成 `artifacts/experiments/EXP-157/report.md`。

- [x] （条件执行）仅当 EXP-150 产生合格胜出候选时，在 `EXPERIMENTS.md` 登记 EXP-151 ~ EXP-156，并依次运行胜出变体的 6 组压力测试：
  - *（已按方案第 5.1 与 6 节门槛规则：EXP-150 全候选失格，坚决停止 6 组压力测试，未消耗 EXP-151~156 账户预算）*
- [x] 运行 EXP-157 全景对比评估：
  - 汇总 R0、R1、R3 及 R5~R7 全量数据；
  - 横向对比净收益、最大回撤、交易周期、摩擦费用与动量保留；
  - 给出因果性、相对改善与周 1.5% 目标的三层结论，生成综合报告 `report.md` 与 `comparison.json`。

---

## Task 6：终审验收、文档归档与安全交接

文件：`README.md`、`STATUS.md`、`DECISIONS.md`、`EXPERIMENTS.md`、`WORKLOG.md`。

- [x] 更新 `DECISIONS.md`：记录 D-038（第九轮方案）与 D-039（第九轮相对强弱解耦实验结论）；
- [x] 更新 `EXPERIMENTS.md`：补齐 EXP-141 ~ EXP-157 的实际运行结果与产物链接；
- [x] 更新 `README.md`：补充第九轮 CLI 命令与参数说明；
- [x] 更新 `WORKLOG.md`：详细记录本轮操作、检查日志与数据证据；
- [x] 更新 `STATUS.md`：反映第九轮最终状态、核心结论与下一步行动。
