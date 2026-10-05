import json
import pandas as pd

with open('artifacts/research/promoted_trades_diagnosis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

summary = data['summary']
cycles = data['cycles']

print("="*100)
print(f"总计恢复加仓周期数: {summary['total_cycles']} 个 (盈利: {summary['winners_count']} 个, 亏损: {summary['losers_count']} 个, 胜率: {summary['win_rate']*100:.1f}%)")
print("="*100)

print("\n【币种分布】")
by_sym = {}
for outcome, syms in summary['by_symbol'].items():
    for s, count in syms.items():
        by_sym.setdefault(s, {})[outcome] = count

for s, counts in by_sym.items():
    w = counts.get('Win', 0)
    l = counts.get('Loss', 0)
    total = w + l
    wr = (w / total * 100) if total > 0 else 0
    print(f"  {s}: 胜 {w} / 负 {l} (胜率: {wr:.1f}%)")

print("\n【研究窗口分布】")
by_wnd = {}
for outcome, wnds in summary['by_window'].items():
    for wnd, count in wnds.items():
        by_wnd.setdefault(wnd, {})[outcome] = count

for wnd, counts in by_wnd.items():
    w = counts.get('Win', 0)
    l = counts.get('Loss', 0)
    total = w + l
    wr = (w / total * 100) if total > 0 else 0
    print(f"  {wnd}: 胜 {w} / 负 {l} (胜率: {wr:.1f}%)")

print("\n" + "="*100)
print(f"{'入场前结构特征':<26} | {'盈利中位数':>10} | {'亏损中位数':>10} | {'中位数差异(W-L)':>14} | {'盈利均值':>10} | {'亏损均值':>10}")
print("-"*100)

metrics = summary['metrics_comparison']
for k, v in metrics.items():
    w_med = f"{v['winners_median']:.4f}" if v['winners_median'] is not None else "-"
    l_med = f"{v['losers_median']:.4f}" if v['losers_median'] is not None else "-"
    d_med = f"{v['delta_median (win - loss)']:+.4f}" if v['delta_median (win - loss)'] is not None else "-"
    w_mean = f"{v['winners_mean']:.4f}" if v['winners_mean'] is not None else "-"
    l_mean = f"{v['losers_mean']:.4f}" if v['losers_mean'] is not None else "-"
    print(f"{k:<26} | {w_med:>10} | {l_med:>10} | {d_med:>14} | {w_mean:>10} | {l_mean:>10}")

print("\n" + "="*100)
print("【所有 19 个恢复加仓周期的明细列表】")
print("-"*100)
df_c = pd.DataFrame(cycles)
cols = ['window', 'symbol', 'entry_time', 'exit_time', 'outcome', 'net_return', 'net_pnl', 'ret_72h', 'btc_ret_72h', 'excess_ret_72h', 'ret_24h', 'btc_dist_sma200', 'probability_at_entry', 'exit_reason']
print(df_c[cols].to_string(index=False))
