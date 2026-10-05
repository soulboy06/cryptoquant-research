"""可复核的收益／回撤与中文报告；金额仍为 Decimal。"""

from collections import Counter
import json

import pandas as pd

from decimal import Decimal
from cryptoquant.cli import write_json
from cryptoquant.trading.ledger import Portfolio, ZERO, amount
from cryptoquant.baselines.periods import period_bounds


LIMITATIONS = [
    '本次只评价2022—2024开发期；没有训练模型，没有打开验证／保留测试评价，也不是实时或真实收益。',
    '当前公开规则快照近似历史规则；市价名义金额用模拟成交价检查，未重建参考价或分钟VWAP。',
    '小时开盘近似成交；不还原盘口、排队、冲击或小时内路径；费用固定且无BNB优惠。',
    '固定50 USDT底线在真实小时收盘观察，停机恢复首个真实开盘补查；触发不保证退出后仍有50。',
    '停机／no_trade按已核验日历禁止成交，这是离线执行约束，不能从当根最终成交量提前产生在线信号。',
    'EMA在缺口后重启，744个连续观察之前不调仓；风险退出不受预热限制。尾差和陈旧估值都保留。',
    '净值与回撤来自交易前起点、小时收盘和成交后检查点；未识别小时内最大回撤。',
    '每年是同一账户的连续分段；没有年度重置。开发结果没有用于搜索EMA或风险参数。',
]


