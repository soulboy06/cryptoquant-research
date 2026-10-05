"""研究来源门禁：只操作临时实验副本，不触碰冻结实验。"""
import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from cryptoquant.data.archive import sha_file
from cryptoquant.models.research_config import load_research_config
from cryptoquant.models.research_data import load_research_samples, load_research_features
from cryptoquant.models.research_models import load_research_models

PROJECT = Path(__file__).resolve().parents[1]


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


@pytest.fixture
def research_copy(tmp_path):
    shutil.copytree(PROJECT / 'configs', tmp_path / 'configs')
    for exp_id in ['EXP-063', 'EXP-064']:
        source = PROJECT / 'artifacts/experiments' / exp_id
        dest = tmp_path / 'artifacts/experiments' / exp_id
        shutil.copytree(source, dest)
        child_name = 'prepared_manifest.json' if exp_id == 'EXP-063' else 'train_manifest.json'
        child = json.loads((dest / child_name).read_text('utf-8'))
        def relocate(value):
            if isinstance(value, dict):
                return {k: relocate(v) for k, v in value.items()}
            if isinstance(value, list):
                return [relocate(v) for v in value]
            if isinstance(value, str) and value.startswith(str(source)):
                return str(dest) + value[len(str(source)):]
            return value
        write(dest / child_name, relocate(child))
        run = json.loads((dest / 'run_manifest.json').read_text('utf-8'))
        run[child_name.replace('.json', '_sha256')] = sha_file(dest / child_name)
        write(dest / 'run_manifest.json', run)
    return tmp_path, load_research_config(tmp_path / 'configs/fifth_experiment.toml', tmp_path)


def resign(root, exp_id, child_name, child, changed=None):
    folder = root / 'artifacts/experiments' / exp_id
    if changed:
        child['artifacts'][changed] = sha_file(folder / changed)
    write(folder / child_name, child)
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    run[child_name.replace('.json', '_sha256')] = sha_file(folder / child_name)
    write(folder / 'run_manifest.json', run)


def test_research_sample_rejects_changed_bytes_before_read(research_copy, monkeypatch):
    root, _ = research_copy
    path = root / 'artifacts/experiments/EXP-063/samples/gross_direction_v1/BTCUSDT.parquet'
    frame = pd.read_parquet(path)
    frame.loc[0, 'return_1h'] += 0.1
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match='SHA'):
        load_research_samples(root, 'EXP-063', 'W1', 'gross_direction_v1', 'BTCUSDT')


def test_models_reject_environment_before_deserialization(research_copy, monkeypatch):
    root, cfg = research_copy
    folder = root / 'artifacts/experiments/EXP-064'
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    run['environment']['packages']['scikit-learn'] = '0.0.0'
    write(folder / 'run_manifest.json', run)
    monkeypatch.setattr('cryptoquant.models.research_models.joblib.load', lambda *a: pytest.fail('unverified joblib loaded'))
    with pytest.raises(ValueError, match='environment'):
        load_research_models(root, 'EXP-064', cfg)


@pytest.mark.parametrize('fault', ['future', 'label_end', 'duplicate', 'label', 'feature_order'])
def test_samples_reject_semantic_corruption_with_updated_hashes(research_copy, fault):
    root, _ = research_copy
    folder = root / 'artifacts/experiments/EXP-063'
    manifest = json.loads((folder / 'prepared_manifest.json').read_text('utf-8'))
    rel = 'samples/gross_direction_v1/BTCUSDT.parquet'
    path = folder / rel
    frame = pd.read_parquet(path)
    if fault == 'future':
        frame.loc[0, 'feature_available_time'] = frame.loc[0, 'decision_time'] + pd.Timedelta(1, unit='h')
    elif fault == 'label_end':
        frame.loc[0, 'label_end'] += pd.Timedelta(1, unit='h')
    elif fault == 'duplicate':
        frame.loc[1, 'decision_time'] = frame.loc[0, 'decision_time']
    elif fault == 'label':
        frame.loc[0, 'label'] = 1 - frame.loc[0, 'label']
    else:
        manifest['feature_names'].reverse()
    frame.to_parquet(path, index=False)
    manifest['samples']['gross_direction_v1']['BTCUSDT']['sha256'] = sha_file(path)
    resign(root, 'EXP-063', 'prepared_manifest.json', manifest, rel)
    with pytest.raises(ValueError):
        load_research_samples(root, 'EXP-063', 'W1', 'gross_direction_v1', 'BTCUSDT')


