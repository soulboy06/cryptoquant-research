"""沿证据哈希加载指定开发或验证分区；不读取保留测试行情。"""

import json
from pathlib import Path
import re

import pandas as pd

from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.calendar import policy_info
from cryptoquant.data.rules import parse_market_rules
from cryptoquant.baselines.periods import period_bounds


def experiment_id(value):
    if not re.fullmatch(r'EXP-[0-9]{3,}', value) or int(value[4:]) == 0:
        raise ValueError('invalid experiment ID')
    return value


def load_development(root, data_id, config):
    return load_period(root, data_id, config, 'development')


def load_period(root, data_id, config, period):
    period_bounds(config, period)
    root = Path(root).resolve()
    experiment = root / 'artifacts/experiments' / experiment_id(data_id)
    state = json.loads((experiment / 'step_state.json').read_text('utf-8'))
    if state.get('type') != 'data_check' or any(state['steps'][s]['status'] != 'complete' for s in ['prepare', 'rules', 'check-data']):
        raise ValueError('data checks not complete')

    def verified_json(path, digest):
        path = Path(path).resolve()
        if not path.is_relative_to(experiment) or sha_file(path) != digest:
            raise ValueError('evidence path or hash mismatch')
        return json.loads(path.read_text('utf-8'))

    prepared = state['steps']['prepare']['result']
    checked = state['steps']['check-data']['result']
    quality = verified_json(checked['quality_report'], checked['quality_report_sha256'])
    manifest = verified_json(prepared['manifest'], prepared['manifest_sha256'])
    policy_hash = policy_info(config.data_policy)[1]
    if quality['status'] != 'passed' or quality['data_manifest_sha256'] != prepared['manifest_sha256']:
        raise ValueError('invalid quality evidence')
    if any(x.get('data_policy') != config.data_policy or x.get('data_policy_sha256') != policy_hash for x in [quality, manifest]):
        raise ValueError('data policy mismatch')
    saved_config_path = Path(state['steps']['prepare']['attempts'][-1]['path']).resolve() / 'config.toml'
    if not saved_config_path.is_relative_to(experiment):
        raise ValueError('data config path mismatch')
    saved = load_config(saved_config_path)
    if any(x.get('config_hash') != saved.config_hash for x in [state, manifest, quality]):
        raise ValueError('frozen data config hash mismatch')
    for key in ['symbols', 'download_start', 'download_end', 'development_start', 'development_end', 'validation_start', 'validation_end', 'test_start', 'test_end']:
        if getattr(saved, key) != getattr(config, key):
            raise ValueError('data configuration mismatch: ' + key)
    rule_result = state['steps']['rules']['result']
    rule_report_path = Path(rule_result['rules_report']).resolve()
    if not rule_report_path.is_relative_to(experiment):
        raise ValueError('rule report path mismatch')
    rule_report = json.loads(rule_report_path.read_text('utf-8'))
    rule_path = Path(rule_report['snapshot']).resolve()
    if not (rule_path.is_relative_to(root / 'data/rules') or rule_path.is_relative_to(experiment)):
        raise ValueError('rule snapshot path mismatch')
    if rule_report['status'] != 'passed' or sha_file(rule_path) != rule_result['rules_sha256'] or quality['rules_sha256'] != rule_result['rules_sha256']:
        raise ValueError('rule hash mismatch')
    info = json.loads(rule_path.read_text('utf-8'))
    items = {item['symbol']: item for item in info['symbols']}
    if len(items) != len(info['symbols']) or set(items) != set(config.symbols):
        raise ValueError('rule symbols mismatch')
    rules = {s: parse_market_rules(items[s], config.minimum_order_notional) for s in config.symbols}
    partitions = quality['partitions'][period]
    if set(partitions) != set(config.symbols):
        raise ValueError('partition symbols mismatch')
    frames = {}
    for symbol, item in partitions.items():
        path = Path(item['path']).resolve()
        if not path.is_relative_to(root / 'data/processed' / period) or sha_file(path) != item['sha256']:
            raise ValueError(period + ' partition path or hash mismatch')
        frames[symbol] = pd.read_parquet(path)
    return frames, rules, dict(data_experiment_id=data_id, period=period,
                              data_manifest_sha256=prepared['manifest_sha256'],
                              quality_report_sha256=checked['quality_report_sha256'],
                              rules_sha256=rule_result['rules_sha256'], data_policy_sha256=policy_hash,
                              rule_report_sha256=sha_file(rule_report_path), partitions=partitions)
