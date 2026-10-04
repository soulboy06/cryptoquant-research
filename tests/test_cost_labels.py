"""合成价格／产物检查：精确成本边界、语义隔离和固定研究范围。"""

from decimal import Decimal as D, localcontext
from importlib.util import find_spec
import json
from pathlib import Path

import pandas as pd
import pytest


def test_exact_cost_boundary_and_invalid_inputs():
    assert find_spec('cryptoquant.models.labels') is not None, 'precise label policies are not implemented'
    from cryptoquant.models.labels import label_values
    net, gross = 'net_positive_base_v1', 'gross_direction_v1'
    kwargs = dict(fee=D('.001'), adverse=D('.0005'))
    # Both finite products coincide exactly; nearby prices differ beyond the default context.
    entry, exit_price = D('.9975019995'), D('1.0005')
    with localcontext() as ctx:
        ctx.prec = 120
        prices = [exit_price - D('1e-80'), exit_price, exit_price + D('1e-80')]
        for price, expected in zip(prices, [0, 0, 1]):
            result = label_values(entry, price, net, **kwargs)
            assert result['label'] == expected
            assert (D(result['label_net_return_text']) > 0) == bool(expected)
        assert D(label_values(entry, exit_price, net, **kwargs)['label_net_return_text']) == 0
        # Very large coefficients and exponents must not change the sign.
        for scale in [D('1e1000'), D('1e-1000')]:
            assert [label_values(entry * scale, p * scale, net, **kwargs)['label'] for p in prices] == [0, 0, 1]
    assert label_values('100', '100.1', gross) == dict(label_return=.001, label_net_return_text=None, label=1)
    assert label_values('100', '100.1', net, **kwargs)['label'] == 0
    assert label_values('100', '99', net, **kwargs)['label'] == 0
    for entry_price, policy, costs in [('NaN', net, kwargs), ('Infinity', gross, {}), ('0', gross, {}),
                                       ('-1', net, kwargs), ('1', 'unknown', {}), ('1', net, {}),
                                       ('1', net, dict(fee='.002', adverse='.0005')),
                                       ('1', net, dict(fee='.001', adverse='NaN')),
                                       ('1', gross, kwargs)]:
        with pytest.raises(ValueError):
            label_values(entry_price, '2', policy, **costs)


def test_label_metadata_legacy_loaders_and_separate_answers(tmp_path):
    assert find_spec('cryptoquant.models.labels') is not None, 'label semantics are not implemented'
    from cryptoquant.models.labels import label_metadata, validate_label_metadata
    from cryptoquant.models.predictions import evaluation_labels, load_frozen_models
    from cryptoquant.models.training import load_training_samples
    from cryptoquant.config import load_config
    from test_model_training import CONFIG, sample_experiment
    gross, net = 'gross_direction_v1', 'net_positive_base_v1'
    for kind in ['training_samples', 'model_training']:
        assert validate_label_metadata(dict(type=kind)) == label_metadata(gross)
    for manifest in [dict(type='research_training'), dict(type='unknown', **label_metadata(gross)),
                     dict(type='model_training', label_policy='unknown'),
                     dict(type='model_training', **(label_metadata(gross) | dict(label_horizon_hours=8))),
                     dict(type='training_samples', **(label_metadata(gross) | dict(label_fee='.001')))]:
        with pytest.raises(ValueError):
            validate_label_metadata(manifest)
    net_card = label_metadata(net, fee='.001', adverse='.0005')
    assert validate_label_metadata(dict(type='research_training', **net_card)) == net_card
    with pytest.raises(ValueError):
        validate_label_metadata(dict(type='research_training', **net_card), expected_policy=gross)
    config = load_config(CONFIG)
    folder = sample_experiment(tmp_path)
    frames, provenance = load_training_samples(tmp_path, 'EXP-006', config)
    assert len(frames) == 3 and provenance['label_policy'] == gross
    path = folder / 'sample_manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    path.write_text(json.dumps(manifest | net_card), encoding='utf-8')
    with pytest.raises(ValueError, match='policy'):
        load_training_samples(tmp_path, 'EXP-006', config)
    model_folder = tmp_path / 'artifacts/experiments/EXP-007'
    model_folder.mkdir()
    (model_folder / 'train_manifest.json').write_text(json.dumps(dict(type='model_training', **net_card)), encoding='utf-8')
    with pytest.raises(ValueError, match='policy'):
        load_frozen_models(tmp_path, 'EXP-007', config)
    times = pd.date_range('2023-01-01', periods=5, freq='h', tz='UTC')
    quotes = pd.DataFrame(dict(open_time=times, open=['100', '100', '100', '100', '100.1'], market_state='observed'))
    probabilities = pd.DataFrame([dict(symbol='BTCUSDT', decision_time=times[0], probability=.8)])
    old = evaluation_labels({'BTCUSDT': quotes}, probabilities, times[-1])
    assert list(old.columns) == ['symbol', 'decision_time', 'probability', 'label_start', 'label_end', 'label_return', 'label']
    assert old.iloc[0].label == 1
    new = evaluation_labels({'BTCUSDT': quotes}, probabilities, times[-1], policy=net, fee='.001', adverse='.0005')
    assert new.iloc[0].label == 0 and D(new.iloc[0].label_net_return_text) < 0
    assert list(probabilities.columns) == ['symbol', 'decision_time', 'probability']


