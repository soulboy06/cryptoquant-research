# EXP-139 第八轮动态响应基础筛选报告

- 整体筛选判定：`【失格】`
- 选定最优变体：`无合格候选`

## 变体筛选明细

### 变体 R2（dynamic_threshold）
- 资格判定：`失格`
- 失败检查项：`W1:closed_cycles>=30, W2:closed_cycles>=30, W2:net_return>=0.15, combined_g_week>R0`
- 合成周收益：`0.014135%/周`（R0: 0.088985%, R1: 0.003944%）
- 2025 达到 >-5% 进阶减亏目标：`False`

### 变体 R3（dynamic_sizing）
- 资格判定：`失格`
- 失败检查项：`W1:closed_cycles>=30, W2:net_return>=0.15, combined_g_week>R0`
- 合成周收益：`0.046297%/周`（R0: 0.088985%, R1: 0.003944%）
- 2025 达到 >-5% 进阶减亏目标：`False`

### 变体 R4（dual_synergy）
- 资格判定：`失格`
- 失败检查项：`W1:closed_cycles>=30, W2:closed_cycles>=30, W2:net_return>=0.15, combined_g_week>R0`
- 合成周收益：`0.006298%/周`（R0: 0.088985%, R1: 0.003944%）
- 2025 达到 >-5% 进阶减亏目标：`False`

```json
{
  "eligible": false,
  "selected_variant": null,
  "eligible_variants": {
    "R2": {
      "eligible": false,
      "failed_checks": [
        "W1:closed_cycles>=30",
        "W2:closed_cycles>=30",
        "W2:net_return>=0.15",
        "combined_g_week>R0"
      ],
      "combined_g_week": "0.0001413535966029533847839079048983319625070379132",
      "r0_combined_g_week": "0.0008898527598482337493232417457697329207227635991",
      "r1_combined_g_week": "0.0000394433354965263672264496925590618073786578731",
      "r2025_above_minus_five_percent": false,
      "weekly_target_achieved": false
    },
    "R3": {
      "eligible": false,
      "failed_checks": [
        "W1:closed_cycles>=30",
        "W2:net_return>=0.15",
        "combined_g_week>R0"
      ],
      "combined_g_week": "0.0004629724886268671856841145211832932657579197305",
      "r0_combined_g_week": "0.0008898527598482337493232417457697329207227635991",
      "r1_combined_g_week": "0.0000394433354965263672264496925590618073786578731",
      "r2025_above_minus_five_percent": false,
      "weekly_target_achieved": false
    },
    "R4": {
      "eligible": false,
      "failed_checks": [
        "W1:closed_cycles>=30",
        "W2:closed_cycles>=30",
        "W2:net_return>=0.15",
        "combined_g_week>R0"
      ],
      "combined_g_week": "0.0000629754973046817001014581368928306088113685971",
      "r0_combined_g_week": "0.0008898527598482337493232417457697329207227635991",
      "r1_combined_g_week": "0.0000394433354965263672264496925590618073786578731",
      "r2025_above_minus_five_percent": false,
      "weekly_target_achieved": false
    }
  }
}
```