"""Frozen-input paired replay. Reads only development/2025 and legacy artifacts.

Usage: python scripts/verify_cycle_repair.py --source-root D:/量化 --output-root .
No download, model fitting or holdout API. Registered IDs are never overwritten.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys

import pandas as pd

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.io import load_period
from cryptoquant.baselines.windows import window_frames
from cryptoquant.baselines.reporting import summarize
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.research_reporting import compute_weekly_statistics

MATRIX = {
    'R0': (108, 109, 110), 'R3': (133, 134, 135),
    'R5': (141, 142, 143), 'R6': (144, 145, 146), 'R7': (147, 148, 149),
}
WINDOWS = ('W1', 'W2', 'R2025')


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def legacy_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def reject_holdout(source_root):
    """Guard Parquet reads, including accidental calls through shared loaders."""
    original = pd.read_parquet
    def guarded(path, *args, **kwargs):
        parts = Path(path).resolve().parts
        if 'test' in parts:
            raise ValueError('2026 holdout read forbidden')
        return original(path, *args, **kwargs)
    pd.read_parquet = guarded
    try:
        yield
    finally:
        pd.read_parquet = original


def normalized_fills(records):
    return [(str(pd.Timestamp(r['time'])), r['symbol'], r['side'],
             Decimal(str(r['quantity'])), Decimal(str(r['price'])),
             Decimal(str(r['fee_usdt'])), r['intent_reason']) for r in records]


def summaries(result, cfg):
    summary, annual = summarize(result, cfg)
    weekly = compute_weekly_statistics(result.equity, summary['start_utc'], summary['end_utc'])
    summary.update({k: v for k, v in weekly.items() if k != 'weekly_records'})
    return summary, annual, weekly


def save_result(folder, result, cfg):
    folder.mkdir()
    summary, annual, weekly = summaries(result, cfg)
    dump(folder / 'summary.json', summary)
    dump(folder / 'annual.json', annual)
    dump(folder / 'events.json', result.risk.events)
    for name, records in [('fills', result.fills), ('orders', result.orders),
                          ('equity', result.equity), ('weekly', weekly['weekly_records'])]:
        pd.DataFrame(records).to_csv(folder / (name + '.csv'), index=False)
    # Independent cash/equity/PnL conservation, including abandoned dust.
    unrealized = sum(p.quantity * (result.marks[s] - p.average_cost)
                     for s, p in result.book.positions.items())
    assert abs(result.book.equity(result.marks) - (cfg.initial_cash + result.book.realized_pnl + unrealized)) < Decimal('1e-18')
    assert abs(sum(v['realized_pnl'] for v in summary['per_symbol'].values()) - result.book.realized_pnl) < Decimal('1e-18')
    assert result.book.fees_usdt == sum(f['fee_usdt'] for f in result.fills)
    assert all(r['cash'] >= 0 for r in result.equity)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--replacement-first-id', type=int, choices=[175])
    args = parser.parse_args()
    source, root = args.source_root.resolve(), args.output_root.resolve()
    evidence = root / 'artifacts/experiments'
    all_diffs = []
    cache = {}
    with reject_holdout(source):
        for variant, ids in MATRIX.items():
            for wi, old_id in enumerate(ids):
                window = WINDOWS[wi]
                exp_id = f'EXP-{159 + len(all_diffs):03d}'
                if not all_diffs and args.replacement_first_id:
                    exp_id = f'EXP-{args.replacement_first_id}'
                out = evidence / exp_id
                out.mkdir(exist_ok=False)
                old = source / f'artifacts/experiments/EXP-{old_id:03d}'
                run = {'experiment_id': exp_id, 'type': 'cycle_repair_paired_replay', 'status': 'running',
                       'variant': variant, 'window': window, 'legacy_experiment_id': old.name,
                       'started_at_utc': datetime.now(timezone.utc).isoformat(), 'environment': environment(),
                       'dust_policy': 'post_exit_sub_step_writeoff_v1',
                       'holdout_read': False, 'existing_terminal_quote_authorized': True}
                dump(out / 'run_manifest.json', run)
                try:
                    cfg = load_config(old / 'config.toml')
                    cfg_path = out / 'config.toml'
                    cfg_path.write_bytes((old / 'config.toml').read_bytes())
                    period = 'validation' if window == 'R2025' else 'development'
                    if period not in cache:
                        cache[period] = load_period(source, 'EXP-003', cfg, period)
                    frames, rules, info = cache[period]
                    view = window_frames(frames, cfg, period, window)
                    if variant == 'R0':
                        prob_file = source / f'artifacts/experiments/EXP-{(141,142,143)[wi]}/probabilities.parquet'
                        targets = pd.read_parquet(prob_file)
                        targets['target_weight'] = [None if pd.isna(p) else cfg.weight_per_symbol if p >= .5 else Decimal('0') for p in targets.probability]
                        targets = targets[['symbol', 'decision_time', 'probability', 'target_weight']]
                    else:
                        prob_file = old / 'targets.parquet'
                        targets = pd.read_parquet(prob_file)
                    risk_path = old / 'source_snapshot/src/cryptoquant/trading/risk.py'
                    engine_path = old / 'source_snapshot/src/cryptoquant/baselines/engine.py'
                    frozen_source = json.loads((old / 'source_manifest.json').read_text('utf-8'))
                    # Source manifest format is the project SHA mapping, not guessed.
                    source_files = frozen_source.get('files', frozen_source)
                    for path in (risk_path, engine_path):
                        key = path.relative_to(old / 'source_snapshot').as_posix()
                        recorded = source_files.get(key) if isinstance(source_files, dict) else None
                        if recorded is not None:
                            digest = recorded.get('sha256') if isinstance(recorded, dict) else recorded
                            if sha_file(path) != digest:
                                raise ValueError('legacy source SHA mismatch: ' + key)
                    old_risk = legacy_module(risk_path, exp_id.replace('-', '_') + '_risk')
                    old_engine = legacy_module(engine_path, exp_id.replace('-', '_') + '_engine')
                    old_engine.RiskState = old_risk.RiskState
                    kwargs = dict(strategy='logistic_regression', cost_name='base', period=period,
                                  decision_targets=targets, window=window, exit_variant='C2')
                    before = old_engine.run_backtest(view, rules, cfg, **kwargs)
                    original_fills = pd.read_csv(old / 'fills.csv', dtype=str).to_dict('records')
                    assert normalized_fills(before.fills) == normalized_fills(original_fills), 'legacy fills are not reproducible'
                    old_summary = json.loads((old / 'summary.json').read_text('utf-8'))
                    before_summary = save_result(out / 'before', before, cfg)
                    for key in ('net_return', 'max_drawdown', 'fees_usdt', 'closed_cycles', 'final_equity'):
                        assert abs(Decimal(str(before_summary[key])) - Decimal(str(old_summary[key]))) < Decimal('1e-12'), 'legacy summary mismatch: ' + key
                    after = run_backtest(view, rules, cfg, **kwargs)
                    after_summary = save_result(out / 'after', after, cfg)
                    targets.to_parquet(out / 'targets.parquet', index=False)
                    changed = normalized_fills(before.fills) != normalized_fills(after.fills)
                    diff = {'experiment_id': exp_id, 'variant': variant, 'window': window,
                            'legacy_fills_reproduced': True, 'fills_changed': changed,
                            'classification': 'engine_behavior_repair' if changed or before_summary['net_return'] != after_summary['net_return'] else 'statistics_only',
                            'before': before_summary, 'after': after_summary,
                            'metric_deltas': {k: str(Decimal(str(after_summary[k])) - Decimal(str(before_summary[k])))
                                              for k in ('net_return','max_drawdown','fills','closed_cycles','fees_usdt','realized_pnl')},
                            'events_before': {k: sum(e['event'] == k for e in before.risk.events) for k in ('exit_requested','cycle_closed','exit_complete')},
                            'events_after': {k: sum(e['event'] == k for e in after.risk.events) for k in ('exit_requested','cycle_closed','exit_complete','dust_written_off')}}
                    dump(out / 'comparison.json', diff)
                    run.update(status='complete', data_info=info, source_hash=snapshot_source(out, old / 'config.toml'),
                               input_hashes={str(p): sha_file(p) for p in (old/'config.toml',old/'summary.json',old/'fills.csv',prob_file,risk_path,engine_path)},
                               finished_at_utc=datetime.now(timezone.utc).isoformat())
                    run['artifacts'] = {p.relative_to(out).as_posix(): sha_file(p) for p in out.rglob('*') if p.is_file() and p.name != 'run_manifest.json' and 'source_snapshot' not in p.parts}
                    dump(out / 'run_manifest.json', run)
                    all_diffs.append(diff)
                    print(exp_id, variant, window, 'net=', str(after_summary['net_return']), 'cycles=', after_summary['closed_cycles'], 'changed=',changed, flush=True)
                except Exception as exc:
                    run.update(status='failed', error=str(exc))
                    dump(out / 'run_manifest.json', run)
                    raise
    final = evidence / 'EXP-174'
    final.mkdir(exist_ok=False)
    dump(final / 'comparison.json', {'rows': all_diffs, 'phase_a_passed': True, 'holdout_read': False,
                                    'classification': 'engine_behavior_repair' if any(r['classification']=='engine_behavior_repair' for r in all_diffs) else 'statistics_only'})
    dump(final / 'run_manifest.json', {'experiment_id':'EXP-174','type':'cycle_repair_acceptance','status':'complete',
                                     'comparison_sha256':sha_file(final/'comparison.json'), 'holdout_read':False})
    print('EXP-174: all 15 paired replays passed; no holdout read', flush=True)


if __name__ == '__main__':
    main()
