# EXP-124 R1历史账户

来源与接口：已核对冻结配置、状态、模型、R0输入SHA及有限预算；执行接口小型合成等价证据不代表全年账户重跑。

历史相对改善与代价：按冻结门槛评价收益、回撤、交易周期、手续费与阻断买单；减少交易不单独判为成功，止损记录全部保留。

收益目标：长期几何平均周净收益1.5%单列；三窗独立100 USDT账户的几何合成不是三年连续账户。

2023、2024、2025全部为已查看研究／选择数据，没有新独立样本外或实时模拟证明。2026继续封存；未接真实账户、借款、合约或付费部署。

原第六轮strict W2 EXP-119 +14.9816541437466%未达15%，原失败保留。

详细精确结果与失格项：

```json
{
  "strategy": "logistic_regression",
  "period": "development",
  "cost": "base",
  "initial_equity": "100",
  "start_utc": "2024-01-01 00:00:00+00:00",
  "end_utc": "2025-01-01 00:00:00+00:00",
  "final_equity": "107.34675517257550000000",
  "final_cash": "106.43288571657550000000",
  "residual_value": "0.91386945600000000000",
  "net_return": "0.07346755172575500000",
  "max_drawdown": "0.02894345977777872460701675111",
  "longest_drawdown_hours": 4066.0,
  "drawdown_unrecovered": true,
  "fills": 34,
  "rejected_orders": 6461,
  "rejection_reasons": {
    "zero_quantity": 6387,
    "minimum_notional": 4,
    "regime_blocked": 70
  },
  "fees_usdt": "1.04195324334025000000",
  "turnover_usdt": "1041.95324334025000000",
  "turnover_multiple": "10.41953243340250000",
  "mean_hourly_open_exposure": "0.01027254413534452979829813427",
  "closed_cycles": 17,
  "floor_triggers": 0,
  "stop_triggers": 0,
  "permanent_buy_lock": false,
  "stale_checkpoints": 0,
  "realized_pnl": "7.26133534486439639920613049",
  "per_symbol": {
    "BTCUSDT": {
      "realized_pnl": "-1.25331953841329901217851693",
      "buy_fills": 8,
      "sell_fills": 8,
      "fees_usdt": "0.48288209204475000000",
      "residual_quantity": "0.00000593",
      "residual_value": "0.5549056800000000",
      "residual_unrealized_pnl": "0.02102721775079901217851692908"
    },
    "ETHUSDT": {
      "realized_pnl": "3.31222606619304479387093252",
      "buy_fills": 5,
      "sell_fills": 5,
      "fees_usdt": "0.3100922844205000000",
      "residual_quantity": "0.0000527",
      "residual_value": "0.175901006000000",
      "residual_unrealized_pnl": "0.009089735099955206129067480632"
    },
    "SOLUSDT": {
      "realized_pnl": "5.20242881708465061751371490",
      "buy_fills": 4,
      "sell_fills": 4,
      "fees_usdt": "0.248978866875000000",
      "residual_quantity": "0.000967",
      "residual_value": "0.18306277000000",
      "residual_unrealized_pnl": "0.05530287486034938248628509916"
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
  "g_week": 0.0013568179485312637,
  "total_window_hours": 8784.0,
  "full_weeks_count": 52,
  "losing_full_weeks_count": 23,
  "losing_full_weeks_ratio": 0.4423076923076923,
  "worst_full_week_return": -0.0034022846371208892,
  "partial_week_present": true,
  "experiment_id": "EXP-124",
  "regime_variant": "R1",
  "state_experiment_id": "EXP-122",
  "training_experiment_id": "EXP-067",
  "prepared_experiment_id": "EXP-063",
  "label_policy": "net_positive_base_v1",
  "threshold": 0.5,
  "status": "complete",
  "regime_blocked_records": 70,
  "regime_blocked_positive_quantity_records": 70,
  "regime_blocked_zero_quantity_records": 0,
  "regime_blocked_by_symbol": {
    "SOLUSDT": 28,
    "BTCUSDT": 21,
    "ETHUSDT": 21
  },
  "regime_blocked_positive_by_symbol": {
    "SOLUSDT": 28,
    "BTCUSDT": 21,
    "ETHUSDT": 21
  },
  "allowed_decisions": 818,
  "total_decisions": 2196,
  "blocked_count_limitation": "Counts include repeated rebalance attempts; positive quantity does not imply an independent missed trade or profitable opportunity."
}
```
