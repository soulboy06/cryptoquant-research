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

- 决策 D-046、D-047、D-048 与 D-050 已登记；
- **第一阶段（4h 连续净收益回归 vs 分类基准）实证与剪枝已完成（D-047）**：证实 4h 连续回归在低信噪比下发生均值收缩，无法超越分类基准；
- **第二阶段（多预测周期 4h / 8h / 12h / 24h 受控实验与纯动态 C2 消融）已完成（D-048）**：确认 4h 为最佳预测周期，彻底终止长预测周期展期方向；
- **第三阶段（4h 二分类模型结构受控比较：LR vs LightGBM vs XGBoost vs CatBoost）已圆满完成（D-050）**：
  - 产物目录：`artifacts/research/model_family_phase3/`；
  - 冻结基准复现：OPT-0026（LR C=0.10, th=0.48, 纯动态 C2）精确复现 $g_{week} = \mathbf{+0.1293\%/w}$（2023=+7.16%, 2024=+17.41%, 2025=-2.70%, MDD=11.51%）；
  - 双轨对照实证结果：
    - **Lane A（固定 0.48 阈值）**：LR_C0.10（+0.1293%/w）与 LR_C0.50（+0.1181%/w）表现突出，而所有树模型（LGB_shallow -0.0515%/w, LGB_conservative -0.0103%/w, XGB_shallow -0.0482%/w, XGB_conservative -0.0272%/w, CAT_shallow -0.0295%/w, CAT_conservative -0.0285%/w）合成收益**全部为负**；
    - **Lane B（严格时序内 inner walk-forward 自适应阈值选择，0 lookahead）**：自适应校准各模型概率标尺后，表现最好的树模型为 CAT_shallow（+0.0676%/w），但仍显著落后于 Champion OPT-0026（落后 6.2 bps），且平均持仓长达 36.2 小时；其余树模型合成周收益全部在 -0.0027%/w 至 -0.0909%/w 之间；
  - 预测诊断与交易实证脱节：树模型在验证集的 ROC-AUC（0.58~0.60）普遍略高于 LR（0.55~0.57），但在真实扣成本（0.30055%）仿真中全面劣于线性强正则模型，证实高 AUC 仅为微观非线性噪声过拟合；
  - 核心科学结论：**确凿证实属于【情况 B】——当前收益瓶颈绝非模型表达能力不足，而是现有 12 个特征本身缺乏更强的净 Alpha 信息量**；
  - 终审剪枝裁决：**彻底停止继续扩大模型复杂度，严禁引入神经网络或复杂非线性集成；Champion OPT-0026 坚决不予更换**；
  - 测试验证：`tests/test_model_family_phase3.py`（6项测试）、`test_holdout_guard.py`（4项测试）、`test_optimization_pipeline.py`（4项测试）共计 14 项 pytest 100% 通过。

## 已完成与证据

- **第一阶段（4h 连续回归受控实验）**：产物见 `artifacts/research/regression_phase1/`。
- **第二阶段（多预测周期与纯动态 C2 受控实验）**：产物见 `artifacts/research/multi_horizon_phase2/` 与 `artifacts/research/horizon_c2_ablation/`。
- **第三阶段（4h 二分类模型结构受控比较）**：产物见 `artifacts/research/model_family_phase3/`（含 `comparison_report.md`, `trading_metrics.csv`, `prediction_metrics.csv`, `threshold_selection.csv`, `model_family_summary.csv`, `results.json`, `experiment_config.json`）。
- **单测体系**：`tests/test_model_family_phase3.py` 严格覆盖事前时序阈值隔离、训练截断零未来泄露、特征列一致性、决策网格一致性、随机种子可复现性及 2026 数据封存。

## 当前限制与长期边界

- 2026 年数据继续严格隔离，未用于训练、特征计算、阈值选择或评估（严格执行 no future leakage；test 分区物理 0 读取）。
- 面对实验事实实事求是接受，坚决不进行事后反向调参（如为了让树模型赢而人为修改参数或阈值）。
- 100 USDT 虚拟资金、三币共用账户、固定 50 USDT 底线、普通现货/无杠杆边界保持不变。
- 当前最优基准依然为 OPT-0026（+0.1293%/w），距离 1.5%/week 目标仍有约 11.6 倍数量级差距。

## 下一行动与交接

1. **Phase 3 实验全部执行完毕，按要求立即停止，向用户汇报完整成果、代码修改、测试结果与 Git commit；不自动进入下一阶段。**
2. **严守研究红线**：
   - 2026 数据未用于训练、特征计算或评估（严格执行 no future leakage，test 分区物理 0 读取）；
   - 100 USDT 虚拟本金、50 USDT 固定底线、现货无杠杆与合规档位严格保持；
   - 坚决不刷细碎参数，不改变 C2 出场规则，不在未经验证的假设上堆砌复杂度。


