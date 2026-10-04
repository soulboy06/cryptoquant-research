"""第五轮研究样本准备、来源核验与资金费率快照。

核验 EXP-003 development 分区与 EXP-021 既有 12 特征样本。
读取资金费率后截断至 2025-12-31 20:00:00 UTC，重算 12 特征并核对 EXP-021 同时间一致性。
派生 gross_direction_v1 与 net_positive_base_v1 两种政策样本，不覆盖旧产物。
"""

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from cryptoquant.baselines.io import experiment_id, load_period
from cryptoquant.cli import write_json
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.features import build_features, ALL_FEATURE_NAMES
from cryptoquant.models.samples import METADATA
from cryptoquant.models.labels import (
    label_values, GROSS_POLICY, NET_POLICY, label_metadata, validate_label_metadata
)
from cryptoquant.models.research_config import (
    load_research_config, ResearchConfig, RESEARCH_WINDOWS
)

FUNDING_CUTOFF_UTC = pd.Timestamp('2025-12-31 20:00:00+00:00')


def verify_sources(root, data_id, sample_id, research_cfg):
    """核对 EXP-003 development 及 EXP-021 来源与样本 SHA，杜绝未来分区。"""
    root = Path(root).resolve()
    frames, rules, data_info = load_period(root, data_id, research_cfg.execution_config, 'development')
    
    exp_dir = root / 'artifacts/experiments' / experiment_id(sample_id)
    if not exp_dir.exists():
        raise ValueError(f'source sample experiment directory {sample_id} not found')
    manifest_path = exp_dir / 'sample_manifest.json'
    if not manifest_path.exists():
        raise ValueError(f'sample_manifest.json not found in {sample_id}')
    manifest = json.loads(manifest_path.read_text('utf-8'))
    
    if manifest.get('type') != 'training_samples' or manifest.get('status') != 'complete':
        raise ValueError('source sample experiment is not a completed training_samples experiment')
    if manifest.get('period') != 'development':
        raise ValueError('source sample experiment must be development period')
    if manifest.get('data', {}).get('data_experiment_id') != data_id:
        raise ValueError('source sample data experiment ID mismatch')
    if manifest.get('feature_policy') != 'kline_and_funding':
        raise ValueError('source sample feature policy must be kline_and_funding')
    if manifest.get('feature_names') != ALL_FEATURE_NAMES:
        raise ValueError('source sample feature names mismatch')
    
    samples_by_symbol = {}
    for symbol in research_cfg.execution_config.symbols:
        if symbol not in manifest.get('symbols', {}):
            raise ValueError(f'symbol {symbol} not in source sample manifest')
        sym_info = manifest['symbols'][symbol]
        sample_path = Path(sym_info['samples_path'])
        if not sample_path.is_absolute():
            sample_path = root / sample_path
        if not sample_path.exists():
            raise ValueError(f'source sample file {sample_path} not found')
        actual_sha = sha_file(sample_path)
        if actual_sha != sym_info['samples_sha256']:
            raise ValueError(f'source sample SHA mismatch for {symbol}')
        
        df = pd.read_parquet(sample_path)
        if (df.symbol != symbol).any():
            raise ValueError(f'symbol column mismatch in {symbol} samples')
        times = pd.DatetimeIndex(df.decision_time)
        if not times.is_unique or not times.is_monotonic_increasing:
            raise ValueError(f'non-unique or non-monotonic decision times for {symbol}')
        for col in ALL_FEATURE_NAMES:
            if col not in df.columns:
                raise ValueError(f'missing feature {col} in {symbol} samples')
        samples_by_symbol[symbol] = df
        
    return frames, manifest, samples_by_symbol


