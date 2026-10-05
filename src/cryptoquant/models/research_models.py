"""第五轮显式三模型训练器与加载器。

按时间严格截取窗口样本（W1 train_end=2023-01-01，W2 train_end=2024-01-01），
仅使用固定 C=0.1、12 特征逻辑回归拟合三币独立分类器。
持久化保存模型、参数卡、独立训练概率（三列）与标签分表，支持加载核验。
"""

from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss, roc_auc_score

from cryptoquant.baselines.io import experiment_id
from cryptoquant.cli import write_json
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.models.labels import (
    validate_label_metadata, GROSS_POLICY, NET_POLICY
)
from cryptoquant.models.research_config import (
    load_research_config, ResearchConfig, RESEARCH_WINDOWS
)
from cryptoquant.models.research_data import (
    load_research_samples, load_research_features
)
from cryptoquant.models.training import (
    fit_model, predict_probabilities, feature_matrix, MODEL_PARAMETERS
)
from cryptoquant.models.research_integrity import (
    verify_completed_experiment, verify_prepared, verify_config_binding, bound_metadata_file, SYMBOLS
)
from cryptoquant.models.research_data import _utc_columns


def train_research_window(root, prepared_id, window, label_policy, research_cfg, out_dir, selection_experiment_id=None):
    """为指定窗口和标签政策拟合三币独立的 C=0.1 逻辑回归模型。"""
    root = Path(root).resolve()
    from cryptoquant.models.research_gates import authorize_research
    authorize_research(root, research_cfg, prepared_id, window, label_policy,
                       selection_id=selection_experiment_id, training=True)
    prep_dir = root / 'artifacts/experiments' / experiment_id(prepared_id)
    prep_manifest, _ = verify_prepared(root, prepared_id, research_cfg)
    
    if window not in RESEARCH_WINDOWS:
        raise ValueError(f'unknown research window: {window}')
    win = RESEARCH_WINDOWS[window]
    
    if label_policy not in research_cfg.label_policies:
        raise ValueError(f'unknown label policy: {label_policy}')
    label_card = prep_manifest['label_policies'].get(label_policy)
    if not label_card:
        raise ValueError(f'missing label policy {label_policy} in prepared manifest')
    validate_label_metadata(dict(type='research_training', **label_card), expected_policy=label_policy)
    
    models_dir = out_dir / 'models'
    models_dir.mkdir(parents=True, exist_ok=True)
    probs_dir = out_dir / 'training_probabilities'
    probs_dir.mkdir(parents=True, exist_ok=True)
    labels_dir = out_dir / 'training_labels'
    labels_dir.mkdir(parents=True, exist_ok=True)
    
    models_meta = {}
    artifacts_dict = {}
    
    for symbol in research_cfg.execution_config.symbols:
        samples_df = load_research_samples(root, prepared_id, window, label_policy, symbol, research_cfg)
        if len(samples_df) == 0:
            raise ValueError(f'no training samples for {symbol} in window {window}')
        
        # Verify strict time boundaries
        fit_start = pd.Timestamp(win.fit_start)
        fit_end = pd.Timestamp(win.fit_end)
        if (samples_df.decision_time < fit_start).any() or (samples_df.label_end >= fit_end).any():
            raise ValueError(f'training sample boundary violation for {symbol} in window {window}')
        
        # Verify classes
        labels = samples_df['label']
        unique_classes = set(labels.unique())
        if unique_classes != {0, 1}:
            raise ValueError(f'single class in training samples for {symbol} in {window}: {unique_classes}')
        
        # Fit model
        model = fit_model(samples_df, C=0.1, feature_names=ALL_FEATURE_NAMES, model_family='logistic_regression')
        
        # Save model pipeline
        model_path = models_dir / f'{symbol}.joblib'
        joblib.dump(model, model_path)
        model_sha = sha_file(model_path)
        artifacts_dict[f'models/{symbol}.joblib'] = model_sha
        
        # Verify reload consistency
        reloaded = joblib.load(model_path)
        probs = predict_probabilities(reloaded, samples_df)
        orig_probs = predict_probabilities(model, samples_df)
        if not np.allclose(probs, orig_probs, atol=1e-12):
            raise ValueError(f'reloaded model probability discrepancy for {symbol}')
        
        # Diagnostics
        lr = model.named_steps['classifier']
        scaler = model.named_steps['scaler']
        y_true = labels.to_numpy(dtype=int)
        acc = float(((probs >= 0.5) == y_true).mean())
        auc = float(roc_auc_score(y_true, probs))
        brier = float(brier_score_loss(y_true, probs))
        
        # Model parameter card JSON
        param_card = dict(
            symbol=symbol,
            window=window,
            label_policy=label_policy,
            C=0.1,
            solver='lbfgs',
            max_iter=1000,
            classes=[0, 1],
            feature_names=ALL_FEATURE_NAMES,
            coefficients=lr.coef_[0].tolist(),
            intercept=float(lr.intercept_[0]),
            scaler_mean=scaler.mean_.tolist(),
            scaler_scale=scaler.scale_.tolist(),
            training_samples=len(samples_df),
            training_label_1=int((y_true == 1).sum()),
            training_label_0=int((y_true == 0).sum()),
            training_accuracy=acc,
            training_roc_auc=auc,
            training_brier_score=brier,
            fit_start_utc=samples_df.decision_time.min().isoformat(),
            last_decision_utc=samples_df.decision_time.max().isoformat(),
            last_label_end_utc=samples_df.label_end.max().isoformat()
        )
        card_path = models_dir / f'{symbol}.json'
        write_json(card_path, param_card)
        artifacts_dict[f'models/{symbol}.json'] = sha_file(card_path)
        
        # Save training probabilities (strictly 3 columns: symbol, decision_time, probability)
        prob_df = pd.DataFrame(dict(
            symbol=symbol,
            decision_time=samples_df.decision_time,
            probability=probs
        ))
        prob_path = probs_dir / f'{symbol}.csv'
        prob_df.to_csv(prob_path, index=False)
        artifacts_dict[f'training_probabilities/{symbol}.csv'] = sha_file(prob_path)
        
        # Save training labels separately
        label_df = samples_df[['symbol', 'decision_time', 'label_end', 'label_return', 'label_net_return_text', 'label']].copy()
        label_path = labels_dir / f'{symbol}.csv'
        label_df.to_csv(label_path, index=False)
        artifacts_dict[f'training_labels/{symbol}.csv'] = sha_file(label_path)
        
        models_meta[symbol] = dict(
            model_path=str(model_path),
            model_sha256=model_sha,
            card_path=str(card_path),
            card_sha256=artifacts_dict[f'models/{symbol}.json'],
            probabilities_path=str(prob_path),
            probabilities_sha256=artifacts_dict[f'training_probabilities/{symbol}.csv'],
            labels_path=str(label_path),
            labels_sha256=artifacts_dict[f'training_labels/{symbol}.csv'],
            training_samples=len(samples_df),
            label_1=int((y_true == 1).sum()),
            label_0=int((y_true == 0).sum()),
            accuracy=acc,
            roc_auc=auc,
            brier_score=brier
        )
        
    return models_meta, artifacts_dict, label_card


