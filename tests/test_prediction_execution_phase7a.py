import json
from pathlib import Path
import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = PROJECT / 'artifacts/research/prediction_execution_phase7a'


def test_phase7a_artifacts_exist():
    required_files = [
        'label_definition_audit.md',
        'benchmark_replication.json',
        'prediction_decision_alignment.csv',
        'executed_trade_alignment.csv',
        'prediction_execution_mismatch.csv',
        'holding_period_analysis.csv',
        'probability_pnl_analysis.csv',
        'symbol_year_comparison.csv',
        'statistical_uncertainty.json',
        'results.json',
        'comparison_report.md',
    ]
    for fname in required_files:
        fpath = ARTIFACT_DIR / fname
        assert fpath.exists(), f"Required artifact {fname} missing"
        assert fpath.stat().st_size > 0, f"Artifact {fname} is empty"


def test_benchmark_replication_exact():
    repl_path = ARTIFACT_DIR / 'benchmark_replication.json'
    data = json.loads(repl_path.read_text(encoding='utf-8'))
    assert data['replication_status'] == 'EXACT_MATCH'
    obs = data['observed_metrics']
    assert obs['closed_cycles'] == 208
    assert abs(obs['g_week_pct'] - 0.1371) < 1e-3
    assert abs(obs['annualized_pct'] - 7.38) < 0.1
    assert abs(obs['ret_2023_pct'] - 8.83) < 0.1
    assert abs(obs['ret_2024_pct'] - 18.50) < 0.1
    assert abs(obs['ret_2025_pct'] - (-3.91)) < 0.1
    assert abs(obs['worst_mdd_pct'] - 11.60) < 0.1


def test_decision_alignment_integrity():
    df_dec = pd.read_csv(ARTIFACT_DIR / 'prediction_decision_alignment.csv')
    assert len(df_dec) == 19725, f"Expected 19725 decisions, got {len(df_dec)}"
    expected_cols = [
        'decision_time', 'fold', 'symbol', 'model_probability', 'prediction_label',
        'actual_4h_label', 'actual_4h_net_return', 'original_target_weight',
        'actual_position_before_decision', 'alignment_category', 'actual_fills',
        'trade_id', 'actual_exit_time', 'actual_holding_hours',
        'actual_execution_net_pnl', 'actual_exit_reason'
    ]
    for col in expected_cols:
        assert col in df_dec.columns, f"Missing column {col} in prediction_decision_alignment.csv"

    # Category C count must exactly equal 208
    c_buys = df_dec[df_dec['alignment_category'] == 'C_EXECUTED_BUY']
    assert len(c_buys) == 208, f"Expected 208 C_EXECUTED_BUY decisions, got {len(c_buys)}"


def test_executed_trades_integrity():
    df_trades = pd.read_csv(ARTIFACT_DIR / 'executed_trade_alignment.csv')
    assert len(df_trades) == 208, f"Expected 208 executed trades, got {len(df_trades)}"

    # Check alignment status counts
    aligned_cnt = df_trades['alignment_status'].isin(['ALIGNED_WIN', 'ALIGNED_LOSS']).sum()
    assert aligned_cnt == 191, f"Expected 191 aligned trades, got {aligned_cnt}"
    assert aligned_cnt / len(df_trades) >= 0.90, "Alignment rate must be >= 90%"

    # Check mismatches count
    mismatch_cnt = df_trades['alignment_status'].isin([
        'MISMATCH_4H_POS_TRADE_LOST', 'MISMATCH_4H_NEG_TRADE_WON'
    ]).sum()
    assert mismatch_cnt == 17, f"Expected 17 mismatches, got {mismatch_cnt}"


def test_holding_period_effect():
    df_holding = pd.read_csv(ARTIFACT_DIR / 'holding_period_analysis.csv')
    exact_4h_row = df_holding[(df_holding['dimension'] == 'DURATION_BUCKET') & (df_holding['category'] == '==4h')]
    assert len(exact_4h_row) == 1
    assert int(list(exact_4h_row['trade_count'])[0]) == 153
    assert float(list(exact_4h_row['total_net_pnl_usdt'])[0]) > 30.0, "Exact 4h trades must have generated >30 USDT"

    over_4h_row = df_holding[(df_holding['dimension'] == 'DURATION_BUCKET') & (df_holding['category'] == '>4h')]
    assert len(over_4h_row) == 1
    assert int(list(over_4h_row['trade_count'])[0]) == 48
    assert float(list(over_4h_row['total_net_pnl_usdt'])[0]) < -10.0, "Over 4h trades must have lost <-10 USDT"


def test_probability_binning_inversion():
    df_prob = pd.read_csv(ARTIFACT_DIR / 'probability_pnl_analysis.csv')
    assert len(df_prob) == 6
    high_bin = df_prob[df_prob['prob_bin'] == '>=0.55']
    assert len(high_bin) == 1
    # Check that >=0.55 lost money in real trading
    assert float(list(high_bin['total_net_pnl_usdt'])[0]) < 0.0, ">=0.55 prob bin must show negative trading PnL"


def test_final_decision_results():
    results = json.loads((ARTIFACT_DIR / 'results.json').read_text(encoding='utf-8'))
    assert results['final_decision']['choice'] == 'C'
    assert '模型本身缺乏足够预测能力' in results['final_decision']['title']
    assert results['prediction_layer_metrics']['roc_auc'] > 0.55
    assert results['trading_layer_metrics']['total_trades'] == 208
