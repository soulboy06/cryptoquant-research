"""公开数据流程入口；步骤状态与失败尝试都保留。"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def begin_step(root, experiment_id, step, config_hash, resume=False):
    if not re.fullmatch(r"EXP-[0-9]{3,}", experiment_id) or int(experiment_id[4:]) == 0:
        raise ValueError("invalid experiment ID")
    if step not in {"prepare", "rules", "check-data"}:
        raise ValueError("unknown data step")
    experiment = Path(root) / experiment_id
    state_path = experiment / "step_state.json"
    temporary_state = state_path.with_suffix(".json.tmp")
    if resume and temporary_state.exists():
        # Only adopt a complete state written for this exact experiment/config.
        # Interrupted/foreign JSON stays on disk and is never silently replaced.
        try:
            candidate = json.loads(temporary_state.read_text(encoding="utf-8"))
            valid = candidate.get("experiment_id") == experiment_id and candidate.get("config_hash") == config_hash and candidate.get("type") == "data_check" and isinstance(candidate.get("steps"), dict)
            for name, entry in candidate.get("steps", {}).items():
                valid = valid and name in {"prepare", "rules", "check-data"} and entry.get("status") in {"running", "complete", "failed"} and isinstance(entry.get("attempts"), list)
                for attempt in entry.get("attempts", []):
                    location = Path(attempt["path"]).resolve()
                    valid = valid and location.parent == (experiment / name).resolve() and re.fullmatch(r"attempt-[0-9]{3,}", location.name) is not None
            if not valid:
                raise ValueError("temporary state belongs to another experiment or config")
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            raise ValueError("incomplete temporary state; preserved for inspection") from exc
        os.replace(temporary_state, state_path)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("config_hash") != config_hash:
            raise ValueError("experiment config changed; register a new ID")
    else:
        if experiment.exists() and any(experiment.iterdir()):
            raise ValueError("refusing to overwrite unrecognized experiment directory")
        if step != "prepare":
            raise ValueError("prepare must complete first")
        state = {"experiment_id": experiment_id, "config_hash": config_hash, "type": "data_check", "steps": {}}
    dependencies = {"prepare": (), "rules": ("prepare",), "check-data": ("prepare", "rules")}
    if any(state["steps"].get(item, {}).get("status") != "complete" for item in dependencies[step]):
        raise ValueError("dependency step not complete")
    previous = state["steps"].get(step)
    if previous and previous["status"] == "complete":
        raise ValueError("step already completed; use new experiment ID")
    if previous and not resume:
        raise ValueError("interrupted/failed step requires --resume")
    attempts = previous["attempts"] if previous else []
    attempt_path = experiment / step / f"attempt-{len(attempts) + 1:03d}"
    attempts.append({"path": str(attempt_path.resolve()), "status": "running", "started_at": datetime.now(timezone.utc).isoformat()})
    state["steps"][step] = {"status": "running", "attempts": attempts}
    # Register the attempt before creating its folder. A crash after this write
    # remains a known running attempt and --resume allocates a fresh directory.
    write_json(state_path, state)
    attempt_path.mkdir(parents=True, exist_ok=False)
    return experiment, attempt_path


def finish_step(experiment, step, status, result):
    state_path = Path(experiment) / "step_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    current = state["steps"][step]
    if current["status"] != "running" or status not in {"complete", "failed"}:
        raise ValueError("invalid step transition")
    current.update(status=status, result=result)
    current["attempts"][-1].update(status=status, ended_at=datetime.now(timezone.utc).isoformat(), result=result)
    write_json(state_path, state)


def main(argv=None):
    parser = argparse.ArgumentParser(description="公开现货数据与离线研究（模拟模式）")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ["prepare", "rules", "check-data"]:
        sub = subcommands.add_parser(command)
        sub.add_argument("--config", type=Path, required=True)
        sub.add_argument("--experiment-id", required=True)
        sub.add_argument("--resume", action="store_true")
    backtest = subcommands.add_parser('backtest')
    backtest.add_argument('--config', type=Path, required=True)
    backtest.add_argument('--experiment-id', required=True)
    backtest.add_argument('--data-experiment-id', default='EXP-003')
    backtest.add_argument('--strategy', choices=['buy_hold', 'ema_trend'], required=True)
    backtest.add_argument('--period', choices=['development', 'validation'], required=True)
    backtest.add_argument('--cost', choices=['base', 'higher_execution', 'strict'], required=True)
    samples = subcommands.add_parser('build-samples')
    samples.add_argument('--config', type=Path, required=True)
    samples.add_argument('--experiment-id', required=True)
    samples.add_argument('--data-experiment-id', default='EXP-003')
    train = subcommands.add_parser('train')
    train.add_argument('--config', type=Path, required=True)
    train.add_argument('--experiment-id', required=True)
    train.add_argument('--sample-experiment-id', default='EXP-006')
    validate = subcommands.add_parser('validate')
    validate.add_argument('--config', type=Path, required=True)
    validate.add_argument('--experiment-id', required=True)
    validate.add_argument('--data-experiment-id', default='EXP-003')
    validate.add_argument('--training-experiment-id', default='EXP-007')
    validate.add_argument('--C', type=float, choices=[.1, 1., 10.], required=True)
    validate.add_argument('--threshold', type=float, choices=[.55, .60, .61, .62, .63, .64, .65], required=True)
    validate.add_argument('--cost', choices=['base', 'higher_execution', 'strict'], required=True)
    funding = subcommands.add_parser('fetch-funding')
    funding.add_argument('--config', type=Path, required=True)
    research_prep = subcommands.add_parser('research-prepare')
    research_prep.add_argument('--research-config', type=Path, required=True)
    research_prep.add_argument('--experiment-id', required=True)
    research_prep.add_argument('--data-experiment-id', default='EXP-003')
    research_prep.add_argument('--source-sample-experiment-id', default='EXP-021')
    research_train = subcommands.add_parser('research-train')
    research_train.add_argument('--research-config', type=Path, required=True)
    research_train.add_argument('--experiment-id', required=True)
    research_train.add_argument('--prepared-experiment-id', required=True)
    research_train.add_argument('--window', choices=['W1', 'W2', 'R2025'], required=True)
    research_train.add_argument('--label-policy', choices=['gross_direction_v1', 'net_positive_base_v1'], required=True)
    research_eval = subcommands.add_parser('research-evaluate')
    research_eval.add_argument('--research-config', type=Path, required=True)
    research_eval.add_argument('--experiment-id', required=True)
    research_eval.add_argument('--prepared-experiment-id', required=True)
    research_eval.add_argument('--training-experiment-id', required=True)
    research_eval.add_argument('--window', choices=['W1', 'W2', 'R2025'], required=True)
    research_eval.add_argument('--label-policy', choices=['gross_direction_v1', 'net_positive_base_v1'], required=True)
    research_eval.add_argument('--threshold', type=float, choices=[0.40, 0.50, 0.60, 0.64], required=True)
    research_eval.add_argument('--cost', choices=['base', 'higher_execution', 'strict'], default='base')
    research_eval.add_argument('--exit-variant', choices=['C0', 'C1', 'C2', 'C3'], default='C0')
    research_eval.add_argument('--data-experiment-id', default='EXP-003')
    research_sel = subcommands.add_parser('research-select')
    research_sel.add_argument('--research-config', type=Path, required=True)
    research_sel.add_argument('--experiment-id', required=True)
    research_sel.add_argument('--prepared-experiment-id', required=True)
    research_sel.add_argument('--base-experiment-ids', required=True)
    research_comp = subcommands.add_parser('research-compare')
    research_comp.add_argument('--research-config', type=Path, required=True)
    research_comp.add_argument('--experiment-id', required=True)
    research_comp.add_argument('--selection-experiment-id', required=True)
    research_comp.add_argument('--evaluated-experiment-ids', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'research-prepare':
            from cryptoquant.models.research_data import execute_research_prepare
            return execute_research_prepare(args, Path.cwd())
        if args.command == 'research-train':
            from cryptoquant.models.research_models import execute_research_train
            return execute_research_train(args, Path.cwd())
        if args.command == 'research-evaluate':
            from cryptoquant.models.research_workflow import execute_research_evaluate
            return execute_research_evaluate(args, Path.cwd())
        if args.command == 'research-select':
            from cryptoquant.models.research_workflow import execute_research_select
            if isinstance(args.base_experiment_ids, str):
                args.base_experiment_ids = [x.strip() for x in args.base_experiment_ids.split(',') if x.strip()]
            return execute_research_select(args, Path.cwd())
        if args.command == 'research-compare':
            from cryptoquant.models.research_workflow import execute_research_compare
            if isinstance(args.evaluated_experiment_ids, str):
                args.evaluated_experiment_ids = [x.strip() for x in args.evaluated_experiment_ids.split(',') if x.strip()]
            return execute_research_compare(args, Path.cwd())
        if args.command == 'fetch-funding':
            from cryptoquant.data.funding_workflow import execute
            return execute(args, Path.cwd())
        if args.command == 'validate':
            from cryptoquant.models.validation_workflow import execute
            return execute(args, Path.cwd())
        if args.command == 'train':
            from cryptoquant.models.training_workflow import execute
            return execute(args, Path.cwd())
        if args.command == 'build-samples':
            from cryptoquant.models.workflow import execute
            return execute(args, Path.cwd())
        if args.command == 'backtest':
            from cryptoquant.baselines.workflow import execute
            return execute(args, Path.cwd())
        return run_data_step(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def run_data_step(args):
    from cryptoquant.config import load_config
    from cryptoquant.data.workflow import execute

    config = load_config(args.config)
    root = Path.cwd()
    experiment, attempt = begin_step(root / "artifacts/experiments", args.experiment_id, args.command, config.config_hash, resume=args.resume)
    try:
        result = execute(args.command, config, root, experiment, attempt, args.config)
        finish_step(experiment, args.command, "complete", result)
    except Exception as exc:
        write_json(attempt / "failure.json", {"status": "failed", "error_type": type(exc).__name__, "error": str(exc), "at_utc": datetime.now(timezone.utc).isoformat()})
        finish_step(experiment, args.command, "failed", {"error": str(exc), "failure_report": str((attempt / "failure.json").resolve())})
        raise
    print(f"{args.command} complete: {args.experiment_id}")
    return 0
