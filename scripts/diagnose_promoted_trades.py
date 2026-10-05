"""只读诊断：比较 R8/R10 在 W1、W2、2025 中所有恢复加仓交易的入场前结构差异。
严格只读：不新增策略、不调参数、不打开 2026。
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
    
    # 1. 严格只读取开发集与验证集行情（绝不触碰 2026）
    frames_dev, _, _ = load_period(root, 'EXP-003', cfg, 'development')
    frames_val, _, _ = load_period(root, 'EXP-003', cfg, 'validation')
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    market = {}
    for s in symbols:
        comb = pd.concat([frames_dev[s], frames_val[s]]).drop_duplicates('open_time').sort_values('open_time').reset_index(drop=True)
        comb['close_num'] = pd.to_numeric(comb['close'], errors='coerce')
        comb['volume_num'] = pd.to_numeric(comb['volume'], errors='coerce')
        comb['high_num'] = pd.to_numeric(comb['high'], errors='coerce')
        comb['low_num'] = pd.to_numeric(comb['low'], errors='coerce')
        market[s] = comb.set_index('open_time')

    # 读取 funding rate
    funding_rates = {}
    for s in symbols:
        fpath = root / f'data/processed/funding_rate/{s}.parquet'
        if fpath.exists():
            fdf = pd.read_parquet(fpath).sort_values('funding_time').set_index('funding_time')
            funding_rates[s] = fdf
        else:
            funding_rates[s] = None

    # 读取市场状态
    states_by_window = {}
    for w in ['W1', 'W2', 'R2025']:
        spath = root / f'artifacts/experiments/EXP-122/state_{w}.parquet'
        states_by_window[w] = pd.read_parquet(spath).set_index('decision_time')

    # 2. 收集 R8 与 R10 的所有恢复加仓周期
    # R8: EXP-176 (W1), EXP-177 (W2), EXP-178 (2025)
    # R10: EXP-182 (W1), EXP-183 (W2), EXP-184 (2025)
    experiments = {
        ('R8', 'W1'): 'EXP-176',
        ('R8', 'W2'): 'EXP-177',
        ('R8', 'R2025'): 'EXP-178',
        ('R10', 'W1'): 'EXP-182',
        ('R10', 'W2'): 'EXP-183',
        ('R10', 'R2025'): 'EXP-184',
    }

    cycles_record = {} # key: (window, symbol, entry_time) -> cycle data

    for (variant, window), exp_id in experiments.items():
        audit = pd.read_csv(root / f'artifacts/experiments/{exp_id}/targets_audit.csv')
        fills = pd.read_csv(root / f'artifacts/experiments/{exp_id}/account/fills.csv')
        orders = pd.read_csv(root / f'artifacts/experiments/{exp_id}/account/orders.csv')
        cycles = pd.read_csv(root / f'artifacts/experiments/{exp_id}/closed_cycles.csv')
        prom = audit[audit.promoted]

        for _, pr in prom.iterrows():
            s = pr['symbol']
            t_dec = pr['decision_time']
            # 找到包含该恢复决策的周期
            matches = cycles[(cycles.symbol == s) & (cycles.entry_time <= t_dec) & (cycles.exit_time >= t_dec)]
            for _, cyc in matches.iterrows():
                key = (window, cyc['symbol'], cyc['entry_time'])
                if key not in cycles_record:
                    t_in = cyc['entry_time']
                    t_out = cyc['exit_time']
                    exit_orders = orders[(orders.symbol == s) & (orders.time == t_out) & (orders.side == 'SELL') & (orders.accepted)]
                    intent = exit_orders.iloc[0].intent_reason if not exit_orders.empty else 'unknown'
                    hours = (pd.Timestamp(t_out) - pd.Timestamp(t_in)).total_seconds() / 3600
                    
                    cycles_record[key] = {
                        'window': window,
                        'symbol': cyc['symbol'],
                        'entry_time': t_in,
                        'exit_time': t_out,
                        'holding_hours': hours,
                        'net_pnl': float(cyc['net_pnl']),
                        'net_return': float(cyc['net_return']),
                        'cost': float(cyc['cost']),
                        'outcome': 'Win' if float(cyc['net_pnl']) > 0 else 'Loss',
                        'exit_reason': intent,
                        'variants': [variant],
                        'promoted_times': [t_dec],
                        'probability_at_entry': float(pr['probability']) if t_dec == t_in else None
                    }
                else:
                    if variant not in cycles_record[key]['variants']:
                        cycles_record[key]['variants'].append(variant)
                    if t_dec not in cycles_record[key]['promoted_times']:
                        cycles_record[key]['promoted_times'].append(t_dec)

    # 3. 对每个周期计算入场时刻（t_in）之前的结构特征（严格使用 t-1h 之前收盘数据）
    diagnostics = []
    btc_market = market['BTCUSDT']

    for key, cdata in sorted(cycles_record.items(), key=lambda x: (x[1]['window'], x[1]['entry_time'])):
        s = cdata['symbol']
        t_in = pd.Timestamp(cdata['entry_time'])
        w = cdata['window']
        sym_market = market[s]
        
        # 入场决策发生在 t_in，当时可用的最新收盘 K 线是 t_in - 1h
        t_prev = t_in - pd.Timedelta(hours=1)
        
        # 切片截止到 t_prev 的闭合数据
        sym_slice = sym_market.loc[:t_prev]
        btc_slice = btc_market.loc[:t_prev]

        # 价格与收益
        p_now = sym_slice['close_num'].iloc[-1]
        p_4h = sym_slice['close_num'].iloc[-5] if len(sym_slice) >= 5 else np.nan
        p_12h = sym_slice['close_num'].iloc[-13] if len(sym_slice) >= 13 else np.nan
        p_24h = sym_slice['close_num'].iloc[-25] if len(sym_slice) >= 25 else np.nan
        p_72h = sym_slice['close_num'].iloc[-73] if len(sym_slice) >= 73 else np.nan

        ret_4h = float(p_now / p_4h - 1) if not pd.isna(p_4h) else np.nan
        ret_12h = float(p_now / p_12h - 1) if not pd.isna(p_12h) else np.nan
        ret_24h = float(p_now / p_24h - 1) if not pd.isna(p_24h) else np.nan
        ret_72h = float(p_now / p_72h - 1) if not pd.isna(p_72h) else np.nan

        btc_now = btc_slice['close_num'].iloc[-1]
        btc_24h_ago = btc_slice['close_num'].iloc[-25] if len(btc_slice) >= 25 else np.nan
        btc_72h_ago = btc_slice['close_num'].iloc[-73] if len(btc_slice) >= 73 else np.nan
        btc_ret_24h = float(btc_now / btc_24h_ago - 1) if not pd.isna(btc_24h_ago) else np.nan
        btc_ret_72h = float(btc_now / btc_72h_ago - 1) if not pd.isna(btc_72h_ago) else np.nan

        excess_ret_72h = ret_72h - btc_ret_72h if not pd.isna(ret_72h) and not pd.isna(btc_ret_72h) else np.nan
        excess_ret_24h = ret_24h - btc_ret_24h if not pd.isna(ret_24h) and not pd.isna(btc_ret_24h) else np.nan

        # BTC 均线距离
        btc_sma50 = btc_slice['close_num'].iloc[-50:].mean() if len(btc_slice) >= 50 else np.nan
        btc_sma200 = btc_slice['close_num'].iloc[-200:].mean() if len(btc_slice) >= 200 else np.nan
        btc_dist_sma50 = float(btc_now / btc_sma50 - 1) if not pd.isna(btc_sma50) else np.nan
        btc_dist_sma200 = float(btc_now / btc_sma200 - 1) if not pd.isna(btc_sma200) else np.nan

        # 波动率
        hourly_rets_72h = sym_slice['close_num'].iloc[-72:].pct_change().dropna()
        volatility_72h = float(hourly_rets_72h.std()) if len(hourly_rets_72h) >= 24 else np.nan

        btc_hourly_rets_72h = btc_slice['close_num'].iloc[-72:].pct_change().dropna()
        btc_volatility_72h = float(btc_hourly_rets_72h.std()) if len(btc_hourly_rets_72h) >= 24 else np.nan

        # 真实波幅比率 (ATR 24h / close)
        highs = sym_slice['high_num'].iloc[-24:]
        lows = sym_slice['low_num'].iloc[-24:]
        closes = sym_slice['close_num'].iloc[-25:-1]
        tr = np.maximum(highs.values - lows.values, np.abs(highs.values - closes.values))
        tr = np.maximum(tr, np.abs(lows.values - closes.values))
        atr_ratio_24h = float(np.mean(tr) / p_now) if len(tr) >= 20 else np.nan

        # 成交量比例
        vol_24h = sym_slice['volume_num'].iloc[-24:].mean()
        vol_72h = sym_slice['volume_num'].iloc[-72:].mean()
        vol_ratio_24h_72h = float(vol_24h / vol_72h) if vol_72h > 0 else np.nan

        # 资金费率
        fr_df = funding_rates.get(s)
        if fr_df is not None:
            fr_sub = fr_df.loc[:t_prev]
            latest_funding = float(fr_sub['funding_rate'].iloc[-1]) if not fr_sub.empty else np.nan
            funding_zscore = float(fr_sub['funding_rate_zscore'].iloc[-1]) if not fr_sub.empty and 'funding_rate_zscore' in fr_sub.columns else np.nan
        else:
            latest_funding = np.nan
            funding_zscore = np.nan

        # 弱市状态持续时长 (weak hours prior to entry)
        states_df = states_by_window[w]
        states_prior = states_df.loc[:t_in]
        weak_count = 0
        for val in reversed(states_prior['allow_buy'].tolist()):
            if not val: # allow_buy == False 即弱市
                weak_count += 4 # 每次决策为 4h
            else:
                break

        # 预测概率
        if cdata['probability_at_entry'] is None:
            # 取最早的 promoted_time 对应的概率
            aud = pd.read_csv(root / f'artifacts/experiments/{experiments[(cdata["variants"][0], w)]}/targets_audit.csv')
            match_row = aud[(aud.symbol == s) & (aud.decision_time == cdata["entry_time"])]
            cdata['probability_at_entry'] = float(match_row.iloc[0]['probability']) if not match_row.empty else np.nan

        row_diag = {
            **cdata,
            'ret_4h': ret_4h,
            'ret_12h': ret_12h,
            'ret_24h': ret_24h,
            'ret_72h': ret_72h,
            'btc_ret_24h': btc_ret_24h,
            'btc_ret_72h': btc_ret_72h,
            'excess_ret_72h': excess_ret_72h,
            'excess_ret_24h': excess_ret_24h,
            'btc_dist_sma50': btc_dist_sma50,
            'btc_dist_sma200': btc_dist_sma200,
            'volatility_72h': volatility_72h,
            'btc_volatility_72h': btc_volatility_72h,
            'atr_ratio_24h': atr_ratio_24h,
            'vol_ratio_24h_72h': vol_ratio_24h_72h,
            'funding_rate': latest_funding,
            'funding_zscore': funding_zscore,
            'weak_regime_hours_prior': weak_count,
        }
        diagnostics.append(row_diag)

    df_diag = pd.DataFrame(diagnostics)
    
    # 4. 分组对比：盈利样本 (10) vs 亏损样本 (9)
    winners = df_diag[df_diag['outcome'] == 'Win']
    losers = df_diag[df_diag['outcome'] == 'Loss']

    metric_cols = [
        'net_return', 'probability_at_entry',
        'ret_4h', 'ret_12h', 'ret_24h', 'ret_72h',
        'btc_ret_24h', 'btc_ret_72h',
        'excess_ret_24h', 'excess_ret_72h',
        'btc_dist_sma50', 'btc_dist_sma200',
        'volatility_72h', 'btc_volatility_72h',
        'atr_ratio_24h', 'vol_ratio_24h_72h',
        'funding_rate', 'weak_regime_hours_prior',
        'holding_hours'
    ]

    summary = {
        'total_cycles': len(df_diag),
        'winners_count': len(winners),
        'losers_count': len(losers),
        'win_rate': len(winners) / len(df_diag),
        'by_symbol': df_diag.groupby(['symbol', 'outcome']).size().unstack(fill_value=0).to_dict(),
        'by_window': df_diag.groupby(['window', 'outcome']).size().unstack(fill_value=0).to_dict(),
        'metrics_comparison': {}
    }

    for col in metric_cols:
        w_vals = winners[col].dropna()
        l_vals = losers[col].dropna()
        summary['metrics_comparison'][col] = {
            'winners_mean': float(w_vals.mean()) if len(w_vals) else None,
            'winners_median': float(w_vals.median()) if len(w_vals) else None,
            'winners_std': float(w_vals.std()) if len(w_vals) else None,
            'losers_mean': float(l_vals.mean()) if len(l_vals) else None,
            'losers_median': float(l_vals.median()) if len(l_vals) else None,
            'losers_std': float(l_vals.std()) if len(l_vals) else None,
            'delta_mean (win - loss)': float(w_vals.mean() - l_vals.mean()) if len(w_vals) and len(l_vals) else None,
            'delta_median (win - loss)': float(w_vals.median() - l_vals.median()) if len(w_vals) and len(l_vals) else None,
        }

    # 保存诊断明细与总结
    out_dir = root / 'artifacts/research'
    out_dir.mkdir(exist_ok=True)
    
    with open(out_dir / 'promoted_trades_diagnosis.json', 'w', encoding='utf-8') as f:
        json.dump({
            'summary': summary,
            'cycles': diagnostics
        }, f, indent=2, ensure_ascii=False)

    df_diag.to_csv(out_dir / 'promoted_trades_diagnosis.csv', index=False)
    print("Diagnosis completed successfully. Output written to artifacts/research/promoted_trades_diagnosis.json")


if __name__ == '__main__':
    main()
