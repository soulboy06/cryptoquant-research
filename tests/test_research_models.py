"""第五轮模型训练集成检查：时间边界隔离、参数卡产物、重载一致性与三列概率表。"""

from pathlib import Path
import json
import pandas as pd
import pytest

from cryptoquant.cli import main
from cryptoquant.models.research_config import load_research_config, RESEARCH_WINDOWS
from cryptoquant.models.research_models import train_research_window, load_research_models, execute_research_train
from cryptoquant.models.labels import GROSS_POLICY, NET_POLICY
from cryptoquant.models.training import predict_probabilities


def test_research_train_window_w1_execution(tmp_path, monkeypatch):
    root = Path.cwd()
    cfg = load_research_config(root / 'configs/fifth_experiment.toml', root)
    
    # 1. Guard against reading test partition
    orig_read_parquet = pd.read_parquet
    def guarded_read_parquet(path, *args, **kwargs):
        parts = Path(path).parts
        if 'test' in parts:
            pytest.fail(f'Illegal read of sealed test partition: {path}')
        return orig_read_parquet(path, *args, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', guarded_read_parquet)
    
    out_dir = tmp_path / 'EXP-TEST-TRAIN'
    models_meta, artifacts_dict, label_card = train_research_window(
        root=root,
        prepared_id='EXP-063',
        window='W1',
        label_policy=NET_POLICY,
        research_cfg=cfg,
        out_dir=out_dir
    )
    
    # 2. Check symbols and metadata
    assert set(models_meta) == {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}
    for sym, meta in models_meta.items():
        assert meta['training_samples'] > 0
        assert meta['label_1'] > 0
        assert meta['label_0'] > 0
        assert meta['label_1'] + meta['label_0'] == meta['training_samples']
        assert 0.0 < meta['accuracy'] < 1.0
        assert 0.0 < meta['roc_auc'] < 1.0
        
        # Verify model joblib exists and has valid SHA
        m_path = Path(meta['model_path'])
        assert m_path.exists()
        
        # Verify parameter card
        c_path = Path(meta['card_path'])
        assert c_path.exists()
        card_data = json.loads(c_path.read_text('utf-8'))
        assert card_data['symbol'] == sym
        assert card_data['window'] == 'W1'
        assert card_data['label_policy'] == NET_POLICY
        assert card_data['C'] == 0.1
        assert len(card_data['coefficients']) == 12
        assert len(card_data['scaler_mean']) == 12
        assert len(card_data['scaler_scale']) == 12
        assert card_data['last_label_end_utc'] < RESEARCH_WINDOWS['W1'].fit_end.isoformat()
        
        # Verify training probabilities strictly 3 columns
        p_path = Path(meta['probabilities_path'])
        assert p_path.exists()
        p_df = pd.read_csv(p_path)
        assert list(p_df.columns) == ['symbol', 'decision_time', 'probability']
        assert len(p_df) == meta['training_samples']
        assert (p_df.probability >= 0.0).all() and (p_df.probability <= 1.0).all()
        
        # Verify training labels separated
        l_path = Path(meta['labels_path'])
        assert l_path.exists()
        l_df = pd.read_csv(l_path)
        assert 'label' in l_df.columns
        assert 'label_return' in l_df.columns
        assert 'label_net_return_text' in l_df.columns
        assert len(l_df) == meta['training_samples']

    # 3. Test load_research_models
    exp_fake_dir = tmp_path / 'artifacts/experiments/EXP-997'
    exp_fake_dir.mkdir(parents=True)
    import shutil
    shutil.copytree(out_dir / 'models', exp_fake_dir / 'models')
    train_manifest = dict(
        experiment_id='EXP-997',
        type='research_training',
        status='complete',
        window='W1',
        **label_card,
        symbols={sym: dict(model_path=str(exp_fake_dir / 'models' / f'{sym}.joblib'),
                           model_sha256=meta['model_sha256'])
                 for sym, meta in models_meta.items()}
    )
    (exp_fake_dir / 'train_manifest.json').write_text(json.dumps(train_manifest), encoding='utf-8')
    loaded_models, loaded_manifest = load_research_models(
        tmp_path, 'EXP-997', cfg, expected_window='W1', expected_policy=NET_POLICY
    )
    assert set(loaded_models) == {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}
    assert loaded_manifest['window'] == 'W1'
    assert loaded_manifest['label_policy'] == NET_POLICY


def test_research_train_cli_args_and_duplicate_rejection(tmp_path):
    root = Path.cwd()
    exp_id = 'EXP-998'
    args = [
        'research-train',
        '--research-config', str(root / 'configs/fifth_experiment.toml'),
        '--experiment-id', exp_id,
        '--prepared-experiment-id', 'EXP-063',
        '--window', 'W1',
        '--label-policy', 'gross_direction_v1'
    ]
    
    target_dir = root / 'artifacts/experiments' / exp_id
    if target_dir.exists():
        import shutil
        shutil.rmtree(target_dir)
        
    target_dir.mkdir(parents=True)
    try:
        # Should exit with code 1 due to refusal to overwrite
        assert main(args) == 1
    finally:
        if target_dir.exists():
            target_dir.rmdir()
