# 当前状态

最后更新：2026-10-06（Asia/Shanghai）。本文件是当前进度的唯一摘要，历史操作及旧结论见WORKLOG／EXPERIMENTS。

## 本轮任务

根据用户最新指令与决策 D-046：
1. **统一最终研究目标**：在严格时间序列 Walk-Forward、扣除所有模拟交易成本后，实现长期几何周净收益 **$g_{week} \ge 1.5\%$**（52 周年复利约 +116.89%），并保持合理最大回撤；
2. **终结局部细碎调参**：停止以“比 R6 略好”为主要成功标准；当前最优约 0.13%/week（OPT-0026 的 +0.1293%/week），与 1.5%/week 存在约 11.6 倍数量级差距，全面停止围绕现有 4h 二分类阈值、C 值与仓位进行细粒度微调；
3. **固化基准**：R6（人工基准，$g_{week}=+0.0979\%$）与 OPT-0026（参数搜索基准，$g_{week}=+0.1293\%$）仅保留为基准对照；
4. **下一阶段：系统性 Alpha 研究**：暂时只使用现有数据与 12 个特征，系统性跨维度自动比较：
   - 不同预测目标：二分类、未来净收益连续回归、风险调整收益；
   - 不同预测与持仓周期：4h、8h、12h、24h；
   - 模型架构：Logistic Regression / Ridge / Lasso、LightGBM 浅层与深度决策树族等；
   - 机制结构：自动滚动重训（Walk-Forward Periodic Retraining）、横截面排序择优、动态出场与 no-trade 过滤；
5. **剪枝原则与硬性约束**：无明显 Alpha 提升主动停止该路线，优先寻找数量级跨越；只能用过去训练未来，**2026 数据严格隔离，未用于训练、特征计算或评估（无未来泄露）**。

## 进行中与检查点

- 决策 D-046、D-047、D-048、D-050、D-051 与 D-052 已登记；
- **第一阶段（4h 连续净收益回归 vs 分类基准）已完成（D-047）**：证实连续回归在低信噪比下发生均值收缩，无法超越分类基准；
- **第二阶段（多预测周期 4h / 8h / 12h / 24h 受控实验与纯动态 C2 消融）已完成（D-048）**：确认 4h 为最佳预测周期，彻底终止长预测周期展期方向；
- **第三阶段（4h 二分类模型结构受控比较：LR vs LightGBM vs XGBoost vs CatBoost）已完成（D-050）**：在当前 12 个特征、4h 标签和执行体系下，LightGBM / XGBoost / CatBoost 未能明显超过 LR，因此暂时停止扩大模型复杂度；
- **第四阶段 A（No-Trade / 信号精选受控实验）已完成（D-051）**：
  - 本轮预先冻结的 9 种简单 No-Trade 过滤机制均未超过 Champion，因此暂时停止该类 No-Trade 规则研究；
- **第四阶段 B（Cross-Sectional Top-K / 相对强弱横截面分配受控实验）已完成（D-052）**：
  - 产物目录：`artifacts/research/topk_phase4b/`；
  - 实证定论：在固定单币仓位、被淘汰资金直接留现金的 Selection-Only 条件下，Top-1 / Top-2 横截面筛选均未超过 Champion（+0.0758%/w 至 +0.1136%/w）；
  - 核心机理：恶化主因之一是资金闲置（cash-drag），在多币齐涨大牛市中强行限制单币仓位留存大量现金导致踏空。
- **第四阶段 B2（Selection + 资本重分配受控实验）已完成（D-053）**：
  - 产物目录：`artifacts/research/reallocation_phase4b2/`；
  - 冻结基准精准复现：Control_OPT0026（LR C=0.10, th=0.48, 纯动态 C2）精确复现 $g_{week} = \mathbf{+0.1293\%/w}$（W1: +7.16%, W2: +17.41%, 2025: -2.70%, MDD: 11.51%, 225 周期）；
  - 8 组预冻结机制实证：所有 7 组资本重分配机制长期合成周收益全部跑输基准（+0.0514%/w 至 +0.1077%/w）；
  - 核心科学发现：在 104 次多信号共振事件中，Top-1 Probability 累计净损益为 **-18.39 USDT**（胜率 50.0%），而 Rank 2 为 **+4.79 USDT**（54.8%），Rank 3 为 **+2.38 USDT**（72.7%）；Top-1 呈现显著的负期望选择效应（追高局部超买竭尽点）；
  - 集中度压力测试定论：Cap 45% 与 Cap 60% 激进重分配使 2025 年净亏损放大至 -9.16% ~ -11.20%，MDD 飙升至 14.85%，最大单币敞口达 62.0%，严重放大错误选币的灾难性亏损；
  - 终审定论：在当前三币、当前 12 特征和现有模型信号下，简单横截面选择与资本重分配没有产生显著增量 Alpha；正式停止横截面方向探索。
