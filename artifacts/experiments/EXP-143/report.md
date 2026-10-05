# EXP-143 R5 R2025 base 评估报告

- 变体：`R5`（alpha_decoupled_20）
- 窗口：`R2025`，成本档位：`base`
- 期末净值：`98.0817 USDT`，净收益：`-1.9183%`
- 最大回撤：`11.1009%`
- 闭合交易周期：`57` 笔，成交手续费：`3.2677 USDT`
- 本金底线触发：`0` 次，单币硬止损：`3` 次
- 状态分布：顺势决策点 `725/2189`
- Alpha 龙头识别次数：`1700` 次

```json
{
  "strategy": "logistic_regression",
  "period": "validation",
  "cost": "base",
  "initial_equity": "100",
  "start_utc": "2025-01-01 00:00:00+00:00",
  "end_utc": "2025-12-31 20:00:00+00:00",
  "final_equity": "98.08167547070130000000",
  "final_cash": "97.31081732970130000000",
  "residual_value": "0.77085814100000000000",
  "net_return": "-0.01918324529298700000",
  "max_drawdown": "0.1110094418386225788169535999",
  "longest_drawdown_hours": 8291.0,
  "drawdown_unrecovered": true,
  "fills": 120,
  "rejected_orders": 6268,
  "rejection_reasons": {
    "zero_quantity": 6127,
    "minimum_notional": 134,
    "risk_blocked": 7
  },
  "fees_usdt": "3.26766076592485000000",
  "turnover_usdt": "3267.66076592485000000",
  "turnover_multiple": "32.67660765924850000",
  "mean_hourly_open_exposure": "0.02139147436168706025096438713",
  "closed_cycles": 57,
  "floor_triggers": 0,
  "stop_triggers": 3,
  "permanent_buy_lock": false,
  "stale_checkpoints": 0,
  "realized_pnl": "-1.872144825917937959540747409",
  "per_symbol": {
    "BTCUSDT": {
      "realized_pnl": "0.308621644967146565409147373",
      "buy_fills": 10,
      "sell_fills": 11,
      "fees_usdt": "0.56805280805785000000",
      "residual_quantity": "0.00000698",
      "residual_value": "0.6110421130000000",
      "residual_unrealized_pnl": "-0.01593093136284656540914742487"
    },
    "ETHUSDT": {
      "realized_pnl": "-0.231703261917054551321427070",
      "buy_fills": 33,
      "sell_fills": 33,
      "fees_usdt": "1.8262944335620000000",
      "residual_quantity": "0.0000383",
      "residual_value": "0.113795428000000",
      "residual_unrealized_pnl": "-0.004201977070945448678572884025"
    },
    "SOLUSDT": {
      "realized_pnl": "-1.949063208968029973628467712",
      "buy_fills": 16,
      "sell_fills": 17,
      "fees_usdt": "0.873313524305000000",
      "residual_quantity": "0.000370",
      "residual_value": "0.04602060000000",
      "residual_unrealized_pnl": "-0.02604679494697002637153228567"
    }
  },
  "limitations": [
    "本次只评价validation/R2025，没有打开保留测试，不是实时或真实收益。",
    "当前公开规则快照近似历史规则；市价名义金额用模拟成交价检查，未重建参考价或分钟VWAP。",
    "小时开盘近似成交；不还原盘口、排队、冲击或小时内路径；费用固定且无BNB优惠。",
    "固定50 USDT底线在真实小时收盘观察，停机恢复首个真实开盘补查；触发不保证退出后仍有50。",
    "停机／no_trade按已核验日历禁止成交，这是离线执行约束，不能从当根最终成交量提前产生在线信号。",
    "模型特征在缺口后重启，744个连续观察之前保持持仓；风险退出独立生效。预测不fit评价数据。",
    "净值与回撤来自交易前起点、小时收盘和成交后检查点；未识别小时内最大回撤。",
    "每年是同一账户的连续分段；没有年度重置。开发结果没有用于搜索EMA或风险参数。"
  ],
  "window": "R2025",
  "exit_variant": "C2",
  "breakeven_triggers": 6,
  "duration_triggers": 0,
  "g_week": -0.0003715730293791797,
  "total_window_hours": 8756.0,
  "full_weeks_count": 52,
  "losing_full_weeks_count": 26,
  "losing_full_weeks_ratio": 0.5,
  "worst_full_week_return": -0.03336850866327368,
  "partial_week_present": true,
  "experiment_id": "EXP-143",
  "variant": "R5",
  "state_experiment_id": "EXP-122",
  "training_experiment_id": "EXP-094",
  "prepared_experiment_id": "EXP-063",
  "label_policy": "net_positive_base_v1",
  "status": "complete",
  "decision_regime_distribution": {
    "weak": 4392,
    "favorable": 2175
  },
  "target_weight_distribution": {
    "0": 6377,
    "0.30": 76,
    "0.10": 105,
    "0.20": 9
  },
  "alpha_leader_distribution": {
    "false": 4867,
    "true": 1700
  },
  "alpha_accelerating_count": 1064,
  "favorable_decisions": 725,
  "total_decisions": 2189
}
```