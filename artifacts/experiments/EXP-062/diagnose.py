"""EXP-062: read frozen EXP-049 outputs; never load markets, fit models or trade."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform
import sys
import tomllib

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'artifacts/experiments/EXP-049'
INPUTS = ['run_manifest.json', 'config.toml', 'summary.json', 'fills.csv',
          'events.jsonl', 'equity.csv', 'probabilities.csv', 'signals.csv',
          'validation_labels.csv']
ZERO, ONE = Decimal('0'), Decimal('1')
TOL = Decimal('1e-18')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')


def close(a, b):
    assert abs(Decimal(str(a)) - Decimal(str(b))) <= TOL, (a, b)


def stats(frame):
    return dict(count=len(frame), mean_probability=float(frame.probability.mean()),
                up_fraction=float(frame.label.mean()),
                profitable_after_cost_fraction=float((frame.net_4h > 0).mean()),
                mean_gross_4h=float(frame.label_return.mean()),
                median_gross_4h=float(frame.label_return.median()),
                mean_net_4h=float(frame.net_4h.mean()),
                median_net_4h=float(frame.net_4h.median()),
                positive_but_unprofitable=int(((frame.label_return > 0) & (frame.net_4h <= 0)).sum()))


def pct(value):
    return f'{float(value) * 100:.2f}%'


def run():
    assert not (OUT / 'run_manifest.json').exists(), 'Refuse to overwrite any existing diagnostic run.'
    source_manifest = json.loads((SOURCE / 'run_manifest.json').read_text(encoding='utf-8'))
    source_summary = json.loads((SOURCE / 'summary.json').read_text(encoding='utf-8'))
    config = tomllib.loads((SOURCE / 'config.toml').read_text(encoding='utf-8'))
    input_hashes = {name: sha(SOURCE / name) for name in INPUTS}
    for name in INPUTS:
        if name != 'run_manifest.json':
            assert input_hashes[name] == source_manifest['artifacts'][name], name
    assert source_manifest['status'] == 'complete'
    assert source_manifest['period'] == 'validation' and source_manifest['threshold'] == .64
    assert source_manifest['C'] == .1 and source_manifest['training_experiment_id'] == 'EXP-022'
    manifest = dict(experiment_id='EXP-062', type='validation_artifact_diagnostics',
                    status='running', started_at_utc=datetime.now(timezone.utc).isoformat(),
                    source_experiment_id='EXP-049', source_run_manifest=source_manifest,
                    inputs_sha256=input_hashes, script_sha256=sha(Path(__file__)),
                    environment=dict(python=sys.version, platform=platform.platform(), pandas=pd.__version__),
                    command=['.venv/Scripts/python.exe', 'artifacts/experiments/EXP-062/diagnose.py'],
                    no_fit=True, no_new_backtest=True, no_market_partitions_read=True, no_test_read=True)
    write_json(OUT / 'run_manifest.json', manifest)
    try:
        fee = Decimal(config['costs']['base']['fee'])
        adverse = Decimal(config['costs']['base']['adverse_price'])
        factor = (ONE - fee) ** 2 * (ONE - adverse) / (ONE + adverse)
        breakeven = ONE / factor - ONE
        fills = pd.read_csv(SOURCE / 'fills.csv', dtype=str, keep_default_na=False)
        fills['time'] = pd.to_datetime(fills.time, utc=True)
        equity = pd.read_csv(SOURCE / 'equity.csv', dtype=str, keep_default_na=False)
        equity['time'] = pd.to_datetime(equity.time, utc=True)
        events = [json.loads(line) for line in (SOURCE / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        closures = {(x['symbol'], pd.Timestamp(x['time'])) for x in events if x['event'] == 'cycle_closed'}
        assert len(closures) == sum(x['event'] == 'cycle_closed' for x in events) == source_summary['closed_cycles']
        labels = pd.read_csv(SOURCE / 'validation_labels.csv')
        probabilities = pd.read_csv(SOURCE / 'probabilities.csv')
        signals = pd.read_csv(SOURCE / 'signals.csv')
        for name in ['decision_time', 'label_start', 'label_end']:
            labels[name] = pd.to_datetime(labels[name], utc=True)
        probabilities['decision_time'] = pd.to_datetime(probabilities.decision_time, utc=True)
        signals['time'] = pd.to_datetime(signals.time, utc=True)
        keys = ['symbol', 'decision_time']
        assert not labels.duplicated(keys).any() and not probabilities.duplicated(keys).any()
        joined = labels.merge(probabilities, on=keys, validate='one_to_one', suffixes=('', '_saved'))
        assert len(joined) == len(labels) == len(probabilities)
        assert (abs(joined.probability - joined.probability_saved) < 1e-14).all()
        assert (labels.label_start == labels.decision_time).all()
        assert ((labels.label_end - labels.label_start) == pd.Timedelta(hours=4)).all()
        start, end = pd.Timestamp(source_summary['start_utc']), pd.Timestamp(source_summary['end_utc'])
        assert labels.decision_time.min() >= start and labels.label_end.max() <= end
        assert ((labels.label_return > 0).astype(int) == labels.label).all()
        assert fills.time.min() >= start and fills.time.max() <= end
        assert equity.time.min() >= start and equity.time.max() <= end
        labels['net_4h'] = (1 + labels.label_return) * float(factor) - 1
        labels['bucket'] = pd.cut(labels.probability, [0, .55, .60, .64, .65, 1.000001],
                                  right=False, labels=['<0.55', '0.55–0.60', '0.60–0.64', '0.64–0.65', '>=0.65'])
        assert labels.bucket.notna().all()
        selected = labels[labels.probability >= .64].copy()
        selected.to_csv(OUT / 'selected_signals.csv', index=False)
        signal_stats = []
        for symbol in ['ALL'] + config['symbols']:
            frame = labels if symbol == 'ALL' else labels[labels.symbol == symbol]
            for bucket, group in frame.groupby('bucket', observed=True):
                signal_stats.append(dict(symbol=symbol, group=str(bucket), **stats(group)))
            signal_stats.append(dict(symbol=symbol, group='ALL', **stats(frame)))
            signal_stats.append(dict(symbol=symbol, group='>=0.64', **stats(frame[frame.probability >= .64])))
        pd.DataFrame(signal_stats).to_csv(OUT / 'signal_buckets.csv', index=False)

        states = {s: dict(quantity=ZERO, cost=ZERO, ref_cost=ZERO, impact=ZERO, fee=ZERO) for s in config['symbols']}
        active, cycles, consumed = {}, [], set()
        cash = Decimal(config['initial_cash'])
        total_fees, total_realized = ZERO, ZERO
        fill_details = []
        for row in fills.to_dict('records'):
            symbol, time, side = row['symbol'], row['time'], row['side']
            state = states[symbol]
            quantity, price, notional, fill_fee = map(Decimal, [row['quantity'], row['price'], row['notional'], row['fee_usdt']])
            close(quantity * price, notional)
            close(notional * fee, fill_fee)
            assert row['accepted'] == 'True' and row['reason'] == 'filled'
            reference = price / (ONE + adverse if side == 'BUY' else ONE - adverse)
            if side == 'BUY':
                if symbol not in active:
                    match = selected[(selected.symbol == symbol) & (selected.decision_time == time)]
                    assert len(match) == 1, (symbol, time)
                    active[symbol] = dict(symbol=symbol, entry_time=time, exit_time=None,
                                          entry_probability=float(match.iloc[0].probability),
                                          gross_4h=float(match.iloc[0].label_return), net_4h=float(match.iloc[0].net_4h),
                                          carried_tail_quantity=state['quantity'], buy_notional=ZERO,
                                          cycle_fees_paid=ZERO, realized_net=ZERO, reference_price_pnl=ZERO,
                                          recognized_fee=ZERO, adverse_impact=ZERO, sold_cost_basis=ZERO,
                                          buy_count=0, sell_count=0)
                cycle = active[symbol]
                received = quantity * (ONE - fee)
                state['quantity'] += received
                state['cost'] += notional
                state['ref_cost'] += received * reference
                state['impact'] += received * (price - reference)
                state['fee'] += fill_fee
                cash -= notional
                cycle['buy_notional'] += notional
                cycle['buy_count'] += 1
                realized = ZERO
                assert row['fee_asset'] == symbol.removesuffix('USDT')
                close(row['fee_quantity'], quantity * fee)
            else:
                assert side == 'SELL' and symbol in active and quantity <= state['quantity']
                cycle = active[symbol]
                allocated = {k: quantity * (state[k] / state['quantity']) for k in ['cost', 'ref_cost', 'impact', 'fee']}
                realized = notional - fill_fee - allocated['cost']
                reference_pnl = quantity * reference - allocated['ref_cost']
                impact = allocated['impact'] + quantity * (reference - price)
                recognized_fee = allocated['fee'] + fill_fee
                close(reference_pnl - impact - recognized_fee, realized)
                cycle['realized_net'] += realized
                cycle['reference_price_pnl'] += reference_pnl
                cycle['recognized_fee'] += recognized_fee
                cycle['adverse_impact'] += impact
                cycle['sold_cost_basis'] += allocated['cost']
                cycle['sell_count'] += 1
                total_realized += realized
                for k, value in allocated.items():
                    state[k] -= value
                state['quantity'] -= quantity
                cash += notional - fill_fee
                assert row['fee_asset'] == 'USDT'
                close(row['fee_quantity'], fill_fee)
            cycle['cycle_fees_paid'] += fill_fee
            total_fees += fill_fee
            close(cash, row['cash_after'])
            close(state['quantity'], row['holding_after'])
            close(state['ref_cost'] + state['impact'] + state['fee'], state['cost'])
            fill_details.append(dict(time=time, symbol=symbol, side=side, reference_price=reference,
                                     execution_price=price, realized_net=realized, cash=cash, holding=state['quantity']))
            if (symbol, time) in closures:
                assert side == 'SELL' and (symbol, time) not in consumed
                cycle['exit_time'] = time
                cycle['duration_hours'] = (time - cycle['entry_time']).total_seconds() / 3600
                cycle['residual_quantity'] = state['quantity']
                cycle['realized_return_on_sold_cost'] = cycle['realized_net'] / cycle['sold_cost_basis']
                cycle['exit_reason'] = row['intent_reason']
                cycles.append(active.pop(symbol))
                consumed.add((symbol, time))
        assert not active and consumed == closures
        assert len(cycles) == len(selected) == source_summary['closed_cycles'] == 33
        assert all(x['buy_count'] == x['sell_count'] == 1 for x in cycles), 'This report expects one buy and sell per cycle.'
        pd.DataFrame(fill_details).to_csv(OUT / 'fill_reconciliation.csv', index=False)
        cycle_frame = pd.DataFrame(cycles).sort_values(['entry_time', 'symbol'])
        cycle_frame.insert(0, 'cycle_id', range(1, len(cycle_frame) + 1))
        cycle_frame.to_csv(OUT / 'cycles.csv', index=False)
        close(total_fees, source_summary['fees_usdt'])
        close(total_realized, source_summary['realized_pnl'])
        close(cash, source_summary['final_cash'])
        terminal = equity[equity.phase == 'terminal'].iloc[-1]
        final_equity = cash
        residual_unrealized = ZERO
        for symbol, state in states.items():
            close(state['quantity'], source_summary['per_symbol'][symbol]['residual_quantity'])
            mark = Decimal(terminal[symbol + '_mark'])
            final_equity += state['quantity'] * mark
            residual_unrealized += state['quantity'] * mark - state['cost']
            close(sum((x['realized_net'] for x in cycles if x['symbol'] == symbol), ZERO),
                  source_summary['per_symbol'][symbol]['realized_pnl'])
        close(final_equity, source_summary['final_equity'])
        close(final_equity - Decimal(config['initial_cash']), total_realized + residual_unrealized)
        opens = equity[equity.phase == 'open']
        mean_exposure = sum(map(Decimal, opens.exposure), ZERO) / len(opens)
        close(mean_exposure, source_summary['mean_hourly_open_exposure'])
        monthly = []
        for month in range(1, 13):
            group = [x for x in cycles if x['exit_time'].month == month]
            monthly.append(dict(month=f'2025-{month:02}', closed_cycles=len(group),
                                realized_net=sum((x['realized_net'] for x in group), ZERO),
                                fees_paid=sum((x['cycle_fees_paid'] for x in group), ZERO)))
        pd.DataFrame(monthly).to_csv(OUT / 'monthly.csv', index=False)
        winners = [x['realized_net'] for x in cycles if x['realized_net'] > 0]
        losers = [x['realized_net'] for x in cycles if x['realized_net'] < 0]
        price_pnl = sum((x['reference_price_pnl'] for x in cycles), ZERO)
        impacts = sum((x['adverse_impact'] for x in cycles), ZERO)
        recognized_fees = sum((x['recognized_fee'] for x in cycles), ZERO)
        close(price_pnl - impacts - recognized_fees, total_realized)
        close(total_fees - recognized_fees, sum((x['fee'] for x in states.values()), ZERO))
        grouped = {s: dict(cycles=sum(x['symbol'] == s for x in cycles),
                           realized_net=sum((x['realized_net'] for x in cycles if x['symbol'] == s), ZERO),
                           selected_signal_stats=stats(selected[selected.symbol == s])) for s in config['symbols']}
        largest_win = max(cycles, key=lambda x: x['realized_net'])
        largest_loss = min(cycles, key=lambda x: x['realized_net'])
        diagnostic = dict(source_experiment_id='EXP-049', cycles=len(cycles), fills=len(fills),
                          net_account_gain=final_equity - Decimal(config['initial_cash']),
                          realized_net=total_realized, residual_unrealized=residual_unrealized,
                          reference_price_pnl=price_pnl, recognized_fees=recognized_fees,
                          fees_paid=total_fees, adverse_impact=impacts,
                          buy_fees_remaining_in_residual_cost=total_fees - recognized_fees,
                          mean_hourly_open_exposure=mean_exposure,
                          duration_hours=cycle_frame.duration_hours.describe().to_dict(),
                          duration_counts=cycle_frame.duration_hours.value_counts().to_dict(),
                          winning_cycles=len(winners), losing_cycles=len(losers),
                          win_fraction=len(winners) / len(cycles),
                          mean_realized_net=total_realized / len(cycles),
                          median_realized_net=float(pd.Series([float(x['realized_net']) for x in cycles]).median()),
                          profit_factor=sum(winners, ZERO) / -sum(losers, ZERO),
                          largest_win=largest_win, largest_loss=largest_loss,
                          realized_net_excluding_largest_win=total_realized - largest_win['realized_net'],
                          base_breakeven_gross_4h=breakeven, selected_signals=stats(selected),
                          all_signals=stats(labels), per_symbol=grouped,
                          exit_reasons=cycle_frame.exit_reason.value_counts().to_dict())
        write_json(OUT / 'summary.json', diagnostic)
        verification = dict(status='passed', input_artifact_hashes='all_match_frozen_manifest',
                            cash_and_holding_checks=len(fills), cycle_event_matches=len(consumed),
                            labels_probability_one_to_one=len(labels),
                            label_window_hours=4, label_end_max_utc=str(labels.label_end.max()),
                            base_gross_breakeven=str(breakeven),
                            cash_quantity_fees_realized_equity='matched_source_summary',
                            realized_cost_decomposition='matched_to_1e-18_USDT',
                            leftover_fee_basis='retained_and_reconciled',
                            mean_open_exposure='matched',
                            no_market_partitions_read=True, no_fit_or_backtest=True, no_test_read=True)
        write_json(OUT / 'verification.json', verification)

        text = ['# EXP-062：为什么收益低、交易少', '', '日期：2026-10-04（Asia/Shanghai）；所有交易时间UTC。', '',
                '这是对EXP-049既有2025产物的事后诊断，不是新回测、独立验证或模型训练。2025已被反复用于选择；未读取2026保留测试。', '',
                '## 结论', '',
                f'- 100 USDT在该验证年净赚{float(diagnostic["net_account_gain"]):.4f} USDT；33周期平均每月2.75次。平均持仓占净值{pct(mean_exposure)}，平均资金分布以现金为主；不是空仓时间占比。',
                f'- 实际持仓时长：{diagnostic["duration_counts"]}；退出原因：{diagnostic["exit_reasons"]}。持续持仓规则允许超过4小时，本次实际时长以记录为准。',
                f'- 高概率信号平均预测上涨概率{pct(selected.probability.mean())}，实际上涨比例{pct(selected.label.mean())}，扣base成本盈利比例{pct((selected.net_4h > 0).mean())}。33个样本不足以证明概率校准或长期优势。', '',
                '## 实际成交盈亏与成本', '',
                '| 项目 | USDT |', '| --- | ---: |',
                f'| 已卖出数量的开盘参考价盈亏 | {float(price_pnl):.6f} |',
                f'| 减：已分配不利成交影响 | {float(impacts):.6f} |',
                f'| 减：已实现部分双边手续费 | {float(recognized_fees):.6f} |',
                f'| 已实现净盈亏 | {float(total_realized):.6f} |',
                f'| 加：剩余尾差浮动盈亏 | {float(residual_unrealized):.6f} |',
                f'| 账户净利润 | {float(diagnostic["net_account_gain"]):.6f} |', '',
                f'实际支付手续费{float(total_fees):.6f} USDT，其中{float(total_fees - recognized_fees):.6f}仍分配在尾差成本中。上表不是零成本重跑：保留原数量、平均成本与尾差，不能声称取消成本后账户必然赚同样的毛利润。手续费已经在净盈亏中体现，不再重复扣减。', '',
                '## 各币与高阈值信号', '',
                '| 币 | 周期 | 已实现净盈亏USDT | 平均预测上涨概率 | 实际上涨比例 | 扣成本盈利比例 | 平均4h毛涨幅 | 平均4h净收益 |',
                '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for symbol, item in grouped.items():
            s = item['selected_signal_stats']
            text.append(f'| {symbol} | {item["cycles"]} | {float(item["realized_net"]):.4f} | {pct(s["mean_probability"])} | {pct(s["up_fraction"])} | {pct(s["profitable_after_cost_fraction"])} | {pct(s["mean_gross_4h"])} | {pct(s["mean_net_4h"])} |')
        text += ['', 'ETH贡献主要盈利，BTC与SOL抵消部分利润。每币仅24／5／4个样本，不能据此宣称ETH最优或直接删除其他币种。', '',
                 '## 利润集中与持仓观察', '',
                 f'- 净盈利周期{len(winners)}，净亏损周期{len(losers)}；平均每周期已实现净收益{float(total_realized / len(cycles)):.4f} USDT；盈利因子{float(diagnostic["profit_factor"]):.3f}。这些是事后样本描述。',
                 f'- 最大盈利周期：{largest_win["symbol"]}，{largest_win["entry_time"]}至{largest_win["exit_time"]}，净赚{float(largest_win["realized_net"]):.4f} USDT。最大亏损净亏{float(largest_loss["realized_net"]):.4f} USDT。',
                 f'- 剔除最大盈利周期的已实现净盈亏为{float(diagnostic["realized_net_excluding_largest_win"]):.4f} USDT。这里只算利润集中度，不是重跑账户，也不是预测下一年。',
                 '- 没有用更长持仓的未来价格寻找最好卖点；本轮不能证明提前退出损失了多少机会。后续预测期限／退出机制需要另设实验。', '',
                 '## 训练目标与成本的差距', '',
                 '当前训练标签只要求未来4小时毛收益>0；模型概率不是预期净盈利，也不反映上涨／下跌的幅度。', '',
                 f'按base手续费0.10%、不利价偏0.05%（均为单边），独立定额买卖的净收益公式为 `(1+r)*(1-fee)^2*(1-adverse)/(1+adverse)-1`。4小时开盘毛涨幅需要超过{pct(breakeven)}才覆盖成本；精确阈值{breakeven}。该公式未处理账户仓位、数量取整、尾差或资金竞争，不能代替真实成交账本。', '',
                 f'全部{len(labels)}个有效信号中，方向上涨比例{pct(labels.label.mean())}，扣成本盈利比例{pct((labels.net_4h > 0).mean())}；“上涨但不覆盖成本”的信号有{int(((labels.label_return > 0) & (labels.net_4h <= 0)).sum())}个。', '',
                 '固定概率分组仅用于描述，未据此重新挑阈值：', '',
                 '| 概率组 | 信号数 | 平均预测概率 | 实际上涨比例 | 扣成本盈利比例 | 平均4h净收益 |',
                 '| --- | ---: | ---: | ---: | ---: | ---: |']
        for item in signal_stats:
            if item['symbol'] == 'ALL' and item['group'] not in ['ALL', '>=0.64']:
                text.append(f'| {item["group"]} | {item["count"]} | {pct(item["mean_probability"])} | {pct(item["up_fraction"])} | {pct(item["profitable_after_cost_fraction"])} | {pct(item["mean_net_4h"])} |')
        text += ['', '## 下一研究建议与限制', '',
                 '优先把“预测上涨”改为明确考虑成本与盈亏幅度的研究目标；可先比较简单的成本感知分类标签与现有模型。是否改用收益回归、预测期限或退出规则需另写方案，每次只改一个关键因素。调整标签并不保证提高收益，也不保证增加交易。', '',
                 '新研究应先固定有限候选、收益／回撤评价标准与按时间训练的多窗口验证方法；2025只作为已查看研究区间，不能再次称独立盲测。继续保留2026作为最终一次评价，不通过扩大仓位或增加频次放大未证实优势。D-027候选仍作为比较基准，尚未被新策略替代。', '',
                 '本轮没有训练、重跑账户、改变资金风控或打开2026；没有证明稳定盈利。实际持有超过4h时，标签表现与交易表现可能不同；本次已逐周期匹配，详见CSV与summary。', '',
                 '## 复现与证据', '',
                 '命令：`.venv/Scripts/python.exe artifacts/experiments/EXP-062/diagnose.py`；原编号禁止覆盖，未来新分析需新登记编号。',
                 '输入冻结SHA、完整源manifest、脚本SHA、Python／pandas版本及输出SHA见[run_manifest](run_manifest.json)。',
                 '关键对账见[verification](verification.json)；逐周期见[cycles](cycles.csv)，信号分组见[signal_buckets](signal_buckets.csv)，逐成交参考价与账户核对见[fill_reconciliation](fill_reconciliation.csv)。', '']
        (OUT / 'report.md').write_text('\n'.join(text), encoding='utf-8')
        # Confirm original artifacts were not modified during the analysis.
        assert all(sha(SOURCE / name) == digest for name, digest in input_hashes.items())
        outputs = [p for p in OUT.iterdir() if p.is_file() and p.name != 'run_manifest.json']
        manifest.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(),
                        artifacts={p.name: sha(p) for p in outputs})
        write_json(OUT / 'run_manifest.json', manifest)
        print(json.dumps(diagnostic, ensure_ascii=False, default=str, indent=2))
    except Exception as exc:
        manifest.update(status='failed', ended_at_utc=datetime.now(timezone.utc).isoformat(), error=repr(exc))
        write_json(OUT / 'run_manifest.json', manifest)
        write_json(OUT / 'failure.json', dict(error=repr(exc)))
        raise


if __name__ == '__main__':
    run()
