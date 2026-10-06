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
  - 产物目录：`artifacts/research/alpha_phase5b_interactions/`；
  - 终审科学裁决：微观状态存在 4~8 bps 统计差异，但在当前 4h 尺度、LR 线性模型与现货手续费摩擦下，交互特征未能产生稳定可交易 Alpha，四大 Benchmark 维持统治地位。
- **第五阶段 B2（INTERACTION_CONTEXT 收益来源与稳健性深度审计 Phase 5B2）已完成（D-059）**：
  - 产物目录：`artifacts/research/alpha_phase5b2_context_audit/`（含 `audit_summary.json`, `cycle_comparison.csv`, `trade_level_attribution.csv`, `monthly_performance_breakdown.csv`, `cost_stress_test.csv`, `threshold_region_diagnostics.csv`, `block_bootstrap_results.json`, `audit_report.md`）；
  - **核心复现核验**：Control (`OPT-0005_BASE_12`, +0.1371%/w, 208 cycles) 与 Challenger (`OPT-0005_INTERACTION_CONTEXT`, +0.1453%/w, 222 cycles) 严格零误差复现，周收益差额 $\Delta g_{\text{week}} = +0.82\text{ bps/w}$（总净收益差额 $+1.22\text{ USDT}$）；
  - **交易归因与集中度定论**：
    - 组合真实归因证实，超额收益来自新增交易（+1.38 USDT）与出场时机微调（+2.30 USDT），但被入场偏移（-1.21 USDT）与错失交易（-1.81 USDT）大幅对冲；
    - **极端单点行情依赖**：36 个月中，仅 **2023 年 11 月单月** 超额 PnL 就达到 **+3.72 USDT（占总超额收益的 304.8%）**，主要为 SOL 顺势大涨；Top 3 月份超额收益占比高达 **394.9%**；若剔除 2023 年 11 月，其余月份累计跑输基准 -2.50 USDT；单笔交易层面，Top 3 笔单笔交易贡献了 **369.7%** 的超额收益；
  - **成本压力测试**：在 1.5x (45 bps) 和 2.0x (60 bps) 双边成本下，年化收益严重衰退（2.0x 下年化降至 +2.94%，2025 年亏损翻倍至 -9.19%，回撤升至 15.76%，手续费多消耗 +1.10 USDT）；
  - **AUC 与收益脱节根因**：低概率不交易区增加了噪声扰动拉低了全局 AUC，高置信度切点（$p \ge 0.48$）胜率并没有提升，仅是新增的 14 笔交易偶然踩中了 2023 年底的顺势肥尾大单（极值运气溢价）；
  - **统计显著性定论**：Block Bootstrap 95% 置信区间跨 0（$[-3.27, +5.58]\text{ bps}$），单侧 $p$-value 达 0.377~0.415，经 Bonferroni 多重检验校正后彻底不显著；
  - **处置决议**：**严禁自动晋升 Benchmark**，保留为 `Statistical Challenger` 归档。
  - 单测体系：`tests/test_phase5b2_context_audit.py` 6 passed，总计 24 项测试 100% PASS。

