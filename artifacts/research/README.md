# 修复与第十轮证据

日期：2026-10-05（Asia/Shanghai）。[最终报告](../../docs/cycle-repair-and-tenth-results-2026-10-05.md)回答12项交付问题；[汇总JSON](cycle-repair-and-tenth-summary.json)含全部新基线、候选、PnL／费用差异、币种／状态／dust归因及2813项产物与源码哈希检查记录。

[phase-a-and-tenth-evidence.zip](phase-a-and-tenth-evidence.zip)为完整4452文件证据包，46.47MiB，[evidence_manifest.json](evidence_manifest.json)保存压缩包与每个原文件SHA-256。压缩包SHA：`c0338e24a2e44f6721ea4a705edcdd7c453b22ce2e5ab6a8384914516ed33279`，逐文件解压内容SHA实际核对通过。

包含新EXP-159～185／192的完整旧／新成交、订单、风险事件、逐小时净值、周统计、targets、配置、来源和源码快照；包含15组原冻结输入所在旧实验目录、BTC状态文件及原源码，便于查证配对复现。EXP-159失败保留，EXP-175同参数替代；EXP-186～191未运行，没有伪造目录。R6逐入场状态周期归因由现有流水计算，CSV也在包内，无额外账户回测。

不包含原始行情data目录、2026测试分区、真实账户凭据或订单。旧配置／manifest可描述原全量准备范围或测试边界，不表示读取或发布该测试行情；源码中的单元测试也不是市场holdout。

在仓库根目录解压，归档内部路径从artifacts开始，对应固定文件字节。已有同名文件先按manifest核对SHA，不覆盖不同内容的冻结结果。Git文本换行规范可能导致克隆后的JSON／源码字节与实验SHA不同；复核实验SHA应使用压缩包内冻结原字节，不能因此重写manifest。

只复核结果不需要公开行情。重新运行账户还需要单独重建EXP-003 development／validation公开分区并核对各run_manifest.data_info中SHA，以及保持环境／冻结输入版本；数据不随证据包发布，不能声称仅解压就能完全复跑。原已完成编号不允许覆盖，新运行必须事前登记新编号及预算。

报告生成入口：scripts/summarize_cycle_research.py、write_cycle_delivery_report.py；打包入口：scripts/package_cycle_evidence.py。后续压缩包若重新生成，字节／SHA可能变化，应保留本版本冻结证据并另存版本。