def summarize(result, config):
    start, end = period_bounds(config, result.period, window=result.window)
    rows = result.equity
    peak, max_drawdown = rows[0]['equity'], ZERO
    peak_time = rows[0]['time']
    longest_hours = 0.0
    underwater = False
    for row in rows:
        value, time = row['equity'], row['time']
        if value >= peak:
            if underwater:
                longest_hours = max(longest_hours, (time - peak_time).total_seconds() / 3600)
            peak, peak_time = value, time
            underwater = False
        else:
            underwater = True
            longest_hours = max(longest_hours, (time - peak_time).total_seconds() / 3600)
            max_drawdown = max(max_drawdown, (peak - value) / peak)
    # A run that was never below its peak has no underwater duration.
    if max_drawdown == 0:
        longest_hours = 0.0
    final = result.book.equity(result.marks)
    residual = final - result.book.cash
    opens = [r for r in rows if r['phase'] == 'open']
    replay = Portfolio(config.initial_cash, config.symbols)
    per_symbol = {s: dict(realized_pnl=ZERO, buy_fills=0, sell_fills=0, fees_usdt=ZERO) for s in config.symbols}
    cost = config.costs[result.cost_name]
    dust_events = {}
    for event in result.risk.events:
        if event['event'] == 'dust_written_off':
            dust_events.setdefault((event['time'], event['symbol']), []).append(event)
    for fill in result.fills:
        before = replay.realized_pnl
        replay.apply_fill(fill['side'], fill['symbol'], fill['quantity'], fill['price'], cost.fee)
        # Apply explicit abandonment immediately after its real exit fill;
        # later buys must not inherit an already cleared dust cost basis.
        for event in dust_events.pop((fill['time'], fill['symbol']), []):
            replay.write_off_precision_dust(fill['symbol'], event['quantity_step'],
                                           event['value_usdt'] / event['quantity'])
        item = per_symbol[fill['symbol']]
        item['realized_pnl'] += replay.realized_pnl - before
        item['buy_fills' if fill['side'] == 'BUY' else 'sell_fills'] += 1
        item['fees_usdt'] += fill['fee_usdt']
    for s, item in per_symbol.items():
        position = result.book.positions[s]
        item.update(residual_quantity=position.quantity, residual_value=position.quantity * result.marks.get(s, ZERO),
                    residual_unrealized_pnl=position.quantity * (result.marks.get(s, ZERO) - position.average_cost))
    window_name = f'/{result.window}' if result.window else ''
    limitations = [f'本次只评价{result.period}{window_name}，没有打开保留测试，不是实时或真实收益。'] + LIMITATIONS[1:]
    if result.strategy == 'logistic_regression':
        limitations[5] = '模型特征在缺口后重启，744个连续观察之前保持持仓；风险退出独立生效。预测不fit评价数据。'
    summary = dict(strategy=result.strategy, period=result.period, cost=result.cost_name, initial_equity=config.initial_cash,
                   start_utc=start, end_utc=end,
                   final_equity=final, final_cash=result.book.cash, residual_value=residual,
                   net_return=final / config.initial_cash - 1, max_drawdown=max_drawdown,
                   longest_drawdown_hours=longest_hours, drawdown_unrecovered=final < peak,
                   fills=len(result.fills), rejected_orders=sum(not x['accepted'] for x in result.orders),
                   rejection_reasons=dict(Counter(x['reason'] for x in result.orders if not x['accepted'])),
                   fees_usdt=result.book.fees_usdt, turnover_usdt=result.book.turnover_usdt,
                   turnover_multiple=result.book.turnover_usdt / config.initial_cash,
                   mean_hourly_open_exposure=sum((r['exposure'] for r in opens), ZERO) / len(opens) if opens else ZERO,
                   closed_cycles=result.risk.closed_cycles, floor_triggers=result.risk.floor_triggers,
                   stop_triggers=result.risk.stop_triggers, permanent_buy_lock=result.risk.locked,
                   stale_checkpoints=sum(bool(r['stale_symbols']) for r in rows),
                   realized_pnl=result.book.realized_pnl, per_symbol=per_symbol, limitations=limitations)
    policy = getattr(result.risk, 'dust_policy', getattr(result, 'dust_policy', 'retain_mark_to_market'))
    dust_retained_events = [e for e in result.risk.events if e['event'] == 'dust_retained']
    dust_retained_value = sum((Decimal(str(e['value_usdt'])) for e in dust_retained_events), ZERO)
    dust_retained_cost = sum((Decimal(str(e['cost_usdt'])) for e in dust_retained_events), ZERO)
    summary.update(dust_policy=policy,
                   dust_writeoff_value=result.book.dust_writeoff_value,
                   dust_writeoff_cost=result.book.dust_writeoff_cost,
                   dust_retained_value=dust_retained_value,
                   dust_retained_cost=dust_retained_cost)
    if result.window is not None:
        summary['window'] = result.window
    if getattr(result, 'exit_variant', None) is not None:
        summary['exit_variant'] = result.exit_variant
    summary['breakeven_triggers'] = getattr(result.risk, 'breakeven_triggers', 0)
    summary['duration_triggers'] = getattr(result.risk, 'duration_triggers', 0)
    annual = []
    start_value = config.initial_cash
    for year in range(start.year, end.year + 1):
        left = max(pd.Timestamp(start), pd.Timestamp(f'{year}-01-01', tz='UTC'))
        right = min(pd.Timestamp(end), pd.Timestamp(f'{year + 1}-01-01', tz='UTC'))
        if left >= right:
            continue
        end_rows = [r for r in rows if r['time'] == right and r['phase'] in {'close', 'terminal'}]
        if not end_rows:
            raise ValueError('missing annual boundary')
        end_value = end_rows[-1]['equity']
        annual.append(dict(year=year, start_utc=left, end_utc=right, start_equity=start_value,
                           end_equity=end_value, net_return=end_value / start_value - 1))
        start_value = end_value
    return summary, annual


