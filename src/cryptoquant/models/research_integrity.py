"""研究实验的不可变来源校验；校验冻结副本，不要求等于当前源码。"""
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
import tomllib

import pandas as pd

from cryptoquant.baselines.io import experiment_id
from cryptoquant.config import Cost, load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.models.labels import LABEL_POLICIES, validate_label_metadata
from cryptoquant.models.research_config import _FIXED_VALUES_V5, _FIXED_VALUES_V6, RESEARCH_WINDOWS

SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT')
_REPORT_EXCEPTIONS = {'EXP-114': 'ablation_selection_and_freeze',
                      'EXP-121': 'comprehensive_synthesis_report'}


def _require_sha(digest):
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in '0123456789abcdef' for char in digest)):
        raise ValueError('missing or invalid artifact SHA')
    return digest


def _no_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError(f'symlink or junction is forbidden: {path}')


def contained_artifact(root, experiment_dir, path, expected_sha=None):
    """解析清单路径，拒绝逃出实验目录、符号链接和不匹配的文件 SHA。"""
    root, folder = Path(root).resolve(), Path(experiment_dir)
    supplied = Path(path)
    if '..' in supplied.parts:
        raise ValueError(f'artifact path escape: {path}')
    if supplied.is_absolute():
        candidate = supplied
    elif supplied.parts[:2] == ('artifacts', 'experiments'):
        candidate = root / supplied
    else:
        candidate = folder / supplied
    candidate = Path(os.path.abspath(candidate))
    _no_symlinks(candidate)
    if not candidate.is_relative_to(folder.resolve()) or not candidate.is_file():
        raise ValueError(f'artifact path outside experiment or missing: {path}')
    if expected_sha is not None and (not isinstance(expected_sha, str) or sha_file(candidate) != expected_sha):
        raise ValueError(f'artifact SHA mismatch: {path}')
    return candidate


