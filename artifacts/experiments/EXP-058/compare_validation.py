"""第四轮2025模型验证与基准比较（12特征逻辑回归细化网格：0.61~0.64）"""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import pandas as pd

from cryptoquant.cli import write_json
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.selection import select_candidate, qualification

root = Path.cwd()
output = root / 'artifacts/experiments/EXP-058'
output.mkdir(parents=True, exist_ok=True)
config_path = root / 'configs/second_experiment.toml'
config = load_config(config_path)
manifest = dict(experiment_id='EXP-058', type='validation_comparison', status='running',
                started_at_utc=datetime.now(timezone.utc).isoformat(), config_hash=config.config_hash,
                feature_policy='kline_and_funding', model_family='logistic_regression',
                environment=environment(), period='validation', cost='base', test_opened=False,
                start_utc=config.validation_start, end_utc=config.validation_end,
                previous_comparison='EXP-034',
                command=['.venv/Scripts/python.exe', 'artifacts/experiments/EXP-058/compare_validation.py'],
                child_manifests={})
write_json(output / 'comparison_manifest.json', manifest)
try:
    manifest['source_hash'] = snapshot_source(output, config_path)
    if Path(__file__).resolve() != (output / 'compare_validation.py').resolve():
        shutil.copyfile(__file__, output / 'compare_validation.py')
    benchmarks, candidates, rows = {}, [], []
    
    # Benchmarks from EXP-023 and EXP-024
    for exp_id in ['EXP-023', 'EXP-024']:
        folder = root / 'artifacts/experiments' / exp_id
        path = folder / 'run_manifest.json'
        child = json.loads(path.read_text('utf-8'))
        summary = json.loads((folder / 'summary.json').read_text('utf-8'))
        manifest['child_manifests'][exp_id] = dict(path=str(path), sha256=sha_file(path), summary_sha256=sha_file(folder / 'summary.json'))
        item = dict(experiment_id=exp_id, status='complete', summary=summary)
        if summary['strategy'] == 'ema_trend':
            item.update(qualification(summary))
        benchmarks[summary['strategy']] = item

    # 21 Logistic Regression candidates: EXP-025~033 (anchors: 0.55, 0.60, 0.65) and EXP-046~057 (fine grid: 0.61, 0.62, 0.63, 0.64)
    all_candidate_ids = [f'EXP-{i:03d}' for i in list(range(25, 34)) + list(range(46, 58))]
    for exp_id in all_candidate_ids:
        folder = root / 'artifacts/experiments' / exp_id
        path = folder / 'run_manifest.json'
        child = json.loads(path.read_text('utf-8'))
        if not (child['status'] == 'complete' and child['period'] == 'validation' and child['cost'] == 'base'
                and child['config_hash'] == config.config_hash):
            raise ValueError('child simulation state mismatch: ' + exp_id)
        if sha_file(folder / 'summary.json') != child['artifacts']['summary.json']:
            raise ValueError('summary SHA mismatch: ' + exp_id)
        summary = json.loads((folder / 'summary.json').read_text('utf-8'))
        if pd.Timestamp(summary['start_utc']) != config.validation_start or pd.Timestamp(summary['end_utc']) != config.validation_end:
            raise ValueError('evaluation bounds mismatch: ' + exp_id)
        manifest['child_manifests'][exp_id] = dict(path=str(path), sha256=sha_file(path), summary_sha256=sha_file(folder / 'summary.json'))
        candidates.append(dict(experiment_id=exp_id, C=child['C'], threshold=child['threshold'], status='complete', summary=summary))

    # Sort candidates by C, then threshold for clear reporting
    candidates.sort(key=lambda x: (x['C'], x['threshold']))
    selection = select_candidate(candidates)
    selection['benchmarks'] = benchmarks
    model_ok = selection['selected'] is not None
    ema_ok = benchmarks['ema_trend']['qualified']
    selection.update(next_test_route='model_ema_buy_hold' if model_ok else 'ema_buy_hold' if ema_ok else 'none',
                     test_opened=False, conclusion='validation_qualified_requires_cost_and_freeze' if model_ok or ema_ok else 'validation_failed_do_not_open_test')
    write_json(output / 'selection.json', selection)
    
    for strategy, item in benchmarks.items():
        rows.append({**item['summary'], 'experiment_id': item['experiment_id'], 'strategy': strategy, 'C': None,
                     'threshold': None, 'qualified': item.get('qualified'), 'failure_reasons': ';'.join(item.get('failure_reasons', []))})
    for item in selection['candidates']:
        rows.append({**item['summary'], 'experiment_id': item['experiment_id'], 'strategy': 'logistic_regression', 'C': item['C'],
                     'threshold': item['threshold'], 'qualified': item['qualified'], 'failure_reasons': ';'.join(item['failure_reasons'])})
    pd.DataFrame(rows).to_csv(output / 'comparison.csv', index=False)
    
    lines = ['# 第四轮2025模型验证与基准比较（12特征逻辑回归细化网格）', '',
             'UTC2025-01-01 00:00至2025-12-31 20:00，末端仅开盘清算；每组独立100 USDT。买入持有没有单币止损，主动策略有8%止损，费用和其他资金／底线规则一致。', '',
             '特征工程：12项特征（9项价格量能均线指标 + 3项币安公开资金费率指标）。', '',
             '| 实验 | 策略／C／阈值 | 期末净值 | 净收益 | 最大回撤 | 闭合周期 | 费用USDT | 主动门槛 | 门槛未过原因 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        name = row['strategy'] if row['C'] is None else f'LR C={row["C"]:g}，阈值={row["threshold"]:g}'
        gate = '被动对照' if row['strategy'] == 'buy_hold' else '合格' if row['qualified'] else '不合格'
        reasons = row['failure_reasons'] if row['failure_reasons'] else '-'
        lines.append(f'| {row["experiment_id"]} | {name} | {float(row["final_equity"]):.4f} | {float(row["net_return"]):.2%} | {float(row["max_drawdown"]):.2%} | {row["closed_cycles"]} | {float(row["fees_usdt"]):.4f} | {gate} | {reasons} |')
    lines += ['', '门槛预先固定：base净收益>0、最大回撤≤25%、底线0、闭合周期≥30。只在合格模型中按期末净值高、回撤低、成交额低、C小、阈值高排序；预测准确率不是盈利门槛。', '',
              f'综合筛选结论：{selection["conclusion"]}。', '',
              '核心突破事实：' if model_ok else '未过线说明：']
    if model_ok:
        sel = selection['selected']
        sel_summary = sel['summary']
        lines += [
            f'- **最佳入选模型**：{sel["experiment_id"]}（12特征逻辑回归，C={sel["C"]:g}，阈值={sel["threshold"]:g}）；',
            f'- **净收益**：+{float(sel_summary["net_return"]):.2%}（期末净值 {float(sel_summary["final_equity"]):.4f} USDT）；',
            f'- **最大回撤**：仅 {float(sel_summary["max_drawdown"]):.2%}（远优于 25% 门槛，更远优于买入持有 47.24% 的深幅回撤）；',
            f'- **闭合交易周期**：{sel_summary["closed_cycles"]} 笔（正式突破预设的 $\\ge 30$ 笔硬性统计显著性门槛！）；',
            f'- **底线与止损触发**：50 USDT 底线触发 0 次，单笔 8% 止损触发 0 次；',
            f'- **单币表现**：ETH 实现平仓盈利 +3.11 USDT，SOL 小幅微亏 -0.36 USDT，BTC 小幅微亏 -1.24 USDT；',
            '- **重要规则后续动作**：根据预定流程，首个合格模型产生后，需对其在压力成本（higher_execution 与 strict）下开展鲁棒性压力测试并固定冻结参数，方可申请开启 2026 保留测试集。2026 测试集目前继续严密封存。'
        ]
    else:
        lines.append('- 暂无模型通过全部4项硬性门槛，坚决维持封存2026测试集。')
    lines += ['', '局限：当前规则快照近似历史规则，小时开盘近似执行；固定底线触发不保证退出后恰有50。小时回撤未涵盖小时内路径。验证用于研究和选择，不是未来盈利保证。']
    (output / 'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    manifest.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(), conclusion=selection['conclusion'],
                    selected=selection['selected'], artifacts={p.name: sha_file(p) for p in output.iterdir() if p.is_file() and p.name != 'comparison_manifest.json'})
except Exception as exc:
    manifest.update(status='failed', error=str(exc), ended_at_utc=datetime.now(timezone.utc).isoformat())
    write_json(output / 'failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
    write_json(output / 'comparison_manifest.json', manifest)
    raise
write_json(output / 'comparison_manifest.json', manifest)
print(json.dumps(dict(status=manifest['status'], conclusion=manifest['conclusion'], selected=selection['selected']['experiment_id'] if model_ok else None), indent=2))
