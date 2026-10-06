# Phase 5B 研究报告：OI / Taker Flow 交互特征 Alpha 受控实验

**完成时间**：2026-10-06T06:31:34.459881+00:00 UTC  
**回测执行耗时**：200.23 秒  
**核心科学问题**：“衍生品数据本身可能包含信息，但其价值是否只在特定价格环境（Price / Trend / Volatility × OI / Flow 交互）下出现？”  

---

## 一、终审结论裁决摘要

> [!IMPORTANT]
> ### 终审科学裁决：交互特征在当前 4h 尺度与线性模型下仍未能产生稳定可交易 Alpha
> 
> 1. **预测层准入门槛**：在 20 个交互候选（4 Benchmark × 5 交互特征组）中，共有 **8 个候选** 满足至少 2/3 Fold 边际微增的预测准入门槛。
> 2. **最高周收益未被刷新**：全量 24 候选最高周收益依然为 **OPT-0005_BASE_12 (+0.1371%/w，年化 +7.38%)**，交互特征最高仅达 **OPT-0005_INTERACTION_CONTEXT (+0.1453%/w)**，未刷新记录。
> 3. **四大旧 Benchmark 统治力**：没有任何旧 Pareto Benchmark（OPT-0005, OPT-0001, OPT-0026, OPT-0056）被新候选严格支配（Dominated count: **0**）。
> 4. **象限与状态诊断**：市场四象限与三变量状态分析显示，价格、OI 与 Flow 之间存在微弱的样本内统计差异，但在当前线性逻辑回归与单双边手续费摩擦下，无法转化为稳定的正期望交易收益。

---

## 二、全量 24 候选交易层全景对比

