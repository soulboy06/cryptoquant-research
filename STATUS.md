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

- 决策 D-046、D-047、D-048、D-050、D-051 与 D-052 已登记；
- **第一阶段（4h 连续净收益回归 vs 分类基准）已完成（D-047）**：证实连续回归在低信噪比下发生均值收缩，无法超越分类基准；
- **第二阶段（多预测周期 4h / 8h / 12h / 24h 受控实验与纯动态 C2 消融）已完成（D-048）**：确认 4h 为最佳预测周期，彻底终止长预测周期展期方向；
- **第三阶段（4h 二分类模型结构受控比较：LR vs LightGBM vs XGBoost vs CatBoost）已完成（D-050）**：在当前 12 个特征、4h 标签和执行体系下，LightGBM / XGBoost / CatBoost 未能明显超过 LR，因此暂时停止扩大模型复杂度；
- **第四阶段 A（No-Trade / 信号精选受控实验）已完成（D-051）**：
  - 本轮预先冻结的 9 种简单 No-Trade 过滤机制均未超过 Champion，因此暂时停止该类 No-Trade 规则研究；
- **第四阶段 B（Cross-Sectional Top-K / 相对强弱横截面分配受控实验）已圆满完成（D-052）**：
  - 产物目录：`artifacts/research/topk_phase4b/`；
  - 冻结基准复现：Control_OPT0026（LR C=0.10, th=0.48, 纯动态 C2）精确复现 $g_{week} = \mathbf{+0.1293\%/w}$（W1: +7.16%, W2: +17.41%, 2025: -2.70%, MDD: 11.51%, 225 周期）；
  - 9 组预冻结机制实证：所有 8 组 Top-K 择优机制的长期合成周收益全部落后于基准（+0.0758%/w 至 +0.1136%/w）；
  - 核心机理：Top-2 优于 Top-1；恶化主因是大牛市（2024）多币齐涨时强行单币限购导致 70% 资金闲置踏空，收益腰斩（从 +17.41% 暴跌至 +7.88%~+8.97%），而 2025 年未改善；
  - 反事实分析证据：被横截面淘汰的交易在所有候选中 `eliminated_net_pnl` 全部为显著正值（+4.26U 至 +33.21U），胜率超 60%；
  - 核心定论：当前三币横截面择优未产生实质性 Alpha 提升；严格执行既定纪律“Lane A 失败不运行 Lane B”；继续锁定 OPT-0026 为唯一 Champion；
  - 下一步转向：Phase 5 真正的新特征 / 新 Alpha 信息源研究；
  - 测试验证：`tests/test_topk_phase4b.py`、`test_no_trade_phase4a.py`、`test_model_family_phase3.py`、`test_holdout_guard.py`、`test_optimization_pipeline.py` 共计 24 项 pytest 100% 通过。

## 已完成与证据

- **第一阶段（4h 连续回归受控实验）**：产物见 `artifacts/research/regression_phase1/`。
- **第二阶段（多预测周期与纯动态 C2 受控实验）**：产物见 `artifacts/research/multi_horizon_phase2/` 与 `artifacts/research/horizon_c2_ablation/`。
- **第三阶段（4h 二分类模型结构受控比较）**：产物见 `artifacts/research/model_family_phase3/`。
- **第四阶段 A（No-Trade / 信号精选受控实验）**：产物见 `artifacts/research/no_trade_phase4a/`。
- **第四阶段 B（横截面 Top-K / 相对强弱分配受控实验）**：产物见 `artifacts/research/topk_phase4b/`（含 `comparison_report.md`, `candidate_summary.csv`, `eliminated_trade_analysis.csv`, `trading_metrics.csv`, `results.json`, `experiment_config.json`）。
- **单测体系**：`tests/test_topk_phase4b.py` 严格覆盖基准复现、候选边界与 Lane A 纪律、淘汰交易损益恒等式、全候选负超额验证及 2026 数据封存。

## 当前限制与长期边界

- 2026 年数据继续严格隔离，未用于训练、特征计算、阈值选择或评估（严格执行 no future leakage；test 分区物理 0 读取）。
- 面对实验事实实事求是接受，坚决不进行事后反向调参。
- 100 USDT 虚拟资金、三币共用账户、固定 50 USDT 底线、普通现货/无杠杆边界保持不变。
- 当前最优基准依然为 OPT-0026（+0.1293%/w），距离 1.5%/week 目标仍有约 11.6 倍数量级差距。

## 下一行动与交接

1. **Phase 4B 实验全部执行完毕，按用户要求立即停止，向用户汇报完整成果、代码修改、测试结果与 Git commit；绝不自动进入 Phase 5。**
2. **严守研究红线**：
   - 2026 数据未用于训练、特征计算或评估（严格执行 no future leakage，test 分区物理 0 读取）；
   - 100 USDT 虚拟本金、50 USDT 固定底线、现货无杠杆与合规档位严格保持；
   - 坚决不在现有 12 特征内进行无意义调参，准备在用户授权后进入 Phase 5 全新特征与信息源工程。


