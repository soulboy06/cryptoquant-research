"""Attribution decomposition: State Machine Bug Fix vs Dust Policy Writeoff.

Evaluates three strictly comparable execution variants across frozen targets/data:
- Variant A: Legacy (pre-repair engine reproduced bit-for-bit in EXP-174)
- Variant B: Cycle Fix Only (state machine repair with retain_mark_to_market)
- Variant C: Cycle Fix + Current Dust Writeoff (PR #1 post_exit_sub_step_writeoff_v1)

Decomposes effects:
- Bug Fix Effect = Cycle Fix Only - Legacy
- Dust Policy Effect = Cycle Fix + Writeoff - Cycle Fix Only
- Total Effect = Cycle Fix + Writeoff - Legacy
"""

import json
from pathlib import Path
from decimal import Decimal
import pandas as pd

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.io import load_period
from cryptoquant.baselines.windows import window_frames
from cryptoquant.baselines.reporting import summarize
from cryptoquant.config import load_config
from cryptoquant.models.research_reporting import compute_weekly_statistics

MATRIX = {
    'R0': (108, 109, 110),
    'R5': (141, 142, 143),
    'R6': (144, 145, 146),
}
WINDOWS = ('W1', 'W2', 'R2025')


def get_legacy_and_writeoff_data(source_root):
    exp174_file = source_root / 'artifacts/experiments/EXP-174/comparison.json'
    with open(exp174_file, encoding='utf-8') as f:
        data = json.load(f)
    lookup = {}
    for r in data['rows']:
        lookup[(r['variant'], r['window'])] = {
            'legacy': r['before'],
            'writeoff': r['after'],
        }
    return lookup


def run_cycle_fix_only(source_root, variant, window):
    wi = WINDOWS.index(window)
    old_id = MATRIX[variant][wi]
    old = source_root / f'artifacts/experiments/EXP-{old_id:03d}'
    cfg = load_config(old / 'config.toml')
    period = 'validation' if window == 'R2025' else 'development'
    frames, rules, info = load_period(source_root, 'EXP-003', cfg, period)
    view = window_frames(frames, cfg, period, window)

    if variant == 'R0':
        prob_file = source_root / f'artifacts/experiments/EXP-{(141,142,143)[wi]}/probabilities.parquet'
        targets = pd.read_parquet(prob_file)
        targets['target_weight'] = [None if pd.isna(p) else cfg.weight_per_symbol if p >= .5 else Decimal('0') for p in targets.probability]
        targets = targets[['symbol', 'decision_time', 'probability', 'target_weight']]
    else:
        prob_file = old / 'targets.parquet'
        targets = pd.read_parquet(prob_file)

    kwargs = dict(strategy='logistic_regression', cost_name='base', period=period,
                  decision_targets=targets, window=window, exit_variant='C2',
                  dust_policy='retain_mark_to_market')
    result = run_backtest(view, rules, cfg, **kwargs)
    summary, annual = summarize(result, cfg)
    weekly = compute_weekly_statistics(result.equity, summary['start_utc'], summary['end_utc'])
    summary.update({k: v for k, v in weekly.items() if k != 'weekly_records'})

    # Extract dust retained stats
    retained = [e for e in result.risk.events if e['event'] == 'dust_retained']
    dust_val = sum((Decimal(str(e['value_usdt'])) for e in retained), Decimal('0'))
    dust_cost = sum((Decimal(str(e['cost_usdt'])) for e in retained), Decimal('0'))

    # Extract terminal residual asset value
    final_residual = sum(p.quantity * result.marks[s] for s, p in result.book.positions.items())

    return summary, result, {
        'dust_count': len(retained),
        'dust_mark_value': str(dust_val),
        'dust_cost_basis': str(dust_cost),
        'residual_asset_value': str(final_residual),
    }