def test_existing_three_models_and_invalid_feature_rows_remain_loadable(research_copy):
    root, cfg = research_copy
    models, manifest = load_research_models(root, 'EXP-064', cfg)
    assert set(models) == {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}
    assert manifest['window'] == 'W1'
    features = load_research_features(root, 'EXP-063', 'BTCUSDT')
    assert (~features.feature_valid).any()


@pytest.mark.parametrize('fault', ['id', 'child_sha', 'source', 'escape', 'config', 'symbols', 'C', 'fit_end', 'card', 'probabilities'])
def test_model_rejects_wrong_provenance_before_joblib(research_copy, monkeypatch, fault):
    root, cfg = research_copy
    folder = root / 'artifacts/experiments/EXP-064'
    child = json.loads((folder / 'train_manifest.json').read_text('utf-8'))
    if fault == 'id':
        child['experiment_id'] = 'EXP-065'
    elif fault == 'child_sha':
        (folder / 'train_manifest.json').write_text('{}', encoding='utf-8')
    elif fault == 'source':
        (folder / 'source_snapshot/src/cryptoquant/__init__.py').write_text('changed', encoding='utf-8')
    elif fault == 'escape':
        child['symbols']['BTCUSDT']['model_path'] = str(PROJECT / 'artifacts/experiments/EXP-064/models/BTCUSDT.joblib')
    elif fault == 'config':
        child['research_config_hash'] = '0' * 64
    elif fault == 'symbols':
        child['symbols']['OTHER'] = child['symbols']['BTCUSDT']
    elif fault == 'C':
        child['C'] = 1
    elif fault == 'fit_end':
        child['fit_end_utc'] = '2024-01-01T00:00:00+00:00'
    elif fault == 'card':
        child['label_card']['label_fee'] = '0.002'
    else:
        rel = 'training_probabilities/BTCUSDT.csv'
        probs = pd.read_csv(folder / rel)
        probs.loc[0, 'decision_time'] = '2026-01-01T00:00:00+00:00'
        probs.to_csv(folder / rel, index=False)
        child['symbols']['BTCUSDT']['probabilities_sha256'] = sha_file(folder / rel)
        child['artifacts'][rel] = sha_file(folder / rel)
    if fault not in {'child_sha', 'source'}:
        resign(root, 'EXP-064', 'train_manifest.json', child)
    monkeypatch.setattr('cryptoquant.models.research_models.joblib.load', lambda *a: pytest.fail('unverified joblib loaded'))
    with pytest.raises(ValueError):
        load_research_models(root, 'EXP-064', cfg)


def test_missing_sample_sha_cannot_bypass_binding(research_copy):
    root, _ = research_copy
    folder = root / 'artifacts/experiments/EXP-063'
    child = json.loads((folder / 'prepared_manifest.json').read_text('utf-8'))
    del child['samples']['gross_direction_v1']['BTCUSDT']['sha256']
    del child['artifacts']['samples/gross_direction_v1/BTCUSDT.parquet']
    resign(root, 'EXP-063', 'prepared_manifest.json', child)
    with pytest.raises(ValueError, match='SHA'):
        load_research_samples(root, 'EXP-063', 'W1', 'gross_direction_v1', 'BTCUSDT')


