import json
from pathlib import Path
import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT / "artifacts/research/market_regime_phase6a"


def test_phase6a_artifacts_exist():
    """Verify all 8 Phase 6A diagnostic artifacts exist on disk."""
    expected_files = [
        "regime_definitions.json",
        "benchmark_replication.json",
        "regime_performance_by_dimension.csv",
        "regime_performance_by_symbol_year.csv",
        "loss_attribution_2025.csv",
        "loss_mechanism_breakdown.csv",
        "regime_cross_year_stability.csv",
        "phase6a_diagnostic_report.md",
    ]
    for fn in expected_files:
        p = OUT_DIR / fn
        assert p.exists(), f"Missing artifact: {fn}"
        assert p.stat().st_size > 0, f"Artifact is empty: {fn}"


def test_phase6a_benchmark_replication():
    """Verify strict zero-drift replication of OPT-0005 benchmark."""
    rep_path = OUT_DIR / "benchmark_replication.json"
    with open(rep_path, "r", encoding="utf-8") as f:
        rep = json.load(f)

    assert rep["candidate_id"] == "OPT-0005_BASE_12"
    assert rep["g_week_pct"] == 0.1371
    assert rep["annualized_pct"] == 7.38
    assert rep["ret_2023_pct"] == 8.83
    assert rep["ret_2024_pct"] == 18.5
    assert rep["ret_2025_pct"] == -3.91
    assert rep["worst_mdd_pct"] == 11.6
    assert rep["total_closed_cycles"] == 208
    assert rep["cycles_per_year"] == {"2023": 38, "2024": 88, "2025": 82}


def test_phase6a_regime_definitions_and_thresholds():
    """Verify 4 explicit dimensions and train-split quantile monotonicities."""
    def_path = OUT_DIR / "regime_definitions.json"
    with open(def_path, "r", encoding="utf-8") as f:
        reg_defs = json.load(f)

    dims = reg_defs["dimensions"]
    assert "dim1_trend_regime" in dims
    assert "dim2_vol_level" in dims
    assert "dim3_vol_dynamic" in dims
    assert "dim4_price_structure" in dims

    thresholds = reg_defs["train_split_thresholds"]
    for fold_name in ("W1", "W2", "R2025"):
        assert fold_name in thresholds
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            assert sym in thresholds[fold_name]
            th = thresholds[fold_name][sym]
            assert th["q33_trend"] < th["q66_trend"]
            assert th["q33_vol"] < th["q66_vol"]
            assert th["q50_vr"] > 0.0


def test_phase6a_loss_mechanisms_2025():
    """Verify 2025 loss attribution breakdown integrity."""
    df_mech = pd.read_csv(OUT_DIR / "loss_mechanism_breakdown.csv")
    assert len(df_mech) > 0

    total_loss_trades = df_mech["loss_trades_count"].sum()
    assert total_loss_trades == 42

    total_share = df_mech["share_of_gross_losses_pct"].sum()
    assert abs(total_share - 100.0) < 0.2

    # Top mechanism must be CHOP_WHIPSAW_STOP
    top_mech = df_mech.iloc[0]
    assert top_mech["loss_mechanism"] == "CHOP_WHIPSAW_STOP"
    assert top_mech["share_of_gross_losses_pct"] > 50.0


def test_phase6a_cross_year_stability():
    """Verify cross-year regime stability metrics and contracting vol consistency."""
    df_stab = pd.read_csv(OUT_DIR / "regime_cross_year_stability.csv")
    assert len(df_stab) == 10

    # VOL_CONTRACTING must be consistently profitable across all 3 years
    vol_cont = df_stab[df_stab["regime_state"] == "VOL_CONTRACTING"].iloc[0]
    assert vol_cont["consistent_profitable"] is True or vol_cont["consistent_profitable"] == 1
    assert vol_cont["pnl_2023"] > 0
    assert vol_cont["pnl_2024"] > 0
    assert vol_cont["pnl_2025"] > 0
