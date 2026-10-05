# EXP-138 R4 R2025 base 评估报告

- 变体：`R4`（dual_synergy）
- 窗口：`R2025`，成本档位：`base`
- 期末净值：`92.1983 USDT`，净收益：`-7.8017%`
- 最大回撤：`10.1535%`
- 闭合交易周期：`67` 笔，成交手续费：`3.3204 USDT`
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
  "final_equity": "92.19834182323295000000",
  "final_cash": "91.49214033123295000000",
  "residual_value": "0.70620149200000000000",
  "net_return": "-0.07801658176767050000",
  "max_drawdown": "0.1015352758406318191140438079",
  "longest_drawdown_hours": 8317.0,
  "drawdown_unrecovered": true,
  "fills": 134,
  "rejected_orders": 6255,
  "rejection_reasons": {
    "zero_quantity": 6227,
    "risk_blocked": 8,
    "minimum_notional": 20
  },
  "fees_usdt": "3.32040620754015000000",
  "turnover_usdt": "3320.40620754015000000",
  "turnover_multiple": "33.20406207540150000",
  "mean_hourly_open_exposure": "0.02093162718737038081328580018",
  "closed_cycles": 67,
  "floor_triggers": 0,
  "stop_triggers": 4,
  "permanent_buy_lock": false,
  "stale_checkpoints": 0,
  "realized_pnl": "-7.74332145759115501826971761",
  "per_symbol": {
    "BTCUSDT": {
      "realized_pnl": "-1.09333051367713742912542700",
      "buy_fills": 13,
      "sell_fills": 13,
      "fees_usdt": "0.62519330308615000000",
      "residual_quantity": "0.00000664",
      "residual_value": "0.5812778840000000",
      "residual_unrealized_pnl": "-0.01586765457341257087457302107"
    },
    "ETHUSDT": {
      "realized_pnl": "-0.16822945809011658348290459",
      "buy_fills": 40,
      "sell_fills": 40,
      "fees_usdt": "1.9068408962240000000",
      "residual_quantity": "0.0000163",
      "residual_value": "0.048429908000000",
      "residual_unrealized_pnl": "0.001000981413616583482904547230"
    },
    "SOLUSDT": {
      "realized_pnl": "-6.48176148582390100566138602",
      "buy_fills": 14,
      "sell_fills": 14,
      "fees_usdt": "0.788372008230000000",
      "residual_quantity": "0.000615",
      "residual_value": "0.07649370000000",
      "residual_unrealized_pnl": "-0.04347004601609899433861397827"
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
  "g_week": -0.0015572958330157816,
  "total_window_hours": 8756.0,
  "full_weeks_count": 52,
  "losing_full_weeks_count": 27,
  "losing_full_weeks_ratio": 0.5192307692307693,
  "worst_full_week_return": -0.04438907632520184,
  "partial_week_present": true,
  "experiment_id": "EXP-138",
  "variant": "R4",
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
    "0.30": 76,
    "0.15": 21
  },
  "favorable_decisions": 725,
  "total_decisions": 2189
}
```