# EXP-137 R4 W2 base 评估报告

- 变体：`R4`（dual_synergy）
- 窗口：`W2`，成本档位：`base`
- 期末净值：`109.3522 USDT`，净收益：`9.3522%`
- 最大回撤：`2.8599%`
- 闭合交易周期：`26` 笔，成交手续费：`1.3153 USDT`
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
  "final_equity": "109.35223967450195000000",
  "final_cash": "108.62686694050195000000",
  "residual_value": "0.72537273400000000000",
  "net_return": "0.09352239674501950000",
  "max_drawdown": "0.02859871968132285489986999448",
  "longest_drawdown_hours": 2219.0,
  "drawdown_unrecovered": true,
  "fills": 52,
  "rejected_orders": 6443,
  "rejection_reasons": {
    "zero_quantity": 6440,
    "minimum_notional": 3
  },
  "fees_usdt": "1.31533778257410000000",
  "turnover_usdt": "1315.33778257410000000",
  "turnover_multiple": "13.15337782574100000",
  "mean_hourly_open_exposure": "0.01006152724886214612774850296",
  "closed_cycles": 26,
  "floor_triggers": 0,
  "stop_triggers": 0,
  "permanent_buy_lock": false,
  "stale_checkpoints": 0,
  "realized_pnl": "9.27398236584005341604156262",
  "per_symbol": {
    "BTCUSDT": {
      "realized_pnl": "-1.10647460506647652526517626",
      "buy_fills": 12,
      "sell_fills": 12,
      "fees_usdt": "0.60123538276510000000",
      "residual_quantity": "0.00000497",
      "residual_value": "0.4650727200000000",
      "residual_unrealized_pnl": "0.01740905451042652526517626084"
    },
    "ETHUSDT": {
      "realized_pnl": "5.99736221166823936523666569",
      "buy_fills": 10,
      "sell_fills": 10,
      "fees_usdt": "0.4674659214940000000",
      "residual_quantity": "0.0000228",
      "residual_value": "0.076101384000000",
      "residual_unrealized_pnl": "0.005202012864760634763334322336"
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
  "g_week": 0.0017113761191311916,
  "total_window_hours": 8784.0,
  "full_weeks_count": 52,
  "losing_full_weeks_count": 22,
  "losing_full_weeks_ratio": 0.4230769230769231,
  "worst_full_week_return": -0.007155258370738493,
  "partial_week_present": true,
  "experiment_id": "EXP-137",
  "variant": "R4",
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
    "0.30": 20,
    "0.15": 10
  },
  "favorable_decisions": 818,
  "total_decisions": 2196
}
```