- **基准与 Champion 选择全面审计已完成（Champion Selection Audit，D-054 与 D-055）**：
  - 产物目录：`artifacts/research/champion_selection_audit/`（含 `audit_summary.csv`, `top_by_gweek.csv`, `top_by_fitness.csv`, `pareto_front.csv`, `benchmark_comparison.csv`, `selection_history.md`, `comparison_report.md`）；
  - 终审结论判定（正式采纳选项 B）：**“OPT-0026 不是收益最高，也不是 fitness 最高，但在收益 / 2025 防守 / MDD / 交易数量之间是合理折中，因此可继续作为 Benchmark，但不应称绝对 Champion。”**；
  - **复利年化数学口径全面纠正（D-055）**：
    - 统一严格采用 52 周复利公式 $\text{Annual} = (1 + g_{week})^{52} - 1$；
    - 纠偏：OPT-0005（+0.1371%/w）对应 **+7.38%/年**（曾有对话中笔误记为 +103%，已彻底纠正）；OPT-0026（+0.1293%/w）对应 **+6.95%/年**；用户目标 1.5%/w 对应 **+116.89%/年**；
    - 尺度认识：当前策略与 1.5%/w 目标存在 11.6 倍周收益差距和 16 倍年化复利差距；
  - **建立 Phase 5 四大 Pareto Benchmark 体系**：
    - 废除围绕 OPT-0026 单一标尺修补的路径依赖；
    - 设立四大基准集合：
      - `OPT-0005`：高收益型 Benchmark（+0.1371%/w, 年化 +7.38%, MDD 11.60%）；
      - `OPT-0001`：次高收益型 Benchmark（+0.1311%/w, 年化 +7.05%, MDD 11.49%）；
      - `OPT-0026`：平衡型 Benchmark（+0.1293%/w, 年化 +6.95%, MDD 11.51%）；
      - `OPT-0056`：防守型 Benchmark（+0.1024%/w, 年化 +5.47%, MDD 11.21%）；
    - **新前沿评估准则**：新 Alpha 必须在同一套 Walk-Forward 回测引擎下，相对整个四类 Pareto Benchmark 集合，证明其向外推进了收益-风险前沿（Pareto Front Expansion）；
  - 治理与认知修正：全面清理文档中神化修辞，确认样本内筛选偏差与单变量消融局限。

## 已完成与证据

- **第一阶段（4h 连续回归受控实验）**：产物见 `artifacts/research/regression_phase1/`。
- **第二阶段（多预测周期与纯动态 C2 受控实验）**：产物见 `artifacts/research/multi_horizon_phase2/` 与 `artifacts/research/horizon_c2_ablation/`。
- **第三阶段（4h 二分类模型结构受控比较）**：产物见 `artifacts/research/model_family_phase3/`。
- **第四阶段 A（No-Trade / 信号精选受控实验）**：产物见 `artifacts/research/no_trade_phase4a/`。
- **第四阶段 B（横截面 Top-K / 相对强弱分配受控实验）**：产物见 `artifacts/research/topk_phase4b/`。
- **第四阶段 B2（横截面择优 + 资本重分配受控实验）**：产物见 `artifacts/research/reallocation_phase4b2/`。
- **Champion 选择与基准审计（Champion Selection Audit）**：产物见 `artifacts/research/champion_selection_audit/`。
- **第五阶段 A（衍生品持仓量与主动买卖流消融实验 Phase 5A）已完成（D-056）**：
  - 产物目录：`artifacts/research/alpha_phase5a_derivatives_flow/`（含 `data_quality_report.md`, `feature_definitions.json`, `experiment_config.json`, `prediction_metrics.csv`, `trading_metrics.csv`, `benchmark_comparison.csv`, `alpha_attribution.csv`, `pareto_front_before.csv`, `pareto_front_after.csv`, `results.json`, `comparison_report.md`）；
  - 数据质量：Binance 现货 1h Taker Flow 覆盖率 99.9971%；Binance Vision S3 官方 UM OI 覆盖率 99.97%~100.0%，严格无未来泄露；2026 数据完全封存（0 读取）；
  - 16 组全景 Walk-Forward 比较：4 大 Pareto Benchmark 精确零误差复现；加入 OI 或 Flow 的所有候选长期周收益全部弱于对应原基准；
  - 前沿判定：没有任何旧 Pareto Benchmark 被新候选严格支配，Pareto 前沿未产生有效外推；
  - 归因结论：Regime A~H 微观净收益差异仅 2~3 bps，不足以覆盖 0.30055% 双边摩擦，线性模型下稀释了核心 OHLCV 量价权重；
  - 终审定论：在当前数据定义、4h 决策尺度、LR 线性模型与交易体系下，本轮 OI / Taker Flow 未表现出稳定增量 Alpha。