def test_research_config_fixed_budget_costs_and_paths(tmp_path):
    assert find_spec('cryptoquant.models.research_config') is not None, 'research configuration is not implemented'
    from cryptoquant.models.research_config import load_research_config, RESEARCH_WINDOWS
    from cryptoquant.data.archive import sha_file
    project = Path(__file__).resolve().parents[1]
    configs = tmp_path / 'configs'
    configs.mkdir()
    research_path = configs / 'fifth_experiment.toml'
    execution_path = configs / 'second_experiment.toml'
    research_text = (project / 'configs/fifth_experiment.toml').read_text('utf-8')
    execution_text = (project / 'configs/second_experiment.toml').read_text('utf-8')
    research_path.write_text(research_text, encoding='utf-8')
    execution_path.write_text(execution_text, encoding='utf-8')
    config = load_research_config(research_path, root=tmp_path)
    assert config.C == D('.1') and config.max_account_runs == 30
    assert config.thresholds == (D('.40'), D('.50'), D('.60'), D('.64'))
    assert config.research_config_hash == sha_file(research_path)
    assert config.execution_config_hash == sha_file(execution_path) == config.execution_config.config_hash
    assert RESEARCH_WINDOWS['W1'].fit_end.isoformat() == '2023-01-01T00:00:00+00:00'
    assert RESEARCH_WINDOWS['R2025'].end.isoformat() == '2025-12-31T20:00:00+00:00'
    for bad in [research_text + '\nunknown = 1\n', research_text.replace('max_account_runs = 30', 'max_account_runs = 31'),
                research_text.replace('"0.40"', '"0.41"'), research_text.replace('C = "0.1"', 'C = "1"'),
                research_text.replace('"second_experiment.toml"', '"../second_experiment.toml"')]:
        research_path.write_text(bad, encoding='utf-8')
        with pytest.raises(ValueError):
            load_research_config(research_path, root=tmp_path)
    research_path.write_text(research_text, encoding='utf-8')
    for bad in [execution_text.replace('initial_cash = "100"', 'initial_cash = "200"'),
                execution_text.replace('adverse_price = "0.0005"', 'adverse_price = "0.0006"'),
                execution_text.replace('feature_policy = "kline_and_funding"', 'feature_policy = "kline_only"'),
                execution_text.replace('feature_policy = "kline_and_funding"',
                                       'feature_policy = "kline_and_funding"\nmodel_family = "lightgbm"')]:
        execution_path.write_text(bad, encoding='utf-8')
        with pytest.raises(ValueError):
            load_research_config(research_path, root=tmp_path)
