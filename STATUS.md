# 当前状态

最后更新：2026-10-05（Asia/Shanghai）。本文件是当前进度的唯一摘要，历史操作及旧结论见WORKLOG／EXPERIMENTS。

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

- 决策 D-046、D-047、D-048、D-050 与 D-051 已登记；
- **第一阶段（4h 连续净收益回归 vs 分类基准）已完成（D-047）**：证实连续回归在低信噪比下发生均值收缩，无法超越分类基准；
- **第二阶段（多预测周期 4h / 8h / 12h / 24h 受控实验与纯动态 C2 消融）已完成（D-048）**：确认 4h 为最佳预测周期，彻底终止长预测周期展期方向；
- **第三阶段（4h 二分类模型结构受控比较：LR vs LightGBM vs XGBoost vs CatBoost）已完成（D-050）**：证实当前瓶颈源于 12 特征 Alpha 饱和（情况 B），彻底终结非线性模型复杂度扩张；
- **第四阶段 A（No-Trade / 信号精选受控实验）已圆满完成（D-051）**：
  - 产物目录：`artifacts/research/no_trade_phase4a/`；
  - 冻结基准复现：Control_OPT0026（LR C=0.10, th=0.48, 纯动态 C2）精确复现 $g_{week} = \mathbf{+0.1293\%/w}$；
  - 10 组预冻结机制实证：所有 9 组 No-Trade 机制合成周收益全部落后于基准（+0.0990%/w 至 -0.0421%/w）；
  - 反事实分析（Counterfactual Avoidance Analysis）铁证：被 No-Trade 拦截的交易在所有候选中 `avoided_net_pnl` 全部为正（+23.62U 至 +68.48U）！过滤机制在节省 $3 \sim 8$U 手续费的同时，误杀了 $28 \sim 72$U 的毛利润，直接削弱了长期复利；
  - 核心定论：当前主要矛盾绝非单纯的过度交易，单币种时间序列过滤无法弥补 Alpha 瓶颈；正式剪枝 No-Trade 路线，继续锁定 OPT-0026 为唯一 Champion；
  - 下一步转向：Phase 4B 横截面 Top-K / 相对强弱排序（Cross-Sectional Top-K / Relative Strength Ranking）；
  - 测试验证：`tests/test_no_trade_phase4a.py`（5项测试）、`test_model_family_phase3.py`（6项测试）、`test_holdout_guard.py`（4项测试）、`test_optimization_pipeline.py`（4项测试）共计 19 项 pytest 100% 通过。

## 已完成与证据

- **第一阶段（4h 连续回归受控实验）**：产物见 `artifacts/research/regression_phase1/`。
- **第二阶段（多预测周期与纯动态 C2 受控实验）**：产物见 `artifacts/research/multi_horizon_phase2/` 与 `artifacts/research/horizon_c2_ablation/`。
- **第三阶段（4h 二分类模型结构受控比较）**：产物见 `artifacts/research/model_family_phase3/`。
- **第四阶段 A（No-Trade / 信号精选受控实验）**：产物见 `artifacts/research/no_trade_phase4a/`（含 `comparison_report.md`, `candidate_summary.csv`, `rejected_trade_analysis.csv`, `trading_metrics.csv`, `results.json`, `experiment_config.json`）。
- **单测体系**：`tests/test_no_trade_phase4a.py` 严格覆盖基准复现、模型特征一致性、交易修剪单调性、反事实损益恒等式及 2026 数据封存。

## 当前限制与长期边界

- 2026 年数据继续严格隔离，未用于训练、特征计算、阈值选择或评估（严格执行 no future leakage；test 分区物理 0 读取）。
- 面对实验事实实事求是接受，坚决不进行事后反向调参。
- 100 USDT 虚拟资金、三币共用账户、固定 50 USDT 底线、普通现货/无杠杆边界保持不变。
- 当前最优基准依然为 OPT-0026（+0.1293%/w），距离 1.5%/week 目标仍有约 11.6 倍数量级差距。

## 下一行动与交接

1. **Phase 4A 实验全部执行完毕，按用户要求立即停止，向用户汇报完整成果、代码修改、测试结果与 Git commit；绝不自动进入 Phase 4B。**
2. **严守研究红线**：
   - 2026 数据未用于训练、特征计算或评估（严格执行 no future leakage，test 分区物理 0 读取）；
   - 100 USDT 虚拟本金、50 USDT 固定底线、现货无杠杆与合规档位严格保持；
   - 坚决不刷细碎参数，不改变 C2 出场规则，不在未经验证的假设上堆砌复杂度。


