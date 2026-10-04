"""Independent reconciliation against the existing Decimal portfolio implementation."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tomllib

import pandas as pd

from cryptoquant.trading.ledger import Portfolio

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / 'EXP-049'
assert not (OUT / 'independent_verification.json').exists(), 'Refuse to overwrite verification.'
manifest = json.loads((OUT / 'run_manifest.json').read_text(encoding='utf-8'))
assert manifest['status'] == 'complete'
for name, expected in manifest['artifacts'].items():
    assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == expected, name
for name, expected in manifest['inputs_sha256'].items():
    assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, name
config = tomllib.loads((SOURCE / 'config.toml').read_text(encoding='utf-8'))
original = json.loads((SOURCE / 'summary.json').read_text(encoding='utf-8'))
result = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
fee = Decimal(config['costs']['base']['fee'])
book = Portfolio(config['initial_cash'], config['symbols'])
cycles = pd.read_csv(OUT / 'cycles.csv', dtype=str)
actual = {}
for row in pd.read_csv(SOURCE / 'fills.csv', dtype=str).to_dict('records'):
    before = book.realized_pnl
    book.apply_fill(row['side'], row['symbol'], row['quantity'], row['price'], fee)
    assert abs(book.cash - Decimal(row['cash_after'])) < Decimal('1e-18')
    assert abs(book.positions[row['symbol']].quantity - Decimal(row['holding_after'])) < Decimal('1e-18')
    if row['side'] == 'SELL':
        actual[(row['symbol'], row['time'])] = book.realized_pnl - before
assert len(actual) == len(cycles) == 33
differences = []
for row in cycles.to_dict('records'):
    key = (row['symbol'], row['exit_time'])
    assert abs(actual[key] - Decimal(row['realized_net'])) < Decimal('1e-18')
    if (Decimal(row['net_4h']) > 0) != (actual[key] > 0):
        differences.append(dict(symbol=row['symbol'], entry_time=row['entry_time'],
                                ideal_net_4h=row['net_4h'], actual_realized_net=str(actual[key]),
                                carried_tail_quantity=row['carried_tail_quantity']))
assert sum(v > 0 for v in actual.values()) == result['winning_cycles'] == 17
assert abs(book.realized_pnl - Decimal(result['realized_net'])) < Decimal('1e-18')
assert book.fees_usdt == Decimal(original['fees_usdt'])
marks = {s: Decimal(original['per_symbol'][s]['residual_value']) / book.positions[s].quantity
         for s in config['symbols']}
assert abs(book.equity(marks) - Decimal(original['final_equity'])) < Decimal('1e-18')
labels = pd.read_csv(SOURCE / 'validation_labels.csv')
# An independent algebraic form of the round-trip cost conversion.
s = float(config['costs']['base']['adverse_price'])
f = float(fee)
independent_net = (1 + labels.label_return) / (1 + s) * (1 - f) * (1 - s) * (1 - f) - 1
selected = labels.probability >= .64
assert int((independent_net[selected] > 0).sum()) == 18
assert abs(float(independent_net[selected].mean()) - result['selected_signals']['mean_net_4h']) < 1e-14
cost_share = (Decimal(result['adverse_impact']) + Decimal(result['recognized_fees'])) / Decimal(result['reference_price_pnl'])
largest_share = Decimal(result['largest_win']['realized_net']) / book.realized_pnl
checks = dict(status='passed', method='replay recorded fills with existing Portfolio.apply_fill; no trading decisions',
              reconciled_fills=66, matched_cycles=33, actual_profitable_cycles=17,
              ideal_fixed_size_profitable_signals=18, tail_and_rounding_sign_difference=differences,
              source_and_diagnostic_frozen_hashes='matched', fees_cash_quantity_realized_final_equity='matched',
              realized_cost_share_of_reference_pnl=str(cost_share),
              largest_win_share_of_realized_net=str(largest_share),
              diagnostic_manifest_sha256=hashlib.sha256((OUT / 'run_manifest.json').read_bytes()).hexdigest(),
              verification_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              no_fit_or_new_strategy=True, no_market_partitions_or_test_read=True)
(OUT / 'independent_verification.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(checks, ensure_ascii=False, indent=2))