- **第五阶段 A2（衍生品特征校准与阈值稳健性审计 Phase 5A2）已完成（D-057）**：
  - 产物目录：`artifacts/research/alpha_phase5a2_calibration/`；
  - 终审科学裁决：【结论 A】新特征预测层和交易层均无改善，正式剪枝；
  - 单测体系：`tests/test_derivatives_calibration_phase5a2.py` 与 `test_derivatives_flow_phase5a.py` 等测试全部通过。
- **第五阶段 B（衍生品持仓量与主动买卖流交互特征受控实验 Phase 5B）已完成（D-058）**：
  - 产物目录：`artifacts/research/alpha_phase5b_interactions/`（含 `feature_definitions.json`, `experiment_config.json`, `interaction_diagnostic.csv`, `prediction_metrics.csv`, `trading_metrics.csv`, `price_oi_quadrants.csv`, `price_flow_quadrants.csv`, `triple_state_analysis.csv`, `benchmark_comparison.csv`, `pareto_front_before.csv`, `pareto_front_after.csv`, `results.json`, `comparison_report.md`）；
  - 终审科学裁决：**微观状态存在 4~8 bps 统计差异，但在当前 4h 尺度、LR 线性模型与现货手续费摩擦下，交互特征未能产生稳定可交易 Alpha，四大 Benchmark 维持统治地位**；
  - 预测层 vs 交易层分离：
    - `INTERACTION_PRICE_OI` 和 `INTERACTION_OI_FLOW` 满足预测门槛（在 W2/R2025 中 AUC/PR-AUC 微增 +0.05~+0.25 bps），但在交易层中因微小摩擦与时机错配，周收益反而衰退 2~4 bps/week；
    - `INTERACTION_CONTEXT` 在交易层表现出周收益微增（OPT-0005 周收益从 +0.1371%/w 升至 +0.1453%/w，年化从 +7.38% 升至 +7.84%），但在预测层 3 个 Fold 中 AUC/PR-AUC 均无改善（0/3 胜率），缺乏稳健的预测层统计支撑，存在过拟合/样本扰动风险；
  - 象限与三变量联合状态：
    - Price × OI 4 象限中，Q1（价涨+OI涨）相比 Q2（价涨+OI跌）未来 4h 净收益高 4.26 bps；
    - Price × Flow 差异不足 1 bps；
    - 三变量 8 状态中，S1 与最差状态 S5 相比仅相差 7.7 bps，全量状态在扣除 30 bps 双边摩擦后均为负期望；
  - Pareto 前沿评估：四大旧 Benchmark（OPT-0005, OPT-0001, OPT-0026, OPT-0056）未被任何具有稳定统计预测增量的候选严格支配；
  - 单测体系：`tests/test_derivatives_interactions_phase5b.py` 8 passed，总计 18 项衍生品测试 100% PASS。

## 当前限制与长期边界

- 2026 年数据继续严格隔离，未用于训练、特征计算、阈值选择或评估（严格执行 no future leakage；test 分区物理 0 读取）。
- 面对实验事实实事求是接受，坚决不进行事后反向调参。
- 100 USDT 虚拟资金、三币共用账户、固定 50 USDT 底线、普通现货/无杠杆边界保持不变。
- 四大 Pareto Benchmark 作为当前实证权衡基准，当前最佳周收益仍以具有稳健预测支撑的 OPT-0005 (+0.1371%/w，年化 +7.38%) 为主，距离 1.5%/week 目标仍有约 10.9 倍周收益差距。

## 下一行动与交接

1. **Phase 5B 交互特征探索圆满闭环**：完成 8 项交互特征、象限分析、三变量状态诊断与 24 候选 Walk-Forward 回测，登记 D-058。
2. **严守停止纪律**：正式结束当前 Open Interest 与 Taker Flow 研究路线；立即停止，**不自动进入后续阶段，等待用户指令**。


