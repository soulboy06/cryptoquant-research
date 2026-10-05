# EXP-126 R1基础资格

来源与接口：已核对冻结配置、状态、模型、R0输入SHA及有限预算；执行接口小型合成等价证据不代表全年账户重跑。

历史相对改善与代价：按冻结门槛评价收益、回撤、交易周期、手续费与阻断买单；减少交易不单独判为成功，止损记录全部保留。

收益目标：长期几何平均周净收益1.5%单列；三窗独立100 USDT账户的几何合成不是三年连续账户。

2023、2024、2025全部为已查看研究／选择数据，没有新独立样本外或实时模拟证明。2026继续封存；未接真实账户、借款、合约或付费部署。

原第六轮strict W2 EXP-119 +14.9816541437466%未达15%，原失败保留。

详细精确结果与失格项：

```json
{
  "result": {
    "eligible": false,
    "failed_checks": [
      "W1:closed_cycles>=30",
      "W2:closed_cycles>=30",
      "W2:net_return>=0.20",
      "combined_g_week>R0"
    ],
    "combined_g_week": "0.0000394433354965263672264496925590618073786578731",
    "r0_combined_g_week": "0.0008898527598482337493232417457697329207227635991",
    "r2025_above_minus_five_percent": false,
    "parameter_card": {
      "regime_variant": "R1",
      "label_policy": "net_positive_base_v1",
      "C": "0.1",
      "threshold": "0.50",
      "exit_variant": "C2",
      "breakeven_activation": "0.0120",
      "breakeven_ratio": "0.0025",
      "cooldown_hours": 4,
      "stop_loss": "0.08",
      "initial_cash": "100",
      "equity_floor": "50",
      "weight_per_symbol": "0.30",
      "adx_period": 14,
      "adx_min": 20,
      "ema_period": 72,
      "slope_hours": 24,
      "history_hours": 744,
      "regime_symbol": "BTCUSDT"
    },
    "weekly_target": "0.015",
    "target_achieved": false
  },
  "inputs": [
    {
      "experiment_id": "EXP-123",
      "run_manifest_sha256": "47fb6611ba936fadc3ff535a97bee579afdaf051bbae554ed9ef23f3cdb5646c",
      "summary_sha256": "0c377da1e85d76bd9b863370ca27294a77633c2b4b3df922ac5c24e6ded9586e",
      "state_manifest_sha256": "a8c06a53ba8d43377d38aac5a7677263364b0e07292b71a5cea0eefc39b16c62",
      "state_run_manifest_sha256": "c3dea8a7e57ee66a7dc7277c0f82daabc4e12a9190eaecb2886b115282782d04"
    },
    {
      "experiment_id": "EXP-124",
      "run_manifest_sha256": "461d436e2e7a7e89ea4c4e58de55828d33d5f0e27db8448b30c7e82588838cdb",
      "summary_sha256": "18a9d875d82f0e40ba9e4413ba2a1cbe9eda61c7ad00f5530a4f82a62cf9c8c8",
      "state_manifest_sha256": "a8c06a53ba8d43377d38aac5a7677263364b0e07292b71a5cea0eefc39b16c62",
      "state_run_manifest_sha256": "c3dea8a7e57ee66a7dc7277c0f82daabc4e12a9190eaecb2886b115282782d04"
    },
    {
      "experiment_id": "EXP-125",
      "run_manifest_sha256": "798f613a2e4711e30b965b97ddc0cc5de49d97f2ab4c8bc969f9cbc4bb2a738e",
      "summary_sha256": "25d9695d71a216cc4e041e9063e96c53d797fa5c5e0ec22984d390f4f4baedc7",
      "state_manifest_sha256": "a8c06a53ba8d43377d38aac5a7677263364b0e07292b71a5cea0eefc39b16c62",
      "state_run_manifest_sha256": "c3dea8a7e57ee66a7dc7277c0f82daabc4e12a9190eaecb2886b115282782d04"
    }
  ],
  "summaries": {
    "W1": {
      "strategy": "logistic_regression",
      "period": "development",
      "cost": "base",
      "initial_equity": "100",
      "start_utc": "2023-01-01 00:00:00+00:00",
      "end_utc": "2024-01-01 00:00:00+00:00",
      "final_equity": "100.16837672145160000000",
      "final_cash": "99.69667891005160000000",
      "residual_value": "0.47169781140000000000",
      "net_return": "0.00168376721451600000",
      "max_drawdown": "0.04015164449635917594148415220",
      "longest_drawdown_hours": 5978.0,
      "drawdown_unrecovered": true,
      "fills": 36,
      "rejected_orders": 4967,
      "rejection_reasons": {
        "minimum_notional": 9,
        "risk_blocked": 2,
        "zero_quantity": 4930,
        "regime_blocked": 23,
        "no_quote": 3
      },
      "fees_usdt": "1.09375765252070000000",
      "turnover_usdt": "1093.75765252070000000",
      "turnover_multiple": "10.93757652520700000",
      "mean_hourly_open_exposure": "0.006444924049407060825609001186",
      "closed_cycles": 18,
      "floor_triggers": 0,
      "stop_triggers": 0,
      "permanent_buy_lock": false,
      "stale_checkpoints": 4,
      "realized_pnl": "0.07686140884020933371017804",
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
          "realized_pnl": "0.42053041600490446448041826",
          "buy_fills": 2,
          "sell_fills": 2,
          "fees_usdt": "0.1219624117060000000",
          "residual_quantity": "0.0000663",
          "residual_value": "0.151287981000000",
          "residual_unrealized_pnl": "0.03320124379809553551958173933"
        },
        "SOLUSDT": {
          "realized_pnl": "-1.47578090386157558955733410",
          "buy_fills": 13,
          "sell_fills": 13,
          "fees_usdt": "0.789189058800000000",
          "residual_quantity": "0.000290",
          "residual_value": "0.02949880000000",
          "residual_unrealized_pnl": "-0.0009530783634244104426658886450"
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
      "breakeven_triggers": 2,
      "duration_triggers": 0,
      "g_week": 3.226479138440652e-05,
      "total_window_hours": 8760.0,
      "full_weeks_count": 52,
      "losing_full_weeks_count": 27,
      "losing_full_weeks_ratio": 0.5192307692307693,
      "worst_full_week_return": -0.017990225225453904,
      "partial_week_present": true,
      "experiment_id": "EXP-123",
      "regime_variant": "R1",
      "state_experiment_id": "EXP-122",
      "training_experiment_id": "EXP-065",
      "prepared_experiment_id": "EXP-063",
      "label_policy": "net_positive_base_v1",
      "threshold": 0.5,
      "status": "complete",
      "regime_blocked_records": 23,
      "regime_blocked_positive_quantity_records": 23,
      "regime_blocked_zero_quantity_records": 0,
      "regime_blocked_by_symbol": {
        "SOLUSDT": 17,
        "ETHUSDT": 6
      },
      "regime_blocked_positive_by_symbol": {
        "SOLUSDT": 17,
        "ETHUSDT": 6
      },
      "allowed_decisions": 701,
      "total_decisions": 2190,
      "blocked_count_limitation": "Counts include repeated rebalance attempts; positive quantity does not imply an independent missed trade or profitable opportunity."
    },
    "W2": {
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
    },
    "R2025": {
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
  },
  "r0_evidence": {
    "inputs": [
      {
        "experiment_id": "EXP-108",
        "run_manifest_sha256": "27d3606ba4d6a659a952a8a777ab6e4d609cb078920eb0b8329dfeb608370c10",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-065",
          "run_manifest_sha256": "ba77ca0ff286afac02e04e406286eae62229c68b95d0e6e7c4f96ced89d33202",
          "source_hash": "bff27c84a04057811e5f77d4aa489f85e6f2724dd9c8f9ee97c06e5052cbe2f5",
          "verified_source": {},
          "train_manifest_sha256": "64dbb1d42f0a8aaeee17bb6d15420d81724286ca723e641dfbcfd987d05cd1ba",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "f6d027d82ffd3a9b573fa878316491f0afb4a8c92ea6afcb1261e62de3ae48c4",
        "cost": "base",
        "window": "W1"
      },
      {
        "experiment_id": "EXP-109",
        "run_manifest_sha256": "df7b272369c4d4272502531eb1bbeb8b2ac2a2d6c2ce7a1d90c7ebd2e70b3654",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-067",
          "run_manifest_sha256": "29af1e5d2f8dd9c269d535f0db4c8d4604acfc4991422b55a206b3afcee31024",
          "source_hash": "bff27c84a04057811e5f77d4aa489f85e6f2724dd9c8f9ee97c06e5052cbe2f5",
          "verified_source": {},
          "train_manifest_sha256": "da54ef0833802e27b23edc76b75d4f5d4991562a6d964b3eccadc4424f3ab1c7",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "312dadba960eb8b642c65556659145ba6dcc6be91f6960e7da93624a98f25219",
        "cost": "base",
        "window": "W2"
      },
      {
        "experiment_id": "EXP-110",
        "run_manifest_sha256": "976ebb90de3cbe41836faa562404ecc3d4c2b776bd31ae1aa605430195e451d8",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-094",
          "run_manifest_sha256": "5f7003c923591eb772ac257042c016450d2ec0bec1d93bce6439339033bc1da7",
          "source_hash": "e18ad8d5f734035f734e79d1180b3561617c29783a54c2aa4852c42c81819375",
          "verified_source": {},
          "train_manifest_sha256": "f67670ee4fc0839e5b026b99e398b4400bb3de671358c17bb0cdeac2aa7761d9",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "b3072853a7904004b841d18350894fb13d7ce7f193d26313865461926dec4f5c",
        "cost": "base",
        "window": "R2025"
      },
      {
        "experiment_id": "EXP-115",
        "run_manifest_sha256": "1876ed604f13551bb1580c66428cc5a20061d9fd01ba1618f86651f684d76614",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-065",
          "run_manifest_sha256": "ba77ca0ff286afac02e04e406286eae62229c68b95d0e6e7c4f96ced89d33202",
          "source_hash": "bff27c84a04057811e5f77d4aa489f85e6f2724dd9c8f9ee97c06e5052cbe2f5",
          "verified_source": {},
          "train_manifest_sha256": "64dbb1d42f0a8aaeee17bb6d15420d81724286ca723e641dfbcfd987d05cd1ba",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "1ebb6f92e2d2b4e9ca830647f0919c9d6a9e0744ddee37630669d908ec80e931",
        "cost": "higher_execution",
        "window": "W1"
      },
      {
        "experiment_id": "EXP-116",
        "run_manifest_sha256": "e6a52cb2b7cdffe5b468e950d07cc77b49045b9ac699ec8c5fe8fd956f543386",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-067",
          "run_manifest_sha256": "29af1e5d2f8dd9c269d535f0db4c8d4604acfc4991422b55a206b3afcee31024",
          "source_hash": "bff27c84a04057811e5f77d4aa489f85e6f2724dd9c8f9ee97c06e5052cbe2f5",
          "verified_source": {},
          "train_manifest_sha256": "da54ef0833802e27b23edc76b75d4f5d4991562a6d964b3eccadc4424f3ab1c7",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "288a82f78c764220c03a54dcbe8539f1368999d855c84a169cd917dfbfe0ef6c",
        "cost": "higher_execution",
        "window": "W2"
      },
      {
        "experiment_id": "EXP-117",
        "run_manifest_sha256": "26060915ce73742d90c91c32da3a9c5726bb1bb41a156fc6524d52362ab54909",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-094",
          "run_manifest_sha256": "5f7003c923591eb772ac257042c016450d2ec0bec1d93bce6439339033bc1da7",
          "source_hash": "e18ad8d5f734035f734e79d1180b3561617c29783a54c2aa4852c42c81819375",
          "verified_source": {},
          "train_manifest_sha256": "f67670ee4fc0839e5b026b99e398b4400bb3de671358c17bb0cdeac2aa7761d9",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "1804eea462d7037265b1a02cb0c0d425d735f5df25e3e911b27645c6ef279313",
        "cost": "higher_execution",
        "window": "R2025"
      },
      {
        "experiment_id": "EXP-118",
        "run_manifest_sha256": "719e51fee15e62c92d7ca05193a6a5d57ef57f1cafe7bb544008ef33cae43edf",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-065",
          "run_manifest_sha256": "ba77ca0ff286afac02e04e406286eae62229c68b95d0e6e7c4f96ced89d33202",
          "source_hash": "bff27c84a04057811e5f77d4aa489f85e6f2724dd9c8f9ee97c06e5052cbe2f5",
          "verified_source": {},
          "train_manifest_sha256": "64dbb1d42f0a8aaeee17bb6d15420d81724286ca723e641dfbcfd987d05cd1ba",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "2e7b6355b8cf1b558b120ab2fc325c7b0648786012b4beb0de91feadc63b8074",
        "cost": "strict",
        "window": "W1"
      },
      {
        "experiment_id": "EXP-119",
        "run_manifest_sha256": "43700337c968bffed563b62b3fe3276d703cddda7c9bf2f853b100ba3710f57b",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-067",
          "run_manifest_sha256": "29af1e5d2f8dd9c269d535f0db4c8d4604acfc4991422b55a206b3afcee31024",
          "source_hash": "bff27c84a04057811e5f77d4aa489f85e6f2724dd9c8f9ee97c06e5052cbe2f5",
          "verified_source": {},
          "train_manifest_sha256": "da54ef0833802e27b23edc76b75d4f5d4991562a6d964b3eccadc4424f3ab1c7",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "ce63cbf395827eff85dc2a314d377f4f0ac2f1c471e4a482f42ec4d145cd54dd",
        "cost": "strict",
        "window": "W2"
      },
      {
        "experiment_id": "EXP-120",
        "run_manifest_sha256": "992bbdb9051b770a37a0c5a626f5cc2880319f634289958261d43500b7afca44",
        "source_hash": "d0e17fce1de1518c5adae7ad727173ef7c8bebb477be246aef1c857bfcc87085",
        "verified_source": {},
        "training": {
          "experiment_id": "EXP-094",
          "run_manifest_sha256": "5f7003c923591eb772ac257042c016450d2ec0bec1d93bce6439339033bc1da7",
          "source_hash": "e18ad8d5f734035f734e79d1180b3561617c29783a54c2aa4852c42c81819375",
          "verified_source": {},
          "train_manifest_sha256": "f67670ee4fc0839e5b026b99e398b4400bb3de671358c17bb0cdeac2aa7761d9",
          "prepared_manifest_sha256": "903d0b838b821f76e6b43619476c690ed061970f3a7d453b3c2aea779ad6b121",
          "config_compatibility": {
            "mode": "fifth_to_sixth_training_signature",
            "source_research_config_hash": "a9af04e59c1013bd67c8e04a5d7f2d523051ece9458f6eafa263a63623620ec8",
            "source_execution_config_hash": "6a2568ac37f4fa5e970d7b7677d2effb8f2a2f934d9ceb026ab93626e5215b7b",
            "requested_research_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3"
          }
        },
        "summary_sha256": "edfc1a40222fe3b4460a2538d3787d67fe0d0f43e1a387776350eb586a94b56b",
        "cost": "strict",
        "window": "R2025"
      }
    ],
    "source_config_hash": "5937b2124e447acf0c7e218af824724ea29e30fb28328667fa5b2a67e288a4e3",
    "equivalence_proof_sha256": "72ec65fb6637e3b0a3a3d04af37cc0dd12d9adab09973b0f9b56e0d14f85078b",
    "original_execution_proof_sha256": "1384a18d42aeea3e9e8261e58828c2cbd4f7f6f2e1930ca752387579cf28b760",
    "limitation": "R0 uses nine frozen historical accounts; equivalence checked on synthetic 16h only, no annual rerun"
  },
  "regime_budget": {
    "profile": "V7",
    "total_used": 4,
    "total_limit": 12,
    "accounts_used": 3,
    "accounts_limit": 9,
    "records": [
      {
        "experiment_id": "EXP-122",
        "type": "regime_preparation",
        "status": "complete",
        "key": null,
        "state_experiment_id": null,
        "run_manifest_sha256": "c3dea8a7e57ee66a7dc7277c0f82daabc4e12a9190eaecb2886b115282782d04"
      },
      {
        "experiment_id": "EXP-123",
        "type": "regime_evaluation",
        "status": "complete",
        "key": [
          "W1",
          "base",
          "R1"
        ],
        "state_experiment_id": "EXP-122",
        "run_manifest_sha256": "47fb6611ba936fadc3ff535a97bee579afdaf051bbae554ed9ef23f3cdb5646c"
      },
      {
        "experiment_id": "EXP-124",
        "type": "regime_evaluation",
        "status": "complete",
        "key": [
          "W2",
          "base",
          "R1"
        ],
        "state_experiment_id": "EXP-122",
        "run_manifest_sha256": "461d436e2e7a7e89ea4c4e58de55828d33d5f0e27db8448b30c7e82588838cdb"
      },
      {
        "experiment_id": "EXP-125",
        "type": "regime_evaluation",
        "status": "complete",
        "key": [
          "R2025",
          "base",
          "R1"
        ],
        "state_experiment_id": "EXP-122",
        "run_manifest_sha256": "798f613a2e4711e30b965b97ddc0cc5de49d97f2ab4c8bc969f9cbc4bb2a738e"
      }
    ]
  }
}
```