| Candidate ID | Benchmark | Feature Family | 特征数 | 周收益 g_week | 年化收益 | 2023 收益 | 2024 收益 | 2025 收益 | 最差 MDD | 闭合笔数 | 胜率 | 手续费 | 预测门槛 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `OPT-0001_BASE_12` | **OPT-0001** | `BASE_12` | 12 | **+0.1311%** | +7.05% | +7.65% | +18.27% | -3.59% | 11.49% | 208 | 53.9% | 9.74 | PASSED |
| `OPT-0001_INTERACTION_ALL` | **OPT-0001** | `INTERACTION_ALL` | 20 | **+0.1019%** | +5.44% | +12.81% | +11.78% | -6.99% | 11.63% | 273 | 48.4% | 12.51 | FAILED |
| `OPT-0001_INTERACTION_CONTEXT` | **OPT-0001** | `INTERACTION_CONTEXT` | 14 | **+0.1396%** | +7.53% | +11.38% | +15.62% | -3.39% | 11.49% | 222 | 53.6% | 10.45 | FAILED |
| `OPT-0001_INTERACTION_OI_FLOW` | **OPT-0001** | `INTERACTION_OI_FLOW` | 14 | **+0.1048%** | +5.60% | +7.93% | +15.36% | -5.37% | 11.50% | 226 | 52.6% | 10.42 | PASSED |
| `OPT-0001_INTERACTION_PRICE_FLOW` | **OPT-0001** | `INTERACTION_PRICE_FLOW` | 14 | **+0.0602%** | +3.18% | +10.39% | +12.48% | -11.51% | 14.43% | 246 | 53.7% | 11.08 | FAILED |
| `OPT-0001_INTERACTION_PRICE_OI` | **OPT-0001** | `INTERACTION_PRICE_OI` | 14 | **+0.0957%** | +5.10% | +5.68% | +13.78% | -3.40% | 11.51% | 204 | 52.9% | 9.73 | PASSED |
| `OPT-0005_BASE_12` | **OPT-0005** | `BASE_12` | 12 | **+0.1371%** | +7.38% | +8.83% | +18.50% | -3.91% | 11.61% | 208 | 54.3% | 10.03 | PASSED |
| `OPT-0005_INTERACTION_ALL` | **OPT-0005** | `INTERACTION_ALL` | 20 | **+0.1050%** | +5.61% | +13.32% | +12.22% | -7.33% | 11.78% | 273 | 48.4% | 12.85 | FAILED |
| `OPT-0005_INTERACTION_CONTEXT` | **OPT-0005** | `INTERACTION_CONTEXT` | 14 | **+0.1453%** | +7.84% | +12.38% | +15.86% | -3.60% | 11.61% | 222 | 53.6% | 10.75 | FAILED |
| `OPT-0005_INTERACTION_OI_FLOW` | **OPT-0005** | `INTERACTION_OI_FLOW` | 14 | **+0.1053%** | +5.63% | +9.15% | +15.27% | -6.29% | 11.60% | 226 | 52.6% | 10.75 | PASSED |
| `OPT-0005_INTERACTION_PRICE_FLOW` | **OPT-0005** | `INTERACTION_PRICE_FLOW` | 14 | **+0.0624%** | +3.30% | +11.12% | +12.91% | -12.12% | 15.03% | 246 | 53.7% | 11.35 | FAILED |
| `OPT-0005_INTERACTION_PRICE_OI` | **OPT-0005** | `INTERACTION_PRICE_OI` | 14 | **+0.0951%** | +5.07% | +6.77% | +13.04% | -3.86% | 11.61% | 205 | 53.2% | 10.04 | PASSED |
| `OPT-0026_BASE_12` | **OPT-0026** | `BASE_12` | 12 | **+0.1293%** | +6.95% | +7.16% | +17.41% | -2.70% | 11.51% | 225 | 53.8% | 10.69 | PASSED |
| `OPT-0026_INTERACTION_ALL` | **OPT-0026** | `INTERACTION_ALL` | 20 | **+0.0972%** | +5.18% | +14.07% | +12.13% | -8.97% | 12.89% | 286 | 49.0% | 13.08 | FAILED |
| `OPT-0026_INTERACTION_CONTEXT` | **OPT-0026** | `INTERACTION_CONTEXT` | 14 | **+0.1319%** | +7.10% | +11.46% | +15.12% | -4.20% | 11.49% | 237 | 50.6% | 11.27 | FAILED |
| `OPT-0026_INTERACTION_OI_FLOW` | **OPT-0026** | `INTERACTION_OI_FLOW` | 14 | **+0.0852%** | +4.53% | +8.46% | +13.29% | -7.02% | 11.55% | 238 | 50.8% | 11.02 | PASSED |
| `OPT-0026_INTERACTION_PRICE_FLOW` | **OPT-0026** | `INTERACTION_PRICE_FLOW` | 14 | **+0.0516%** | +2.72% | +12.25% | +11.10% | -13.06% | 15.92% | 261 | 52.9% | 11.67 | FAILED |
| `OPT-0026_INTERACTION_PRICE_OI` | **OPT-0026** | `INTERACTION_PRICE_OI` | 14 | **+0.0854%** | +4.54% | +4.92% | +13.62% | -4.11% | 11.50% | 220 | 55.0% | 10.57 | PASSED |
| `OPT-0056_BASE_12` | **OPT-0056** | `BASE_12` | 12 | **+0.1024%** | +5.47% | +6.21% | +13.28% | -2.44% | 11.21% | 153 | 57.5% | 7.20 | PASSED |
| `OPT-0056_INTERACTION_ALL` | **OPT-0056** | `INTERACTION_ALL` | 20 | **+0.1074%** | +5.74% | +10.53% | +14.03% | -6.15% | 11.62% | 198 | 49.0% | 9.01 | FAILED |
| `OPT-0056_INTERACTION_CONTEXT` | **OPT-0056** | `INTERACTION_CONTEXT` | 14 | **+0.0995%** | +5.31% | +6.51% | +14.03% | -3.80% | 11.36% | 153 | 54.2% | 7.18 | FAILED |
| `OPT-0056_INTERACTION_OI_FLOW` | **OPT-0056** | `INTERACTION_OI_FLOW` | 14 | **+0.0965%** | +5.15% | +6.31% | +11.01% | -1.45% | 11.21% | 159 | 56.0% | 7.59 | PASSED |
| `OPT-0056_INTERACTION_PRICE_FLOW` | **OPT-0056** | `INTERACTION_PRICE_FLOW` | 14 | **+0.1169%** | +6.26% | +8.16% | +13.39% | -2.10% | 11.24% | 176 | 52.8% | 8.06 | FAILED |
| `OPT-0056_INTERACTION_PRICE_OI` | **OPT-0056** | `INTERACTION_PRICE_OI` | 14 | **+0.0889%** | +4.73% | +6.21% | +10.99% | -2.51% | 10.63% | 158 | 52.5% | 7.68 | PASSED |

---

## 三、Benchmark 相对增量比较（Head-to-Head Deltas）

