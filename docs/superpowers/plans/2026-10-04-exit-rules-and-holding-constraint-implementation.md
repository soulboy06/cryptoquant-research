# 第六轮：出场机制优化与持仓约束实施计划

日期：2026-10-04（Asia/Shanghai）；版本：v0.1

依据：[出场机制优化与持仓约束设计方案](../specs/2026-10-04-exit-rules-and-holding-constraint-design.md)。
最新事实：[STATUS.md](../../../STATUS.md)；历史实验编号已至 EXP-101，本轮实验自 EXP-102 起现场登记。

---

## 阶段规划概览

- **Task 1**：在交易风控（`risk.py`）与事件引擎（`engine.py`）中实现持仓时长跟踪、时限平仓（Rule A）与动态保本止损（Rule B），编写针对性单元测试；
- **Task 2**：在研究配置（`research_config.py`）与工作流（`research_workflow.py`）中扩展策略变体参数（C0, C1, C2, C3）；
- **Task 3**：登记并执行三窗口（W1, W2, R2025）下四组候选的 12 次 base 账户回测（预计 EXP-102~EXP-113）；
- **Task 4**：依据预先冻结标准进行消融对比评估与选优（EXP-114），对胜出者运行 6 组 higher_execution 与 strict 压力测试（EXP-115~EXP-120）；
- **Task 5**：生成第六轮全景综合报告（EXP-121），同步 STATUS、EXPERIMENTS、WORKLOG 与 DECISIONS，保持 2026 测试集物理封存。

---

## Task 1：风控内核扩展与针对性行为检查

**Files:** 修改 `src/cryptoquant/trading/risk.py`、`src/cryptoquant/baselines/engine.py`；新增 `tests/test_exit_rules.py`。

- [x] **Step 1：在 `RiskState` 中实现持仓时长与浮盈状态追踪。**
  - 为每个持仓币种维护 `entry_time`、`holding_hours`、`max_return_observed` 和 `breakeven_active`；
  - 每小时收盘时更新 `holding_hours += 1`，并计算当前收盘价相对于 `position.average_cost` 的浮动收益率，更新 `max_return_observed`；
  - 若 `max_return_observed >= 0.0120`（+1.20%），置 `breakeven_active = True`；
- [x] **Step 2：实现两项出场触发逻辑（纠正成本口径）。**
  - **时限触发（Rule A）**：若启用 `max_holding_hours`（8 小时），当 `holding_hours >= max_holding_hours` 时，将 `pending` 置为 `max_duration_exit`；
  - **动态保本触发（Rule B）**：若启用 `breakeven_stop` 且 `breakeven_active == True`，当 `marks[symbol] <= position.average_cost * Decimal('1.0025')`（+0.25% 覆盖单边卖出摩擦 +0.1502% 与 +0.10% 缓冲）时，将 `pending` 置为 `breakeven_exit`；
  - **硬止损优先级**：原有的 8% 硬止损（`stop_loss`）依然拥有最高安全级别，一旦跌破 -8% 无条件优先触发；
- [x] **Step 3：引擎撮合支持新意图、禁止同K重买并引入冷却期。**
  - `engine.py` 在处理 `pending` 为 `max_duration_exit` 或 `breakeven_exit` 时，执行全平意图并在次小时开盘市价撮合；
  - **同K禁止重买**：执行 `max_duration_exit` 的币种自动加入当期 `blocked`，杜绝同开盘买入；
  - **强制 4 小时冷却**：平仓完成后进入 4 小时冷却期（`cooldown_until = timestamp + 4h`），避免到期刚平立刻重买造成双重摩擦损耗；
- [x] **Step 4：编写针对性单元测试 `tests/test_exit_rules.py`。**
  - 验证时限上限在精确第 8 小时触发平仓、同K不重买且进入 4h 冷却；
  - 验证浮盈达到 +1.20% 激活保本、回落至 `average_cost * 1.0025` 触发退出并进入 4h 冷却；
  - 验证突发跳空低开时撮合不崩溃，依然遵守资金守恒；
  - 运行命令：`.venv/Scripts/python.exe -m pytest tests/test_exit_rules.py -q -W error`（4 passed）。