def execute_research_train(args, root):
    """执行 Task 4 研究模型训练 CLI 入口。"""
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    from cryptoquant.models.research_gates import authorize_research
    qualification = authorize_research(root, cfg, args.prepared_experiment_id, args.window, args.label_policy,
                                      selection_id=getattr(args, 'selection_experiment_id', None), training=True)
    out_dir = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if out_dir.exists():
        raise ValueError('experiment directory already exists; refusing overwrite')
    out_dir.mkdir(parents=True, exist_ok=False)
    
    start_time = datetime.now(timezone.utc).isoformat()
    manifest = dict(
        experiment_id=args.experiment_id,
        type='research_training',
        status='running',
        started_at_utc=start_time,
        prepared_experiment_id=args.prepared_experiment_id,
        window=args.window,
        label_policy=args.label_policy,
        C=0.1,
        **qualification,
        research_config_path=str(args.research_config),
        research_config_hash=cfg.research_config_hash,
        execution_config_hash=cfg.execution_config_hash,
        environment=environment(),
        command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'research-train',
                 '--research-config', str(args.research_config),
                 '--prepared-experiment-id', args.prepared_experiment_id,
                 '--window', args.window,
                 '--label-policy', args.label_policy,
                 '--experiment-id', args.experiment_id]
    )
    selection_id = getattr(args, 'selection_experiment_id', None)
    if selection_id is not None:
        manifest['command'].extend(['--selection-experiment-id', selection_id])
    write_json(out_dir / 'run_manifest.json', manifest)
    
    try:
        source_hash = snapshot_source(out_dir, cfg.research_config_path)
        manifest['source_hash'] = source_hash
        
        # Fit models
        models_meta, artifacts_dict, label_card = train_research_window(
            root, args.prepared_experiment_id, args.window, args.label_policy, cfg, out_dir,
            selection_experiment_id=getattr(args, 'selection_experiment_id', None)
        )
        
        # Copy configs
        (out_dir / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
        (out_dir / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        artifacts_dict['config.toml'] = sha_file(out_dir / 'config.toml')
        artifacts_dict['research_config.toml'] = sha_file(out_dir / 'research_config.toml')
        
        # Generate train_manifest.json
        win = RESEARCH_WINDOWS[args.window]
        train_manifest = dict(
            experiment_id=args.experiment_id,
            type='research_training',
            status='complete',
            started_at_utc=start_time,
            ended_at_utc=datetime.now(timezone.utc).isoformat(),
            prepared_experiment_id=args.prepared_experiment_id,
            prepared_manifest_sha256=sha_file(root / 'artifacts/experiments' / experiment_id(args.prepared_experiment_id) / 'prepared_manifest.json'),
            window=args.window,
            fit_start_utc=win.fit_start.isoformat(),
            fit_end_utc=win.fit_end.isoformat(),
            **label_card,
            label_card=label_card,
            C=0.1,
            model_family='logistic_regression',
            feature_names=ALL_FEATURE_NAMES,
            **qualification,
            execution_config_hash=cfg.execution_config_hash,
            research_config_hash=cfg.research_config_hash,
            symbols=models_meta,
            artifacts=artifacts_dict
        )
        write_json(out_dir / 'train_manifest.json', train_manifest)
        
        # Generate report.md
        report_content = generate_train_report(train_manifest, cfg)
        (out_dir / 'report.md').write_text(report_content, encoding='utf-8')
        artifacts_dict['report.md'] = sha_file(out_dir / 'report.md')
        train_manifest['artifacts'] = artifacts_dict
        write_json(out_dir / 'train_manifest.json', train_manifest)
        
        manifest['status'] = 'complete'
        manifest['ended_at_utc'] = train_manifest['ended_at_utc']
        manifest['train_manifest_sha256'] = sha_file(out_dir / 'train_manifest.json')
        write_json(out_dir / 'run_manifest.json', manifest)
        
        print(f"research-train complete: {args.experiment_id}; window={args.window}; policy={args.label_policy}")
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


def generate_train_report(manifest, cfg):
    lines = [
        f"# {manifest['experiment_id']}：第五轮模型训练报告（{manifest['window']} - {manifest['label_policy']}）",
        "",
        "## 1. 训练配置与边界",
        "",
        f"- 窗口：`{manifest['window']}`（样本区间：{manifest['fit_start_utc']} 至 {manifest['fit_end_utc']}）",
        f"- 标签政策：`{manifest['label_policy']}`",
        "- 模型架构：StandardScaler + LogisticRegression (L2, lbfgs, C=0.1, max_iter=1000, random_state=42)",
        "- 特征工程：12 项连续历史特征（9 项价格/均线 + 3 项资金费率）",
        f"- 样本来源：`{manifest['prepared_experiment_id']}`",
        "",
        "## 2. 三币训练诊断统计",
        "",
        "| 币种 | 训练样本数 | 正样本数 (1) | 负样本数 (0) | 准确率 (Acc) | ROC-AUC | Brier 得分 | 求解器迭代 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    for s, m in manifest['symbols'].items():
        lines.append(f"| {s} | {m['training_samples']} | {m['label_1']} | {m['label_0']} | {m['accuracy']:.4f} | {m['roc_auc']:.4f} | {m['brier_score']:.4f} | 收敛 |")
    
    lines.extend([
        "",
        "## 3. 产物与持久化校验",
        "",
        "- 三币模型 joblib 均持久化保存并重载核对预测概率一致性（diff < 1e-12）。",
        "- 训练概率独立保存为三列 CSV（`symbol`, `decision_time`, `probability`），未来标签独立保存于 `training_labels/` 分表。",
        "",
        "## 4. 限制声明",
        "",
        "- 训练集内的准确率和 ROC-AUC 仅为收敛诊断指标，不代表未见行情的预测能力，亦不代表实际账户交易盈利能力。",
        "- 最终策略表现必须基于独立账户评价。",
        ""
    ])
    return "\n".join(lines)


def load_research_models(root, training_id, research_cfg, expected_window=None, expected_policy=None):
    """加载并核验已训练好的三币研究模型。"""
    root = Path(root).resolve()
    t_dir, run = verify_completed_experiment(root, training_id, 'research_training')
    manifest = json.loads((t_dir / 'train_manifest.json').read_text('utf-8'))
    current_environment = environment()
    recorded = run['environment']
    necessary = ('numpy', 'pandas', 'pyarrow', 'scikit-learn', 'scipy', 'joblib', 'threadpoolctl')
    if (recorded.get('python') != current_environment['python']
            or any(recorded.get('packages', {}).get(name) != current_environment['packages'][name] for name in necessary)):
        raise ValueError('model environment Python or required package version mismatch')
    compatibility = verify_config_binding(root, t_dir, manifest, run, research_cfg)
    card = validate_label_metadata(manifest, expected_policy=expected_policy)
    if manifest.get('label_card') != card:
        raise ValueError('training label card mismatch')
    window, policy = manifest.get('window'), manifest.get('label_policy')
    if window not in RESEARCH_WINDOWS or policy not in research_cfg.label_policies:
        raise ValueError('training window or policy outside requested research scope')
    win = RESEARCH_WINDOWS[window]
    if (manifest.get('feature_names') != ALL_FEATURE_NAMES or manifest.get('C') != .1
            or manifest.get('model_family') != 'logistic_regression'
            or manifest.get('fit_start_utc') != win.fit_start.isoformat()
            or manifest.get('fit_end_utc') != win.fit_end.isoformat()
            or set(manifest.get('symbols', {})) != set(SYMBOLS)
            or tuple(research_cfg.execution_config.symbols) != SYMBOLS
            or any(manifest.get(key) != run.get(key) for key in ['window', 'label_policy', 'C', 'prepared_experiment_id'])):
        raise ValueError('training configuration, symbols or fit boundary mismatch')
    if expected_window is not None and manifest.get('window') != expected_window:
        raise ValueError(f'window mismatch: expected {expected_window}, got {manifest.get("window")}')
    if expected_policy is not None and manifest.get('label_policy') != expected_policy:
        raise ValueError(f'label policy mismatch: expected {expected_policy}, got {manifest.get("label_policy")}')
    
    prepared_id = manifest.get('prepared_experiment_id')
    prepared, prep_run = verify_prepared(root, prepared_id, research_cfg)
    prepared_dir = root / 'artifacts/experiments' / experiment_id(prepared_id)
    parent_compatibility = verify_config_binding(root, prepared_dir, prepared, prep_run, research_cfg)
    parent_profile_matches = prepared['research_config_hash'] == manifest['research_config_hash']
    # A new sixth-profile fit may consume fifth-profile prepared samples, but
    # both profiles must independently bind to their real snapshots and the
    # same frozen training signature. The reverse direction is not authorized.
    if not parent_profile_matches and not (
            compatibility['mode'] == 'exact'
            and parent_compatibility['mode'] == 'fifth_to_sixth_training_signature'):
        raise ValueError('training parent prepared research profile mismatch')
    if (prepared['execution_config_hash'] != manifest['execution_config_hash']
            or prepared['label_policies'][policy] != card):
        raise ValueError('training parent prepared config or policy mismatch')
    parent_sha = prep_run['prepared_manifest_sha256']
    declared_parent_sha = manifest.get('prepared_manifest_sha256')
    legacy_ids = {'EXP-064', 'EXP-065', 'EXP-066', 'EXP-067', 'EXP-093', 'EXP-094'}
    if declared_parent_sha != parent_sha:
        if declared_parent_sha is not None or training_id not in legacy_ids or prepared_id != 'EXP-063':
            raise ValueError('training prepared manifest SHA mismatch or missing')
        compatibility['prepared_binding'] = 'legacy_fifth_verified_parent'
    else:
        compatibility['prepared_binding'] = 'sha256'
    compatibility.update(prepared_experiment_id=prepared_id, prepared_manifest_sha256=parent_sha,
                         training_experiment_id=training_id,
                         prepared_research_config_hash=prepared['research_config_hash'],
                         prepared_training_compatibility='exact' if parent_profile_matches else parent_compatibility['mode'])

    # All three metadata/file/table checks finish before the first deserialization.
    checked = {}
    for symbol, info in manifest['symbols'].items():
        files = {}
        for kind in ('model', 'card', 'probabilities', 'labels'):
            files[kind] = bound_metadata_file(root, t_dir, manifest, info, kind + '_path', kind + '_sha256')
        params = json.loads(files['card'].read_text('utf-8'))
        samples = load_research_samples(root, prepared_id, window, policy, symbol, research_cfg)
        n = len(samples)
        if (n == 0 or info.get('training_samples') != n or info.get('label_1') != int(samples.label.sum())
                or info.get('label_0') != int((samples.label == 0).sum())
                or params.get('symbol') != symbol or params.get('window') != window
                or params.get('label_policy') != policy or params.get('C') != .1
                or params.get('solver') != MODEL_PARAMETERS['solver']
                or params.get('max_iter') != MODEL_PARAMETERS['max_iter']
                or params.get('classes') != [0, 1] or params.get('feature_names') != ALL_FEATURE_NAMES
                or params.get('training_samples') != n
                or params.get('training_label_1') != info['label_1'] or params.get('training_label_0') != info['label_0']
                or params.get('fit_start_utc') != samples.decision_time.min().isoformat()
                or params.get('last_decision_utc') != samples.decision_time.max().isoformat()
                or params.get('last_label_end_utc') != samples.label_end.max().isoformat()
                or samples.label_end.max() >= pd.Timestamp(win.fit_end)):
            raise ValueError(f'model parameter card or training sample boundary mismatch: {symbol}')
        probability = pd.read_csv(files['probabilities'])
        labels = pd.read_csv(files['labels'], dtype={'label_net_return_text': 'object'})
        if list(probability) != ['symbol', 'decision_time', 'probability'] or list(labels) != [
                'symbol', 'decision_time', 'label_end', 'label_return', 'label_net_return_text', 'label']:
            raise ValueError('training probability or label table column mismatch')
        for table, time_names in [(probability, ['decision_time']), (labels, ['decision_time', 'label_end'])]:
            try:
                for time_name in time_names:
                    table[time_name] = pd.to_datetime(table[time_name])
            except (ValueError, TypeError) as exc:
                raise ValueError('invalid saved training table UTC') from exc
            _utc_columns(table, time_names)
            if len(table) != n or not (table.symbol == symbol).all() or not table.decision_time.equals(samples.decision_time):
                raise ValueError('training table symbols, count or decision boundary mismatch')
        if (not labels.label_end.equals(samples.label_end) or not labels.label.equals(samples.label)
                or not np.allclose(labels.label_return, samples.label_return, rtol=0, atol=1e-14)
                or not np.isfinite(probability.probability).all()
                or not probability.probability.between(0, 1).all()):
            raise ValueError('saved training labels or probability mismatch')
        if policy == GROSS_POLICY:
            if not labels.label_net_return_text.isna().all():
                raise ValueError('gross saved labels carry net returns')
        elif not labels.label_net_return_text.equals(samples.label_net_return_text):
            raise ValueError('saved training net labels mismatch')
        checked[symbol] = (files, params, samples, probability)
    models = {}
    for symbol, (files, params, samples, probability) in checked.items():
        model = joblib.load(files['model'])
        if (not isinstance(model, Pipeline) or list(model.named_steps) != ['scaler', 'classifier']
                or not isinstance(model.named_steps['scaler'], StandardScaler)
                or not isinstance(model.named_steps['classifier'], LogisticRegression)
                or list(model.feature_names_in_) != ALL_FEATURE_NAMES or list(model.classes_) != [0, 1]):
            raise ValueError('model pipeline, features or classes mismatch')
        scaler, classifier = model.named_steps['scaler'], model.named_steps['classifier']
        x = feature_matrix(samples, ALL_FEATURE_NAMES).to_numpy()
        variance, mean = x.var(axis=0), x.mean(axis=0)
        # StandardScaler treats variance below its floating error bound as constant.
        eps, n = np.finfo(np.float64).eps, len(samples)
        expected_scale = np.sqrt(variance)
        expected_scale[variance <= n * eps * variance + (n * mean * eps) ** 2] = 1
        if (not np.all(np.asarray(scaler.n_samples_seen_) == len(samples)) or scaler.n_features_in_ != 12
                or not scaler.with_mean or not scaler.with_std
                or list(scaler.feature_names_in_) != ALL_FEATURE_NAMES
                or not np.allclose(scaler.mean_, x.mean(axis=0), rtol=0, atol=1e-12)
                or not np.allclose(scaler.var_, x.var(axis=0), rtol=1e-12, atol=1e-15)
                or not np.allclose(scaler.scale_, expected_scale, rtol=1e-12, atol=1e-15)
                or not np.allclose(scaler.mean_, params['scaler_mean'], rtol=0, atol=1e-12)
                or not np.allclose(scaler.scale_, params['scaler_scale'], rtol=0, atol=1e-12)
                or classifier.C != .1
                or any(classifier.get_params().get(k) != v for k, v in MODEL_PARAMETERS.items())
                or list(classifier.classes_) != [0, 1]
                or not np.allclose(classifier.coef_[0], params['coefficients'], rtol=0, atol=1e-12)
                or not np.allclose(classifier.intercept_[0], params['intercept'], rtol=0, atol=1e-12)
                or np.any(classifier.n_iter_ >= MODEL_PARAMETERS['max_iter'])):
            raise ValueError('model scaler training provenance or classifier parameters mismatch')
        if not np.allclose(predict_probabilities(model, samples), probability.probability, rtol=0, atol=1e-12):
            raise ValueError('reloaded model training probability mismatch')
        models[symbol] = model
    # Return a copy with verified provenance; never rewrite a frozen manifest.
    manifest = dict(manifest, verified_source=compatibility)
    return models, manifest