def create_funding_snapshots(root, exp_dir, research_cfg, exp021_manifest):
    """读取已校验资金费率并截断到 2025-12-31 20:00:00 UTC，保存不可变副本。"""
    root = Path(root).resolve()
    snapshot_dir = exp_dir / 'funding_snapshot'
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    snapshot_meta = {}
    
    for symbol in research_cfg.execution_config.symbols:
        src_info = exp021_manifest.get('funding_data', {}).get(symbol)
        if not src_info:
            raise ValueError(f'missing funding info for {symbol} in source manifest')
        src_path = Path(src_info['path'])
        if not src_path.is_absolute():
            src_path = root / src_path
        if not src_path.exists():
            raise ValueError(f'funding source file {src_path} not found')
        src_sha = sha_file(src_path)
        if src_sha != src_info['sha256']:
            raise ValueError(f'funding source SHA mismatch for {symbol}')
        
        full_df = pd.read_parquet(src_path)
        if (full_df.symbol != symbol).any():
            raise ValueError(f'symbol mismatch in funding source for {symbol}')
        times = pd.DatetimeIndex(full_df.funding_time)
        if times.tz is None or any(t.utcoffset().total_seconds() != 0 for t in times):
            raise ValueError(f'funding times for {symbol} must be UTC')
        if not times.is_unique or not times.is_monotonic_increasing:
            raise ValueError(f'non-unique or non-monotonic funding times for {symbol}')
        
        # Read after archive, truncated to 2025-12-31 20:00:00 UTC
        snap_df = full_df[full_df.funding_time <= FUNDING_CUTOFF_UTC].copy().reset_index(drop=True)
        if snap_df.empty or snap_df.funding_time.max() > FUNDING_CUTOFF_UTC:
            raise ValueError(f'funding snapshot cutoff violation for {symbol}')
        
        target_path = snapshot_dir / f'{symbol}.parquet'
        snap_df.to_parquet(target_path, index=False)
        snap_sha = sha_file(target_path)
        
        snapshots[symbol] = snap_df
        snapshot_meta[symbol] = dict(
            source_path=str(src_path),
            source_sha256=src_sha,
            snapshot_path=str(target_path),
            snapshot_sha256=snap_sha,
            rows=len(snap_df),
            min_funding_time_utc=snap_df.funding_time.min().isoformat(),
            max_funding_time_utc=snap_df.funding_time.max().isoformat(),
            note='read_archive_and_truncated_at_2025_12_31_20_00_utc'
        )
    return snapshots, snapshot_meta


def rebuild_and_verify_features(frames, funding_snapshots, exp021_samples, research_cfg, exp_dir):
    """从连续历史重算 12 特征，对照 EXP-021 一致性，并另存完整评价决策特征。"""
    features_dir = exp_dir / 'features'
    features_dir.mkdir(parents=True, exist_ok=True)
    all_features = {}
    features_meta = {}
    
    for symbol in research_cfg.execution_config.symbols:
        frame = frames[symbol]
        funding_df = funding_snapshots[symbol]
        feat = build_features(frame, funding_df=funding_df)
        
        sample_df = exp021_samples[symbol]
        merged = pd.merge(sample_df, feat, on=['symbol', 'decision_time'], suffixes=('_sample', '_rebuilt'))
        if len(merged) != len(sample_df):
            raise ValueError(f'feature matching count mismatch for {symbol}: {len(merged)} vs {len(sample_df)}')
        for col in ALL_FEATURE_NAMES:
            max_diff = np.abs(merged[f'{col}_sample'] - merged[f'{col}_rebuilt']).max()
            if max_diff >= 1e-10:
                raise ValueError(f'feature discrepancy in {col} for {symbol}: max diff {max_diff}')
        
        feat_path = features_dir / f'{symbol}.parquet'
        feat.to_parquet(feat_path, index=False)
        feat_sha = sha_file(feat_path)
        
        all_features[symbol] = feat
        features_meta[symbol] = dict(
            path=str(feat_path),
            sha256=feat_sha,
            rows=len(feat),
            feature_valid_count=int(feat.feature_valid.sum()),
            min_decision_utc=feat.decision_time.min().isoformat(),
            max_decision_utc=feat.decision_time.max().isoformat()
        )
    return all_features, features_meta


