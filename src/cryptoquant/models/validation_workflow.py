"""2025验证模拟，共用账本；同C预测可在本地批次中共享。"""

from datetime import datetime, timezone

import pandas as pd

from cryptoquant.baselines.engine import run_backtest, validate_frames
from cryptoquant.baselines.io import experiment_id, load_period
from cryptoquant.baselines.reporting import save_report
from cryptoquant.cli import write_json
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.predictions import load_frozen_models, build_probabilities, decision_targets, evaluation_labels, prediction_diagnostics
from cryptoquant.models.training import C_VALUES, THRESHOLDS
from cryptoquant.models.labels import GROSS_POLICY, label_metadata


def prepare_validation(root, data_id, training_id, config):
    frames, rules, data = load_period(root, data_id, config, 'validation')
    validate_frames(frames, config, 'validation')
    models, training = load_frozen_models(root, training_id, config)
    funding_dfs = None
    if config.feature_policy == 'kline_and_funding':
        funding_dir = root / 'data/processed/funding_rate'
        funding_dfs = {s: pd.read_parquet(funding_dir / f'{s}.parquet') for s in config.symbols}
    predictions, labels = {}, {}
    for C in C_VALUES:
        predictions[C] = build_probabilities(frames, models[C], config.validation_start, config.validation_end, funding_dfs=funding_dfs)
        labels[C] = evaluation_labels(frames, predictions[C], config.validation_end)
    return dict(config_hash=config.config_hash, data_id=data_id, training_id=training_id,
                frames=frames, rules=rules, data=data, training=training, predictions=predictions, labels=labels)


def execute(args, root, prepared=None):
    config = load_config(args.config)
    if args.C not in C_VALUES or args.threshold not in THRESHOLDS or args.cost not in config.costs:
        raise ValueError('candidate outside predefined validation grid')
    output = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if output.exists():
        raise ValueError('experiment directory already exists; refusing overwrite')
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(experiment_id=args.experiment_id, type='model_validation', status='running',
                    started_at_utc=datetime.now(timezone.utc).isoformat(), config_hash=config.config_hash,
                    strategy=config.model_family, period='validation', C=args.C, threshold=args.threshold, cost=args.cost,
                    start_utc=config.validation_start, end_utc=config.validation_end,
                    data_experiment_id=args.data_experiment_id, training_experiment_id=args.training_experiment_id,
                    environment=environment(), refitted=False,
                    command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'validate', '--config', str(args.config.resolve()),
                             '--data-experiment-id', args.data_experiment_id, '--training-experiment-id', args.training_experiment_id,
                             '--C', str(args.C), '--threshold', str(args.threshold), '--cost', args.cost, '--experiment-id', args.experiment_id])
    manifest.update(label_metadata(GROSS_POLICY))
    write_json(output / 'run_manifest.json', manifest)
    try:
        manifest['source_hash'] = snapshot_source(output, args.config)
        context = prepared or prepare_validation(root, args.data_experiment_id, args.training_experiment_id, config)
        if (context['config_hash'], context['data_id'], context['training_id']) != (config.config_hash, args.data_experiment_id, args.training_experiment_id):
            raise ValueError('prepared validation context mismatch')
        probabilities, labels = context['predictions'][args.C], context['labels'][args.C]
        targets = decision_targets(probabilities, args.threshold, config.weight_per_symbol)
        manifest.update(data=context['data'], training=context['training'], shared_prediction_C=args.C,
                        probability_rows=len(probabilities), invalid_probability_rows=int(probabilities.probability.isna().sum()))
        probabilities.to_csv(output / 'probabilities.csv', index=False)
        targets.to_csv(output / 'decision_targets.csv', index=False)
        labels.to_csv(output / 'validation_labels.csv', index=False)
        write_json(output / 'prediction_diagnostics.json', prediction_diagnostics(labels, config.symbols, args.threshold))
        write_json(output / 'run_manifest.json', manifest)
        result = run_backtest(context['frames'], context['rules'], config, 'logistic_regression', args.cost,
                              period='validation', decision_targets=targets)
        save_report(result, config, output, args.experiment_id)
        with (output / 'report.md').open('a', encoding='utf-8') as stream:
            stream.write(f'\n模型来源{args.training_experiment_id}，固定C={args.C:g}，阈值={args.threshold:g}；未重新fit。三个币使用同C，阈值共用冻结概率。概率指标见prediction_diagnostics.json，答案仅在验证期到期且五小时窗口可观察时计入，不参与交易目标。\n')
        manifest.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(),
                        artifacts={p.name: sha_file(p) for p in output.iterdir() if p.is_file() and p.name != 'run_manifest.json'})
    except Exception as exc:
        manifest.update(status='failed', ended_at_utc=datetime.now(timezone.utc).isoformat(), error=str(exc))
        write_json(output / 'failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
        write_json(output / 'run_manifest.json', manifest)
        raise
    write_json(output / 'run_manifest.json', manifest)
    print(f'validation complete: {args.experiment_id}; C={args.C:g}; threshold={args.threshold:g}; cost={args.cost}', flush=True)
    return 0