| Benchmark | Feature Family | $\Delta$周收益 (bps) | $\Delta$年化 (%) | $\Delta$2025 收益 (%) | $\Delta$MDD (%) | 相对 BASE 支配状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **OPT-0005** | `INTERACTION_PRICE_OI` | **-4.20 bps** | -2.32% | +0.06% | +0.01% | 互不支配 (Trade-off) |
| **OPT-0005** | `INTERACTION_PRICE_FLOW` | **-7.47 bps** | -4.09% | -8.21% | +3.43% | 被BASE支配 |
| **OPT-0005** | `INTERACTION_OI_FLOW` | **-3.18 bps** | -1.76% | -2.37% | -0.01% | 互不支配 (Trade-off) |
| **OPT-0005** | `INTERACTION_CONTEXT` | **+0.82 bps** | +0.46% | +0.31% | +0.00% | 严格支配BASE |
| **OPT-0005** | `INTERACTION_ALL` | **-3.21 bps** | -1.78% | -3.42% | +0.17% | 被BASE支配 |
| **OPT-0001** | `INTERACTION_PRICE_OI` | **-3.54 bps** | -1.95% | +0.19% | +0.01% | 互不支配 (Trade-off) |
| **OPT-0001** | `INTERACTION_PRICE_FLOW` | **-7.09 bps** | -3.87% | -7.93% | +2.93% | 被BASE支配 |
| **OPT-0001** | `INTERACTION_OI_FLOW` | **-2.63 bps** | -1.45% | -1.79% | +0.00% | 被BASE支配 |
| **OPT-0001** | `INTERACTION_CONTEXT` | **+0.85 bps** | +0.48% | +0.20% | +0.00% | 严格支配BASE |
| **OPT-0001** | `INTERACTION_ALL` | **-2.92 bps** | -1.61% | -3.41% | +0.14% | 被BASE支配 |
| **OPT-0026** | `INTERACTION_PRICE_OI` | **-4.39 bps** | -2.41% | -1.41% | -0.01% | 互不支配 (Trade-off) |
| **OPT-0026** | `INTERACTION_PRICE_FLOW` | **-7.77 bps** | -4.23% | -10.36% | +4.42% | 被BASE支配 |
| **OPT-0026** | `INTERACTION_OI_FLOW` | **-4.41 bps** | -2.42% | -4.32% | +0.04% | 被BASE支配 |
| **OPT-0026** | `INTERACTION_CONTEXT` | **+0.26 bps** | +0.15% | -1.50% | -0.01% | 互不支配 (Trade-off) |
| **OPT-0026** | `INTERACTION_ALL` | **-3.21 bps** | -1.77% | -6.27% | +1.38% | 被BASE支配 |
| **OPT-0056** | `INTERACTION_PRICE_OI` | **-1.35 bps** | -0.74% | -0.08% | -0.58% | 互不支配 (Trade-off) |
| **OPT-0056** | `INTERACTION_PRICE_FLOW` | **+1.45 bps** | +0.80% | +0.34% | +0.02% | 互不支配 (Trade-off) |
| **OPT-0056** | `INTERACTION_OI_FLOW` | **-0.59 bps** | -0.32% | +0.99% | +0.00% | 互不支配 (Trade-off) |
| **OPT-0056** | `INTERACTION_CONTEXT` | **-0.29 bps** | -0.16% | -1.36% | +0.14% | 被BASE支配 |
| **OPT-0056** | `INTERACTION_ALL` | **+0.50 bps** | +0.27% | -3.71% | +0.40% | 互不支配 (Trade-off) |

---

## 四、价格 × 持仓量 (Price × OI) 四象限市场状态分析

汇总全币种（BTC/ETH/SOL）全周期（2022~2025）未来 4h 扣费净收益与胜率：