def test_report_exception_still_rejects_artifact_escape(tmp_path):
    from cryptoquant.models.research_integrity import verify_completed_experiment
    folder = tmp_path / 'artifacts/experiments/EXP-114'
    folder.mkdir(parents=True)
    (folder / 'report.md').write_text('report', encoding='utf-8')
    run = dict(experiment_id='EXP-114', type='ablation_selection_and_freeze', status='complete',
               artifacts={'report.md': sha_file(folder / 'report.md')})
    write(folder / 'run_manifest.json', run)
    assert verify_completed_experiment(tmp_path, 'EXP-114')[0] == folder
    run['artifacts']['../EXP-114/report.md'] = sha_file(folder / 'report.md')
    write(folder / 'run_manifest.json', run)
    with pytest.raises(ValueError, match='escape'):
        verify_completed_experiment(tmp_path, 'EXP-114')


def test_sixth_config_only_reuses_matching_net_training(research_copy):
    root, cfg = research_copy
    sixth = load_research_config(root / 'configs/sixth_experiment.toml', root)
    from cryptoquant.models.research_integrity import verify_prepared
    assert verify_prepared(root, 'EXP-063', sixth)[0]['execution_config_hash'] == cfg.execution_config_hash
    # Gross training is outside sixth policy scope even with identical fit signature.
    with pytest.raises(ValueError, match='policy'):
        load_research_models(root, 'EXP-064', sixth)


def test_new_prepare_reuses_truncated_funding_without_archive_read(research_copy, monkeypatch, tmp_path):
    from cryptoquant.models.research_data import create_funding_snapshots
    root, cfg = research_copy
    prepared = json.loads((root / 'artifacts/experiments/EXP-063/prepared_manifest.json').read_text('utf-8'))
    source_manifest = {'funding_data': {s: {'path': str(PROJECT / 'data/processed/funding_rate' / (s + '.parquet')),
                                          'sha256': meta['source_sha256']}
                                      for s, meta in prepared['funding_snapshot'].items()}}
    original = pd.read_parquet
    def guarded(path, *args, **kwargs):
        if 'funding_rate' in Path(path).parts:
            pytest.fail('sealed full funding archive read')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', guarded)
    frames, info = create_funding_snapshots(root, tmp_path / 'new-prepare', cfg, source_manifest)
    assert set(frames) == {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}
    assert all(x.funding_time.max() <= pd.Timestamp('2025-12-31T20:00:00+00:00') for x in frames.values())
    assert all(x['source_experiment_id'] == 'EXP-063' for x in info.values())


def test_prepared_rejects_rehashed_execution_cost_change(research_copy):
    from cryptoquant.models.research_integrity import verify_prepared
    root, _ = research_copy
    folder = root / 'artifacts/experiments/EXP-063'
    config = folder / 'config.toml'
    config.write_text(config.read_text('utf-8').replace('fee = "0.001"', 'fee = "0.003"'), encoding='utf-8')
    child = json.loads((folder / 'prepared_manifest.json').read_text('utf-8'))
    child['execution_config_hash'] = sha_file(config)
    child['artifacts']['config.toml'] = sha_file(config)
    resign(root, 'EXP-063', 'prepared_manifest.json', child)
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    run['execution_config_hash'] = sha_file(config)
    write(folder / 'run_manifest.json', run)
    with pytest.raises(ValueError, match='scope'):
        verify_prepared(root, 'EXP-063')


def test_empty_environment_does_not_satisfy_source_contract(research_copy):
    from cryptoquant.models.research_integrity import verify_completed_experiment
    root, _ = research_copy
    path = root / 'artifacts/experiments/EXP-063/run_manifest.json'
    run = json.loads(path.read_text('utf-8'))
    run['environment'] = {}
    write(path, run)
    with pytest.raises(ValueError, match='environment'):
        verify_completed_experiment(root, 'EXP-063')


def test_report_artifact_requires_digest(tmp_path):
    from cryptoquant.models.research_integrity import verify_completed_experiment
    folder = tmp_path / 'artifacts/experiments/EXP-114'
    folder.mkdir(parents=True)
    (folder / 'report.md').write_text('unbound', encoding='utf-8')
    write(folder / 'run_manifest.json', dict(experiment_id='EXP-114', type='ablation_selection_and_freeze',
                                           status='complete', artifacts={'report.md': None}))
    with pytest.raises(ValueError, match='SHA'):
        verify_completed_experiment(tmp_path, 'EXP-114')


