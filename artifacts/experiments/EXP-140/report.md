# EXP-140 第八轮动态阈值与自适应仓位全景对比评估报告

## 1. 核心结果概览

- 筛选胜出变体：`None`
- 全量评估账户数：`9` 个

## 2. 三层结论最终评定

1. **结论一（因果性与方法有效性）**：【通过】BTC 状态与动态阈值/权重严格按已闭合小时生成（截至 t-1h），零未来信息泄漏；
2. **结论二（相对改善与机会代价权衡）**：参见下方全景对比数据；
3. **结论三（用户每周 1.5% 长期复利目标）**：`【未达到】`；

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