def analyze_account(lookup, source_root, variant, window):
    rec = lookup[(variant, window)]
    legacy = rec['legacy']
    writeoff = rec['writeoff']

    cf_summary, cf_result, cf_dust = run_cycle_fix_only(source_root, variant, window)

    # Compile attribution metrics
    def extract_metrics(sum_dict, dust_info=None):
        m = {
            'net_return': Decimal(str(sum_dict['net_return'])),
            'final_equity': Decimal(str(sum_dict['final_equity'])),
            'max_drawdown': Decimal(str(sum_dict['max_drawdown'])),
            'closed_cycles': int(sum_dict['closed_cycles']),
            'fills': int(sum_dict['fills']),
            'fees_usdt': Decimal(str(sum_dict['fees_usdt'])),
            'realized_pnl': Decimal(str(sum_dict['realized_pnl'])),
        }
        if dust_info:
            m['dust_count'] = dust_info['dust_count']
            m['dust_mark_value'] = Decimal(dust_info['dust_mark_value'])
            m['dust_cost_basis'] = Decimal(dust_info['dust_cost_basis'])
            m['residual_asset_value'] = Decimal(dust_info['residual_asset_value'])
        else:
            m['dust_count'] = sum_dict.get('dust_writeoff_count', 0)
            m['dust_mark_value'] = Decimal(str(sum_dict.get('dust_writeoff_value', '0')))
            m['dust_cost_basis'] = Decimal(str(sum_dict.get('dust_writeoff_cost', '0')))
            # Residual in writeoff is essentially zero because dust was cleared
            m['residual_asset_value'] = Decimal(str(sum_dict.get('final_equity', '0'))) - Decimal(str(sum_dict.get('cash_at_end', sum_dict.get('final_equity', '0'))))
        return m

    m_legacy = extract_metrics(legacy)
    m_cf = extract_metrics(cf_summary, cf_dust)
    m_writeoff = extract_metrics(writeoff)

    # Effects
    bug_fix_effect = {k: m_cf[k] - m_legacy[k] for k in m_legacy if isinstance(m_legacy[k], Decimal)}
    dust_policy_effect = {k: m_writeoff[k] - m_cf[k] for k in m_cf if isinstance(m_cf[k], Decimal)}
    total_effect = {k: m_writeoff[k] - m_legacy[k] for k in m_legacy if isinstance(m_legacy[k], Decimal)}

    return {
        'variant': variant,
        'window': window,
        'metrics': {
            'Legacy': m_legacy,
            'Cycle Fix Only': m_cf,
            'Cycle Fix + Writeoff': m_writeoff,
        },
        'effects': {
            'Bug Fix Effect (CF - Legacy)': bug_fix_effect,
            'Dust Policy Effect (Writeoff - CF)': dust_policy_effect,
            'Total Effect (Writeoff - Legacy)': total_effect,
        }
    }


