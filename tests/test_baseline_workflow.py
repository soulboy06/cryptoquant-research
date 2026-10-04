import json
from pathlib import Path

import pytest

from cryptoquant.baselines.io import load_development
from cryptoquant.baselines.reporting import summarize
from cryptoquant.cli import main, write_json
from cryptoquant.data.archive import sha_file
from cryptoquant.data.calendar import policy_info
from cryptoquant.baselines.engine import run_backtest
from test_baseline_engine import fixture


def fake_data(root, frames, config):
    experiment = root / 'artifacts/experiments/EXP-001'
    experiment.mkdir(parents=True)
    manifest = experiment / 'manifest.json'
    write_json(manifest, {'data_policy': config.data_policy, 'data_policy_sha256': policy_info(config.data_policy)[1]})
    # Preserve original config, including dates; fixture dates are shortened in memory.
    source_config = experiment / 'config.toml'
    text = (Path(__file__).parents[1] / 'configs/first_experiment.toml').read_text('utf-8')
    text = text.replace('2025-01-01T00:00:00Z', config.development_end.isoformat().replace('+00:00', 'Z'))
    source_config.write_text(text, 'utf-8')
    frozen_hash = sha_file(source_config)
    write_json(manifest, {'config_hash': frozen_hash, 'data_policy': config.data_policy,
                          'data_policy_sha256': policy_info(config.data_policy)[1]})
    raw_rules = experiment / 'exchangeInfo.json'
    info = {'symbols': [{'symbol': s, 'status': 'TRADING', 'isSpotTradingAllowed': True,
                        'orderTypes': ['MARKET'], 'filters': [
                        {'filterType': 'LOT_SIZE', 'minQty': '.001', 'maxQty': '1000', 'stepSize': '.001'},
                        {'filterType': 'MIN_NOTIONAL', 'minNotional': '10', 'applyToMarket': True, 'avgPriceMins': 5}]} for s in config.symbols]}
    write_json(raw_rules, info)
    rules_report = experiment / 'rules_report.json'
    write_json(rules_report, {'status': 'passed', 'snapshot': str(raw_rules), 'sha256': sha_file(raw_rules)})
    parts = {}
    for s, frame in frames.items():
        path = root / 'data/processed/development/EXP-001' / (s + '.parquet')
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        parts[s] = {'path': str(path), 'sha256': sha_file(path)}
    quality = experiment / 'quality_report.json'
    write_json(quality, {'status': 'passed', 'config_hash': frozen_hash, 'data_manifest_sha256': sha_file(manifest),
                        'data_policy': config.data_policy, 'data_policy_sha256': policy_info(config.data_policy)[1],
                        'rules_sha256': sha_file(raw_rules), 'partitions': {'development': parts,
                        'validation': {'do_not_open': 'sealed'}, 'test': {'do_not_open': 'sealed'}}})
    write_json(experiment / 'step_state.json', {'type': 'data_check', 'config_hash': frozen_hash, 'steps': {
        'prepare': {'status': 'complete', 'result': {'manifest': str(manifest), 'manifest_sha256': sha_file(manifest)},
                    'attempts': [{'path': str(experiment)}]},
        'rules': {'status': 'complete', 'result': {'rules_report': str(rules_report), 'rules_sha256': sha_file(raw_rules)}},
        'check-data': {'status': 'complete', 'result': {'quality_report': str(quality), 'quality_report_sha256': sha_file(quality)}}}})
    return source_config


def test_loader_reads_only_development_and_rejects_tampering(tmp_path, monkeypatch):
    frames, _, config = fixture()
    fake_data(tmp_path, frames, config)
    import cryptoquant.baselines.io as io
    original = io.pd.read_parquet
    seen = []
    def checked(path):
        seen.append(str(path))
        assert 'development' in str(path)
        return original(path)
    monkeypatch.setattr(io.pd, 'read_parquet', checked)
    loaded, rules, provenance = load_development(tmp_path, 'EXP-001', config)
    assert len(seen) == 3 and set(loaded) == set(rules) == set(config.symbols)
    assert provenance['period'] == 'development'
    Path(provenance['partitions']['BTCUSDT']['path']).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='hash'):
        load_development(tmp_path, 'EXP-001', config)


def test_summary_accounts_for_fees_tail_drawdown_and_annual_returns():
    frames, rules, config = fixture()
    result = run_backtest(frames, rules, config, 'buy_hold', 'base')
    summary, annual = summarize(result, config)
    assert summary['final_equity'] == result.book.equity(result.marks)
    assert summary['final_equity'] == summary['final_cash'] + summary['residual_value']
    assert summary['net_return'] < 0 and summary['max_drawdown'] > 0
    assert summary['fees_usdt'] == sum(x['fee_usdt'] for x in result.fills)
    assert summary['closed_cycles'] == 3 and summary['drawdown_unrecovered']
    assert annual[0]['end_equity'] == summary['final_equity']


def test_cli_offline_end_to_end_duplicate_id_and_failure_preservation(tmp_path, monkeypatch):
    frames, _, config = fixture()
    source_config = fake_data(tmp_path, frames, config)
    monkeypatch.chdir(tmp_path)
    import requests
    monkeypatch.setattr(requests, 'Session', lambda: pytest.fail('backtest attempted network'))
    command = ['backtest', '--config', str(source_config), '--data-experiment-id', 'EXP-001', '--experiment-id', 'EXP-002',
               '--strategy', 'buy_hold', '--period', 'development', '--cost', 'base']
    assert main(command) == 0
    output = tmp_path / 'artifacts/experiments/EXP-002'
    assert json.loads((output / 'run_manifest.json').read_text('utf-8'))['status'] == 'complete'
    for name in ['events.jsonl', 'signals.csv', 'orders.csv', 'fills.csv', 'equity.csv', 'annual.csv', 'summary.json', 'equity.png', 'report.md']:
        assert (output / name).exists()
    previous = sha_file(output / 'fills.csv')
    assert main(command) == 1 and sha_file(output / 'fills.csv') == previous
    command[command.index('EXP-002')] = 'EXP-003'
    command[command.index('EXP-001')] = 'EXP-999'
    assert main(command) == 1
    failed = tmp_path / 'artifacts/experiments/EXP-003'
    assert json.loads((failed / 'run_manifest.json').read_text('utf-8'))['status'] == 'failed'
    assert (failed / 'failure.json').exists()


@pytest.mark.parametrize('period', ['test'])
def test_cli_rejects_sealed_period(period):
    with pytest.raises(SystemExit):
        main(['backtest', '--config', 'x', '--experiment-id', 'EXP-001', '--strategy', 'buy_hold', '--period', period, '--cost', 'base'])
