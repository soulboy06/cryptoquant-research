# EXP-132 R2 R2025 base 评估报告

- 变体：`R2`（dynamic_threshold）
- 窗口：`R2025`，成本档位：`base`
- 期末净值：`90.9057 USDT`，净收益：`-9.0943%`
- 最大回撤：`11.1402%`
- 闭合交易周期：`67` 笔，成交手续费：`3.7750 USDT`
- 本金底线触发：`0` 次，单币硬止损：`4` 次
- 状态分布：顺势决策点 `725/2189`

```json
{
  "strategy": "logistic_regression",
  "period": "validation",
  "cost": "base",
  "initial_equity": "100",
  "start_utc": "2025-01-01 00:00:00+00:00",
  "end_utc": "2025-12-31 20:00:00+00:00",
  "final_equity": "90.90567685651465000000",
  "final_cash": "90.15041555701465000000",
  "residual_value": "0.75526129950000000000",
  "net_return": "-0.09094323143485350000",
  "max_drawdown": "0.1114022987605675855804864087",
  "longest_drawdown_hours": 7298.0,
  "drawdown_unrecovered": true,
  "fills": 134,
  "rejected_orders": 6255,
  "rejection_reasons": {
    "zero_quantity": 6227,
    "risk_blocked": 8,
    "minimum_notional": 20
  },
  "fees_usdt": "3.77496070620415000000",
  "turnover_usdt": "3774.96070620415000000",
  "turnover_multiple": "37.74960706204150000",
  "mean_hourly_open_exposure": "0.02148202411731247591462068310",
  "closed_cycles": 67,
  "floor_triggers": 0,
  "stop_triggers": 4,
  "permanent_buy_lock": false,
  "stale_checkpoints": 0,
  "realized_pnl": "-9.04118096146719463315122713",
  "per_symbol": {
    "BTCUSDT": {
      "realized_pnl": "-1.62825163603615828084959753",
      "buy_fills": 13,
      "sell_fills": 13,
      "fees_usdt": "0.71712786469765000000",
      "residual_quantity": "0.00000611",
      "residual_value": "0.5348807035000000",
      "residual_unrealized_pnl": "-0.01468038032919171915040249938"
    },
    "ETHUSDT": {
      "realized_pnl": "-0.86556759161913649791829069",
      "buy_fills": 40,
      "sell_fills": 40,
      "fees_usdt": "2.2616317071065000000",
      "residual_quantity": "0.0000496",
      "residual_value": "0.147369536000000",
      "residual_unrealized_pnl": "0.003031622149136497918290739536"
    },
    "SOLUSDT": {
      "realized_pnl": "-6.54736173381189985438333891",
      "buy_fills": 14,
      "sell_fills": 14,
      "fees_usdt": "0.796201134400000000",
      "residual_quantity": "0.000587",
      "residual_value": "0.07301106000000",
      "residual_unrealized_pnl": "-0.04149342383810014561666107395"
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
  "breakeven_triggers": 5,
  "duration_triggers": 0,
  "g_week": -0.0018277496803074111,
  "total_window_hours": 8756.0,
  "full_weeks_count": 52,
  "losing_full_weeks_count": 27,
  "losing_full_weeks_ratio": 0.5192307692307693,
  "worst_full_week_return": -0.04428765123682632,
  "partial_week_present": true,
  "experiment_id": "EXP-132",
  "variant": "R2",
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
    "0": 6470,
    "0.30": 97
  },
  "favorable_decisions": 725,
  "total_decisions": 2189
}
```