def _json(root, folder, path, expected_sha=None):
    file = contained_artifact(root, folder, path, expected_sha)
    try:
        result = json.loads(file.read_text('utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f'invalid JSON manifest: {path}') from exc
    if not isinstance(result, dict):
        raise ValueError(f'manifest must be an object: {path}')
    return result


def verify_completed_experiment(root, experiment_id, expected_type=None):
    """返回 (实验目录, run清单)，先验证所有声明文件和源码快照。"""
    root = Path(root).resolve()
    # Keep the public argument name while reusing the project ID validator.
    from cryptoquant.baselines.io import experiment_id as validate_id
    folder = root / 'artifacts/experiments' / validate_id(experiment_id)
    _no_symlinks(folder)
    if not folder.is_dir():
        raise ValueError(f'experiment directory missing: {experiment_id}')
    run = _json(root, folder, 'run_manifest.json')
    if (run.get('experiment_id') != experiment_id or run.get('status') != 'complete'
            or not isinstance(run.get('type'), str)):
        raise ValueError('experiment ID, type or completion status mismatch')
    if expected_type is not None and run['type'] != expected_type:
        raise ValueError(f'experiment type mismatch: expected {expected_type}')
    manifests = [run]
    for name in ('prepared_manifest', 'train_manifest'):
        path = folder / (name + '.json')
        key = name + '_sha256'
        if path.exists() or key in run:
            if key not in run:
                raise ValueError(f'missing child manifest SHA: {name}')
            child = _json(root, folder, path, _require_sha(run[key]))
            if any(child.get(k) != run.get(k) for k in ('experiment_id', 'type', 'status')):
                raise ValueError(f'child manifest identity mismatch: {name}')
            manifests.append(child)
    if run['type'] in {'research_samples', 'research_training'} and len(manifests) != 2:
        raise ValueError('missing required child manifest')
    for manifest in manifests:
        artifacts = manifest.get('artifacts', {})
        if not isinstance(artifacts, dict):
            raise ValueError('invalid artifact manifest')
        for path, digest in artifacts.items():
            contained_artifact(root, folder, path, _require_sha(digest))
    if _REPORT_EXCEPTIONS.get(experiment_id) == run['type'] and 'source_hash' not in run:
        if not run.get('artifacts'):
            raise ValueError('report must declare artifacts')
        missing = ['source_snapshot']
        if not run.get('environment'):
            missing.append('environment')
        return folder, dict(run, verified_source=dict(
            mode='legacy_report_artifacts_only', missing_evidence=missing,
            artifacts_verified=True, legacy_report_exception=True))
    env = run.get('environment')
    if (not run.get('source_hash') or not isinstance(env, dict) or not env.get('python')
            or not isinstance(env.get('packages'), dict) or not env['packages']):
        raise ValueError('research experiment requires source snapshot and environment')
    source = _json(root, folder, 'source_manifest.json', run.get('source_manifest_sha256'))
    files = source.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('missing source snapshot files')
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    if source.get('source_hash') != digest or run['source_hash'] != digest:
        raise ValueError('source manifest SHA mismatch')
    for path, file_sha in files.items():
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('source snapshot path escape')
        contained_artifact(root, folder, Path('source_snapshot') / path, _require_sha(file_sha))
    return folder, run


def verify_config_binding(root, experiment_dir, manifest, run_manifest, research_cfg=None):
    """绑定保存配置与清单；仅允许明确冻结的第五轮训练来源供第六轮使用。"""
    folder = Path(experiment_dir)
    for filename, key in [('config.toml', 'execution_config_hash'),
                          ('research_config.toml', 'research_config_hash')]:
        digest = manifest.get(key)
        if not digest or run_manifest.get(key) != digest or manifest.get('artifacts', {}).get(filename) != digest:
            raise ValueError(f'config hash binding mismatch: {filename}')
        contained_artifact(root, folder, filename, digest)
    execution = load_config(folder / 'config.toml')
    raw = tomllib.loads((folder / 'research_config.toml').read_text('utf-8-sig'))
    if raw not in (_FIXED_VALUES_V5, _FIXED_VALUES_V6):
        raise ValueError('saved research config differs from frozen scope')
    if (execution.symbols != SYMBOLS or execution.feature_policy != 'kline_and_funding'
            or execution.model_family != 'logistic_regression' or execution.initial_cash != 100
            or execution.equity_floor != 50 or execution.data_policy != 'halt_aware_v2'
            or execution.weight_per_symbol != Decimal('.30') or execution.stop_loss != Decimal('.08')
            or execution.cooldown_hours != 4 or execution.minimum_order_notional != 10
            or execution.costs != {'base': Cost(Decimal('.001'), Decimal('.0005')),
                                   'higher_execution': Cost(Decimal('.001'), Decimal('.001')),
                                   'strict': Cost(Decimal('.002'), Decimal('.001'))}
            or execution.development_start != RESEARCH_WINDOWS['W1'].fit_start
            or execution.development_end != RESEARCH_WINDOWS['W2'].end
            or execution.validation_start != RESEARCH_WINDOWS['R2025'].start
            or execution.validation_end != RESEARCH_WINDOWS['R2025'].end):
        raise ValueError('saved execution config violates research scope')
    compatibility = dict(mode='exact', source_research_config_hash=manifest['research_config_hash'],
                         source_execution_config_hash=manifest['execution_config_hash'])
    if research_cfg is not None:
        if (research_cfg.execution_config_hash != manifest['execution_config_hash']
                or research_cfg.execution_config.config_hash != execution.config_hash):
            raise ValueError('execution config hash mismatch')
        requested = tomllib.loads(research_cfg.research_config_path.read_text('utf-8-sig'))
        if sha_file(research_cfg.research_config_path) != research_cfg.research_config_hash:
            raise ValueError('requested research config SHA mismatch')
        if research_cfg.research_config_hash != manifest['research_config_hash']:
            if not (raw == _FIXED_VALUES_V5 and requested == _FIXED_VALUES_V6
                    and str(research_cfg.C) == '0.1'
                    and list(research_cfg.windows) == raw['windows']
                    and set(research_cfg.label_policies) <= set(raw['label_policies'])):
                raise ValueError('research config hash mismatch; incompatible training signature')
            compatibility['mode'] = 'fifth_to_sixth_training_signature'
        compatibility['requested_research_config_hash'] = research_cfg.research_config_hash
    return compatibility


def bound_metadata_file(root, folder, manifest, item, path_key='path', sha_key='sha256'):
    """单文件元数据必须指向实验内且与产物清单为同一文件和同一 SHA。"""
    digest = _require_sha(item.get(sha_key))
    path = contained_artifact(root, folder, item.get(path_key, ''), digest)
    relative = path.relative_to(Path(folder)).as_posix()
    if manifest.get('artifacts', {}).get(relative) != item.get(sha_key):
        raise ValueError(f'metadata artifact SHA binding mismatch: {relative}')
    return path


def verify_prepared(root, prepared_id, research_cfg=None):
    """返回 (prepared清单, run清单)，只核验已截断资金副本，不访问完整归档。"""
    folder, run = verify_completed_experiment(root, prepared_id, 'research_samples')
    manifest = _json(root, folder, 'prepared_manifest.json', run['prepared_manifest_sha256'])
    verify_config_binding(root, folder, manifest, run, research_cfg)
    if manifest.get('feature_names') != ALL_FEATURE_NAMES:
        raise ValueError('prepared feature order mismatch')
    if set(manifest.get('label_policies', {})) != set(LABEL_POLICIES) or set(manifest.get('samples', {})) != set(LABEL_POLICIES):
        raise ValueError('prepared must contain both label policies')
    for policy, card in manifest['label_policies'].items():
        validate_label_metadata(dict(type='research_samples', **card), policy)
        if set(manifest['samples'][policy]) != set(SYMBOLS):
            raise ValueError('prepared samples require exactly three symbols')
        for item in manifest['samples'][policy].values():
            bound_metadata_file(root, folder, manifest, item)
    for key in ('features', 'funding_snapshot'):
        if set(manifest.get(key, {})) != set(SYMBOLS):
            raise ValueError(f'prepared {key} require exactly three symbols')
        for symbol, item in manifest[key].items():
            path = bound_metadata_file(root, folder, manifest, item,
                                       'snapshot_path' if key == 'funding_snapshot' else 'path',
                                       'snapshot_sha256' if key == 'funding_snapshot' else 'sha256')
            if key == 'funding_snapshot':
                frame = pd.read_parquet(path)
                times = pd.DatetimeIndex(frame.funding_time)
                if (str(times.tz) != 'UTC' or times.hasnans or not times.is_unique
                        or not times.is_monotonic_increasing or len(frame) != item['rows']
                        or not (frame.symbol == symbol).all() or frame.empty
                        or times.max() > pd.Timestamp('2025-12-31T20:00:00+00:00')
                        or times.min() != pd.Timestamp(item['min_funding_time_utc'])
                        or times.max() != pd.Timestamp(item['max_funding_time_utc'])):
                    raise ValueError('funding snapshot symbol, UTC, count or cutoff mismatch')
    return manifest, run