def generate_policy_samples(frames, exp021_samples, research_cfg, exp_dir):
    """以 EXP-021 同一批决策为基准，分别派生 gross 与 net 标签样本。"""
    samples_root = exp_dir / 'samples'
    policy_dfs = {}
    policy_meta = {}
    
    for policy in research_cfg.label_policies:
        p_dir = samples_root / policy
        p_dir.mkdir(parents=True, exist_ok=True)
        policy_dfs[policy] = {}
        policy_meta[policy] = {}
        
        card = label_metadata(
            policy,
            fee='0.001' if policy == NET_POLICY else None,
            adverse='0.0005' if policy == NET_POLICY else None
        )
        
        for symbol in research_cfg.execution_config.symbols:
            frame = frames[symbol]
            quotes = {row['open_time']: row for row in frame.to_dict('records')}
            sample_df = exp021_samples[symbol]
            
            rows = []
            for _, row in sample_df.iterrows():
                entry = row['decision_time']
                exit_time = row['label_end']
                entry_quote = quotes.get(entry)
                exit_quote = quotes.get(exit_time)
                if entry_quote is None or exit_quote is None:
                    raise ValueError(f'quote missing at {entry} or {exit_time} for {symbol}')
                entry_price = entry_quote['open']
                exit_price = exit_quote['open']
                
                vals = label_values(
                    entry_price, exit_price, policy,
                    fee=card['label_fee'], adverse=card['label_adverse_price']
                )
                
                if policy == GROSS_POLICY and vals['label'] != row['label']:
                    raise ValueError(f'gross label mismatch at {entry} for {symbol}')
                
                item = {col: row[col] for col in METADATA + ALL_FEATURE_NAMES}
                item.update(
                    label_start=entry,
                    label_end=exit_time,
                    label_return=vals['label_return'],
                    label_net_return_text=vals['label_net_return_text'],
                    label=vals['label']
                )
                rows.append(item)
            
            sample_columns = METADATA + ALL_FEATURE_NAMES + [
                'label_start', 'label_end', 'label_return', 'label_net_return_text', 'label'
            ]
            p_df = pd.DataFrame(rows)[sample_columns]
            p_path = p_dir / f'{symbol}.parquet'
            p_df.to_parquet(p_path, index=False)
            p_sha = sha_file(p_path)
            
            w1_mask = (p_df.decision_time >= '2022-01-01') & (p_df.label_end < '2023-01-01')
            w2_mask = (p_df.decision_time >= '2022-01-01') & (p_df.label_end < '2024-01-01')
            
            policy_dfs[policy][symbol] = p_df
            policy_meta[policy][symbol] = dict(
                path=str(p_path),
                sha256=p_sha,
                total_samples=len(p_df),
                label_1=int((p_df.label == 1).sum()),
                label_0=int((p_df.label == 0).sum()),
                w1_samples=int(w1_mask.sum()),
                w1_label_1=int((p_df.loc[w1_mask, 'label'] == 1).sum()),
                w2_samples=int(w2_mask.sum()),
                w2_label_1=int((p_df.loc[w2_mask, 'label'] == 1).sum())
            )
    return policy_dfs, policy_meta


