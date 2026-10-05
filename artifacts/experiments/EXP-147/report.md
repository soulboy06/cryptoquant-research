# EXP-147 R7 W1 base 评估报告

- 变体：`R7`（alpha_multi_horizon）
- 窗口：`W1`，成本档位：`base`
- 期末净值：`103.3118 USDT`，净收益：`3.3118%`
- 最大回撤：`3.6961%`
- 闭合交易周期：`29` 笔，成交手续费：`1.4003 USDT`
- 本金底线触发：`0` 次，单币硬止损：`1` 次
- 状态分布：顺势决策点 `701/2190`
- Alpha 龙头识别次数：`1542` 次

```json
{
  "strategy": "logistic_regression",
  "period": "development",
  "cost": "base",
  "initial_equity": "100",
  "start_utc": "2023-01-01 00:00:00+00:00",
  "end_utc": "2024-01-01 00:00:00+00:00",
  "final_equity": "103.31180396164010000000",
  "final_cash": "102.80335003224010000000",
  "residual_value": "0.50845392940000000000",
  "net_return": "0.03311803961640100000",
  "max_drawdown": "0.03696050088022936100843922072",
  "longest_drawdown_hours": 4904.0,
  "drawdown_unrecovered": true,
  "fills": 60,
  "rejected_orders": 5085,
  "rejection_reasons": {
    "minimum_notional": 25,
    "risk_blocked": 4,
    "zero_quantity": 5053,
    "no_quote": 3
  },
  "fees_usdt": "1.40025190212220000000",
  "turnover_usdt": "1400.25190212220000000",
  "turnover_multiple": "14.00251902122200000",
  "mean_hourly_open_exposure": "0.007779000210130811872922418011",
  "closed_cycles": 29,
  "floor_triggers": 0,
  "stop_triggers": 1,
  "permanent_buy_lock": false,
  "stale_checkpoints": 4,
  "realized_pnl": "3.22867437758796009412423436",
  "per_symbol": {
    "BTCUSDT": {
      "realized_pnl": "1.13211189669688045878709388",
      "buy_fills": 3,
      "sell_fills": 3,
      "fees_usdt": "0.18260618201470000000",
      "residual_quantity": "0.00000688",
      "residual_value": "0.2909110304000000",
      "residual_unrealized_pnl": "0.05926714717671954121290611458"
    },
    "ETHUSDT": {
      "realized_pnl": "0.41097218196742481372973394",
      "buy_fills": 4,
      "sell_fills": 4,
      "fees_usdt": "0.1625080519625000000",
      "residual_quantity": "0.0000537",
      "residual_value": "0.122536419000000",
      "residual_unrealized_pnl": "0.02693265512407518627026606572"
    },
    "SOLUSDT": {
      "realized_pnl": "1.68559029892365482160740654",
      "buy_fills": 23,
      "sell_fills": 23,
      "fees_usdt": "1.055137668145000000",
      "residual_quantity": "0.000934",
      "residual_value": "0.09500648000000",
      "residual_unrealized_pnl": "-0.003070218248654821607406541936"
    }
  },
  "limitations": [
    "本次只评价development/W1，没有打开保留测试，不是实时或真实收益。",
    "当前公开规则快照近似历史规则；市价名义金额用模拟成交价检查，未重建参考价或分钟VWAP。",
    "小时开盘近似成交；不还原盘口、排队、冲击或小时内路径；费用固定且无BNB优惠。",
    "固定50 USDT底线在真实小时收盘观察，停机恢复首个真实开盘补查；触发不保证退出后仍有50。",
    "停机／no_trade按已核验日历禁止成交，这是离线执行约束，不能从当根最终成交量提前产生在线信号。",
    "模型特征在缺口后重启，744个连续观察之前保持持仓；风险退出独立生效。预测不fit评价数据。",
    "净值与回撤来自交易前起点、小时收盘和成交后检查点；未识别小时内最大回撤。",
    "每年是同一账户的连续分段；没有年度重置。开发结果没有用于搜索EMA或风险参数。"
  ],
  "window": "W1",
  "exit_variant": "C2",
  "breakeven_triggers": 3,
  "duration_triggers": 0,
  "g_week": 0.0006250450305165245,
  "total_window_hours": 8760.0,
  "full_weeks_count": 52,
  "losing_full_weeks_count": 25,
  "losing_full_weeks_ratio": 0.4807692307692308,
  "worst_full_week_return": -0.018020344606754946,
  "partial_week_present": true,
  "experiment_id": "EXP-147",
  "variant": "R7",
  "state_experiment_id": "EXP-122",
  "training_experiment_id": "EXP-065",
  "prepared_experiment_id": "EXP-063",
  "label_policy": "net_positive_base_v1",
  "status": "complete",
  "decision_regime_distribution": {
    "weak": 4467,
    "favorable": 2103
  },
  "target_weight_distribution": {
    "0": 5960,
    "0.30": 29,
    "0.10": 16,
    "None": 558,
    "0.15": 6,
    "0.25": 1
  },
  "alpha_leader_distribution": {
    "false": 5028,
    "true": 1542
  },
  "alpha_accelerating_count": 891,
  "favorable_decisions": 701,
  "total_decisions": 2190
}
```