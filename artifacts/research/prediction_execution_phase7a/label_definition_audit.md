# 训练标签彻底审计报告：`net_positive_base_v1`

## 一、代码位置与核心实现

- **定义模块**：`src/cryptoquant/models/labels.py`（函数 `label_values` 与 `label_metadata`）
- **样本构建**：`src/cryptoquant/models/samples.py`（函数 `build_training_samples`）与 `src/cryptoquant/models/research_data.py`
- **常量参数**：
  - `GROSS_POLICY = 'gross_direction_v1'`
  - `NET_POLICY = 'net_positive_base_v1'`
  - `BASE_FEE = Decimal('0.001')`（10 bps 单边手续费）
  - `BASE_ADVERSE = Decimal('0.0005')`（5 bps 单边不利价格偏移/滑点/价差）
  - `LABEL_HORIZON_HOURS = 4`（固定 4 小时前向窗口）

```python
# src/cryptoquant/models/labels.py
def label_values(entry, exit, policy, fee=None, adverse=None):
    card = label_metadata(policy, fee, adverse)
    entry, exit = _finite_decimal(entry, 'entry price'), _finite_decimal(exit, 'exit price')
    ...
    fee, adverse = Decimal(card['label_fee']), Decimal(card['label_adverse_price'])
    numerator = exit * (1 - fee) ** 2 * (1 - adverse)
    denominator = entry * (1 + adverse)
    return dict(
        label_return=gross,
        label_net_return_text=str(numerator / denominator - 1),
        label=int(numerator > denominator)
    )
```

---

## 二、八大审计问题逐项核验

### 1. 标签预测的到底是什么？
**二分类目标：固定 4 小时后，扣除 Base 摩擦成本的净收益是否严格大于 0。**
它预测从当前决策时刻 $t$ 买入，持有到 $t + 4\text{h}$ 准时卖出，扣除买入与卖出双边手续费及价差滑点后，净美元收益是否能覆盖全部摩擦并录得净盈利。若净收益 $> 0$，则 $Y = 1$；否则 $Y = 0$。

### 2. 使用什么价格作为入场价？
使用决策时刻 $t$ 的 **K 线开盘价（Open Price）**：
$$P_{\text{entry}} = \text{Candle}_{t}[\text{'open'}]$$
例如在 04:00:00 UTC 的决策点，入场基准价格严格取 04:00:00 UTC K 线的开盘价。

### 3. 使用什么价格作为未来 4 小时出场价？
使用决策时刻未来第 4 个小时 $t + 4\text{h}$ 的 **K 线开盘价（Open Price）**：
$$P_{\text{exit}} = \text{Candle}_{t + 4\text{h}}[\text{'open'}]$$
例如在 04:00:00 UTC 进场，出场基准价格严格取 08:00:00 UTC K 线的开盘价。

### 4. 是否考虑买卖价差、手续费和滑点？
**完全考虑，严格采用 Base 交易成本模型。**
- **手续费率**：单边 $0.10\%$（10 bps），买卖双边累计因子为 $(1 - 0.001)^2 \approx 1 - 0.002 = 1 - 20\text{ bps}$；
- **不利价格偏移（滑点与买卖价差）**：单边 $0.05\%$（5 bps），买入不利入场价为 $P_{\text{entry}} \times (1 + 0.0005)$，卖出不利出场价为 $P_{\text{exit}} \times (1 - 0.0005)$；
- **全流程双边总摩擦**：约为 $20\text{ bps} + 10\text{ bps} \approx 30.055\text{ bps}$（$0.30055\%$）。

### 5. 正收益的实际判定条件是什么？
严格要求分子严格大于分母：
$$\text{Numerator} = P_{\text{exit}} \times (1 - \text{fee})^2 \times (1 - \text{adverse})$$
$$\text{Denominator} = P_{\text{entry}} \times (1 + \text{adverse})$$
$$\text{Label} = 1 \quad \iff \quad \text{Numerator} > \text{Denominator}$$

等价收益率公式：
$$\frac{P_{\text{exit}}}{P_{\text{entry}}} > \frac{1 + \text{adverse}}{(1 - \text{fee})^2 \times (1 - \text{adverse})} = \frac{1.0005}{(0.999)^2 \times 0.9995} = \frac{1.0005}{0.997501} \approx 1.0030065$$
**即：未来 4 小时价格纯毛涨幅必须严格突破 $+0.30065\%$，标签才会被判定为 1。**

### 6. 训练标签是否与模型决策时间严格一致？
**严格一致，零未来信息泄露。**
- 决策时间在 $t$（如 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC）；
- 计算输入特征所使用的 OHLCV 序列截止至 $t - 1\text{h}$ 的收盘价（即严格已经闭合的全部历史信息）；
- 入场发生在 $t$ 的 Open 报价。

### 7. 标签所需的未来价格是否完全处于训练窗口内部？
**严格处于训练窗口内部。**
在 `src/cryptoquant/models/samples.py` 的构建逻辑中：
```python
if exit_time >= end:
    reason = 'label_crosses_boundary'
```
当决策时刻未来 4 小时的出口 $t + 4\text{h} \ge \text{train\_end}$ 时，该决策点会被作为跨界样本直接剔除，训练集标签绝对不会跨越到评估或测试区间。

### 8. 标签是否包含真实交易系统中的 C2、止损和提前退出？
**完全不包含！这是最核心的机制性差异：**
- **忽略中间路径**：标签只看 $t$ 与 $t+4\text{h}$ 的两点开盘价比值，完全忽略 4 小时窗口内的 High 和 Low，对盘中发生的巨幅震荡完全盲目；
- **不包含硬止损**：若盘中跌穿 $8\%$ 止损线，真实策略在小时收盘时立即平仓并承担大亏，而标签仍只记录 4h 后的 Open；
- **不包含 C2 动态保本**：若盘中价格曾冲高 $+1.20\%$ 激活保本机制，随后跌回 $+0.25\%$ 被动锁定微利出局，真实策略已平仓，而标签若发现 4h Open 随后又大幅回落或反弹，标签数值与实际交易彻底脱节；
- **不包含持仓展期**：若 4 小时后模型预测仍然 $\ge 0.48$，真实策略会选择**继续持仓**（持仓时长可达 8h, 12h, 24h 甚至数天）；标签在此处却假设 4h 已经完全平仓；
- **不包含账户资金竞争与最小交易额**：真实账户 100 USDT 共享，多币共振或资金不足时买单可能被拒，标签则假设每次都能以理想仓位参与。

---

## 三、标签审计结论

`net_positive_base_v1` 是一个**静态、固定 4 小时持有、仅考虑开盘价差和理论摩擦**的二分类标签。它是一个局部无状态的微观快照，与真实交易引擎中具有记忆、动态追踪、多层出场和共享资金约束的生命周期存在先天理论差异。
