"""已登记的首次验证批次；冻结本脚本供结果追溯，不是调参循环。"""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pandas as pd

from cryptoquant.baselines.workflow import execute as baseline
from cryptoquant.cli import write_json
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.selection import select_candidate, qualification
from cryptoquant.models.training import C_VALUES, THRESHOLDS
from cryptoquant.models.validation_workflow import prepare_validation, execute as validate

root = Path.cwd()
config_path = root / 'configs/first_experiment.toml'
config = load_config(config_path)
output = root / 'artifacts/experiments/EXP-019'
output.mkdir(parents=True, exist_ok=False)
manifest = dict(experiment_id='EXP-019', type='validation_comparison', status='running',
                started_at_utc=datetime.now(timezone.utc).isoformat(), config_hash=config.config_hash,
                environment=environment(), period='validation', start_utc=config.validation_start,
                end_utc=config.validation_end, data_experiment_id='EXP-003', training_experiment_id='EXP-007',
                child_experiments=[], command=['.venv/Scripts/python.exe', '.cache/run_validation.py'],
                test_opened=False)
write_json(output / 'comparison_manifest.json', manifest)

def finish_child(args, runner, **kwargs):
    item = dict(experiment_id=args.experiment_id, status='running')
    manifest['child_experiments'].append(item)
    write_json(output / 'comparison_manifest.json', manifest)
    print(f'start {args.experiment_id}', flush=True)
    try:
        runner(args, root, **kwargs)
        item['status'] = 'complete'
    except Exception as exc:
        item.update(status='failed', error=str(exc))
    write_json(output / 'comparison_manifest.json', manifest)
    return item

