# 第三轮2025模型验证与基准比较（LightGBM 树模型）

UTC2025-01-01 00:00至2025-12-31 20:00，末端仅开盘清算；每组独立100 USDT。买入持有没有单币止损，主动策略有8%止损，费用和其他资金／底线规则一致。

模型结构：梯度提升决策树（LightGBM），采用12项特征（9项K线量价 + 3项公开资金费率指标）。

| 实验 | 模型／候选／阈值 | 期末净值 | 净收益 | 最大回撤 | 闭合周期 | 费用USDT | 主动门槛 | 门槛未过原因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EXP-023 | buy_hold | 84.3191 | -15.68% | 47.24% | 3 | 0.1624 | 被动对照 | - |
| EXP-024 | ema_trend | 65.2595 | -34.74% | 45.93% | 202 | 10.0461 | 不合格 | net_return_not_positive;max_drawdown_exceeds_25_percent |
| EXP-036 | LGBM C=0.1，阈值=0.55 | 49.6740 | -50.33% | 50.76% | 617 | 25.2845 | 不合格 | net_return_not_positive;max_drawdown_exceeds_25_percent;equity_floor_triggered |
| EXP-037 | LGBM C=0.1，阈值=0.6 | 92.1724 | -7.83% | 9.31% | 98 | 5.4947 | 不合格 | net_return_not_positive |
| EXP-038 | LGBM C=0.1，阈值=0.65 | 100.0000 | 0.00% | 0.00% | 0 | 0.0000 | 不合格 | net_return_not_positive;fewer_than_30_closed_cycles |
| EXP-039 | LGBM C=1，阈值=0.55 | 49.5177 | -50.48% | 50.95% | 636 | 25.9736 | 不合格 | net_return_not_positive;max_drawdown_exceeds_25_percent;equity_floor_triggered |
| EXP-040 | LGBM C=1，阈值=0.6 | 67.5020 | -32.50% | 33.22% | 335 | 16.2603 | 不合格 | net_return_not_positive;max_drawdown_exceeds_25_percent |
| EXP-041 | LGBM C=1，阈值=0.65 | 96.1319 | -3.87% | 3.95% | 14 | 0.7978 | 不合格 | net_return_not_positive;fewer_than_30_closed_cycles |
| EXP-042 | LGBM C=10，阈值=0.55 | 49.8456 | -50.15% | 50.67% | 733 | 30.9459 | 不合格 | net_return_not_positive;max_drawdown_exceeds_25_percent;equity_floor_triggered |
| EXP-043 | LGBM C=10，阈值=0.6 | 64.8162 | -35.18% | 35.71% | 340 | 15.8007 | 不合格 | net_return_not_positive;max_drawdown_exceeds_25_percent |
| EXP-044 | LGBM C=10，阈值=0.65 | 96.1474 | -3.85% | 4.59% | 24 | 1.3714 | 不合格 | net_return_not_positive;fewer_than_30_closed_cycles |

门槛预先固定：base净收益>0、最大回撤≤25%、底线0、闭合周期≥30。只在合格模型中按期末净值高、回撤低、成交额低、C小、阈值高排序；预测准确率不是盈利门槛。

结论：九组LightGBM树模型候选与EMA均未通过验证门槛，坚决不打开2026保留测试，未证明稳定盈利。

与前两轮对比（核心发现）：
- 逻辑回归（EXP-030/033）：在0.65高阈值下净收益为 +1.20% ~ +1.87%，最大回撤仅 2.58% ~ 2.84%，表现为稳健盈利，但闭合周期为 24 笔（差6笔未达30笔硬门槛）；
- LightGBM树模型（EXP-036—044）：训练集拟合度明显更高（准确率达61%），但在2025样本外验证中表现出明显的过拟合现象：阈值0.60出击过于频繁（335~340笔），手续费摩擦磨损严重（亏损-32%~-35%）；阈值0.65出击稀疏（0~24笔）且净收益仍为负（-3.85%）；
- 启示：金融时间序列高噪声环境下，复杂的非线性树模型在开发集上的高拟合往往转化为样本外的高方差与假突破；而强正则化的线性平滑模型在泛化和风控上表现出更强的一致性。

局限：当前规则快照近似历史规则，小时开盘近似执行；固定底线触发不保证退出后恰有50。小时回撤未涵盖小时内路径。验证用于研究和选择，不是未来盈利保证。
