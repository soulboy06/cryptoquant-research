"""离线训练九个候选模型；不读取validation/test，不选择交易阈值。"""

from datetime import datetime, timezone
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score

from cryptoquant.baselines.io import experiment_id
from cryptoquant.cli import write_json
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.features import FEATURE_NAMES, ALL_FEATURE_NAMES
from cryptoquant.models.labels import GROSS_POLICY, label_metadata
from cryptoquant.models.training import C_VALUES, THRESHOLDS, MODEL_PARAMETERS, LIGHTGBM_CANDIDATE_PARAMS, fit_model, load_training_samples, predict_probabilities


def execute(args, root):
    config = load_config(args.config)
    output = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if output.exists():
        raise ValueError('experiment directory already exists; refusing overwrite')
    output.mkdir(parents=True, exist_ok=False)
    feature_names = ALL_FEATURE_NAMES if config.feature_policy == 'kline_and_funding' else FEATURE_NAMES
    model_family = config.model_family
    manifest = dict(experiment_id=args.experiment_id, type='model_training', status='running',
                    started_at_utc=datetime.now(timezone.utc).isoformat(), config_hash=config.config_hash,
                    sample_experiment_id=args.sample_experiment_id, period='development',
                    start_utc=config.development_start, label_end_before_utc=config.development_end,
                    feature_names=feature_names, feature_policy=config.feature_policy, model_family=model_family,
                    C_values=C_VALUES, thresholds_for_later_validation=THRESHOLDS,
                    parameters=LIGHTGBM_CANDIDATE_PARAMS if model_family == 'lightgbm' else MODEL_PARAMETERS,
                    regularization='LightGBM tree constraints' if model_family == 'lightgbm' else 'L2 (l1_ratio=0)',
                    environment=environment(), cpu_threads=1, selected_candidate=None,
                    command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'train', '--config', str(args.config.resolve()),
                             '--sample-experiment-id', args.sample_experiment_id, '--experiment-id', args.experiment_id], models=[])
    manifest.update(label_metadata(GROSS_POLICY))
    write_json(output / 'train_manifest.json', manifest)
    try:
        manifest['source_hash'] = snapshot_source(output, args.config)
        frames, manifest['samples'] = load_training_samples(root, args.sample_experiment_id, config)
        (output / 'models').mkdir()
        (output / 'training_probabilities').mkdir()
        (output / 'training_labels').mkdir()
        for symbol, frame in frames.items():
            frame.loc[:, ['symbol', 'decision_time', 'label_start', 'label_end', 'label_return', 'label']].to_csv(
                output / 'training_labels' / (symbol + '.csv'), index=False)
        for C in C_VALUES:
            for symbol in config.symbols:
                item = dict(symbol=symbol, C=C, status='running', samples=len(frames[symbol]))
                manifest['models'].append(item)
                write_json(output / 'train_manifest.json', manifest)
                started = perf_counter()
                try:
                    frame = frames[symbol]
                    model = fit_model(frame, C, feature_names=feature_names, model_family=model_family)
                    probability = predict_probabilities(model, frame)
                    model_path = output / 'models' / f'{symbol}_C-{C:g}.joblib'
                    probability_path = output / 'training_probabilities' / f'{symbol}_C-{C:g}.csv'
                    card_path = model_path.with_suffix('.json')
                    joblib.dump(model, model_path, compress=3)
                    # Only reload our own newly created local model. This verifies persistence
                    # without fitting again or opening the untouched evaluation datasets.
                    reloaded = joblib.load(model_path)
                    if not np.array_equal(probability, predict_probabilities(reloaded, frame)):
                        raise ValueError('saved model predictions changed after reload')
                    if model_family == 'logistic_regression':
                        scaler, classifier = model.named_steps['scaler'], model.named_steps['classifier']
                        if int(scaler.n_samples_seen_) != len(frame):
                            raise ValueError('scaler fitted sample count mismatch')
                        card = dict(symbol=symbol, C=C, model_family=model_family, feature_names=feature_names,
                                    classifier_parameters=classifier.get_params(), regularization='L2',
                                    classes=classifier.classes_.tolist(), coefficients=classifier.coef_.tolist(),
                                    intercept=classifier.intercept_.tolist(), iterations=classifier.n_iter_.tolist(),
                                    scaler=dict(parameters=scaler.get_params(), mean=scaler.mean_.tolist(),
                                                variance=scaler.var_.tolist(), scale=scaler.scale_.tolist(),
                                                n_samples_seen=int(scaler.n_samples_seen_)),
                                    sample_provenance=manifest['samples']['inputs'][symbol],
                                    environment=manifest['environment'])
                        iterations = int(classifier.n_iter_.max())
                    else:
                        card = dict(symbol=symbol, C=C, model_family=model_family, feature_names=feature_names,
                                    classifier_parameters=model.get_params(), regularization='LightGBM tree constraints',
                                    classes=model.classes_.tolist(),
                                    feature_importances=dict(zip(feature_names, model.feature_importances_.tolist())),
                                    sample_provenance=manifest['samples']['inputs'][symbol],
                                    environment=manifest['environment'])
                        iterations = int(model.n_estimators)
                    card.update(label_metadata(GROSS_POLICY))
                    write_json(card_path, card)
                    pd.DataFrame(dict(symbol=symbol, decision_time=frame.decision_time,
                                      probability=probability)).to_csv(probability_path, index=False)
                    item.update(status='complete', model_path=model_path.relative_to(output).as_posix(),
                                model_sha256=sha_file(model_path), card_path=card_path.relative_to(output).as_posix(),
                                probabilities_path=probability_path.relative_to(output).as_posix(),
                                reload_verified=True, iterations=iterations,
                                elapsed_seconds=perf_counter() - started,
                                training_accuracy=float(accuracy_score(frame.label, probability >= .5)),
                                training_roc_auc=float(roc_auc_score(frame.label, probability)),
                                training_brier=float(brier_score_loss(frame.label, probability)),
                                majority_accuracy=float(frame.label.value_counts().max() / len(frame)),
                                probability_min=float(probability.min()), probability_max=float(probability.max()))
                    print(f'trained {symbol} C={C:g}: {len(frame)} samples; reload verified', flush=True)
                except Exception as exc:
                    item.update(status='failed', error_type=type(exc).__name__, error=str(exc), elapsed_seconds=perf_counter() - started)
                write_json(output / 'train_manifest.json', manifest)
        if any(item['status'] != 'complete' for item in manifest['models']):
            raise ValueError('one or more predefined fits failed; see models in train_manifest.json')
        write_json(output / 'probability_manifest.json', dict(type='training_probabilities',
                   training_experiment_id=args.experiment_id, **label_metadata(GROSS_POLICY),
                   files={item['probabilities_path']: sha_file(output / item['probabilities_path']) for item in manifest['models']}))
        pd.DataFrame(manifest['models']).to_csv(output / 'training_diagnostics.csv', index=False)
        model_title = 'LightGBM 树模型训练' if model_family == 'lightgbm' else '逻辑回归模型训练'
        lines = ['# ' + args.experiment_id + ' ' + model_title, '',
                 f'BTC、ETH、SOL各用2022—2024的训练样本（特征策略：{config.feature_policy}，共{len(feature_names)}项特征）独立拟合{model_family}。候选组别（对应C标识：0.1／1／10），共9个模型已保存并重新加载核对概率一致。', '',
                 '以下全是训练集内诊断，不是验证成绩、交易收益或盈利证明。未根据这些数字选参数；阈值0.55／0.60／0.65留待2025验证，同候选共享模型预测。', '',
                 '| 交易对 | 候选标识(C) | 样本数 | 训练准确率 | 多数类别准确率 | 训练ROC-AUC | 训练Brier | 树棵数/迭代 |',
                 '| --- | --- | --- | --- | --- | --- | --- | --- |']
        lines += [f'| {x["symbol"]} | {x["C"]:g} | {x["samples"]} | {x["training_accuracy"]:.2%} | {x["majority_accuracy"]:.2%} | {x["training_roc_auc"]:.4f} | {x["training_brier"]:.4f} | {x["iterations"]} |' for x in manifest['models']]
        lines += ['', '固定参数：L2、lbfgs、max_iter=1000、class_weight=None、random_state=42，CPU单线程；scikit-learn 1.8起用l1_ratio=0表达L2。没有自动更换算法、增加迭代或搜索其他特征。', '',
                  f'仅加载{args.sample_experiment_id}的三份training_samples Parquet，逐份核对SHA、类别、UTC决策与标签截止。输入取{len(feature_names)}个历史特征，不含未来label／label_return；scaler只fit训练样本。2025验证与2026保留测试文件均未读取。', '',
                  'models/*.joblib包含每个模型和对应scaler；同名JSON包含系数、标准化参数及来源。只加载自己保存的可信模型，并使用同一锁定环境。training_probabilities/*.csv仅含symbol、decision_time、probability三列，为训练期诊断，不是未见行情的预测成绩；未来答案单独保存在training_labels/，不能作为交易输入。', '',
                  '训练完成不代表能赚钱。下一步实现2025验证期预测和共用交易接口，扣除成本，与EMA和买入持有比较；合格并冻结后才能使用保留测试。', '',
                  '模型参数API依据：[scikit-learn官方文档](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)。']
        (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        manifest.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(),
                        artifacts={p.relative_to(output).as_posix(): sha_file(p) for p in output.rglob('*')
                                   if p.is_file() and p.name != 'train_manifest.json' and 'source_snapshot' not in p.parts})
    except Exception as exc:
        manifest.update(status='failed', ended_at_utc=datetime.now(timezone.utc).isoformat(), error=str(exc))
        write_json(output / 'failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
        write_json(output / 'train_manifest.json', manifest)
        raise
    write_json(output / 'train_manifest.json', manifest)
    print(f'train complete: {args.experiment_id}; report: {output / "report.md"}')
    return 0
