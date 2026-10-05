import json
import pandas as pd

with open('artifacts/experiments/EXP-193/alpha_validation_report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)

print("="*100)
print(f"EXP-193 弱市全量候选只读验证报告 (样本量: {report['total_observations']} 条四小时决策记录)")
print("="*100)

# -------------------------------------------------------------
# 假设 1: 币自己真的强 vs 假超额
# -------------------------------------------------------------
print("\n" + "#"*100)
print("【假设 1 验证：币自己真的强 (ret_72h > 0) vs 跌得慢的假超额 (ret_72h <= 0)】")
print("#"*100)

for scope_title, scope_key in [("纯相对超额全量池 (excess_72h > 0)", "Pure Relative Alpha (excess_72h > 0)"),
                                ("相对超额且模型概率 >= 0.50", "Relative Alpha & Prob >= 0.50")]:
    print(f"\n--- {scope_title} ---")
    h1 = report['h1_true_vs_false_alpha'][scope_key]
    for coin in ['Pooled', 'SOLUSDT', 'ETHUSDT']:
        c_res = h1[coin]
        t = c_res['True Alpha (ret_72h > 0 & excess > 0)']
        f = c_res['False Alpha (ret_72h <= 0 & excess > 0)']
        d = c_res['Difference (True - False)']
        print(f"[{coin}]")
        print(f"  真 Alpha: 样本数={t['count']}, 4h净胜率={t['win_rate_net']*100:.2f}%, 4h扣费均值={t['mean_net_4h']*100:+.3f}%, 4h扣费中位数={t['median_net_4h']*100:+.3f}%")
        print(f"  假 Alpha: 样本数={f['count']}, 4h净胜率={f['win_rate_net']*100:.2f}%, 4h扣费均值={f['mean_net_4h']*100:+.3f}%, 4h扣费中位数={f['median_net_4h']*100:+.3f}%")
        print(f"  差异对比 (True - False): 净胜率差异={d['win_rate_diff']*100:+.2f}%, 4h净均值差异={d['mean_net_4h_diff']*100:+.3f}%")

# -------------------------------------------------------------
# 假设 2: BTC 明显下跌时，相对强势表现
# -------------------------------------------------------------
print("\n" + "#"*100)
print("【假设 2 验证：BTC 明显下跌时，相对强势候选表现】")
print("#"*100)
h2 = report['h2_btc_crash_effect']
rows_h2 = []
for bname, data in h2.items():
    p = data['Pooled']
    sol = data['SOLUSDT']
    eth = data['ETHUSDT']
    rows_h2.append({
        'BTC 72h 状态分桶': bname,
        'Pooled 样本': p['count'],
        'Pooled 4h净收益': f"{p['mean_net_4h']*100:+.3f}%",
        'Pooled 净胜率': f"{p['win_rate_net']*100:.1f}%",
        'SOL 4h净收益': f"{sol['mean_net_4h']*100:+.3f}%",
        'SOL 净胜率': f"{sol['win_rate_net']*100:.1f}%",
        'ETH 4h净收益': f"{eth['mean_net_4h']*100:+.3f}%",
        'ETH 净胜率': f"{eth['win_rate_net']*100:.1f}%",
    })
print(pd.DataFrame(rows_h2).to_string(index=False))

# -------------------------------------------------------------
# 假设 3: 72h 强且 24h 回调 vs 24h 暴涨
# -------------------------------------------------------------
print("\n" + "#"*100)
print("【假设 3 验证：真 Alpha 中，24h 回调 (ret_24h < 0) vs 24h 暴涨 (ret_24h >= 0)】")
print("#"*100)
h3 = report['h3_pullback_vs_chasing']
for coin in ['Pooled', 'SOLUSDT', 'ETHUSDT']:
    c_res = h3[coin]
    pb = c_res['Pullback (ret_24h < 0)']
    ch = c_res['Chase Surge (ret_24h >= 0)']
    dpb = c_res['Deep Pullback (< -2%)']
    mpb = c_res['Mild Pullback (-2% ~ 0%)']
    ms = c_res['Mild Surge (0% ~ +2%)']
    ss = c_res['Strong Surge (>= +2%)']
    d = c_res['Difference (Pullback - Chase)']
    print(f"\n[{coin}] (在真 Alpha ret_72h > 0 & excess > 0 & prob >= 0.50 内部)")
    print(f"  回踩组 (24h < 0): 样本={pb['count']}, 4h净胜率={pb['win_rate_net']*100:.2f}%, 4h扣费均值={pb['mean_net_4h']*100:+.3f}%, 中位数={pb['median_net_4h']*100:+.3f}%")
    print(f"    - 深回踩 (<-2%):  样本={dpb['count']}, 4h净胜率={dpb['win_rate_net']*100:.2f}%, 4h扣费均值={dpb['mean_net_4h']*100:+.3f}%")
    print(f"    - 浅回踩 (-2%~0%): 样本={mpb['count']}, 4h净胜率={mpb['win_rate_net']*100:.2f}%, 4h扣费均值={mpb['mean_net_4h']*100:+.3f}%")
    print(f"  追高组 (24h >= 0): 样本={ch['count']}, 4h净胜率={ch['win_rate_net']*100:.2f}%, 4h扣费均值={ch['mean_net_4h']*100:+.3f}%, 中位数={ch['median_net_4h']*100:+.3f}%")
    print(f"    - 浅追高 (0%~+2%): 样本={ms['count']}, 4h净胜率={ms['win_rate_net']*100:.2f}%, 4h扣费均值={ms['mean_net_4h']*100:+.3f}%")
    print(f"    - 强追高 (>=+2%):  样本={ss['count']}, 4h净胜率={ss['win_rate_net']*100:.2f}%, 4h扣费均值={ss['mean_net_4h']*100:+.3f}%")
    print(f"  回踩 vs 追高差异: 净胜率差异={d['win_rate_diff']*100:+.2f}%, 4h扣费均值差异={d['mean_net_4h_diff']*100:+.3f}%")

# -------------------------------------------------------------
# 跨年份分段稳定性
# -------------------------------------------------------------
print("\n" + "#"*100)
print("【跨年份稳定性分段核查 (W1 2023 / W2 2024 / R2025 2025)】")
print("#"*100)
cy = report['cross_year_robustness']
rows_cy = []
for wnd, data in cy.items():
    t = data['True_Alpha']
    f = data['False_Alpha']
    pb = data['Pullback']
    ch = data['Chase']
    bc = data['BTC_Drop (<-2%)']
    bs = data['BTC_Stable (>=-2%)']
    rows_cy.append({
        '年份窗口': wnd,
        '真Alpha净收益(N)': f"{t['mean_net_4h']*100:+.3f}% ({t['count']})",
        '假Alpha净收益(N)': f"{f['mean_net_4h']*100:+.3f}% ({f['count']})",
        '真Alpha胜率': f"{t['win_rate_net']*100:.1f}% vs {f['win_rate_net']*100:.1f}%",
        '回踩净收益(N)': f"{pb['mean_net_4h']*100:+.3f}% ({pb['count']})",
        '追高净收益(N)': f"{ch['mean_net_4h']*100:+.3f}% ({ch['count']})",
        '大盘稳定净收益(N)': f"{bs['mean_net_4h']*100:+.3f}% ({bs['count']})",
        '大盘深跌净收益(N)': f"{bc['mean_net_4h']*100:+.3f}% ({bc['count']})",
    })
print(pd.DataFrame(rows_cy).to_string(index=False))
