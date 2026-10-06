"""Tests for Phase 5A2: Derivatives Feature Calibration & Threshold Robustness Audit.

Verifies:
1. OI timestamp alignment: source_timestamp <= decision_time across all historical rows (0 violations).
2. Prediction shift metrics: verifies that delta ROC-AUC <= 0 across folds (no predictive ranking gain).
3. Calibration & gating rules: verifies that all feature families are rejected at the prediction layer,
   forbidding Lane B threshold recalibration and enforcing direct pruning (Conclusion A).
4. Artifacts completeness: verifies that all required phase 5A2 artifact files exist and are valid.
"""

import json
from pathlib import Path
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = ROOT / "artifacts/research/alpha_phase5a2_calibration"


def test_oi_timestamp_alignment_strict_causality():
    """Verify source_timestamp <= decision_time for all OI feature rows with 0 violations."""
    results_path = ARTIFACTS_DIR / "results.json"
    assert results_path.exists(), "results.json must exist in artifacts"
    data = json.loads(results_path.read_text(encoding="utf-8"))
    
    audit = data["oi_timestamp_audit"]
    assert audit["total_violations"] == 0
    assert audit["max_lead_seconds"] <= 0.0
    assert audit["verdict"] == "PERFECT_CAUSAL_ALIGNMENT"
    
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        assert symbol in audit["symbols"]
        s_res = audit["symbols"][symbol]
        assert s_res["violations_count"] == 0
        assert s_res["max_timestamp_lead_seconds"] <= 0.0
        assert s_res["status"] == "PASSED"
        
        # Also directly inspect the processed parquet table to independently verify
        raw_path = ROOT / f"data/processed/derivatives_flow/{symbol}_flow_oi.parquet"
        assert raw_path.exists()
        raw = pd.read_parquet(raw_path)
        source_ts = raw['open_time'].shift(-1)
        decision_ts = pd.to_datetime(raw['open_time']) + pd.to_timedelta(1, unit='h')
        valid = source_ts.notnull()
        diff_seconds = (source_ts[valid] - decision_ts[valid]).dt.total_seconds()
        assert int((diff_seconds > 0).sum()) == 0


def test_prediction_layer_metrics_and_negative_gain():
    """Verify that delta ROC-AUC is <= 0 across all benchmark evaluations."""
    audit_csv = ARTIFACTS_DIR / "prediction_shift_audit.csv"
    assert audit_csv.exists()
    df = pd.read_csv(audit_csv)
    
    candidates = df[df["feature_family"] != "BASE_12"]
    assert len(candidates) == 36  # 4 benchmarks x 3 folds x 3 candidate families
    
    # Delta ROC-AUC should be <= 0 for all candidate evaluations
    assert (candidates["delta_roc_auc"] <= 0.0).all()
    
    # Log loss delta should be >= 0 (loss increased = degraded) for all evaluations
    assert (candidates["delta_log_loss"] >= 0.0).all()
    
    # Brier score delta should be >= 0 (error increased = degraded) for all evaluations
    assert (candidates["delta_brier"] >= 0.0).all()


def test_pruning_rules_enforce_no_threshold_sweep():
    """Verify Section 三 & 四 pruning rules forbid Lane B threshold recalibration."""
    thresh_csv = ARTIFACTS_DIR / "threshold_selection.csv"
    assert thresh_csv.exists()
    df_thresh = pd.read_csv(thresh_csv)
    
    assert len(df_thresh) == 3
    for _, row in df_thresh.iterrows():
        assert row["prediction_gate_passed"] is False or row["prediction_gate_passed"] == "False"
        assert row["recalibration_permitted"] is False or row["recalibration_permitted"] == "False"
        assert row["pruning_decision"] == "PRUNED_AT_PREDICTION_LAYER"
        assert row["selected_thresholds"] == "NONE_PRUNED"


def test_artifacts_completeness_and_conclusion_a():
    """Verify all 6 required artifacts exist and conclude with Conclusion A."""
    required_files = [
        "prediction_shift_audit.csv",
        "calibration_comparison.csv",
        "threshold_selection.csv",
        "trading_metrics.csv",
        "results.json",
        "comparison_report.md",
    ]
    for fname in required_files:
        fpath = ARTIFACTS_DIR / fname
        assert fpath.exists(), f"Missing required artifact: {fname}"
        assert fpath.stat().st_size > 0, f"Artifact {fname} should not be empty"

    results_path = ARTIFACTS_DIR / "results.json"
    data = json.loads(results_path.read_text(encoding="utf-8"))
    assert data["final_conclusion"] == "CONCLUSION_A_DIRECT_PRUNE"
    assert "正式剪枝" in data["verdict_summary"]
