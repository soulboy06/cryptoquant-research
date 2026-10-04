"""第五轮研究样本准备集成检查：来源SHA、政策样本、截断快照与重复ID拒绝。"""

import json
from pathlib import Path

import pandas as pd
import pytest

from cryptoquant.cli import main
from cryptoquant.data.archive import sha_file
from cryptoquant.models.research_config import load_research_config
from cryptoquant.models.research_data import (
    verify_sources, create_funding_snapshots, rebuild_and_verify_features,
    generate_policy_samples, load_research_samples, load_research_features,
    FUNDING_CUTOFF_UTC
)
from cryptoquant.models.labels import GROSS_POLICY, NET_POLICY


def test_research_prepare_pipeline_integration(tmp_path, monkeypatch):
    root = Path.cwd()
    research_cfg_path = root / 'configs/fifth_experiment.toml'
    cfg = load_research_config(research_cfg_path, root)
    
    # 1. Guard against reading validation or test partitions
    orig_read_parquet = pd.read_parquet
    def guarded_read_parquet(path, *args, **kwargs):
        parts = Path(path).parts
        if 'test' in parts:
            pytest.fail(f'Illegal read of sealed test partition: {path}')
        if 'validation' in parts and 'EXP-003' in parts:
            pytest.fail(f'Illegal read of validation partition during research prepare: {path}')
        return orig_read_parquet(path, *args, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', guarded_read_parquet)
    
    # 2. Run source verification
    frames, exp021_manifest, exp021_samples = verify_sources(root, 'EXP-003', 'EXP-021', cfg)
    assert set(frames) == {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}
    assert len(exp021_samples['BTCUSDT']) == 6387
    
    # 3. Test execution on a temporary experiment directory
    exp_dir = tmp_path / 'EXP-TEST-PREPARE'
    snaps, snap_meta = create_funding_snapshots(root, exp_dir, cfg, exp021_manifest)
    for sym, snap in snaps.items():
        assert snap.funding_time.max() <= FUNDING_CUTOFF_UTC
        assert (snap_meta[sym]['rows'] == len(snap))
        assert Path(snap_meta[sym]['snapshot_path']).exists()
    
    # 4. Features check & export
    feats, feats_meta = rebuild_and_verify_features(frames, snaps, exp021_samples, cfg, exp_dir)
    for sym, feat in feats.items():
        assert len(feat) == 27049
        assert Path(feats_meta[sym]['path']).exists()
    
    # 5. Policy samples generation
    policy_dfs, policy_meta = generate_policy_samples(frames, exp021_samples, cfg, exp_dir)
    assert set(policy_dfs) == {GROSS_POLICY, NET_POLICY}
    for sym in cfg.execution_config.symbols:
        gross_df = policy_dfs[GROSS_POLICY][sym]
        net_df = policy_dfs[NET_POLICY][sym]
        assert len(gross_df) == 6387
        assert len(net_df) == 6387
        assert (gross_df.decision_time == net_df.decision_time).all()
        # Gross label matches EXP-021
        assert (gross_df.label == exp021_samples[sym].label).all()
        # Net positive is strictly <= gross positive (costs filter out marginal wins)
        assert (net_df.label == 1).sum() < (gross_df.label == 1).sum()
        assert (net_df.label_net_return_text.notna()).all()
        assert (gross_df.label_net_return_text.isna()).all()


def test_research_prepare_cli_and_duplicate_rejection(tmp_path, monkeypatch):
    root = Path.cwd()
    exp_id = 'EXP-999'
    args = [
        'research-prepare',
        '--research-config', str(root / 'configs/fifth_experiment.toml'),
        '--experiment-id', exp_id,
        '--data-experiment-id', 'EXP-003',
        '--source-sample-experiment-id', 'EXP-021'
    ]
    
    target_dir = root / 'artifacts/experiments' / exp_id
    if target_dir.exists():
        import shutil
        shutil.rmtree(target_dir)
    
    target_dir.mkdir(parents=True)
    try:
        # Should return 1 due to refusal to overwrite
        assert main(args) == 1
    finally:
        if target_dir.exists():
            target_dir.rmdir()


def test_research_sources_sha_mismatch_rejection(tmp_path, monkeypatch):
    root = Path.cwd()
    cfg = load_research_config(root / 'configs/fifth_experiment.toml', root)
    
    orig_read_text = Path.read_text
    def bad_manifest_read(path_obj, *args, **kwargs):
        content = orig_read_text(path_obj, *args, **kwargs)
        if path_obj.name == 'sample_manifest.json':
            data = json.loads(content)
            data['symbols']['BTCUSDT']['samples_sha256'] = '0' * 64
            return json.dumps(data)
        return content
    monkeypatch.setattr(Path, 'read_text', bad_manifest_read)
    
    with pytest.raises(ValueError, match='SHA mismatch'):
        verify_sources(root, 'EXP-003', 'EXP-021', cfg)