try:
    manifest['source_hash'] = snapshot_source(output, config_path)
    shutil.copyfile(__file__, output / 'run_validation.py')
    manifest['runner_sha256'] = sha_file(output / 'run_validation.py')
    for number, strategy in [(8, 'buy_hold'), (9, 'ema_trend')]:
        args = SimpleNamespace(config=config_path, data_experiment_id='EXP-003', strategy=strategy,
                               period='validation', cost='base', experiment_id=f'EXP-{number:03d}')
        finish_child(args, baseline)
    context = prepare_validation(root, 'EXP-003', 'EXP-007', config)
    manifest['data'] = context['data']
    manifest['training'] = context['training']
    manifest['shared_predictions_generated'] = 3
    number = 10
    candidates = []
    for C in C_VALUES:
        for threshold in THRESHOLDS:
            args = SimpleNamespace(config=config_path, data_experiment_id='EXP-003', training_experiment_id='EXP-007',
                                   C=C, threshold=threshold, cost='base', experiment_id=f'EXP-{number:03d}')
            item = finish_child(args, validate, prepared=context)
            entry = dict(experiment_id=args.experiment_id, C=C, threshold=threshold, status=item['status'])
            if item['status'] == 'complete':
                entry['summary'] = json.loads((root / 'artifacts/experiments' / args.experiment_id / 'summary.json').read_text('utf-8'))
            else:
                entry['error'] = item['error']
            candidates.append(entry)
            number += 1
    selection = select_candidate(candidates)
    benchmarks = {}
    for exp_id, strategy in [('EXP-008', 'buy_hold'), ('EXP-009', 'ema_trend')]:
        item = next(x for x in manifest['child_experiments'] if x['experiment_id'] == exp_id)
        if item['status'] == 'complete':
            summary = json.loads((root / 'artifacts/experiments' / exp_id / 'summary.json').read_text('utf-8'))
            benchmarks[strategy] = dict(experiment_id=exp_id, status='complete', summary=summary)
            if strategy == 'ema_trend':
                benchmarks[strategy].update(qualification(summary))
        else:
            benchmarks[strategy] = item
    selection['benchmarks'] = benchmarks
    model_ok = selection['selected'] is not None
    ema_ok = benchmarks['ema_trend'].get('qualified', False)
    selection['next_test_route'] = 'model_ema_buy_hold' if model_ok else 'ema_buy_hold' if ema_ok else 'none'
    selection['test_opened'] = False
    selection['conclusion'] = 'validation_qualified_requires_cost_and_freeze' if model_ok or ema_ok else 'validation_failed_do_not_open_test'
    write_json(output / 'selection.json', selection)
    rows = []
    for strategy, item in benchmarks.items():
        rows.append(dict(experiment_id=item['experiment_id'], strategy=strategy, C=None, threshold=None,
                         qualified=item.get('qualified'), status=item['status'], **item.get('summary', {})))
    for item in selection['candidates']:
        rows.append(dict(experiment_id=item['experiment_id'], C=item['C'], threshold=item['threshold'],
                         qualified=item['qualified'], status=item['status'], failure_reasons=';'.join(item['failure_reasons']), **item.get('summary', {})))
    comparison = pd.DataFrame(rows)
    comparison.to_csv(output / 'comparison.csv', index=False)
    lines = ['# 首次2025模型验证与基准比较', '',
             '范围UTC2025-01-01 00:00至2025-12-31 20:00，末端仅开盘清算。每组独立100 USDT，原费用与风控一致；买入持有没有单币止损，主动策略有8%止损。', '',
             '| 实验 | 策略／C／阈值 | 期末净值 | 净收益 | 最大回撤 | 闭合周期 | 费用USDT | 主动门槛 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        if row['status'] != 'complete':
            lines.append(f'| {row["experiment_id"]} | 失败 | — | — | — | — | — | 不合格 |')
            continue
        name = row['strategy'] if row['C'] is None else f'C={row["C"]:g}，阈值={row["threshold"]:g}'
        gate = '被动对照' if row['strategy'] == 'buy_hold' else '合格' if row['qualified'] else '不合格'
        lines.append(f'| {row["experiment_id"]} | {name} | {float(row["final_equity"]):.4f} | {float(row["net_return"]):.2%} | {float(row["max_drawdown"]):.2%} | {row["closed_cycles"]} | {float(row["fees_usdt"]):.4f} | {gate} |')
    lines += ['', '门槛预先固定：base净收益>0、最大回撤≤25%、底线0、闭合周期≥30；仅合格模型按净值、回撤、成交额、C、阈值排序。训练准确率与验证预测指标均不是盈利筛选。', '',
              '结论：' + ('有主动策略通过验证，仍需固定参数记录压力成本并冻结后才能开启一次保留测试。' if model_ok or ema_ok else '模型九候选与主动趋势未通过验证；不打开2026保留测试，也未证明稳定盈利。后续根据交易诊断研究改进，另登记假设和实验，不把重复调参当独立验证。'), '',
              'EXP-007保持冻结，三组C各预测一次，同C三个阈值共享概率；每个模拟新建账户，不消费未来标签，不fit验证数据。概率诊断分别保存在子实验prediction_diagnostics.json，订单／成交／净值／季度和失败原因完整保留。', '',
              '规则快照近似历史规则，小时开盘近似执行；50底线不能保证退出后恰有50。小时回撤不涵盖小时内路径。所有结果是历史模拟，不能保证未来盈利。']
    (output / 'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    manifest.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(),
                    conclusion=selection['conclusion'], selected=selection['selected'],
                    artifacts={p.name: sha_file(p) for p in output.iterdir() if p.is_file() and p.name != 'comparison_manifest.json'})
except Exception as exc:
    manifest.update(status='failed', error=str(exc), ended_at_utc=datetime.now(timezone.utc).isoformat())
    write_json(output / 'failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
    write_json(output / 'comparison_manifest.json', manifest)
    raise
write_json(output / 'comparison_manifest.json', manifest)
print(json.dumps(dict(status=manifest['status'], conclusion=manifest['conclusion'], selected=bool(manifest['selected'])), indent=2), flush=True)
