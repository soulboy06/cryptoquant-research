"""Read existing frozen results only; build delivery attribution without accounts."""
from collections import defaultdict
from decimal import Decimal as D
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from cryptoquant.data.archive import sha_file
from cryptoquant.models.regime_reporting import combined_weekly
from run_tenth_research import cycle_distributions


def main():
    root=Path.cwd()
    evidence=root/'artifacts/experiments'
    output=root/'artifacts/research'
    output.mkdir(exist_ok=True)
    a=json.loads((evidence/'EXP-174/comparison.json').read_text('utf-8'))
    b=json.loads((evidence/'EXP-192/comparison.json').read_text('utf-8'))
    paired={}
    sha_checks=0
    for number in (*range(160,186),192):
        folder=evidence/f'EXP-{number}'
        run=json.loads((folder/'run_manifest.json').read_text('utf-8'))
        assert run['status']=='complete' and run['holdout_read'] is False
        hashes=run.get('artifacts',{})
        for name,value in hashes.items():
            assert sha_file(folder/name)==value, (number,name)
            sha_checks+=1
        sm=folder/'source_manifest.json'
        if sm.exists():
            manifest=json.loads(sm.read_text('utf-8'))
            for name,value in manifest['files'].items():
                assert sha_file(folder/'source_snapshot'/name)==value, (number,name)
                sha_checks+=1
    all_rows={**b['baselines'],**b['candidates']}
    state_contributions={}
    symbol_contributions={}
    for variant,rows in all_rows.items():
        symbol_contributions[variant]={}
        for window,row in rows.items():
            symbol_contributions[variant][window]={s:{
                'net_pnl':str(D(p['realized_pnl'])+D(p['residual_unrealized_pnl'])),
                'fees':p['fees_usdt'],
            } for s,p in row['per_symbol'].items()}
    for window,number in zip(('W1','W2','R2025'),(168,169,170)):
        folder=evidence/f'EXP-{number}'
        audit_path=evidence/f'EXP-{176+('W1','W2','R2025').index(window)}/targets_audit.csv'
        audit=pd.read_csv(audit_path)
        audit['decision_time']=pd.to_datetime(audit.decision_time,utc=True)
        fills=pd.read_csv(folder/'after/fills.csv',dtype=str).to_dict('records')
        for fill in fills:
            for column in ('notional','fee_usdt'):
                fill[column]=D(fill[column])
        events=json.loads((folder/'after/events.json').read_text('utf-8'))
        result=SimpleNamespace(fills=fills,risk=SimpleNamespace(events=events,closed_cycles=all_rows['R6'][window]['closed_cycles']))
        cycles,groups=cycle_distributions(result,audit)
        assert abs(sum((c['net_pnl'] for c in cycles),D(0))-D(all_rows['R6'][window]['realized_pnl']))<D('1e-18')
        state_contributions.setdefault('R6',{})[window]=groups
        pd.DataFrame(cycles).to_csv(output/f'R6_{window}_closed_cycles.csv',index=False)
    for variant,rows in b['candidates'].items():
        for window,row in rows.items():
            state_contributions.setdefault(variant,{})[window]=row['entry_state_distribution']
    for row in a['rows']:
        folder=evidence/row['experiment_id']
        before=pd.read_csv(folder/'before/fills.csv',dtype=str)
        after=pd.read_csv(folder/'after/fills.csv',dtype=str)
        fields=['time','symbol','side','quantity','price','fee_usdt','intent_reason']
        old=list(map(tuple,before[fields].to_numpy()))
        new=list(map(tuple,after[fields].to_numpy()))
        first=next((i for i,(x,y) in enumerate(zip(old,new)) if x!=y),min(len(old),len(new)))
        paired[row['experiment_id']]=dict(variant=row['variant'],window=row['window'],
            before_fills=len(old),after_fills=len(new),first_changed_fill_index=first,
            first_before=old[first] if first<len(old) else None,
            first_after=new[first] if first<len(new) else None,
            pnl_delta=str((D(row['after']['net_return'])-D(row['before']['net_return']))*100),
            fees_delta=str(D(row['after']['fees_usdt'])-D(row['before']['fees_usdt'])))
    dust={}
    for variant,rows in all_rows.items():
        for window,row in rows.items():
            if variant in b['candidates']:
                folder=evidence/row['experiment_id']/'account'
            else:
                pair=next(p for p in a['rows'] if p['variant']==variant and p['window']==window)
                folder=evidence/pair['experiment_id']/'after'
            per_symbol=defaultdict(lambda: {'value':D(0),'cost':D(0),'count':0})
            for event in json.loads((folder/'events.json').read_text('utf-8')):
                if event['event']=='dust_written_off':
                    item=per_symbol[event['symbol']]
                    item['value']+=D(event['value_usdt'])
                    item['cost']+=D(event['cost_usdt'])
                    item['count']+=1
            assert abs(sum((d['value'] for d in per_symbol.values()),D(0))-D(row['dust_writeoff_value']))<D('1e-18')
            dust.setdefault(variant,{})[window]=dict(per_symbol)
    differences={}
    for variant,rows in b['candidates'].items():
        differences[variant]={}
        for ref in ('R0','R5','R6'):
            differences[variant][ref]={window:dict(
                return_delta_pp=str((D(rows[window]['net_return'])-D(all_rows[ref][window]['net_return']))*100),
                drawdown_delta_pp=str((D(rows[window]['max_drawdown'])-D(all_rows[ref][window]['max_drawdown']))*100),
            ) for window in rows}
            differences[variant][ref]['combined_week_delta_pp']=str((combined_weekly(rows)-combined_weekly(all_rows[ref]))*100)
    target_effects={}
    for variant,rows in b['candidates'].items():
        target_effects[variant]={}
        for window,row in rows.items():
            folder=evidence/row['experiment_id']
            audit=pd.read_csv(folder/'targets_audit.csv')
            favorable=audit[audit.regime_state=='favorable']
            assert (favorable.target_weight.eq(favorable.parent_weight) |
                    (favorable.target_weight.isna() & favorable.parent_weight.isna())).all()
            promotions=audit[audit.promoted]
            target_effects[variant][window]=dict(promoted_points=len(promotions),
                promoted_by_symbol=promotions.groupby('symbol').size().to_dict(),
                targets_sha256=sha_file(folder/'targets.parquet'))
    result=dict(phase_a_fill_differences=paired,summaries=all_rows,
        differences=differences,symbol_contributions=symbol_contributions,
        state_contributions=state_contributions,dust_by_symbol=dust,target_effects=target_effects,
        artifact_and_source_sha_checks=sha_checks,
        new_base_accounts=9,new_pressure_accounts=0,phase_a_replay_accounts=32,
        selected_variant=None,best_descriptive=b['best_descriptive'],holdout_read=False,
        limitation='Attribution by entry state is descriptive, not causal profit. Dust policy is simulated abandonment, not an executable exchange conversion.')
    path=output/'cycle-repair-and-tenth-summary.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('Summary complete; verified artifact/source hashes:',sha_checks)
    for variant in ('R6','R8','R9','R10'):
        print(variant,'symbol PnL:',symbol_contributions[variant])
        print(variant,'state PnL:',{w:{s:g['net_pnl'] for s,g in groups.items()} for w,groups in state_contributions[variant].items()})
        print(variant,'dust:',{w:str(sum((d['value'] for d in ss.values()),D(0))) for w,ss in dust[variant].items()})


if __name__=='__main__':
    main()