---

## Task 2：研究配置扩展与工作流适配

**Files:** 修改 `src/cryptoquant/models/research_config.py`、`src/cryptoquant/models/research_workflow.py`、`src/cryptoquant/cli.py`。

- [x] **Step 1：扩展研究配置支持出场变体。**
  - 在配置中定义 `exit_variant`：`C0`（基准对照）、`C1`（仅时限）、`C2`（仅保本）、`C3`（组合）；创建 `configs/sixth_experiment.toml`；
- [x] **Step 2：CLI 与工作流透传。**
  - 让 `research-evaluate` 接受 `--exit-variant` 参数，调用对应风控规则，报告与 summary.json 包含变体及触发统计。

---

## Task 3：12 次受控窗口 base 回测执行（EXP-102 至 EXP-113）

**Files:** `artifacts/experiments/EXP-102` ~ `EXP-113`。

- [x] **Step 1：现场登记实验编号。**
  - 在 `EXPERIMENTS.md` 登记 EXP-102 至 EXP-113：
    - W1（2023）：C0（EXP-102）、C1（EXP-105）、C2（EXP-108）、C3（EXP-111）
    - W2（2024）：C0（EXP-103）、C1（EXP-106）、C2（EXP-109）、C3（EXP-112）
    - R2025（2025）：C0（EXP-104）、C1（EXP-107）、C2（EXP-110）、C3（EXP-113）
- [x] **Step 2：严格按顺序执行回测。**
  - 每次使用独立 100 USDT 虚拟资金，生成 orders、fills、equity、weekly CSV 与 summary.json，全部完成。

---

## Task 4：消融评估、参数冻结与压力测试（EXP-114 至 EXP-120）

**Files:** `artifacts/experiments/EXP-114` ~ `EXP-120`。

- [x] **Step 1：执行预先冻结的四项硬门槛与二级准则，冻结最优候选（EXP-114）。**
  - 检查 50U 底线 0 触发、交易次数 $\ge 30$、回撤未恶化；
  - 评估 2024 牛市收益保留率：C2 达到 82.16% $\ge 75\%$（唯一合格，C1 仅 69.97% 淘汰）；
  - 产出分析评估报告：`artifacts/experiments/EXP-114/report.md`，冻结 C2 参数卡；
- [x] **Step 2：对最优候选运行 6 组压力测试（EXP-115 至 EXP-120）。**
  - `higher_execution`（0.40%）：W1（EXP-115, +3.21%）、W2（EXP-116, +21.55%）、R2025（EXP-117, -16.27%）全部指标满分通过；
  - `strict`（0.60%）：W1（EXP-118, +0.62%）、W2（EXP-119, +14.98%）、R2025（EXP-120, -23.10%）运行完成；2026-10-05复核EXP-119精确净收益为14.9816541437466%，低于预定15.00%，因此strict整体未通过，不改门槛或冻结报告。

---

## Task 5：综合对比报告与文档交接（EXP-121）

**Files:** `artifacts/experiments/EXP-121/report.md`、`STATUS.md`、`EXPERIMENTS.md`、`WORKLOG.md`、`DECISIONS.md`。

- [x] **Step 1：生成消融对比综合报告 EXP-121。**
  - 清晰呈现 C0、C1、C2、C3 在三时期的收益、回撤、交易次数、止损次数与周收益对账表，以及压力测试全景；
- [x] **Step 2：全面更新文档体系。**
  - 记录决策 D-032，更新 STATUS 最新状态与下一步，追加 WORKLOG WL-027；
  - 保持 2026 测试集封存。

## 2026-10-05进度复核补充

上述勾选记录已有实施和产物，不替代当前方法验收：EXP-102—121产物与摘要已核对，strict W2收益未过线，样本／模型来源校验与研究选择资格／参数／预算门禁仍有缺口，出场关键行为检查需核对真实执行证据。不得将全部勾选推定为方法、压力或盈利目标全部通过。现状和下一行动统一见STATUS；保留原实验报告与失败，不启动新的研究或放宽标准。
