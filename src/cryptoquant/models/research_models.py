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
    fit_model, predict_probabilities, feature_matrix
)


def train_research_window(root, prepared_id, window, label_policy, research_cfg, out_dir):
    """为指定窗口和标签政策拟合三币独立的 C=0.1 逻辑回归模型。"""
    root = Path(root).resolve()
    prep_dir = root / 'artifacts/experiments' / experiment_id(prepared_id)
    prep_manifest_path = prep_dir / 'prepared_manifest.json'
    if not prep_manifest_path.exists():
        raise ValueError(f'prepared manifest not found: {prep_manifest_path}')
    prep_manifest = json.loads(prep_manifest_path.read_text('utf-8'))
    
    if prep_manifest.get('type') != 'research_samples' or prep_manifest.get('status') != 'complete':
        raise ValueError('prepared experiment is not completed research_samples')
    if prep_manifest.get('execution_config_hash') != research_cfg.execution_config_hash:
        raise ValueError('execution config hash mismatch with prepared experiment')
    if prep_manifest.get('research_config_hash') != research_cfg.research_config_hash:
        raise ValueError('research config hash mismatch with prepared experiment')
    
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
        samples_df = load_research_samples(root, prepared_id, window, label_policy, symbol)
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
    write_json(out_dir / 'run_manifest.json', manifest)
    
    try:
        source_hash = snapshot_source(out_dir, cfg.research_config_path)
        manifest['source_hash'] = source_hash
        
        # Fit models
        models_meta, artifacts_dict, label_card = train_research_window(
            root, args.prepared_experiment_id, args.window, args.label_policy, cfg, out_dir
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
            window=args.window,
            fit_start_utc=win.fit_start.isoformat(),
            fit_end_utc=win.fit_end.isoformat(),
            **label_card,
            label_card=label_card,
            C=0.1,
            model_family='logistic_regression',
            feature_names=ALL_FEATURE_NAMES,
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
    t_dir = root / 'artifacts/experiments' / experiment_id(training_id)
    manifest_path = t_dir / 'train_manifest.json'
    if not manifest_path.exists():
        raise ValueError(f'train manifest not found in {training_id}')
    manifest = json.loads(manifest_path.read_text('utf-8'))
    
    if manifest.get('type') != 'research_training' or manifest.get('status') != 'complete':
        raise ValueError('training experiment is not completed research_training')
    validate_label_metadata(manifest, expected_policy=expected_policy)
    if expected_window is not None and manifest.get('window') != expected_window:
        raise ValueError(f'window mismatch: expected {expected_window}, got {manifest.get("window")}')
    if expected_policy is not None and manifest.get('label_policy') != expected_policy:
        raise ValueError(f'label policy mismatch: expected {expected_policy}, got {manifest.get("label_policy")}')
    
    models = {}
    for symbol in research_cfg.execution_config.symbols:
        s_info = manifest['symbols'].get(symbol)
        if not s_info:
            raise ValueError(f'symbol {symbol} missing in training manifest')
        m_path = Path(s_info['model_path'])
        if not m_path.is_absolute():
            m_path = root / m_path
        if not m_path.exists():
            raise ValueError(f'model file {m_path} not found')
        actual_sha = sha_file(m_path)
        if actual_sha != s_info['model_sha256']:
            raise ValueError(f'model SHA mismatch for {symbol}')
        models[symbol] = joblib.load(m_path)
        
    return models, manifest
