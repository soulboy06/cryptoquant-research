"""只读development生成训练样本；尚不拟合或评价模型。"""

from datetime import datetime, timezone

import pandas as pd

from cryptoquant.baselines.io import experiment_id, load_development
from cryptoquant.cli import write_json
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.features import FEATURE_NAMES, ALL_FEATURE_NAMES, HOUR
from cryptoquant.models.samples import build_training_samples
from cryptoquant.models.labels import GROSS_POLICY, label_metadata


def execute(args, root):
    config = load_config(args.config)
    output = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if output.exists():
        raise ValueError('experiment directory already exists; refusing overwrite')
    output.mkdir(parents=True, exist_ok=False)
    feature_names = ALL_FEATURE_NAMES if config.feature_policy == 'kline_and_funding' else FEATURE_NAMES
    manifest = dict(experiment_id=args.experiment_id, type='training_samples', status='running',
                    started_at_utc=datetime.now(timezone.utc).isoformat(), config_hash=config.config_hash,
                    period='development', start_utc=config.development_start, label_end_before_utc=config.development_end,
                    feature_names=feature_names, feature_policy=config.feature_policy,
                    data_experiment_id=args.data_experiment_id, environment=environment(),
                    command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'build-samples', '--config', str(args.config.resolve()),
                             '--data-experiment-id', args.data_experiment_id, '--experiment-id', args.experiment_id], symbols={})
    manifest.update(label_metadata(GROSS_POLICY))
    write_json(output / 'sample_manifest.json', manifest)
    try:
        manifest['source_hash'] = snapshot_source(output, args.config)
        frames, _, provenance = load_development(root, args.data_experiment_id, config)
        manifest['data'] = provenance
        funding_dfs = {}
        if config.feature_policy == 'kline_and_funding':
            funding_dir = root / 'data/processed/funding_rate'
            manifest['funding_data'] = {}
            for symbol in config.symbols:
                funding_path = funding_dir / f'{symbol}.parquet'
                if not funding_path.exists():
                    raise ValueError(f'missing funding rate data for {symbol}')
                funding_dfs[symbol] = pd.read_parquet(funding_path)
                manifest['funding_data'][symbol] = dict(path=str(funding_path), sha256=sha_file(funding_path), rows=len(funding_dfs[symbol]))
        for name in ['training_samples', 'excluded_decisions']:
            (output / name).mkdir()
        for symbol in config.symbols:
            samples, excluded = build_training_samples(frames[symbol], config.development_start, config.development_end,
                                                       funding_df=funding_dfs.get(symbol))
            if samples.empty:
                raise ValueError(f'no valid training samples: {symbol}')
            # Limited run-time checks protect saved data, rather than re-audit
            # every archive or rerun the already verified trading account.
            if not ((samples.feature_available_time <= samples.decision_time).all() and
                    (samples.label_end < config.development_end).all() and
                    (samples.label_end - samples.label_start == 4 * HOUR).all()):
                raise ValueError('sample time invariant failed')
            sample_path = output / 'training_samples' / (symbol + '.parquet')
            excluded_path = output / 'excluded_decisions' / (symbol + '.parquet')
            samples.to_parquet(sample_path, index=False)
            excluded.to_parquet(excluded_path, index=False)
            manifest['symbols'][symbol] = dict(samples=len(samples), excluded=len(excluded),
                                               label_1=int(samples.label.sum()), label_0=int((samples.label == 0).sum()),
                                               first_decision_utc=samples.decision_time.min(), last_decision_utc=samples.decision_time.max(),
                                               last_label_end_utc=samples.label_end.max(), exclusion_reasons=excluded.reason.value_counts().to_dict(),
                                               samples_path=str(sample_path.resolve()), samples_sha256=sha_file(sample_path),
                                               excluded_path=str(excluded_path.resolve()), excluded_sha256=sha_file(excluded_path))
            write_json(output / 'sample_manifest.json', manifest)
        lines = ['# ' + args.experiment_id + ' 训练样本准备', '',
                 f'已生成三币development训练样本（特征策略：{config.feature_policy}，共{len(feature_names)}项特征），仅使用2022—2024决策时刻，2021-12只作历史预热。没有拟合模型、预测交易或计算收益。', '',
                 '| 交易对 | 有效样本 | 剔除决策 | 上涨／其余标签 | 最后答案时间UTC |', '| --- | --- | --- | --- | --- |']
        lines += [f'| {s} | {x["samples"]} | {x["excluded"]} | {x["label_1"]}／{x["label_0"]} | {x["last_label_end_utc"]} |' for s, x in manifest['symbols'].items()]
        lines += ['', f'{len(feature_names)}项特征仅使用已可获得历史；no_trade／halt后累计744连续观察重新预热。标签用真实五个日历小时窗口的入口／四小时后出口开盘，答案严格早于2025-01-01。无效或不足历史不填零，原始行情不改。', '',
                  '特征为浮点，标签方向按Decimal价格比较；未标准化，scaler在下一阶段只对训练样本拟合。标签是未扣成本的方向答案，类别比例不能证明策略盈利。', '',
                  '分币样本与剔除原因见对应Parquet，数量／时间／数据／源码SHA见sample_manifest.json。加载仅development；验证／保留测试未读取，费用和账本未修改，已有基准未重复运行。', '',
                  '下一步：训练三个币的逻辑回归，再实现验证期预测和共用交易接口。']
        (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        manifest.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(),
                        artifacts={p.relative_to(output).as_posix(): sha_file(p) for p in output.rglob('*')
                                   if p.is_file() and p.name != 'sample_manifest.json' and 'source_snapshot' not in p.parts})
    except Exception as exc:
        manifest.update(status='failed', ended_at_utc=datetime.now(timezone.utc).isoformat(), error=str(exc))
        write_json(output / 'failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
        write_json(output / 'sample_manifest.json', manifest)
        raise
    write_json(output / 'sample_manifest.json', manifest)
    print(f'training samples complete: {args.experiment_id}; report: {output / "report.md"}')
    return 0
