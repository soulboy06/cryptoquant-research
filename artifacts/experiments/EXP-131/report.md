# EXP-131 R2 W2 base 评估报告

- 变体：`R2`（dynamic_threshold）
- 窗口：`W2`，成本档位：`base`
- 期末净值：`112.2763 USDT`，净收益：`12.2763%`
- 最大回撤：`3.3841%`
- 闭合交易周期：`26` 笔，成交手续费：`1.6049 USDT`
- 本金底线触发：`0` 次，单币硬止损：`0` 次
- 状态分布：顺势决策点 `818/2196`

```json
{
  "strategy": "logistic_regression",
  "period": "development",
  "cost": "base",
  "initial_equity": "100",
  "start_utc": "2024-01-01 00:00:00+00:00",
  "end_utc": "2025-01-01 00:00:00+00:00",
  "final_equity": "112.27627500184980000000",
  "final_cash": "111.41577476384980000000",
  "residual_value": "0.86050023800000000000",
  "net_return": "0.12276275001849800000",
  "max_drawdown": "0.03384054430869517151966184553",
  "longest_drawdown_hours": 2399.0,
  "drawdown_unrecovered": true,
  "fills": 52,
  "rejected_orders": 6443,
  "rejection_reasons": {
    "zero_quantity": 6440,
    "minimum_notional": 3
  },
  "fees_usdt": "1.60487951611515000000",
  "turnover_usdt": "1604.87951611515000000",
  "turnover_multiple": "16.04879516115150000",
  "mean_hourly_open_exposure": "0.01001680624690982186878792755",
  "closed_cycles": 26,
  "floor_triggers": 0,
  "stop_triggers": 0,
  "permanent_buy_lock": false,
  "stale_checkpoints": 0,
  "realized_pnl": "12.18602551371394843988985350",
  "per_symbol": {
    "BTCUSDT": {
      "realized_pnl": "-0.98454316956664775376091897",
      "buy_fills": 12,
      "sell_fills": 12,
      "fees_usdt": "0.72617712236865000000",
      "residual_quantity": "0.00000396",
      "residual_value": "0.3705609600000000",
      "residual_unrealized_pnl": "0.01367927398594775376091894814"
    },
    "ETHUSDT": {
      "realized_pnl": "8.78747392404230561758069928",
      "buy_fills": 10,
      "sell_fills": 10,
      "fees_usdt": "0.6320659154315000000",
      "residual_quantity": "0.0000916",
      "residual_value": "0.305740648000000",
      "residual_unrealized_pnl": "0.02092397286319438241930071309"
    },
    "SOLUSDT": {
      "realized_pnl": "4.38309475923829057607007319",
      "buy_fills": 4,
      "sell_fills": 4,
      "fees_usdt": "0.246636478315000000",
      "residual_quantity": "0.000973",
      "residual_value": "0.18419863000000",
      "residual_unrealized_pnl": "0.05564624128670942392992679527"
    }
  },
  "limitations": [
    "本次只评价development/W2，没有打开保留测试，不是实时或真实收益。",
    "当前公开规则快照近似历史规则；市价名义金额用模拟成交价检查，未重建参考价或分钟VWAP。",
    "小时开盘近似成交；不还原盘口、排队、冲击或小时内路径；费用固定且无BNB优惠。",
    "固定50 USDT底线在真实小时收盘观察，停机恢复首个真实开盘补查；触发不保证退出后仍有50。",
    "停机／no_trade按已核验日历禁止成交，这是离线执行约束，不能从当根最终成交量提前产生在线信号。",
    "模型特征在缺口后重启，744个连续观察之前保持持仓；风险退出独立生效。预测不fit评价数据。",
    "净值与回撤来自交易前起点、小时收盘和成交后检查点；未识别小时内最大回撤。",
    "每年是同一账户的连续分段；没有年度重置。开发结果没有用于搜索EMA或风险参数。"
  ],
  "window": "W2",
  "exit_variant": "C2",
  "breakeven_triggers": 0,
  "duration_triggers": 0,
  "g_week": 0.002217062589197516,
  "total_window_hours": 8784.0,
  "full_weeks_count": 52,
  "losing_full_weeks_count": 21,
  "losing_full_weeks_ratio": 0.40384615384615385,
  "worst_full_week_return": -0.013869040775306707,
  "partial_week_present": true,
  "experiment_id": "EXP-131",
  "variant": "R2",
  "state_experiment_id": "EXP-122",
  "training_experiment_id": "EXP-067",
  "prepared_experiment_id": "EXP-063",
  "label_policy": "net_positive_base_v1",
  "status": "complete",
  "decision_regime_distribution": {
    "favorable": 2454,
    "weak": 4134
  },
  "target_weight_distribution": {
    "0": 6558,
    "0.30": 30
  },
  "favorable_decisions": 818,
  "total_decisions": 2196
}
```