- **第六阶段 A（市场状态与策略亏损归因研究 Phase 6A）已圆满完成（D-060）**：
  - 产物目录：`artifacts/research/market_regime_phase6a/`（含 `regime_definitions.json`, `benchmark_replication.json`, `regime_performance_by_dimension.csv`, `regime_performance_by_symbol_year.csv`, `loss_attribution_2025.csv`, `loss_mechanism_breakdown.csv`, `regime_cross_year_stability.csv`, `phase6a_diagnostic_report.md`）；
  - **严格复现核验**：OPT-0005 严格零误差复现 $g_{\text{week}} = +0.1371\%/\text{w}$（年化 $+7.38\%$），最差回撤 $11.60\%$，208 闭合周期（2023 年 $+8.83\%$ 38笔，2024 年 $+18.50\%$ 88笔，2025 年 $-3.91\%$ 82笔）；
  - **4 维度市场状态因果性拟合**：趋势状态（UPTREND/SIDEWAYS/DOWNTREND）、波动率水平（LOW/MED/HIGH_VOL）、波动率动态（VOL_EXPANDING/VOL_CONTRACTING）、价格结构（BREAKOUT/PULLBACK/NORMAL）。所有分位数门槛严格在对应 Fold 训练集内拟合（严格零未来泄露）；
  - **微观收益结构重大发现（打破直觉偏见）**：
    - OPT-0005 本质上是“震荡低吸与主趋势回调”策略，而非顺强趋势突破策略：全周期净利润中，`SIDEWAYS` 贡献 $+14.50\text{ USDT}$（占比 $87.2\%$），`PULLBACK` 贡献 $+11.63\text{ USDT}$（占比 $70.0\%$），`DOWNTREND`（超跌反弹）贡献 $+5.64\text{ USDT}$（$33.9\%$）；
    - 相反，强顺势追涨（`UPTREND`）累计净亏损 $-3.51\text{ USDT}$（胜率仅 $42.4\%$），追突破（`BREAKOUT`）累计净亏损 $-1.16\text{ USDT}$（胜率 $33.3\%$），追涨极易买在波段顶部；
  - **2025 年亏损核心归因**：
    - 2025 年 82 笔交易中，胜率 $48.8\%$（40 胜 42 负），净实现损益 $-7.15\text{ USDT}$（期末收益率 $-3.91\%$），手续费达 $4.71\text{ USDT}$；
    - **频繁震荡止损（`CHOP_WHIPSAW_STOP`）** 贡献毛亏损的 **$54.9\%$**（-14.16 USDT，31 笔交易）；在横盘区虽产生 62 笔交易，但价格短促无持续性，在 4~8 小时内频繁被动平仓/保本退出并付出高额摩擦；
    - **高波剧烈下杀（`HIGH_VOL_DEEP_LOSS`）** 贡献毛亏损的 **$30.1\%$**（-7.77 USDT，6 笔交易）；
    - **假突破追高（`FALSE_BREAKOUT_TRAP`）** 贡献毛亏损的 **$11.4\%$**（-2.93 USDT，1 笔单笔大亏）；
    - 前两项合计解释了 2025 年 **$85.1\%$** 的毛亏损；
  - **跨年稳定性与币种异质性**：
    - `VOL_CONTRACTING`（波动率收缩）是**全周期唯一跨三年全部保持正收益的状态**（2023: $+0.91$, 2024: $+2.02$, 2025: $+3.20\text{ USDT}$，累计 $+6.14\text{ USDT}$，胜率 $56.7\%$）；
    - `VOL_EXPANDING`（波动率扩张）在 2025 年发生系统性失效，单年亏损高达 **$-10.35\text{ USDT}$**；
    - 币种层面：2025 年亏损重灾区为 **ETHUSDT**（42 笔交易净亏损 $-3.44\text{ USDT}$，手续费支出 $2.42\text{ USDT}$）和 **SOLUSDT**（30 笔交易净亏损 $-3.07\text{ USDT}$，手续费 $1.73\text{ USDT}$）；BTC 相对可控（$-0.64\text{ USDT}$）；
- **第六阶段 B（市场状态过滤器与风控优化实验 Phase 6B）已圆满完成（D-061）**：
  - 产物目录：`artifacts/research/market_regime_phase6b/`（含 `accounting_audit.md`, `accounting_reconciliation.csv`, `experiment_config.json`, `filter_definitions.json`, `trading_metrics.csv`, `monthly_comparison.csv`, `symbol_comparison.csv`, `filter_decision_audit.csv`, `exposure_comparison.csv`, `cost_stress_test.csv`, `bootstrap_results.json`, `pareto_comparison.csv`, `results.json`, `comparison_report.md` 共 14 项完整交付物）；
  - **第一阶段财务审计彻底核准**：官方回测账本数学计算 100% 严谨无误，逐年对账误差为严格 0.0000；2025 年真实净亏损严格为 **-3.91%**（-3.9148 USDT），Phase 6A 中的 -7.15 USDT 纯属离线辅助函数将 step-size 精度零头视作 100% 灭失的统计偏差；
  - **三大过滤器实验实证定论**：
    - Control (`OPT-0005`): $g_{\text{week}} = +0.1371\%$/w, Ann +7.38%, 2023: +8.83%, 2024: +18.50%, 2025: -3.91%, MDD 11.60%, 208 周期;
    - Filter A (`NoUptrend`): $g_{\text{week}} = +0.0999\%$/w, Ann +5.33%, 2023: +8.84%, 2024: +16.30%, 2025: -7.63%, MDD 18.84%, 163 周期（2025 亏损扩大，回撤恶化至 18.84%，严重跑输）;
    - Filter B (`DownsizeVolExp`): $g_{\text{week}} = +0.0572\%$/w, Ann +3.02%, 2023: +3.56%, 2024: +15.97%, 2025: -8.95%, MDD 10.52%, 299 周期（本质为降仓防守，平均持仓敞口压缩至 1.63%，单位敞口收益下降，2025 亏损放大）;
    - Filter C (`NoVolExp`): $g_{\text{week}} = +0.0467\%$/w, Ann +2.46%, 2023: +0.88%, 2024: +1.62%, 2025: +4.95%, MDD 2.48%, 37 周期（灾难性踏空，扼杀 82.2% 交易机会，2024 利润归零）;
  - **统计检验与成本压力**：Block Bootstrap 检验中 Filter B 与 Filter C 显著跑输基准；在 2.0x 交易成本下 Control 保持 +2.41% 年化正收益，所有候选均被 Control 击败；
  - **终审裁决**：**三个过滤器全部未能满足 Challenger 准入标准，本轮正式宣告失败并予以全面剪枝。基准严格维持原 `OPT-0005_BASE_12`**；
  - 单测体系：`tests/test_market_regime_phase6b.py` 11 项专用单测及相关回归测试 24 passed 100% PASS。

- **第七阶段 A（预测目标与真实交易结果一致性审计 Phase 7A）已圆满完成（D-062）**：
  - 产物目录：`artifacts/research/prediction_execution_phase7a/`（含 `label_definition_audit.md`, `benchmark_replication.json`, `prediction_decision_alignment.csv`, `executed_trade_alignment.csv`, `prediction_execution_mismatch.csv`, `holding_period_analysis.csv`, `probability_pnl_analysis.csv`, `symbol_year_comparison.csv`, `statistical_uncertainty.json`, `results.json`, `comparison_report.md` 共 11 项完整交付物）；
  - **基准精确零误差复现**：OPT-0005 严格复现 208 周期，$g_{\text{week}} = +0.1371\%$/w，年化复利 $+7.38\%$，Worst MDD $11.60\%$（2023: +8.83%, 2024: +18.50%, 2025: -3.91%）；
  - **标签与交易一致率极高（91.8% 一致率）**：208 笔交易中 191 笔的盈亏方向与未来 4h 成本后标签完全一致（4h 为正时交易胜率 92.2%，4h 为负时交易亏损率 91.3%）；
  - **假说 B 彻底证伪**：“4h 预测正确却被提前止损导致大额亏损”仅发生 9 次（占 4.3%），累计亏损仅 -3.16 USDT，彻底排除了假说 B；
  - **持仓时长错配重大实证发现**：
    - 严格 4h 出场交易（153 笔，73.6%）：狂赚 **+32.73 USDT**，胜率 **63.4%**，是全策略核心盈利来源；
    - 展期持仓 >4h 交易（48 笔，23.1%）：巨亏 **-14.01 USDT**，胜率崩塌至 **33.3%**；2025 年严格 4h 依然盈利 +4.68 USDT，亏损完全来自 14 笔 >4h 交易（-10.73 USDT）；
  - **概率反向失真重大实证发现**：中等置信度 $0.50 \sim 0.55$ 贡献最大盈利（+16.28 USDT），而极端高置信度 $\ge 0.55$ 累计亏损 **-7.54 USDT**（胜率仅 50.0%），表现为极端超买赶顶追高陷阱；
  - **终审裁定**：**正式采纳结论【C】：“模型本身缺乏足够预测能力（真实交易表现不佳主要不是标签与执行错配造成）”**；
  - 单测体系：`tests/test_prediction_execution_phase7a.py` 7 项专用测试及回归测试 26 passed 100% PASS。

## 当前限制与长期边界

- 2026 年数据继续严格隔离，未用于训练、特征计算、阈值选择或评估（严格执行 no future leakage；test 分区物理 0 读取）。
- 面对实验事实实事求是接受，坚决不进行事后反向调参，不擅自混编新规则。
- 100 USDT 虚拟资金、三币共用账户、固定 50 USDT 底线、普通现货/无杠杆边界保持不变。
- 四大 Pareto Benchmark 体系中，当前最佳周收益仍以具有稳健预测支撑的 OPT-0005 (+0.1371%/w，年化 +7.38%) 为主。

## 下一行动与交接

1. **Phase 7A 预测目标与真实交易结果一致性审计圆满闭环**：全套 11 项产物生成，D-062 裁决生效（采纳结论 C），严格维持原 OPT-0005 Benchmark。
2. **严守停止纪律**：本阶段宣告闭环，坚决不擅自进入 Phase 7B 或自动修改模型与策略，立即停止，等待用户指示下一步研究方向。