def save_report(result, config, output, experiment_id):
    start, end = period_bounds(config, result.period, window=result.window)
    summary, annual = summarize(result, config)
    write_json(output / 'summary.json', summary)
    for name, records, fallback in [
        ('orders', result.orders, ['time', 'symbol', 'side', 'accepted', 'reason']),
        ('fills', result.fills, ['time', 'symbol', 'side', 'quantity', 'price']),
        ('equity', result.equity, []), ('signals', result.signals, ['time', 'symbol', 'weight', 'history_count', 'ema24', 'ema72']),
        ('annual', annual, [])]:
        pd.DataFrame(records, columns=None if records else fallback).to_csv(output / (name + '.csv'), index=False)
    with (output / 'events.jsonl').open('w', encoding='utf-8') as stream:
        for event in result.risk.events:
            stream.write(json.dumps(event, ensure_ascii=False, default=str) + '\n')
    quarterly = []
    start_value = config.initial_cash
    for year in range(start.year, end.year + 1):
        for quarter in range(1, 5):
            month = 3 * (quarter - 1) + 1
            left = max(pd.Timestamp(start), pd.Timestamp(f'{year}-{month:02d}-01', tz='UTC'))
            right_boundary = pd.Timestamp(f'{year + 1}-01-01' if quarter == 4 else f'{year}-{month + 3:02d}-01', tz='UTC')
            right = min(pd.Timestamp(end), right_boundary)
            if left >= right:
                continue
            end_rows = [r for r in result.equity if r['time'] == right and r['phase'] in {'close', 'terminal'}]
            if not end_rows:
                raise ValueError('missing quarterly boundary')
            end_value = end_rows[-1]['equity']
            quarterly.append(dict(quarter=f'{year}Q{quarter}', start_utc=left, end_utc=right,
                                  start_equity=start_value, end_equity=end_value, net_return=end_value / start_value - 1))
            start_value = end_value
    pd.DataFrame(quarterly).to_csv(output / 'quarterly.csv', index=False)
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot([r['time'] for r in result.equity], [float(r['equity']) for r in result.equity], label=result.strategy)
    ax.axhline(float(config.equity_floor), color='red', linestyle='--', label='Fixed floor')
    window_title = ' / ' + result.window if result.window else ''
    ax.set(ylabel='Equity (USDT)', xlabel='UTC', title=experiment_id + ' / ' + result.period + window_title + ' / ' + result.cost_name)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / 'equity.png', dpi=160)
    plt.close(fig)
    pct = lambda x: f'{x * 100:.2f}%'
    window_title = f' {result.window}窗口' if result.window else ''
    lines = ['# ' + experiment_id + ' ' + ('开发期' if result.period == 'development' else '验证期') + window_title + '结果', '',
             f'策略 `{result.strategy}`，成本 `{result.cost_name}`。三币共同{config.initial_cash} USDT账户；{start.isoformat()} 至 {end.isoformat()} UTC终点只清算。', '',
             f'期末净值 **{summary["final_equity"]:.4f} USDT**，净收益 **{pct(summary["net_return"])}**，最大回撤 **{pct(summary["max_drawdown"])}**。', '',
             f'期末现金 {summary["final_cash"]:.4f}，剩余持仓价值 {summary["residual_value"]:.6f} USDT；尾差没有抹除。',
             f'成交 {summary["fills"]} 笔，闭合周期 {summary["closed_cycles"]}；手续费折合 {summary["fees_usdt"]:.4f} USDT，成交额 {summary["turnover_usdt"]:.4f} USDT。',
             f'底线触发 {summary["floor_triggers"]} 次，单币止损 {summary["stop_triggers"]} 次；永久禁买：{summary["permanent_buy_lock"]}。拒单 {summary["rejected_orders"]} 笔，原因 {summary["rejection_reasons"]}。',
             f'最长回撤 {summary["longest_drawdown_hours"]:.0f} 小时，期末未恢复：{summary["drawdown_unrecovered"]}。小时开盘暴露平均 {pct(summary["mean_hourly_open_exposure"])}，陈旧估值检查点 {summary["stale_checkpoints"]}。', '',
             '| 年份 | 期初净值 | 期末净值 | 分段收益 |', '| --- | --- | --- | --- |']
    lines += [f'| {r["year"]} | {r["start_equity"]:.4f} | {r["end_equity"]:.4f} | {pct(r["net_return"])} |' for r in annual]
    lines += ['', '逐币已实现盈亏和剩余浮盈亏见 summary.json；订单与拒单见 orders.csv，成交见 fills.csv，所有持仓与估值年龄见 equity.csv。暴露均值按每个小时开盘后的持仓市值占比计算，不是小时内路径积分。', '',
              '年度与季度是同一账户的连续分段，季度详见quarterly.csv，末段包含清算费用。', '',
              '本结果是历史模拟，不能据此判定实盘盈利。验证筛选按完整候选与预定门槛进行；保留测试需要先合格并冻结，不能用本期成绩替代。', '', '## 局限', '']
    lines += ['- ' + text for text in summary['limitations']]
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary
