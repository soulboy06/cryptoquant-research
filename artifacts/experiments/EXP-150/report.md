# EXP-150 第九轮相对强弱解耦基础筛选报告

- 整体筛选判定：`【失格】`
- 选定最优变体：`无合格候选`

## 变体筛选明细

### 变体 R5（alpha_decoupled_20）
- 资格判定：`失格`
- 失败检查项：`W1:closed_cycles>=30, W2:net_return>=0.15`
- 合成周收益：`0.096479%/周`（R0: 0.088985%, R1: 0.003944%）
- 2025 达到 >-5% 进阶减亏目标：`True`

### 变体 R6（alpha_decoupled_25）
- 资格判定：`失格`
- 失败检查项：`W1:closed_cycles>=30, W2:net_return>=0.15`
- 合成周收益：`0.099379%/周`（R0: 0.088985%, R1: 0.003944%）
- 2025 达到 >-5% 进阶减亏目标：`True`

### 变体 R7（alpha_multi_horizon）
- 资格判定：`失格`
- 失败检查项：`W1:closed_cycles>=30, W2:net_return>=0.15, combined_g_week>R0`
- 合成周收益：`0.088978%/周`（R0: 0.088985%, R1: 0.003944%）
- 2025 达到 >-5% 进阶减亏目标：`True`

```json
{
  "eligible": false,
  "selected_variant": null,
  "eligible_variants": {
    "R5": {
      "eligible": false,
      "failed_checks": [
        "W1:closed_cycles>=30",
        "W2:net_return>=0.15"
      ],
      "combined_g_week": "0.0009647909148137556175711389505417383575018191208",
      "r0_combined_g_week": "0.0008898527598482337493232417457697329207227635991",
      "r1_combined_g_week": "0.0000394433354965263672264496925590618073786578731",
      "r2025_above_minus_five_percent": true,
      "weekly_target_achieved": false
    },
    "R6": {
      "eligible": false,
      "failed_checks": [
        "W1:closed_cycles>=30",
        "W2:net_return>=0.15"
      ],
      "combined_g_week": "0.0009937943981781428264488938403305945325379014515",
      "r0_combined_g_week": "0.0008898527598482337493232417457697329207227635991",
      "r1_combined_g_week": "0.0000394433354965263672264496925590618073786578731",
      "r2025_above_minus_five_percent": true,
      "weekly_target_achieved": false
    },
    "R7": {
      "eligible": false,
      "failed_checks": [
        "W1:closed_cycles>=30",
        "W2:net_return>=0.15",
        "combined_g_week>R0"
      ],
      "combined_g_week": "0.0008897813840871882838877527268673508175953108016",
      "r0_combined_g_week": "0.0008898527598482337493232417457697329207227635991",
      "r1_combined_g_week": "0.0000394433354965263672264496925590618073786578731",
      "r2025_above_minus_five_percent": true,
      "weekly_target_achieved": false
    }
  }
}
```