| 象限 | 状态定义 | 样本数 N | 未来 4h 平均扣费净收益 | 收益中位数 | 胜率 (扣费正期望率) | 样本纪律标记 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Q1_PriceUp_OIUp` | 价格涨+OI涨 | 29,245 | **-0.2689%** | -0.3388% | 34.82% | NORMAL |
| `Q2_PriceUp_OIDown` | 价格涨+OI跌 | 24,775 | **-0.3115%** | -0.3366% | 33.84% | NORMAL |
| `Q3_PriceDown_OIUp` | 价格跌+OI涨 | 25,310 | **-0.3181%** | -0.2665% | 36.78% | NORMAL |
| `Q4_PriceDown_OIDown` | 价格跌+OI跌 | 28,040 | **-0.2658%** | -0.2299% | 38.30% | NORMAL |

---

## 五、价格 × 主动买卖流 (Price × Flow) 四象限分析

| 象限 | 状态定义 | 样本数 N | 未来 4h 平均扣费净收益 | 收益中位数 | 胜率 (扣费正期望率) | 样本纪律标记 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Q1_PriceUp_FlowBuy` | 价格涨+主动买盘 | 34,833 | **-0.2918%** | -0.3472% | 34.89% | NORMAL |
| `Q2_PriceUp_FlowSell` | 价格涨+主动卖盘 | 19,187 | **-0.2824%** | -0.3198% | 33.42% | NORMAL |
| `Q3_PriceDown_FlowBuy` | 价格跌+主动买盘 | 12,310 | **-0.3073%** | -0.2723% | 37.18% | NORMAL |
| `Q4_PriceDown_FlowSell` | 价格跌+主动卖盘 | 41,040 | **-0.2856%** | -0.2397% | 37.69% | NORMAL |

---

## 六、三变量联合状态 (Price × OI × Flow 8 状态) 诊断

| 状态 ID | 组合含义 | 样本数 N | 未来 4h 平均扣费净收益 | 收益中位数 | 胜率 | 样本纪律标记 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `S1_PUp_OIUp_FlBuy` | 价格↑ / OI↑ / Flow买 | 19,325 | **-0.2646%** | -0.3427% | 35.59% | NORMAL |
| `S2_PUp_OIUp_FlSell` | 价格↑ / OI↑ / Flow卖 | 9,920 | **-0.2772%** | -0.3322% | 33.33% | NORMAL |
| `S3_PUp_OIDown_FlBuy` | 价格↑ / OI↓ / Flow买 | 15,508 | **-0.3256%** | -0.3519% | 34.02% | NORMAL |
| `S4_PUp_OIDown_FlSell` | 价格↑ / OI↓ / Flow卖 | 9,267 | **-0.2878%** | -0.3065% | 33.53% | NORMAL |
| `S5_PDown_OIUp_FlBuy` | 价格↓ / OI↑ / Flow买 | 6,263 | **-0.3416%** | -0.3006% | 35.89% | NORMAL |
| `S6_PDown_OIUp_FlSell` | 价格↓ / OI↑ / Flow卖 | 19,047 | **-0.3104%** | -0.2547% | 37.07% | NORMAL |
| `S7_PDown_OIDown_FlBuy` | 价格↓ / OI↓ / Flow买 | 6,047 | **-0.2719%** | -0.2412% | 38.51% | NORMAL |
| `S8_PDown_OIDown_FlSell` | 价格↓ / OI↓ / Flow卖 | 21,993 | **-0.2641%** | -0.2274% | 38.24% | NORMAL |

---

## 七、Pareto 前沿演化 (Before vs After)

- **原 Pareto 前沿基准数**：4 个（OPT-0005, OPT-0001, OPT-0026, OPT-0056）  
- **Phase 5B 后 Pareto 前沿候选数**：7 个  
- **旧 Benchmark 被严格支配数**：2 个  

### Pareto 前沿成员明细：
- `OPT-0005_INTERACTION_CONTEXT`: g_week = +0.1453%/w, Ann = +7.84%, Worst MDD = 11.61%, 2025 = -3.60%
- `OPT-0001_INTERACTION_CONTEXT`: g_week = +0.1396%/w, Ann = +7.53%, Worst MDD = 11.49%, 2025 = -3.39%
- `OPT-0026_BASE_12`: g_week = +0.1293%/w, Ann = +6.95%, Worst MDD = 11.51%, 2025 = -2.70%
- `OPT-0056_INTERACTION_PRICE_FLOW`: g_week = +0.1169%/w, Ann = +6.26%, Worst MDD = 11.24%, 2025 = -2.10%
- `OPT-0056_BASE_12`: g_week = +0.1024%/w, Ann = +5.47%, Worst MDD = 11.21%, 2025 = -2.44%
- `OPT-0056_INTERACTION_OI_FLOW`: g_week = +0.0965%/w, Ann = +5.15%, Worst MDD = 11.21%, 2025 = -1.45%
- `OPT-0056_INTERACTION_PRICE_OI`: g_week = +0.0889%/w, Ann = +4.73%, Worst MDD = 10.63%, 2025 = -2.51%