def execute_research_prepare(args, root):
    """执行 Task 3 研究数据准备 CLI 入口。"""
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    out_dir = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if out_dir.exists():
        raise ValueError('experiment directory already exists; refusing overwrite')
    out_dir.mkdir(parents=True, exist_ok=False)
    
    start_time = datetime.now(timezone.utc).isoformat()
    manifest = dict(
        experiment_id=args.experiment_id,
        type='research_samples',
        status='running',
        started_at_utc=start_time,
        data_experiment_id=args.data_experiment_id,
        source_sample_experiment_id=args.source_sample_experiment_id,
        research_config_path=str(args.research_config),
        research_config_hash=cfg.research_config_hash,
        execution_config_hash=cfg.execution_config_hash,
        environment=environment(),
        command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'research-prepare',
                 '--research-config', str(args.research_config),
                 '--data-experiment-id', args.data_experiment_id,
                 '--source-sample-experiment-id', args.source_sample_experiment_id,
                 '--experiment-id', args.experiment_id]
    )
    write_json(out_dir / 'run_manifest.json', manifest)
    
    try:
        source_hash = snapshot_source(out_dir, cfg.research_config_path)
        manifest['source_hash'] = source_hash
        
        # 1. Verify sources
        frames, exp021_manifest, exp021_samples = verify_sources(
            root, args.data_experiment_id, args.source_sample_experiment_id, cfg
        )
        
        # 2. Funding snapshot
        funding_snaps, funding_meta = create_funding_snapshots(root, out_dir, cfg, exp021_manifest)
        
        # 3. Features check and export
        all_features, features_meta = rebuild_and_verify_features(
            frames, funding_snaps, exp021_samples, cfg, out_dir
        )
        
        # 4. Generate policy samples
        policy_dfs, policy_meta = generate_policy_samples(frames, exp021_samples, cfg, out_dir)
        
        # Save copies of configs
        (out_dir / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
        (out_dir / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        
        # Write prepared_manifest.json
        artifacts_dict = {
            'config.toml': sha_file(out_dir / 'config.toml'),
            'research_config.toml': sha_file(out_dir / 'research_config.toml'),
        }
        for s in cfg.execution_config.symbols:
            artifacts_dict[f'funding_snapshot/{s}.parquet'] = funding_meta[s]['snapshot_sha256']
            artifacts_dict[f'features/{s}.parquet'] = features_meta[s]['sha256']
            for p in cfg.label_policies:
                artifacts_dict[f'samples/{p}/{s}.parquet'] = policy_meta[p][s]['sha256']
        
        prepared_manifest = dict(
            experiment_id=args.experiment_id,
            type='research_samples',
            status='complete',
            started_at_utc=start_time,
            ended_at_utc=datetime.now(timezone.utc).isoformat(),
            data_experiment_id=args.data_experiment_id,
            source_sample_experiment_id=args.source_sample_experiment_id,
            execution_config_hash=cfg.execution_config_hash,
            research_config_hash=cfg.research_config_hash,
            feature_names=ALL_FEATURE_NAMES,
            label_policies={
                GROSS_POLICY: label_metadata(GROSS_POLICY),
                NET_POLICY: label_metadata(NET_POLICY, fee='0.001', adverse='0.0005')
            },
            funding_snapshot=funding_meta,
            features=features_meta,
            samples=policy_meta,
            artifacts=artifacts_dict
        )
        write_json(out_dir / 'prepared_manifest.json', prepared_manifest)
        
        # Write report.md
        report_content = generate_prepare_report(prepared_manifest, cfg)
        (out_dir / 'report.md').write_text(report_content, encoding='utf-8')
        artifacts_dict['report.md'] = sha_file(out_dir / 'report.md')
        prepared_manifest['artifacts'] = artifacts_dict
        write_json(out_dir / 'prepared_manifest.json', prepared_manifest)
        
        manifest['status'] = 'complete'
        manifest['ended_at_utc'] = prepared_manifest['ended_at_utc']
        manifest['prepared_manifest_sha256'] = sha_file(out_dir / 'prepared_manifest.json')
        write_json(out_dir / 'run_manifest.json', manifest)
        
        print(f"research-prepare complete: {args.experiment_id}")
        return 0
    except Exception as exc:
        manifest['status'] = 'failed'
        manifest['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['error'] = str(exc)
        write_json(out_dir / 'run_manifest.json', manifest)
        write_json(out_dir / 'failure.json', {
            'status': 'failed',
            'error_type': type(exc).__name__,
            'error': str(exc),
            'at_utc': datetime.now(timezone.utc).isoformat()
        })
        raise


def generate_prepare_report(manifest, cfg):
    lines = [
        f"# {manifest['experiment_id']}：第五轮研究样本准备与资金费率快照报告",
        "",
        "## 1. 目标与依据",
        "",
        "- 按照[第五轮方案](docs/superpowers/specs/2026-10-04-cost-aware-label-design.md)实施样本准备。",
        f"- 数据源：{manifest['data_experiment_id']}（development 分区）与 {manifest['source_sample_experiment_id']}（既有 12 特征样本）。",
        "- 绝不读取 validation 与 2026 test 分区；资金费率截断至 UTC 2025-12-31 20:00:00，无未来信息泄露。",
        "",
        "## 2. 资金费率快照信息",
        "",
        "| 币种 | 源行数 | 快照行数 | 最早时间 (UTC) | 最晚时间 (UTC) | 截断说明 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    for s, m in manifest['funding_snapshot'].items():
        lines.append(f"| {s} | {m['rows']} | {m['rows']} | {m['min_funding_time_utc']} | {m['max_funding_time_utc']} | 读取归档后截断至 2025-12-31 20:00 |")
    
    lines.extend([
        "",
        "## 3. 两种政策样本统计与分布对比",
        "",
        "| 币种 | 政策 | 总样本数 | 正样本数 (label=1) | 负样本数 (label=0) | 正样本率 | W1 样本 (2022) | W1 正样本 | W2 样本 (2022-2023) | W2 正样本 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ])
    for s in cfg.execution_config.symbols:
        for p in cfg.label_policies:
            meta = manifest['samples'][p][s]
            total = meta['total_samples']
            pos = meta['label_1']
            rate = f"{pos / total * 100:.2f}%" if total > 0 else "N/A"
            p_label = "gross (毛收益>0)" if p == GROSS_POLICY else "net (扣费盈利>0)"
            lines.append(f"| {s} | {p_label} | {total} | {pos} | {meta['label_0']} | {rate} | {meta['w1_samples']} | {meta['w1_label_1']} | {meta['w2_samples']} | {meta['w2_label_1']} |")
    
    lines.extend([
        "",
        "## 4. 特征核验结果",
        "",
        "- 12 项连续历史特征（9 项价格/均线 + 3 项资金费率）重新生成并与 EXP-021 相同决策点逐行比对，最大差异均小于 1e-10，完全一致。",
        "- 全量决策特征库（包含决策点所有状态，包括未满足 744h 连续历史点）已保存至 `features/{symbol}.parquet`，供后续受控窗口评价时直接截取，不重算历史均线。",
        "",
        "## 5. 限制与合规声明",
        "",
        "- 本实验仅准备研究样本，未拟合模型，未评价任何账户交易收益或周收益。",
        "- 2026 保留测试集继续处于严格封存状态，未被加载或读取。",
        ""
    ])
    return "\n".join(lines)


def load_research_samples(root, prepared_id, window, label_policy, symbol):
    """加载指定 window 和 label_policy 下用于训练的样本集。"""
    root = Path(root).resolve()
    exp_dir = root / 'artifacts/experiments' / experiment_id(prepared_id)
    sample_file = exp_dir / 'samples' / label_policy / f'{symbol}.parquet'
    if not sample_file.exists():
        raise ValueError(f'research sample file not found: {sample_file}')
    
    df = pd.read_parquet(sample_file)
    if window not in RESEARCH_WINDOWS:
        raise ValueError(f'unknown research window: {window}')
    win = RESEARCH_WINDOWS[window]
    
    # Filter training samples: decision_time >= fit_start and label_end < fit_end
    mask = (df.decision_time >= pd.Timestamp(win.fit_start)) & (df.label_end < pd.Timestamp(win.fit_end))
    filtered = df.loc[mask].copy().reset_index(drop=True)
    return filtered


def load_research_features(root, prepared_id, target):
    """加载指定 prepared_id 下决策特征集。若 target 为 str 则返回单个 DataFrame；若为 Config 则返回 (frames_dict, manifest)。"""
    root = Path(root).resolve()
    exp_dir = root / 'artifacts/experiments' / experiment_id(prepared_id)
    if isinstance(target, str):
        feature_file = exp_dir / 'features' / f'{target}.parquet'
        if not feature_file.exists():
            raise ValueError(f'research feature file not found: {feature_file}')
        return pd.read_parquet(feature_file)
    
    prep_manifest_path = exp_dir / 'prepared_manifest.json'
    if not prep_manifest_path.exists():
        raise ValueError(f'prepared manifest not found: {prep_manifest_path}')
    prep_manifest = json.loads(prep_manifest_path.read_text('utf-8'))
    
    symbols = target.execution_config.symbols if hasattr(target, 'execution_config') else target.symbols
    feature_frames = {}
    for s in symbols:
        feature_file = exp_dir / 'features' / f'{s}.parquet'
        if not feature_file.exists():
            raise ValueError(f'research feature file not found: {feature_file}')
        feature_frames[s] = pd.read_parquet(feature_file)
    return feature_frames, prep_manifest