def test_scaler_scale_must_match_verified_samples_even_with_consistent_predictions(research_copy):
    import joblib
    from cryptoquant.models.training import predict_probabilities
    root, cfg = research_copy
    folder = root / 'artifacts/experiments/EXP-064'
    child = json.loads((folder / 'train_manifest.json').read_text('utf-8'))
    model_path = folder / 'models/BTCUSDT.joblib'
    model = joblib.load(model_path)
    model.named_steps['scaler'].scale_ *= 2
    joblib.dump(model, model_path)
    card_path = folder / 'models/BTCUSDT.json'
    card = json.loads(card_path.read_text('utf-8'))
    card['scaler_scale'] = model.named_steps['scaler'].scale_.tolist()
    write(card_path, card)
    probability_path = folder / 'training_probabilities/BTCUSDT.csv'
    samples = load_research_samples(root, 'EXP-063', 'W1', 'gross_direction_v1', 'BTCUSDT')
    probs = pd.read_csv(probability_path)
    probs['probability'] = predict_probabilities(model, samples)
    probs.to_csv(probability_path, index=False)
    for kind, path in [('model', model_path), ('card', card_path), ('probabilities', probability_path)]:
        child['symbols']['BTCUSDT'][kind + '_sha256'] = sha_file(path)
        child['artifacts'][path.relative_to(folder).as_posix()] = sha_file(path)
    resign(root, 'EXP-064', 'train_manifest.json', child)
    with pytest.raises(ValueError, match='scaler'):
        load_research_models(root, 'EXP-064', cfg)


def test_new_sixth_training_binds_fifth_prepared_and_reloads_existing_net_models(research_copy, monkeypatch):
    root, _ = research_copy
    sixth = load_research_config(root / 'configs/sixth_experiment.toml', root)
    source = PROJECT / 'artifacts/experiments/EXP-065'
    folder = root / 'artifacts/experiments/EXP-997'
    shutil.copytree(source, folder)
    child = json.loads((folder / 'train_manifest.json').read_text('utf-8'))
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    child['experiment_id'] = run['experiment_id'] = 'EXP-997'
    child['prepared_manifest_sha256'] = sha_file(root / 'artifacts/experiments/EXP-063/prepared_manifest.json')
    (folder / 'research_config.toml').write_bytes(sixth.research_config_path.read_bytes())
    child['research_config_hash'] = run['research_config_hash'] = sixth.research_config_hash
    child['artifacts']['research_config.toml'] = sixth.research_config_hash
    for symbol, info in child['symbols'].items():
        for kind, relative in [('model', f'models/{symbol}.joblib'), ('card', f'models/{symbol}.json'),
                               ('probabilities', f'training_probabilities/{symbol}.csv'),
                               ('labels', f'training_labels/{symbol}.csv')]:
            info[kind + '_path'] = str(folder / relative)
    write(folder / 'run_manifest.json', run)
    resign(root, 'EXP-997', 'train_manifest.json', child)
    monkeypatch.setattr('cryptoquant.models.research_models.fit_model', lambda *a, **kw: pytest.fail('unexpected fit'))
    models, verified = load_research_models(root, 'EXP-997', sixth, expected_window='W1', expected_policy='net_positive_base_v1')
    assert set(models) == {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}
    assert verified['research_config_hash'] == sixth.research_config_hash
    assert verified['verified_source']['prepared_research_config_hash'] != sixth.research_config_hash
    assert verified['verified_source']['prepared_binding'] == 'sha256'
    assert verified['verified_source']['prepared_training_compatibility'] == 'fifth_to_sixth_training_signature'


