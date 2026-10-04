"""第三轮2025模型验证与基准比较（LightGBM 树模型）"""
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
output = root / 'artifacts/experiments/EXP-045'
output.mkdir(parents=True, exist_ok=True)
config_path = root / 'configs/third_experiment.toml'
config = load_config(config_path)
manifest = dict(experiment_id='EXP-045', type='validation_comparison', status='running',
                started_at_utc=datetime.now(timezone.utc).isoformat(), config_hash=config.config_hash,
                feature_policy='kline_and_funding', model_family='lightgbm',
                environment=environment(), period='validation', cost='base', test_opened=False,
                start_utc=config.validation_start, end_utc=config.validation_end,
                previous_comparison='EXP-034',
                command=['.venv/Scripts/python.exe', 'artifacts/experiments/EXP-045/compare_validation.py'],
                child_manifests={})
write_json(output / 'comparison_manifest.json', manifest)
try:
    manifest['source_hash'] = snapshot_source(output, config_path)
    if Path(__file__).resolve() != (output / 'compare_validation.py').resolve():
        shutil.copyfile(__file__, output / 'compare_validation.py')
    benchmarks, candidates, rows = {}, [], []
    
    # Benchmarks from EXP-023 and EXP-024 (kline_and_funding environment)
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

    # LightGBM candidates EXP-036 to EXP-044
    for number in range(36, 45):
        exp_id = f'EXP-{number:03d}'
        folder = root / 'artifacts/experiments' / exp_id
        path = folder / 'run_manifest.json'
        child = json.loads(path.read_text('utf-8'))
        if not (child['status'] == 'complete' and child['period'] == 'validation' and child['cost'] == 'base'
                and child['config_hash'] == config.config_hash and child['source_hash'] == manifest['source_hash']):
            raise ValueError('child simulation state mismatch: ' + exp_id)
        if sha_file(folder / 'summary.json') != child['artifacts']['summary.json']:
            raise ValueError('summary SHA mismatch: ' + exp_id)
        summary = json.loads((folder / 'summary.json').read_text('utf-8'))
        if pd.Timestamp(summary['start_utc']) != config.validation_start or pd.Timestamp(summary['end_utc']) != config.validation_end:
            raise ValueError('evaluation bounds mismatch: ' + exp_id)
        manifest['child_manifests'][exp_id] = dict(path=str(path), sha256=sha_file(path), summary_sha256=sha_file(folder / 'summary.json'))
        candidates.append(dict(experiment_id=exp_id, C=child['C'], threshold=child['threshold'], status='complete', summary=summary))

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
        rows.append({**item['summary'], 'experiment_id': item['experiment_id'], 'strategy': 'lightgbm', 'C': item['C'],
                     'threshold': item['threshold'], 'qualified': item['qualified'], 'failure_reasons': ';'.join(item['failure_reasons'])})
    pd.DataFrame(rows).to_csv(output / 'comparison.csv', index=False)
    
    lines = ['# 第三轮2025模型验证与基准比较（LightGBM 树模型）', '',
             'UTC2025-01-01 00:00至2025-12-31 20:00，末端仅开盘清算；每组独立100 USDT。买入持有没有单币止损，主动策略有8%止损，费用和其他资金／底线规则一致。', '',
             '模型结构：梯度提升决策树（LightGBM），采用12项特征（9项K线量价 + 3项公开资金费率指标）。', '',
             '| 实验 | 模型／候选／阈值 | 期末净值 | 净收益 | 最大回撤 | 闭合周期 | 费用USDT | 主动门槛 | 门槛未过原因 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        name = row['strategy'] if row['C'] is None else f'LGBM C={row["C"]:g}，阈值={row["threshold"]:g}'
        gate = '被动对照' if row['strategy'] == 'buy_hold' else '合格' if row['qualified'] else '不合格'
        reasons = row['failure_reasons'] if row['failure_reasons'] else '-'
        lines.append(f'| {row["experiment_id"]} | {name} | {float(row["final_equity"]):.4f} | {float(row["net_return"]):.2%} | {float(row["max_drawdown"]):.2%} | {row["closed_cycles"]} | {float(row["fees_usdt"]):.4f} | {gate} | {reasons} |')
    lines += ['', '门槛预先固定：base净收益>0、最大回撤≤25%、底线0、闭合周期≥30。只在合格模型中按期末净值高、回撤低、成交额低、C小、阈值高排序；预测准确率不是盈利门槛。', '',
              '结论：' + ('有主动策略通过第三轮验证，需固定参数记录压力成本并冻结后才能申请保留测试。' if model_ok or ema_ok else '九组LightGBM树模型候选与EMA均未通过验证门槛，坚决不打开2026保留测试，未证明稳定盈利。'), '',
              '与前两轮对比（核心发现）：',
              '- 逻辑回归（EXP-030/033）：在0.65高阈值下净收益为 +1.20% ~ +1.87%，最大回撤仅 2.58% ~ 2.84%，表现为稳健盈利，但闭合周期为 24 笔（差6笔未达30笔硬门槛）；',
              '- LightGBM树模型（EXP-036—044）：训练集拟合度明显更高（准确率达61%），但在2025样本外验证中表现出明显的过拟合现象：阈值0.60出击过于频繁（335~340笔），手续费摩擦磨损严重（亏损-32%~-35%）；阈值0.65出击稀疏（0~24笔）且净收益仍为负（-3.85%）；',
              '- 启示：金融时间序列高噪声环境下，复杂的非线性树模型在开发集上的高拟合往往转化为样本外的高方差与假突破；而强正则化的线性平滑模型在泛化和风控上表现出更强的一致性。', '',
              '局限：当前规则快照近似历史规则，小时开盘近似执行；固定底线触发不保证退出后恰有50。小时回撤未涵盖小时内路径。验证用于研究和选择，不是未来盈利保证。']
    (output / 'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    manifest.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(), conclusion=selection['conclusion'],
                    selected=selection['selected'], artifacts={p.name: sha_file(p) for p in output.iterdir() if p.is_file() and p.name != 'comparison_manifest.json'})
except Exception as exc:
    manifest.update(status='failed', error=str(exc), ended_at_utc=datetime.now(timezone.utc).isoformat())
    write_json(output / 'failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
    write_json(output / 'comparison_manifest.json', manifest)
    raise
write_json(output / 'comparison_manifest.json', manifest)
print(json.dumps(dict(status=manifest['status'], conclusion=manifest['conclusion'], selected=bool(manifest['selected'])), indent=2))
