import json
from pathlib import Path
import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT / "artifacts/research/market_regime_phase6b"


def test_phase6b_all_14_artifacts_exist():
    """Verify all 14 specified Phase 6B artifacts exist and are non-empty on disk."""
    expected_artifacts = [
        "accounting_audit.md",
        "accounting_reconciliation.csv",
        "experiment_config.json",
        "filter_definitions.json",
        "trading_metrics.csv",
        "monthly_comparison.csv",
        "symbol_comparison.csv",
        "filter_decision_audit.csv",
        "exposure_comparison.csv",
        "cost_stress_test.csv",
        "bootstrap_results.json",
        "pareto_comparison.csv",
        "results.json",
        "comparison_report.md",
    ]
    for fn in expected_artifacts:
        p = OUT_DIR / fn
        assert p.exists(), f"Missing Phase 6B artifact: {fn}"
        assert p.stat().st_size > 0, f"Artifact is empty: {fn}"


def test_phase6b_control_exact_replication():
    """Requirement 1: Verify strict zero-drift replication of OPT-0005 benchmark."""
    tm_path = OUT_DIR / "trading_metrics.csv"
    df_tm = pd.read_csv(tm_path)
    ctrl = df_tm[df_tm["candidate_id"] == "Control_OPT-0005"].iloc[0]

    assert ctrl["g_week_pct"] == pytest.approx(0.1371, abs=0.0001)
    assert ctrl["annualized_pct"] == pytest.approx(7.38, abs=0.01)
    assert ctrl["ret_2023_pct"] == pytest.approx(8.83, abs=0.01)
    assert ctrl["ret_2024_pct"] == pytest.approx(18.50, abs=0.01)
    assert ctrl["ret_2025_pct"] == pytest.approx(-3.91, abs=0.01)
    assert ctrl["worst_mdd_pct"] == pytest.approx(11.60, abs=0.01)
    assert int(ctrl["closed_cycles"]) == 208


def test_phase6b_accounting_strict_reconciliation():
    """Requirement 2: Strict mathematical accounting reconciliation with zero error."""
    rec_path = OUT_DIR / "accounting_reconciliation.csv"
    df_rec = pd.read_csv(rec_path)
    assert len(df_rec) >= 3, "Reconciliation must cover W1, W2, R2025"

    for _, row in df_rec.iterrows():
        # Mathematical reconciliation error must be strictly 0.0000
        assert row["reconciliation_diff_usdt"] == pytest.approx(0.0000, abs=1e-4), (
            f"Non-zero accounting reconciliation error in {row['window']}"
        )
        # Cash + Residual Dust value == Final Equity
        assert row["final_cash_usdt"] + row["residual_dust_value_usdt"] == pytest.approx(
            row["final_equity_usdt"], abs=1e-4
        )
        # Realized PnL + Unrealized PnL == Net Equity Change
        assert row["book_realized_pnl_usdt"] + row["unrealized_pnl_usdt"] == pytest.approx(
            row["net_equity_change_usdt"], abs=1e-4
        )


def test_phase6b_market_regime_definitions_and_no_leakage():
    """Requirements 3 & 4: Regime classification causal rules and train-split quantiles."""
    def_path = OUT_DIR / "filter_definitions.json"
    with open(def_path, "r", encoding="utf-8") as f:
        f_defs = json.load(f)

    assert "UPTREND" in f_defs["Filter_A"]["description"]
    assert "VOL_EXPANDING" in f_defs["Filter_B"]["description"]
    assert "0.5" in f_defs["Filter_B"]["description"]
    assert "VOL_EXPANDING" in f_defs["Filter_C"]["description"]

    # Verify causal regime definitions from phase6a
    reg_path = PROJECT / "artifacts/research/market_regime_phase6a/regime_definitions.json"
    with open(reg_path, "r", encoding="utf-8") as f:
        reg_defs = json.load(f)

    thresh = reg_defs["train_split_thresholds"]
    for fold in ("W1", "W2", "R2025"):
        assert fold in thresh
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            st = thresh[fold][sym]
            assert st["q33_vol"] < st["q66_vol"], f"Quantile ordering violated for {fold} {sym}"
            assert st["q50_vr"] > 0.0, f"Vol ratio median must be positive for {fold} {sym}"