def test_legacy_report_marks_missing_source_evidence_without_rewriting(tmp_path):
    from cryptoquant.models.research_integrity import verify_completed_experiment
    source = PROJECT / 'artifacts/experiments/EXP-114'
    folder = tmp_path / 'artifacts/experiments/EXP-114'
    folder.mkdir(parents=True)
    for name in ['run_manifest.json', 'report.md', 'evaluation.json']:
        shutil.copyfile(source / name, folder / name)
    original = (folder / 'run_manifest.json').read_bytes()
    _, verified = verify_completed_experiment(tmp_path, 'EXP-114')
    assert verified['verified_source']['mode'] == 'legacy_report_artifacts_only'
    assert verified['verified_source']['missing_evidence'] == ['source_snapshot', 'environment']
    assert (folder / 'run_manifest.json').read_bytes() == original


def test_sixth_prepare_generates_both_policies_from_synthetic_samples(research_copy, tmp_path):
    from cryptoquant.models.research_data import generate_policy_samples
    from cryptoquant.models.features import ALL_FEATURE_NAMES
    from cryptoquant.models.labels import LABEL_POLICIES
    root, _ = research_copy
    sixth = load_research_config(root / 'configs/sixth_experiment.toml', root)
    decision = pd.Timestamp('2022-01-01T00:00:00+00:00')
    end = decision + pd.Timedelta(4, unit='h')
    frames, samples = {}, {}
    for symbol in sixth.execution_config.symbols:
        frames[symbol] = pd.DataFrame([{'open_time': decision, 'open': '100'}, {'open_time': end, 'open': '101'}])
        row = dict(symbol=symbol, feature_open_time=decision - pd.Timedelta(1, unit='h'),
                   decision_time=decision, feature_available_time=decision, source_id='synthetic',
                   history_count=744, label_end=end, label=1)
        row.update({name: 0.0 for name in ALL_FEATURE_NAMES})
        samples[symbol] = pd.DataFrame([row])
    generated, metadata = generate_policy_samples(frames, samples, sixth, tmp_path / 'synthetic-prepare')
    assert set(generated) == set(LABEL_POLICIES)
    assert set(metadata) == set(LABEL_POLICIES)
    assert all(set(by_symbol) == set(sixth.execution_config.symbols) for by_symbol in generated.values())


@pytest.mark.parametrize('reason', ['unexpected_reason', 'insufficient_history', 'halt'])
def test_valid_feature_cannot_be_silently_disabled_by_rehashed_reason(research_copy, reason):
    root, _ = research_copy
    folder = root / 'artifacts/experiments/EXP-063'
    relative = 'features/BTCUSDT.parquet'
    path = folder / relative
    frame = pd.read_parquet(path)
    index = frame.index[frame.feature_valid][0]
    frame.loc[index, 'feature_valid'] = False
    frame.loc[index, 'invalid_reason'] = reason
    frame.to_parquet(path, index=False)
    child = json.loads((folder / 'prepared_manifest.json').read_text('utf-8'))
    child['features']['BTCUSDT']['sha256'] = sha_file(path)
    child['features']['BTCUSDT']['feature_valid_count'] -= 1
    resign(root, 'EXP-063', 'prepared_manifest.json', child, relative)
    with pytest.raises(ValueError, match='features'):
        load_research_features(root, 'EXP-063', 'BTCUSDT')


def test_feature_calendar_rejects_removed_non_decision_hour_with_rehashed_metadata(research_copy):
    root, _ = research_copy
    folder = root / 'artifacts/experiments/EXP-063'
    relative = 'features/BTCUSDT.parquet'
    path = folder / relative
    frame = pd.read_parquet(path)
    index = frame.index[frame.feature_valid & (frame.decision_time.dt.hour % 4 != 0)][0]
    frame = frame.drop(index).reset_index(drop=True)
    frame.to_parquet(path, index=False)
    child = json.loads((folder / 'prepared_manifest.json').read_text('utf-8'))
    child['features']['BTCUSDT']['sha256'] = sha_file(path)
    child['features']['BTCUSDT']['rows'] -= 1
    child['features']['BTCUSDT']['feature_valid_count'] -= 1
    resign(root, 'EXP-063', 'prepared_manifest.json', child, relative)
    with pytest.raises(ValueError, match='features'):
        load_research_features(root, 'EXP-063', 'BTCUSDT')
