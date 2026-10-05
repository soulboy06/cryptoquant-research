"""Execute only the pre-registered eleventh-round mechanism (R11); no fit or holdout.

Run after reading docs/eleventh-experiment-design-2026-10-05.md:
PYTHONPATH=src python scripts/run_eleventh_research.py --source-root D:/量化
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).parent))

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.io import load_period
from cryptoquant.baselines.windows import window_frames
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.leader_allocation import build_closed_momentum, build_leader_targets
from cryptoquant.models.regime_reporting import combined_weekly
from verify_cycle_repair import dump, reject_holdout, save_result

WINDOWS = ('W1', 'W2', 'R2025')
VARIANTS = ('R11',)
FROZEN = {
    'research_id': 'eleventh_pullback_recovery_v1',
    'phase_a_experiment': 'EXP-174',
    'parent_variant': 'R6',
    'parent_rule': 'repaired_R6_baseline',
    'variants': ['R11'],
    'windows': ['W1', 'W2', 'R2025'],
    'promotion_weight': '0.30',
    'neighbor_weight': '0.25',
    'probability_threshold': '0.50',
    'pullback_threshold': '0.0',
    'history_hours': 744,
    'max_base_accounts': 3,
    'max_pressure_accounts': 6,
    'max_records': 11,
    'dust_policy': 'retain_mark_to_market',
    'evaluation_data_status': 'repeatedly_viewed_research_development',
    'holdout_allowed': False,
}


def frozen_config(path):
    cfg = json.loads(Path(path).read_text('utf-8'))
    if cfg != FROZEN:
        raise ValueError('research parameters differ from frozen eleventh-round card')
    return cfg


def assert_budget(records, kind, cost=None):
    if len(records) >= 11:
        raise ValueError('11-record budget exhausted')
    if kind == 'eleventh_evaluation':
        limit = 3 if cost == 'base' else 6
        used = sum(r['type'] == kind and (r.get('cost') == 'base') == (cost == 'base') for r in records)
        if used >= limit:
            raise ValueError('account budget exhausted')


def repaired_baselines(root):
    folder = root / 'artifacts/experiments/EXP-174'
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    if run.get('status') != 'complete' or run.get('holdout_read') is not False:
        raise ValueError('Phase A acceptance required')
    path = folder / 'comparison.json'
    if sha_file(path) != run['comparison_sha256']:
        raise ValueError('Phase A comparison SHA mismatch')
    data = json.loads(path.read_text('utf-8'))
    if not data['phase_a_passed'] or len(data['rows']) != 15 or not all(r['legacy_fills_reproduced'] for r in data['rows']):
        raise ValueError('complete paired replay required before Phase B')
    baselines = defaultdict(dict)
    for row in data['rows']:
        baselines[row['variant']][row['window']] = dict(row['after'], status='complete')
    ranked = sorted(('R5', 'R6'), key=lambda v: (-combined_weekly(baselines[v]),
                 Decimal(baselines[v]['R2025']['max_drawdown']), v))
    if ranked[0] != 'R6':
        raise ValueError('frozen parent does not match repaired baseline selection')
    return dict(baselines)


def gate(rows, baselines, pressure=False):
    failed = []
    for window, row in rows.items():
        if row.get('status') != 'complete':
            failed.append(window + ':complete')
        if row['floor_triggers'] != 0:
            failed.append(window + ':floor=0')
        if row['closed_cycles'] < 30:
            failed.append(window + ':cycles>=30')
        if Decimal(str(row['max_drawdown'])) > Decimal('.25'):
            failed.append(window + ':MDD<=25%')
    if Decimal(str(rows['W1']['net_return'])) <= 0:
        failed.append('W1:return>0')
    if Decimal(str(rows['W2']['net_return'])) < Decimal('.15'):
        failed.append('W2:return>=15%')
    r25 = rows['R2025']
    if Decimal(str(r25['net_return'])) < Decimal(baselines['R6']['R2025']['net_return']):
        failed.append('R2025:return>=parent')
    g = combined_weekly(rows)
    if pressure:
        if g <= 0:
            failed.append('pressure:g_week>0')
    else:
        if Decimal(str(r25['net_return'])) <= Decimal(baselines['R0']['R2025']['net_return']):
            failed.append('R2025:return>R0')
        if Decimal(str(r25['max_drawdown'])) >= Decimal(baselines['R0']['R2025']['max_drawdown']):
            failed.append('R2025:MDD<R0')
        if Decimal(str(r25['max_drawdown'])) > Decimal(baselines['R6']['R2025']['max_drawdown']) + Decimal('.015'):
            failed.append('R2025:MDD<=parent+1.5pp')
        for reference in ('R0', 'R3', 'R6'):
            if g <= combined_weekly(baselines[reference]):
                failed.append('g_week>' + reference)
    return dict(eligible=not failed, failed_checks=failed, combined_g_week=str(g),
                profitable=bool(g > 0), weekly_target_achieved=bool(g >= Decimal('.015')),
                r2025_above_minus_five=Decimal(str(r25['net_return'])) > Decimal('-.05'))


def cycle_distributions(result, audit):
    lookup = {(r.decision_time, r.symbol): r for r in audit.itertuples(index=False)}
    closures = {(pd.Timestamp(e['time']), e['symbol']) for e in result.risk.events if e['event'] == 'cycle_closed'}
    active = {}
    closed = []
    from cryptoquant.trading.ledger import Portfolio
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    book = Portfolio(Decimal(100), symbols)
    fee_rate = Decimal('0.001')
    for fill in result.fills:
        s, t = fill['symbol'], pd.Timestamp(fill['time'])
        p_before = book.realized_pnl
        qty = Decimal(str(fill['quantity']))
        px = Decimal(str(fill['price']))
        fee = Decimal(str(fill['fee_usdt']))
        book.apply_fill(fill['side'], s, qty, px, fee_rate)
        pnl_delta = book.realized_pnl - p_before
        if fill['side'] == 'BUY':
            if s not in active:
                tag = lookup[(t, s)]
                active[s] = dict(symbol=s, entry_time=t, alpha=tag.is_alpha_leader,
                                regime=tag.regime_state, cost=Decimal(0), proceeds=Decimal(0),
                                net_pnl=Decimal(0))
            active[s]['cost'] += Decimal(str(fill['notional']))
        else:
            if s not in active:
                raise ValueError('exit without a cycle entry')
            active[s]['proceeds'] += Decimal(str(fill['notional'])) - fee
            active[s]['net_pnl'] += pnl_delta
            if (t, s) in closures:
                cycle = active.pop(s)
                cycle.update(exit_time=t,
                             net_return=cycle['net_pnl'] / cycle['cost'] if cycle['cost'] else Decimal(0))
                closed.append(cycle)
    if len(closed) != result.risk.closed_cycles:
        raise ValueError('cycle lifecycle and risk counter mismatch')
    grouped = {}
    for group in ('alpha', 'ordinary', 'weak', 'favorable'):
        values = [float(c['net_return']) for c in closed if
                  (c['alpha'] if group == 'alpha' else not c['alpha'] if group == 'ordinary' else c['regime'] == group)]
        pnl = sum((c['net_pnl'] for c in closed if
                   (c['alpha'] if group == 'alpha' else not c['alpha'] if group == 'ordinary' else c['regime'] == group)), Decimal(0))
        grouped[group] = dict(cycles=len(values), win_rate=sum(v > 0 for v in values) / len(values) if values else None,
                              net_pnl=str(pnl), median_return=float(np.median(values)) if values else None,
                              p10_return=float(np.quantile(values, .1)) if values else None,
                              p90_return=float(np.quantile(values, .9)) if values else None)
    return closed, grouped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--research-config', type=Path, default=Path('configs/eleventh_experiment.json'))
    args = parser.parse_args()
    root = Path.cwd().resolve()
    source = args.source_root.resolve()
    frozen_config(args.research_config)
    baselines = repaired_baselines(root)
    evidence = root / 'artifacts/experiments'
    records = []
    data_cache = {}
    inputs = {}
    outputs = {}
    selection = None
    cfg = load_config(root / 'artifacts/experiments/EXP-168/config.toml')
    config_sha = sha_file(args.research_config)
    source_sha = sha_file(root / 'src/cryptoquant/models/leader_allocation.py')

    with reject_holdout(source):
        for i, window in enumerate(WINDOWS):
            period = 'validation' if window == 'R2025' else 'development'
            if period not in data_cache:
                frames, rules, info = load_period(source, 'EXP-003', cfg, period)
                data_cache[period] = (frames, rules, info, build_closed_momentum(frames))
            frames, rules, info, momentum = data_cache[period]
            view = window_frames(frames, cfg, period, window)
            parent_path = evidence / f'EXP-{168+i}/targets.parquet'
            states_path = source / f'artifacts/experiments/EXP-122/state_{window}.parquet'
            parent = pd.read_parquet(parent_path)
            states = pd.read_parquet(states_path)
            sm = json.loads((source / 'artifacts/experiments/EXP-122/state_manifest.json').read_text('utf-8'))
            expected = sm['artifacts'][states_path.name]
            if expected != sha_file(states_path):
                raise ValueError('state SHA mismatch')
            parent_run = json.loads((evidence / f'EXP-{168+i}/run_manifest.json').read_text('utf-8'))
            if sha_file(parent_path) != parent_run['artifacts']['targets.parquet']:
                raise ValueError('repaired parent target SHA mismatch')
            inputs[window] = (view, rules, info, parent, states, momentum, period,
                              {str(parent_path): sha_file(parent_path), str(states_path): sha_file(states_path),
                               'state_manifest.json': sha_file(source / 'artifacts/experiments/EXP-122/state_manifest.json')})

        def start(exp_id, kind, **meta):
            assert_budget(records, kind, meta.get('cost'))
            out = evidence / exp_id
            out.mkdir(exist_ok=True)
            run = dict(experiment_id=exp_id, type=kind, status='running', environment=environment(),
                       started_at_utc=datetime.now(timezone.utc).isoformat(), research_config_sha256=config_sha,
                       allocation_source_sha256=source_sha, runner_sha256=sha_file(Path(__file__)),
                       phase_a_comparison_sha256=sha_file(evidence / 'EXP-174/comparison.json'),
                       holdout_read=False, parent_variant='R6', **meta)
            records.append(run)
            dump(out / 'run_manifest.json', run)
            (out / 'research_config.json').write_bytes(args.research_config.read_bytes())
            run['source_hash'] = snapshot_source(out, root / 'artifacts/experiments/EXP-168/config.toml')
            return out, run

        def finish(out, run, error=None):
            run.update(status='failed' if error else 'complete', finished_at_utc=datetime.now(timezone.utc).isoformat())
            if error:
                run['error'] = str(error)
            run['artifacts'] = {p.relative_to(out).as_posix(): sha_file(p) for p in out.rglob('*')
                               if p.is_file() and p.name != 'run_manifest.json' and 'source_snapshot' not in p.parts}
            dump(out / 'run_manifest.json', run)

        def evaluate(exp_id, variant, window, cost):
            out, run = start(exp_id, 'eleventh_evaluation', variant=variant, window=window, cost=cost)
            try:
                if cost != 'base':
                    if not selection or selection.get('selected_variant') != variant:
                        raise ValueError('pressure requires qualified frozen selection')
                    variant_gate = selection.get('variants', {}).get(variant)
                    if not isinstance(variant_gate, dict) or not variant_gate.get('eligible'):
                        raise ValueError('pressure requires qualified frozen selection')
                view, rules, info, parent, states, momentum, period, hashes = inputs[window]
                targets, audit = build_leader_targets(parent, states, momentum, variant)
                result = run_backtest(view, rules, cfg, 'logistic_regression', cost, period,
                                    decision_targets=targets, window=window, exit_variant='C2')
                summary = save_result(out / 'account', result, cfg)
                summary.update(status='complete', variant=variant, window=window, cost=cost, experiment_id=exp_id)
                summary['worst_annual_return'] = summary['net_return']
                dump(out / 'summary.json', summary)
                targets.to_parquet(out / 'targets.parquet', index=False)
                audit.to_csv(out / 'targets_audit.csv', index=False)
                cycles, distribution = cycle_distributions(result, audit)
                pd.DataFrame(cycles).to_csv(out / 'closed_cycles.csv', index=False)
                dump(out / 'cycle_distributions.json', distribution)
                summary['entry_state_distribution'] = distribution
                run.update(input_hashes=hashes, data_info=info, promoted_decisions=int(audit.promoted.sum()))
                finish(out, run)
                outputs[exp_id] = summary
                print(exp_id, variant, window, cost, 'net=', summary['net_return'], 'cycles=', summary['closed_cycles'], flush=True)
                return summary
            except Exception as exc:
                finish(out, run, exc)
                raise

        matrix = {}
        for vi, variant in enumerate(VARIANTS):
            matrix[variant] = {}
            for wi, window in enumerate(WINDOWS):
                matrix[variant][window] = evaluate(f'EXP-{194+vi*3+wi}', variant, window, 'base')

        out, run = start('EXP-197', 'eleventh_selection')
        variants = {v: gate(matrix[v], baselines) for v in VARIANTS}
        eligible = [v for v in VARIANTS if variants[v]['eligible']]
        winner = eligible[0] if eligible else None
        selection = dict(selected_variant=winner, eligible=winner is not None, variants=variants)
        dump(out / 'selection.json', selection)
        finish(out, run)
        print('EXP-197 eligible=', selection['eligible'], 'winner=', winner, flush=True)

        pressure = {}
        if winner:
            for ci, cost in enumerate(('higher_execution', 'strict')):
                pressure[cost] = {}
                for wi, window in enumerate(WINDOWS):
                    pressure[cost][window] = evaluate(f'EXP-{199+ci*3+wi}', winner, window, cost)

        out, run = start('EXP-198', 'eleventh_comparison')
        stability = {}
        if winner:
            for window in WINDOWS:
                view, rules, info, parent, states, momentum, period, hashes = inputs[window]
                neighbor, _ = build_leader_targets(parent, states, momentum, winner, promotion_weight=Decimal('.25'))
                pd.testing.assert_frame_equal(neighbor, parent)
                stability[window] = dict(targets_equal=True, reused_parent_experiment=f'EXP-{168+WINDOWS.index(window)}',
                                       parent_targets_sha256=hashes[next(iter(hashes))])

        comparison = dict(selection=selection, baselines=baselines, candidates=matrix,
                        pressure_results=pressure, pressure_gates={c: gate(rows, baselines, True) for c, rows in pressure.items()},
                        conditional_neighbor=stability, best_descriptive='R11',
                        final_candidate=None, holdout_read=False,
                        limitation='Repeatedly viewed development data; no independent OOS evidence. Explicit precision dust abandonment is conservative and materially affects results.')
        if winner and pressure and all(gate(rows, baselines, True)['eligible'] for rows in pressure.values()) and combined_weekly(baselines['R6']) > 0:
            comparison['final_candidate'] = winner
        dump(out / 'comparison.json', comparison)

        lines = ['# 第十一轮受控机制消融结果', '',
               '2023—2025均为已查看研究开发数据。2026测试未读取；仅复用已授权终点清算报价。',
               '父策略：修复后的R6。精度零头放弃损失单列，不冒充成交或Alpha。',
               '机制：唯一候选R11（Top-1真Alpha在24h回踩R24h<0时恢复30%）。', '',
               '| 策略 | W1收益／周期 | W2收益／周期 | 2025收益／回撤 | 合成周收益 | 基础资格 |',
               '| --- | --- | --- | --- | --- | --- |']
        for v, rows in {**{k: baselines[k] for k in ('R0', 'R3', 'R6')}, **matrix}.items():
            g = combined_weekly(rows)
            cells = [f"{Decimal(str(rows[w]['net_return']))*100:+.4f}%／{rows[w]['closed_cycles']}" for w in ('W1', 'W2')]
            cells.append(f"{Decimal(str(rows['R2025']['net_return']))*100:+.4f}%／{Decimal(str(rows['R2025']['max_drawdown']))*100:.2f}%")
            lines.append('| ' + v + ' | ' + ' | '.join(cells) + f" | {g*100:+.6f}% | " + ('合格' if v in variants and variants[v]['eligible'] else '失格' if v in variants else '研究对照') + ' |')
        lines += ['', f'基础筛选胜出：{winner}。',
                f"最终候选：{comparison['final_candidate']}。未达到每周1.5%长期目标。", '',
                '## 筛选失败与条件任务', '']
        for v in VARIANTS:
            lines.append('- ' + v + ': ' + (', '.join(variants[v]['failed_checks']) if variants[v]['failed_checks'] else '全部门槛通过'))
        lines += ['', '压力与邻域：' + ('仅运行合格胜出候选；详情见comparison.json。' if winner else '基础失格，压力测试跳过；条件25%邻域未启动，不追加候选。'), '',
                '## 归因与过拟合限制', '',
                '逐币净收益／费用／dust、按入场Alpha与ordinary及weak／favorable的闭合生命周期分布见每个summary.json、cycle_distributions.json与closed_cycles.csv。',
                'R11仅在weak状态且R24h<0时对Top-1真Alpha恢复30%仓位，其余情况严格保持父策略R6权重。',
                '未进行任何参数挖矿或网格优化，未调整概率阈值（0.50）或恢复权重（0.30）。',
                '2026测试集继续物理封存。面对失格实事求是接受，不随意修改参数进行曲线拟合。']
        (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        finish(out, run)
        print('EXP-198 report complete; final candidate=', comparison['final_candidate'], flush=True)


if __name__ == '__main__':
    main()