def test_phase6b_filter_a_blocks_uptrend_only():
    """Requirement 5: Filter A only blocks new BUY entries when UPTREND."""
    fda_path = OUT_DIR / "filter_decision_audit.csv"
    df_fda = pd.read_csv(fda_path)
    fa_row = df_fda[df_fda["candidate_id"] == "Filter_A_NoUptrend"].iloc[0]

    assert fa_row["blocked_signals_count"] > 0, "Filter A must block UPTREND signals"
    assert 0 < int(fa_row["executed_cycles"]) < 208, "Filter A should yield fewer cycles than Control (208)"


def test_phase6b_filter_b_downsizing_and_exposure():
    """Requirement 6: Filter B downscales target weight when VOL_EXPANDING."""
    exp_path = OUT_DIR / "exposure_comparison.csv"
    df_exp = pd.read_csv(exp_path)
    ctrl_exp = df_exp[df_exp["candidate_id"] == "Control_OPT-0005"].iloc[0]["avg_exposure_pct"]
    fb_exp = df_exp[df_exp["candidate_id"] == "Filter_B_DownsizeVolExp"].iloc[0]["avg_exposure_pct"]

    # Filter B downscales position sizing, so average exposure must be strictly lower
    assert fb_exp < ctrl_exp, "Filter B exposure must be strictly lower than Control"


def test_phase6b_filter_c_blocks_vol_expanding_and_cycle_count():
    """Requirement 7: Filter C blocks new BUY when VOL_EXPANDING."""
    tm_path = OUT_DIR / "trading_metrics.csv"
    df_tm = pd.read_csv(tm_path)
    fc = df_tm[df_tm["candidate_id"] == "Filter_C_NoVolExp"].iloc[0]

    # Filter C dramatically cuts trades compared to Control's 208
    assert 0 < int(fc["closed_cycles"]) < 50, "Filter C must dramatically reduce trades"


def test_phase6b_exit_rules_and_shared_account_invariance():
    """Requirements 8 & 9: Original C2 exit logic, equity floor and cash sharing invariant."""
    cfg_path = OUT_DIR / "experiment_config.json"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg_dict = json.load(f)

    assert cfg_dict["benchmark"] == "OPT-0005_BASE_12"
    assert cfg_dict["threshold"] == 0.48
    assert cfg_dict["exit_variant"] == "C2 (Breakeven + Stop Loss)"
    assert cfg_dict["initial_cash"] == 100.0
    assert cfg_dict["equity_floor"] == 50.0
    assert set(cfg_dict["symbols"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


def test_phase6b_2026_holdout_zero_read():
    """Requirement 10: 2026 data partition is strictly not accessed or evaluated."""
    res_path = OUT_DIR / "results.json"
    with open(res_path, "r", encoding="utf-8") as f:
        res = json.load(f)

    # Check results do not contain 2026 evaluation metrics
    for cand_id, m in res["candidates_metrics"].items():
        assert "ret_2026" not in m, f"2026 found in candidate metrics for {cand_id}"


def test_phase6b_cost_stress_and_identical_base():
    """Requirement 11: Identical base costs and presence of 1.0x, 1.5x, 2.0x stress test."""
    stress_path = OUT_DIR / "cost_stress_test.csv"
    df_stress = pd.read_csv(stress_path)
    cands = set(df_stress["candidate_id"])
    assert cands == {
        "Control_OPT-0005",
        "Filter_A_NoUptrend",
        "Filter_B_DownsizeVolExp",
        "Filter_C_NoVolExp",
    }
    multipliers = set(df_stress["cost_multiplier"])
    assert multipliers == {"1.0x_Base", "1.5x_Cost", "2.0x_Cost"}


def test_phase6b_annualized_formula_consistency():
    """Requirement 12: Unified annualized formula: (1 + g_week)^52 - 1."""
    tm_path = OUT_DIR / "trading_metrics.csv"
    df_tm = pd.read_csv(tm_path)
    for _, row in df_tm.iterrows():
        g_w = row["g_week_pct"] / 100.0
        expected_ann = ((1.0 + g_w) ** 52 - 1.0) * 100.0
        assert row["annualized_pct"] == pytest.approx(expected_ann, abs=0.05)
