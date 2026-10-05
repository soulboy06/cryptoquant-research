# EXP-125 R1历史账户

来源与接口：已核对冻结配置、状态、模型、R0输入SHA及有限预算；执行接口小型合成等价证据不代表全年账户重跑。

历史相对改善与代价：按冻结门槛评价收益、回撤、交易周期、手续费与阻断买单；减少交易不单独判为成功，止损记录全部保留。

收益目标：长期几何平均周净收益1.5%单列；三窗独立100 USDT账户的几何合成不是三年连续账户。

2023、2024、2025全部为已查看研究／选择数据，没有新独立样本外或实时模拟证明。2026继续封存；未接真实账户、借款、合约或付费部署。

原第六轮strict W2 EXP-119 +14.9816541437466%未达15%，原失败保留。

详细精确结果与失格项：

```json
{
  "strategy": "logistic_regression",
  "period": "validation",
  "cost": "base",
  "initial_equity": "100",
  "start_utc": "2025-01-01 00:00:00+00:00",
  "end_utc": "2025-12-31 20:00:00+00:00",
  "final_equity": "93.57547799671115000000",
  "final_cash": "92.63836501071115000000",
  "residual_value": "0.93711298600000000000",
  "net_return": "-0.06424522003288850000",
  "max_drawdown": "0.1225149719760993478051925203",
  "longest_drawdown_hours": 8317.0,
  "drawdown_unrecovered": true,
  "fills": 104,
  "rejected_orders": 6286,
  "rejection_reasons": {
    "zero_quantity": 6152,
    "regime_blocked": 110,
    "risk_blocked": 9,
    "minimum_notional": 15
  },
  "fees_usdt": "2.89875891231740000000",
  "turnover_usdt": "2898.75891231740000000",
  "turnover_multiple": "28.98758912317400000",
  "mean_hourly_open_exposure": "0.01989442951524463807454091221",
  "closed_cycles": 52,
  "floor_triggers": 0,
  "stop_triggers": 5,
  "permanent_buy_lock": false,
  "stale_checkpoints": 0,
  "realized_pnl": "-6.35456298674474573637889686",
  "per_symbol": {
    "BTCUSDT": {
      "realized_pnl": "-0.73062766735855336581036469",
      "buy_fills": 10,
      "sell_fills": 10,
      "fees_usdt": "0.54866176056840000000",
      "residual_quantity": "0.00000708",
      "residual_value": "0.6197962980000000",
      "residual_unrealized_pnl": "-0.01602805688779663418963532724"
    },
    "ETHUSDT": {
      "realized_pnl": "0.30321740699007685235958115",
      "buy_fills": 28,
      "sell_fills": 28,
      "fees_usdt": "1.5663091269140000000",
      "residual_quantity": "0.0000803",
      "residual_value": "0.238584148000000",
      "residual_unrealized_pnl": "-0.009190299962576852359581102460"
    },
    "SOLUSDT": {
      "realized_pnl": "-5.92715272637626922292811332",
      "buy_fills": 14,
      "sell_fills": 14,
      "fees_usdt": "0.783788024835000000",
      "residual_quantity": "0.000633",
      "residual_value": "0.07873254000000",
      "residual_unrealized_pnl": "-0.04474065969373077707188666739"
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
  "g_week": -0.0012732301470783636,
  "total_window_hours": 8756.0,
  "full_weeks_count": 52,
  "losing_full_weeks_count": 25,
  "losing_full_weeks_ratio": 0.4807692307692308,
  "worst_full_week_return": -0.03987246448584458,
  "partial_week_present": true,
  "experiment_id": "EXP-125",
  "regime_variant": "R1",
  "state_experiment_id": "EXP-122",
  "training_experiment_id": "EXP-094",
  "prepared_experiment_id": "EXP-063",
  "label_policy": "net_positive_base_v1",
  "threshold": 0.5,
  "status": "complete",
  "regime_blocked_records": 110,
  "regime_blocked_positive_quantity_records": 110,
  "regime_blocked_zero_quantity_records": 0,
  "regime_blocked_by_symbol": {
    "ETHUSDT": 65,
    "SOLUSDT": 31,
    "BTCUSDT": 14
  },
  "regime_blocked_positive_by_symbol": {
    "ETHUSDT": 65,
    "SOLUSDT": 31,
    "BTCUSDT": 14
  },
  "allowed_decisions": 725,
  "total_decisions": 2189,
  "blocked_count_limitation": "Counts include repeated rebalance attempts; positive quantity does not imply an independent missed trade or profitable opportunity."
}
```
