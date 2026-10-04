"""每次回测新建独立实验；失败和源码冻结都保留。"""

from datetime import datetime, timezone
import sys

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.io import experiment_id, load_period
from cryptoquant.baselines.reporting import save_report
from cryptoquant.cli import write_json
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source


def execute(args, root):
    config = load_config(args.config)
    output = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if output.exists():
        raise ValueError('experiment directory already exists; refusing overwrite')
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(experiment_id=args.experiment_id, status='running', type='historical_baseline',
                    started_at_utc=datetime.now(timezone.utc).isoformat(), config_hash=config.config_hash,
                    strategy=args.strategy, period=args.period, cost=args.cost, data_experiment_id=args.data_experiment_id,
                    command=[sys.executable, '-m', 'cryptoquant', 'backtest', '--config', str(args.config.resolve()),
                             '--strategy', args.strategy, '--period', args.period, '--cost', args.cost,
                             '--data-experiment-id', args.data_experiment_id, '--experiment-id', args.experiment_id],
                    environment=environment())
    write_json(output / 'run_manifest.json', manifest)
    try:
        manifest['source_hash'] = snapshot_source(output, args.config)
        frames, rules, provenance = load_period(root, args.data_experiment_id, config, args.period)
        manifest['data'] = provenance
        write_json(output / 'run_manifest.json', manifest)
        result = run_backtest(frames, rules, config, args.strategy, args.cost, period=args.period)
        save_report(result, config, output, args.experiment_id)
        manifest.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(),
                        artifacts={p.name: sha_file(p) for p in output.iterdir() if p.is_file() and p.name != 'run_manifest.json'})
    except Exception as exc:
        manifest.update(status='failed', ended_at_utc=datetime.now(timezone.utc).isoformat(), error=str(exc))
        write_json(output / 'failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
        write_json(output / 'run_manifest.json', manifest)
        raise
    write_json(output / 'run_manifest.json', manifest)
    print(f'backtest complete: {args.experiment_id}; report: {output / "report.md"}')
    return 0
