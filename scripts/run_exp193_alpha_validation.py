"""EXP-193: 2023～2025 弱市全量 Alpha 候选只读结构验证。
严格只读：不新增策略、不调参数、不打开 2026。
验证目标：
1. 币自己真的强（绝对动量 ret_72h > 0）是否比“只是比 BTC 跌得少”（假超额 ret_72h <= 0）更可靠？
2. BTC 明显下跌时，相对强势是不是更容易失败？
3. 72h 强且 24h 回调（ret_24h < 0）是否真的比 24h 继续暴涨（ret_24h >= 0）更好？
4. SOL 和 ETH 分别检验，验证结论是否跨币种、跨年份稳定。
"""

import json
from decimal import Decimal
from pathlib import Path
import numpy as np
import pandas as pd

from cryptoquant.config import load_config
from cryptoquant.baselines.io import load_period


def main():
    root = Path('.').resolve()
    cfg = load_config(root / 'artifacts/experiments/EXP-168/config.toml')

    # 1. 严格只读取开发集与验证集行情（物理封存 2026）
    frames_dev, _, _ = load_period(root, 'EXP-003', cfg, 'development')
    frames_val, _, _ = load_period(root, 'EXP-003', cfg, 'validation')

    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    market = {}
    for s in symbols:
        comb = pd.concat([frames_dev[s], frames_val[s]]).drop_duplicates('open_time').sort_values('open_time').reset_index(drop=True)
        comb['open_num'] = pd.to_numeric(comb['open'], errors='coerce')
        comb['close_num'] = pd.to_numeric(comb['close'], errors='coerce')
        comb['volume_num'] = pd.to_numeric(comb['volume'], errors='coerce')
        comb['high_num'] = pd.to_numeric(comb['high'], errors='coerce')
        comb['low_num'] = pd.to_numeric(comb['low'], errors='coerce')
        market[s] = comb.set_index('open_time')

    btc_market = market['BTCUSDT']

    # 2. 读取状态与模型目标预测
    windows = {
        'W1': ('EXP-168', 'artifacts/experiments/EXP-122/state_W1.parquet'),
        'W2': ('EXP-169', 'artifacts/experiments/EXP-122/state_W2.parquet'),
        'R2025': ('EXP-170', 'artifacts/experiments/EXP-122/state_R2025.parquet')
    }

    records = []

    for window, (target_exp, state_path) in windows.items():
        targets = pd.read_parquet(root / f'artifacts/experiments/{target_exp}/targets.parquet')
        targets_map = targets.set_index(['decision_time', 'symbol'])['probability'].to_dict()

        states = pd.read_parquet(root / state_path).set_index('decision_time')

        # 筛选有效弱市决策点 (weak: allow_buy == False)
        weak_decisions = states[states['state_valid'] & (~states['allow_buy'])].index

        for t_in in weak_decisions:
            t_in = pd.Timestamp(t_in)
            t_prev = t_in - pd.Timedelta(hours=1)
            btc_slice = btc_market.loc[:t_prev]
            if len(btc_slice) < 200:
                continue

            btc_now = btc_slice['close_num'].iloc[-1]
            btc_ret_24h = float(btc_now / btc_slice['close_num'].iloc[-25] - 1)
            btc_ret_72h = float(btc_now / btc_slice['close_num'].iloc[-73] - 1)
            btc_sma200 = float(btc_slice['close_num'].iloc[-200:].mean())
            btc_dist_sma200 = float(btc_now / btc_sma200 - 1)

            # 对 ETH 和 SOL 提取特征与前瞻收益
            for s in ['ETHUSDT', 'SOLUSDT']:
                sym_slice = market[s].loc[:t_prev]
                if len(sym_slice) < 73:
                    continue

                prob = targets_map.get((t_in, s), np.nan)

                p_now = sym_slice['close_num'].iloc[-1]
                ret_4h = float(p_now / sym_slice['close_num'].iloc[-5] - 1)
                ret_24h = float(p_now / sym_slice['close_num'].iloc[-25] - 1)
                ret_72h = float(p_now / sym_slice['close_num'].iloc[-73] - 1)

                excess_72h = ret_72h - btc_ret_72h
                excess_24h = ret_24h - btc_ret_24h

                # ATR 24h
                highs = sym_slice['high_num'].iloc[-24:]
                lows = sym_slice['low_num'].iloc[-24:]
                closes = sym_slice['close_num'].iloc[-25:-1]
                tr = np.maximum(highs.values - lows.values, np.abs(highs.values - closes.values))
                tr = np.maximum(tr, np.abs(lows.values - closes.values))
                atr_ratio_24h = float(np.mean(tr) / p_now) if len(tr) >= 20 else np.nan

                # 量比
                vol_24h = sym_slice['volume_num'].iloc[-24:].mean()
                vol_72h = sym_slice['volume_num'].iloc[-72:].mean()
                vol_ratio = float(vol_24h / vol_72h) if vol_72h > 0 else np.nan

                # 计算前瞻收益 (在 t_in 的 open 买入，分别在 t+4h, t+8h, t+12h open 卖出)
                sym_market = market[s]
                if t_in not in sym_market.index:
                    continue

                open_entry = sym_market.loc[t_in, 'open_num']
                if pd.isna(open_entry) or open_entry <= 0:
                    continue

                # 4h forward
                t_4h = t_in + pd.Timedelta(hours=4)
                open_4h = sym_market.loc[t_4h, 'open_num'] if t_4h in sym_market.index else np.nan
                fwd_ret_4h_gross = float(open_4h / open_entry - 1) if not pd.isna(open_4h) else np.nan
                fwd_ret_4h_net = float(0.999 * open_4h / (open_entry / 0.999) - 1) if not pd.isna(open_4h) else np.nan

                # 8h forward
                t_8h = t_in + pd.Timedelta(hours=8)
                open_8h = sym_market.loc[t_8h, 'open_num'] if t_8h in sym_market.index else np.nan
                fwd_ret_8h_net = float(0.999 * open_8h / (open_entry / 0.999) - 1) if not pd.isna(open_8h) else np.nan

                # 12h forward
                t_12h = t_in + pd.Timedelta(hours=12)
                open_12h = sym_market.loc[t_12h, 'open_num'] if t_12h in sym_market.index else np.nan
                fwd_ret_12h_net = float(0.999 * open_12h / (open_entry / 0.999) - 1) if not pd.isna(open_12h) else np.nan

                records.append({
                    'window': window,
                    'symbol': s,
                    'decision_time': str(t_in),
                    'probability': float(prob) if not pd.isna(prob) else np.nan,
                    'ret_4h': ret_4h,
                    'ret_24h': ret_24h,
                    'ret_72h': ret_72h,
                    'btc_ret_24h': btc_ret_24h,
                    'btc_ret_72h': btc_ret_72h,
                    'excess_72h': excess_72h,
                    'excess_24h': excess_24h,
                    'btc_dist_sma200': btc_dist_sma200,
                    'atr_ratio_24h': atr_ratio_24h,
                    'vol_ratio_24h_72h': vol_ratio,
                    'fwd_ret_4h_gross': fwd_ret_4h_gross,
                    'fwd_ret_4h_net': fwd_ret_4h_net,
                    'fwd_ret_8h_net': fwd_ret_8h_net,
                    'fwd_ret_12h_net': fwd_ret_12h_net,
                    'is_relative_alpha': bool(excess_72h > 0),
                    'is_true_alpha': bool(ret_72h > 0 and excess_72h > 0),
                    'is_false_alpha': bool(ret_72h <= 0 and excess_72h > 0),
                    'pullback_flag': bool(ret_24h < 0),
                })

    df = pd.DataFrame(records).dropna(subset=['fwd_ret_4h_net'])
    print(f"Total weak-regime observations extracted: {len(df)}")

    # 3. 统计分析三大核心假设
    # 定义统计辅助函数
    def calc_metrics(sub):
        n = len(sub)
        if n == 0:
            return {'count': 0, 'win_rate_net': 0, 'mean_net_4h': 0, 'median_net_4h': 0, 'sum_net_4h': 0, 'mean_net_8h': 0, 'mean_net_12h': 0}
        win_rate = float((sub['fwd_ret_4h_net'] > 0).mean())
        mean_4h = float(sub['fwd_ret_4h_net'].mean())
        median_4h = float(sub['fwd_ret_4h_net'].median())
        sum_4h = float(sub['fwd_ret_4h_net'].sum())
        mean_8h = float(sub['fwd_ret_8h_net'].mean())
        mean_12h = float(sub['fwd_ret_12h_net'].mean())
        return {
            'count': n,
            'win_rate_net': win_rate,
            'mean_net_4h': mean_4h,
            'median_net_4h': median_4h,
            'sum_net_4h': sum_4h,
            'mean_net_8h': mean_8h,
            'mean_net_12h': mean_12h
        }

    # -------------------------------------------------------------
    # 假设 1: 币自己真的强 (ret_72h > 0) vs 跌得慢的假超额 (ret_72h <= 0)
    # -------------------------------------------------------------
    h1_results = {}
    for scope_name, sub_df in [('All (Prob >= 0.50)', df[df['probability'] >= 0.50]),
                               ('Pure Relative Alpha (excess_72h > 0)', df[df['is_relative_alpha']]),
                               ('Relative Alpha & Prob >= 0.50', df[df['is_relative_alpha'] & (df['probability'] >= 0.50)])]:
        h1_results[scope_name] = {}
        for coin in ['Pooled', 'SOLUSDT', 'ETHUSDT']:
            c_df = sub_df if coin == 'Pooled' else sub_df[sub_df['symbol'] == coin]
            true_alpha = c_df[c_df['is_true_alpha']]
            false_alpha = c_df[c_df['is_false_alpha']]
            h1_results[scope_name][coin] = {
                'True Alpha (ret_72h > 0 & excess > 0)': calc_metrics(true_alpha),
                'False Alpha (ret_72h <= 0 & excess > 0)': calc_metrics(false_alpha),
                'Difference (True - False)': {
                    'win_rate_diff': calc_metrics(true_alpha)['win_rate_net'] - calc_metrics(false_alpha)['win_rate_net'],
                    'mean_net_4h_diff': calc_metrics(true_alpha)['mean_net_4h'] - calc_metrics(false_alpha)['mean_net_4h']
                }
            }

    # -------------------------------------------------------------
    # 假设 2: BTC 明显下跌时，相对强势是否更容易失败？
    # -------------------------------------------------------------
    # 以 Relative Alpha & Prob >= 0.50 为基础池
    base_pool = df[df['is_relative_alpha'] & (df['probability'] >= 0.50)]
    
    # 定义 BTC 72h 表现分桶
    btc_buckets = [
        ('BTC Strong (>= +2%)', base_pool[base_pool['btc_ret_72h'] >= 0.02]),
        ('BTC Flat/Mild (+0% ~ +2%)', base_pool[(base_pool['btc_ret_72h'] >= 0.0) & (base_pool['btc_ret_72h'] < 0.02)]),
        ('BTC Mild Drop (-2% ~ 0%)', base_pool[(base_pool['btc_ret_72h'] >= -0.02) & (base_pool['btc_ret_72h'] < 0.0)]),
        ('BTC Solid Drop (-5% ~ -2%)', base_pool[(base_pool['btc_ret_72h'] >= -0.05) & (base_pool['btc_ret_72h'] < -0.02)]),
        ('BTC Severe Crash (< -5%)', base_pool[base_pool['btc_ret_72h'] < -0.05]),
    ]
    h2_results = {}
    for bname, bdf in btc_buckets:
        h2_results[bname] = {
            'Pooled': calc_metrics(bdf),
            'SOLUSDT': calc_metrics(bdf[bdf['symbol'] == 'SOLUSDT']),
            'ETHUSDT': calc_metrics(bdf[bdf['symbol'] == 'ETHUSDT']),
        }

    # -------------------------------------------------------------
    # 假设 3: 72h 强且 24h 回调 (ret_24h < 0) vs 24h 继续暴涨 (ret_24h >= 0)
    # -------------------------------------------------------------
    # 在 True Alpha & Prob >= 0.50 子集内验证
    true_alpha_pool = df[df['is_true_alpha'] & (df['probability'] >= 0.50)]
    h3_results = {}
    for coin in ['Pooled', 'SOLUSDT', 'ETHUSDT']:
        c_df = true_alpha_pool if coin == 'Pooled' else true_alpha_pool[true_alpha_pool['symbol'] == coin]
        pullback = c_df[c_df['ret_24h'] < 0]
        chase = c_df[c_df['ret_24h'] >= 0]
        deep_pullback = c_df[c_df['ret_24h'] < -0.02]
        mild_pullback = c_df[(c_df['ret_24h'] >= -0.02) & (c_df['ret_24h'] < 0)]
        mild_surge = c_df[(c_df['ret_24h'] >= 0) & (c_df['ret_24h'] < 0.02)]
        strong_surge = c_df[c_df['ret_24h'] >= 0.02]
        h3_results[coin] = {
            'Pullback (ret_24h < 0)': calc_metrics(pullback),
            'Chase Surge (ret_24h >= 0)': calc_metrics(chase),
            'Deep Pullback (< -2%)': calc_metrics(deep_pullback),
            'Mild Pullback (-2% ~ 0%)': calc_metrics(mild_pullback),
            'Mild Surge (0% ~ +2%)': calc_metrics(mild_surge),
            'Strong Surge (>= +2%)': calc_metrics(strong_surge),
            'Difference (Pullback - Chase)': {
                'win_rate_diff': calc_metrics(pullback)['win_rate_net'] - calc_metrics(chase)['win_rate_net'],
                'mean_net_4h_diff': calc_metrics(pullback)['mean_net_4h'] - calc_metrics(chase)['mean_net_4h']
            }
        }

    # -------------------------------------------------------------
    # 按年份分段验证稳定性 (Cross-Year Robustness: W1, W2, 2025)
    # -------------------------------------------------------------
    year_results = {}
    for window in ['W1', 'W2', 'R2025']:
        w_df = df[df['window'] == window]
        w_true = w_df[w_df['is_true_alpha'] & (w_df['probability'] >= 0.50)]
        w_false = w_df[w_df['is_false_alpha'] & (w_df['probability'] >= 0.50)]
        w_pullback = w_true[w_true['ret_24h'] < 0]
        w_chase = w_true[w_true['ret_24h'] >= 0]
        w_btc_crash = w_df[w_df['is_relative_alpha'] & (w_df['probability'] >= 0.50) & (w_df['btc_ret_72h'] < -0.02)]
        w_btc_stable = w_df[w_df['is_relative_alpha'] & (w_df['probability'] >= 0.50) & (w_df['btc_ret_72h'] >= -0.02)]

        year_results[window] = {
            'True_Alpha': calc_metrics(w_true),
            'False_Alpha': calc_metrics(w_false),
            'Pullback': calc_metrics(w_pullback),
            'Chase': calc_metrics(w_chase),
            'BTC_Drop (<-2%)': calc_metrics(w_btc_crash),
            'BTC_Stable (>=-2%)': calc_metrics(w_btc_stable),
        }

    output_payload = {
        'total_observations': len(df),
        'h1_true_vs_false_alpha': h1_results,
        'h2_btc_crash_effect': h2_results,
        'h3_pullback_vs_chasing': h3_results,
        'cross_year_robustness': year_results
    }

    out_dir = root / 'artifacts/experiments/EXP-193'
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / 'alpha_validation_report.json', 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)

    df.to_parquet(out_dir / 'weak_alpha_candidates.parquet', index=False)
    print("EXP-193 completed successfully. Artifacts saved to artifacts/experiments/EXP-193/")


if __name__ == '__main__':
    main()