def main():
    root = Path('.').resolve()
    lookup = get_legacy_and_writeoff_data(root)

    print("================================================================================")
    print("PHASE 1: ATTRIBUTION FOR 3 PRIMARY REPRESENTATIVE ACCOUNTS (R0 W2, R6 W2, R6 R2025)")
    print("================================================================================\n")

    primary_accounts = [('R0', 'W2'), ('R6', 'W2'), ('R6', 'R2025')]
    primary_results = []
    for var, win in primary_accounts:
        res = analyze_account(lookup, root, var, win)
        primary_results.append(res)
        m = res['metrics']
        eff = res['effects']
        print(f"--- {var} {win} ---")
        print(f"{'Metric':<22} | {'Legacy':<14} | {'Cycle Fix Only':<16} | {'CF + Writeoff':<14} | {'Bug Fix Effect':<14} | {'Dust Policy Effect':<18}")
        print("-" * 110)
        for k in ['net_return', 'final_equity', 'max_drawdown', 'closed_cycles', 'fills', 'fees_usdt', 'realized_pnl', 'dust_mark_value', 'dust_cost_basis', 'residual_asset_value']:
            leg_val = f"{m['Legacy'][k]:.4%}" if 'return' in k or 'drawdown' in k else f"{m['Legacy'][k]}"
            cf_val = f"{m['Cycle Fix Only'][k]:.4%}" if 'return' in k or 'drawdown' in k else f"{m['Cycle Fix Only'][k]}"
            wo_val = f"{m['Cycle Fix + Writeoff'][k]:.4%}" if 'return' in k or 'drawdown' in k else f"{m['Cycle Fix + Writeoff'][k]}"
            bf_eff = f"{eff['Bug Fix Effect (CF - Legacy)'][k]:+.4%}" if 'return' in k or 'drawdown' in k else f"{eff['Bug Fix Effect (CF - Legacy)'][k]:+.4f}" if k in eff['Bug Fix Effect (CF - Legacy)'] else "-"
            dp_eff = f"{eff['Dust Policy Effect (Writeoff - CF)'][k]:+.4%}" if 'return' in k or 'drawdown' in k else f"{eff['Dust Policy Effect (Writeoff - CF)'][k]:+.4f}" if k in eff['Dust Policy Effect (Writeoff - CF)'] else "-"
            print(f"{k:<22} | {leg_val:<14} | {cf_val:<16} | {wo_val:<14} | {bf_eff:<14} | {dp_eff:<18}")
        print("\n")

    print("================================================================================")
    print("PHASE 2: EXTENDING TO ALL 9 ACCOUNTS (R0, R5, R6 across W1, W2, R2025)")
    print("================================================================================\n")

    all_accounts = [
        ('R0', 'W1'), ('R0', 'W2'), ('R0', 'R2025'),
        ('R5', 'W1'), ('R5', 'W2'), ('R5', 'R2025'),
        ('R6', 'W1'), ('R6', 'W2'), ('R6', 'R2025'),
    ]
    all_results = []
    for var, win in all_accounts:
        res = analyze_account(lookup, root, var, win)
        all_results.append(res)

    # Print summary comparative table
    print(f"{'Variant':<4} {'Win':<6} | {'Legacy Net':<11} {'CF Only Net':<12} {'Writeoff Net':<13} | {'BugFix Eff':<11} {'DustPolicy Eff':<15} | {'Dust Value':<10} {'Legacy Cyc':<10} {'CF Cyc':<7}")
    print("-" * 115)
    for res in all_results:
        var = res['variant']
        win = res['window']
        m = res['metrics']
        eff = res['effects']
        leg_net = f"{m['Legacy']['net_return']:+.2%}"
        cf_net = f"{m['Cycle Fix Only']['net_return']:+.2%}"
        wo_net = f"{m['Cycle Fix + Writeoff']['net_return']:+.2%}"
        bf_eff = f"{eff['Bug Fix Effect (CF - Legacy)']['net_return']:+.2%}"
        dp_eff = f"{eff['Dust Policy Effect (Writeoff - CF)']['net_return']:+.2%}"
        dust_val = f"{m['Cycle Fix + Writeoff']['dust_mark_value']:.2f}U"
        leg_cyc = m['Legacy']['closed_cycles']
        cf_cyc = m['Cycle Fix Only']['closed_cycles']
        print(f"{var:<4} {win:<6} | {leg_net:<11} {cf_net:<12} {wo_net:<13} | {bf_eff:<11} {dp_eff:<15} | {dust_val:<10} {leg_cyc:<10} {cf_cyc:<7}")

    # Save complete JSON
    out_file = root / 'artifacts/research/dust_and_bug_attribution.json'
    out_file.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for r in all_results:
        serializable.append({
            'variant': r['variant'],
            'window': r['window'],
            'metrics': {var: {k: str(v) for k, v in sub.items()} for var, sub in r['metrics'].items()},
            'effects': {eff_name: {k: str(v) for k, v in sub.items()} for eff_name, sub in r['effects'].items()},
        })
    out_file.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\nAttribution data saved to: {out_file}")


if __name__ == '__main__':
    main()
