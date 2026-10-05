"""Render twelve requested answers from audited frozen research summaries."""
from decimal import Decimal as D
import json
from pathlib import Path

from cryptoquant.models.regime_reporting import combined_weekly


def main():
    root=Path.cwd()
    data=json.loads((root/'artifacts/research/cycle-repair-and-tenth-summary.json').read_text('utf-8'))
    rows=data['summaries']
    pct=lambda value:f'{D(str(value))*100:+.4f}%'
    num=lambda value:f'{D(str(value)):+.4f}'
    lines=['# 状态机修复与第十轮最终交付','',
        '日期：2026-10-05（Asia/Shanghai）。本轮任务完成，三候选全部失格，没有最终候选；未进入实时模拟或真实交易。2026测试继续封存。',
        '', '本报告对应用户附件的12项问题。所有收益均来自反复查看的2023—2025研究开发数据，各窗独立100USDT、三币共用余额，固定50USDT底线。R0是固定30%目标的模型策略对照，不是买入持有。合成周收益是独立窗口因子的时间加权几何比较，不是连续账户或独立样本外成绩。',
        '', '## 1．min-notional／cycle_open如何修复','',
        '卖单因金额不足被拒后，任何正持仓继续保持同一cycle_open、pending_exit、入场基准、保本状态及UTC持仓时长，不能提前冷却、重置或冒充新周期。普通strategy_exit也锁存退出请求；恢复可卖时先完成退出。重复观察不会重复增加持仓时间。',
        '', '真实全退出SELL之后，严格小于数量步长的剩余才按事前冻结的post_exit_sub_step_writeoff_v1模拟放弃：持仓实际置零、成本转损失，现金及手续费不变，独立dust_written_off审计。未成交的整个低于10USDT持仓禁止这样清理。核销不是币安dust转换或实际卖出，不能声称具备真实执行可行性。',
        '', '## 2．是否改变历史行为与PnL','',
        '15组旧源码／旧targets重放均复现原逐笔成交及关键收益、费用、回撤；新引擎15组均有成交及PnL变化，属于行为修复。变化还包含新增保守零头放弃政策，未另做政策消融，不能将总差异全部归因于旧bug。',
        '', '例如R6 W2从旧+13.7369%、59周期变为-0.2227%、27周期，核销零头市值8.6252USDT；R6 2025核销18.4763USDT。修复R0在2025触发固定底线，成交后净值49.262USDT，触发阈值不是成交保证。完整旧／新表见[Phase A报告](cycle-state-repair-results-2026-10-05.md)，首次成交差异、费用变化见[汇总JSON](../artifacts/research/cycle-repair-and-tenth-summary.json)。',
        '', '## 3．修复后的真实周期与全部基础成绩','',
        '| 策略 | W1收益／回撤／周期 | W2收益／回撤／周期 | 2025收益／回撤／周期 | 合成周收益 |',
        '| --- | --- | --- | --- | --- |']
    for variant in ('R0','R3','R5','R6','R7','R8','R9','R10'):
        cells=[]
        for window in ('W1','W2','R2025'):
            r=rows[variant][window]
            cells.append(f"{pct(r['net_return'])}／{D(r['max_drawdown'])*100:.2f}%／{r['closed_cycles']}")
        lines.append('| '+variant+' | '+' | '.join(cells)+f' | {combined_weekly(rows[variant])*100:+.6f}% |')
    lines+=['','完整生命周期与SELL成交数量分开；部分再平衡SELL不独立计周期。W1 R5/R6均30，W2为25/27，不能沿用旧“仅从56补至58”的诊断。',
        '', '## 4．哪些旧实验需要重新解释','',
        '原第六至九轮EXP-108～149及其筛选／汇总收益结论不再作为新引擎baseline；相关EXP-111～121、126～128、138～140、150～158保留历史版本和失败，不回写漂亮成绩。EXP-158关于周期口径、Risk Parity必败、固定波动率与W2将达到16%～17%的推演均不能作为已验证结论。旧训练模型不因账本修复自动失效，但交易成绩必须绑定引擎和dust政策；更早交易研究也不能未经重放宣称适用于当前引擎。',
        '', '## 5．三个候选机制','',
        '- 父策略先按修复R5/R6的三窗合成周收益选择R6，未根据第十轮结果改变。',
        '- R8：weak状态中，自身72h正收益且超越BTC的Alpha里选Top-1恢复30%。',
        '- R9：R8加自身24h收益>0才恢复；这是方向确认，不称数学加速度。',
        '- R10：weak Alpha自身概率达到既往预测expanding80%分位数才恢复30%，至少30个既往点，当前预测不进入分位数；不额外要求Top-1。',
        '', '三者只恢复weak仓位，favorable及冻结模型／12特征／C2／风险上限不变。只用已闭合行情、744h连续历史，无0.53／3%结果拟合、无新模型或新币。完整规则与预算见[事前方案](tenth-experiment-design-2026-10-05.md)。',
        '', '## 6．谁最好及资格结论','',
        'R8描述性合成周收益最高（-0.108368%），略好于R10，但仍亏损。R8/R10均因W2周期28<30、收益远低于15%、2025收益低于父策略而失格；R9还未超过父策略合成周收益。EXP-185筛选无胜出者，不把相对负baseline改善当盈利。',
        '', '实际完成EXP-176～184九个Base、EXP-185一次选择、EXP-192一次报告，共11登记项／9新账户。EXP-186～191六个压力账户条件未满足而跳过；未新增R11或重试参数。Phase A包括一次保留技术失败及替代，共32核验账户。',
        '', '## 7．提升来自哪些币及市场状态','',
        '| 策略／窗 | BTC净PnL U | ETH净PnL U | SOL净PnL U | 入场weak闭合PnL U | 入场favorable闭合PnL U |',
        '| --- | --- | --- | --- | --- | --- |']
    for variant in ('R6','R8','R9','R10'):
        for window in ('W1','W2','R2025'):
            sy=data['symbol_contributions'][variant][window]
            st=data['state_contributions'][variant][window]
            cells=[num(sy[s]['net_pnl']) for s in ('BTCUSDT','ETHUSDT','SOLUSDT')]
            cells+=[num(st[s]['net_pnl']) for s in ('weak','favorable')]
            lines.append(f'| {variant}/{window} | '+' | '.join(cells)+' |')
    lines+=['','R8较R6：W1增加0.8987USDT全部来自SOL；W2 SOL增加0.5729U、ETH减少0.1266U、BTC不变，合计+0.4463U。weak入场组W1/W2分别增加0.9081U／0.4627U，2025减少0.4730U。favorable目标不变仍会受到共享现金及净值路径影响；这些是完整周期按入场状态归类的描述，不能证明因果Alpha或每根K线状态归因。',
        '', 'R8完整周期净收益分布（含摩擦与dust；不是只统计盈利交易）：',
        '', '| 窗／组 | 周期 | 胜率 | 净收益中位数 | p10 | p90 | 净PnL U |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for window in ('W1','W2','R2025'):
        for group,st in data['state_contributions']['R8'][window].items():
            fmt=lambda x:'未计算' if x is None else pct(x)
            lines.append(f"| {window}/{group} | {st['cycles']} | {fmt(st['win_rate'])} | {fmt(st['median_return'])} | {fmt(st['p10_return'])} | {fmt(st['p90_return'])} | {num(st['net_pnl'])} |")
    lines+=['','Alpha／ordinary与weak／favorable是两种分别完备的分组，不能把四组加在一起；R9/R10及父策略完整分布见汇总JSON和各cycle_distributions.json。',
        '', '## 8．2025防守是否破坏','',
        '相对修复R6，R8净收益下降0.4373个百分点、最大回撤增加0.2361个百分点；R9/R10也更亏。仍显著好于修复R0且没有触发50底线，但已违反冻结的“2025收益不低于父策略”条件，未达到>-5%防守目标。不能沿用旧-1.92%防守成绩。',
        '', '## 9．参数敏感性','',
        '没有基础合格候选，事前规定的条件25%邻域／压力未启动，不能宣称仓位稳定。已有25%父策略与30% R8只显示W1/W2小幅改善、2025变差，没有出现30%突然异常盈利。R9加方向确认后W1收益增厚消失，表明条件选择会影响效果。没有搜参挑25%或30%赢家。',
        '', '## 10．是否只是适配2024 SOL','',
        'W2仅8个R8恢复决策点（SOL7、ETH1），增益主要来自SOL；稀疏且集中、2025更差，存在适配单年／单币风险，不能排除。R8在W1也有SOL增益，因此也不能断言只适配2024。R8与R10在W1/W2完整targets的SHA相同，置信度机制没有提供独立改善；2025 R10多2个ETH恢复点反而更差。固定3机制与因果检查约束自由度，不能代替未查看数据的泛化证据。',
        '', '## 11．相对R0／R5／R6的真实收益风险差异','',
        '以下为描述性最好R8的差值，单位是百分点；回撤差值正数表示风险更大。其余候选差值在汇总JSON。',
        '', '| 参照 | W1收益差／回撤差 | W2收益差／回撤差 | 2025收益差／回撤差 | 合成周收益差 |',
        '| --- | --- | --- | --- | --- |']
    for ref,delta in data['differences']['R8'].items():
        cells=[f"{num(delta[w]['return_delta_pp'])}／{num(delta[w]['drawdown_delta_pp'])}" for w in ('W1','W2','R2025')]
        lines.append('| '+ref+' | '+' | '.join(cells)+' | '+num(delta['combined_week_delta_pp'])+' |')
    lines+=['','费用与模拟零头损失须同时看：',
        '', '| 策略／窗 | 成交数 | 完整周期 | 费用 U | 核销零头市值 U | 最差年度净收益 |',
        '| --- | --- | --- | --- | --- | --- |']
    for variant in ('R6','R8','R9','R10'):
        for window in ('W1','W2','R2025'):
            r=rows[variant][window]
            lines.append(f"| {variant}/{window} | {r['fills']} | {r['closed_cycles']} | {D(r['fees_usdt']):.4f} | {D(r['dust_writeoff_value']):.4f} | {pct(r['net_return'])} |")
    lines+=['','每窗约一年；“最差年度”此处是该独立窗结果，三窗最差均为2025。逐币dust的数量／成本／市值在汇总JSON，不能用核销前虚拟净收益替代真实账本；历史数量精度快照、手续费买币扣资产及小本金导致零头成本尤其显著，真实dust处理可行性未验证。',
        '', '## 12．2026与下一行动','',
        '建议继续封存2026，不消耗独立检验。三候选全失败，停止本轮，先向用户汇报；后续首先只读核对历史数量步长、手续费处理与dust政策的可实现性并冻结后续方案，不能自动放宽本金／仓位／门槛或继续调参。若未来用户明确授权消耗2026，须规则先冻结且仅一次检验，不能根据2026调整。',
        '', '## 检查、版本与复现证据','',
        '- 修复独立提交3751f9d；第十轮事前冻结提交33ca36e。72项受影响关键检查通过（Phase A 65＋机制5＋预算2），未重复未受影响的全部测试。',
        f"- 汇总脚本核对{data['artifact_and_source_sha_checks']}项产物／源码SHA，并核对完整周期PnL、逐币dust、favorable目标保持；账户回测逐组检查余额非负、资金／费用守恒及逐币PnL。",
        '- EXP-159两次核验后在报告快照阶段SameFileError失败保留；EXP-175同参数技术替代。没有策略参数重试。',
        '- 数据只读EXP-003 development／validation；守卫拒绝test分区，仅复用获授权既有终点报价。数据、模型、旧源码、targets、配置、环境及SHA在各run_manifest。',
        '- [Phase A原始验收](../artifacts/experiments/EXP-174/comparison.json)、[第十轮原始比较](../artifacts/experiments/EXP-192/comparison.json)、[统一归因JSON](../artifacts/research/cycle-repair-and-tenth-summary.json)。新流水／targets／源码快照完整保存在证据压缩包，参见artifacts/research/README.md；没有原始行情、2026测试或交易凭据。',
        '- scripts/verify_cycle_repair.py用于旧／新配对，scripts/run_tenth_research.py用于冻结9Base，scripts/summarize_cycle_research.py与write_cycle_delivery_report.py仅重算既有产物报告。已完成编号不可再覆盖，复跑需要新编号和预算登记。',
        '', '本次完成的是执行修复、来源核验和失败的有限策略研究；没有证明稳定盈利、每周1.5%或独立样本外有效。']
    path=root/'docs/cycle-repair-and-tenth-results-2026-10-05.md'
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(path)


if __name__=='__main__':
    main()
