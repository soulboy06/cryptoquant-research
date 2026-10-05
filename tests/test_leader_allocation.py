from decimal import Decimal as D

import pandas as pd
import pytest

from cryptoquant.models.leader_allocation import build_leader_targets, build_closed_momentum
from test_baseline_engine import fixture


def inputs(n=36):
    times = pd.date_range('2023-01-01', periods=n, freq='4h', tz='UTC')
    parent = pd.DataFrame([dict(symbol=s, decision_time=t, probability=.51,
                               target_weight=D('.10') if s == 'BTCUSDT' else D('.25'))
                           for t in times for s in ('BTCUSDT','ETHUSDT','SOLUSDT')])
    states = pd.DataFrame(dict(decision_time=times, available_time=times,
                              state_valid=True, allow_buy=False))
    momentum = pd.DataFrame([dict(symbol=s, decision_time=t, available_time=t,
                                 return_72h=r, return_24h=.02, history_valid=True)
                             for t in times for s,r in [('BTCUSDT',.01),('ETHUSDT',.03),('SOLUSDT',.06)]])
    return parent, states, momentum


def test_top_leader_and_direction_are_separate_mechanisms():
    p,s,m = inputs(2)
    m.loc[m.symbol == 'SOLUSDT','return_24h'] = -.01
    r8,_ = build_leader_targets(p,s,m,'R8')
    r9,_ = build_leader_targets(p,s,m,'R9')
    assert set(r8.loc[r8.symbol=='SOLUSDT','target_weight']) == {D('.30')}
    assert set(r8.loc[r8.symbol=='ETHUSDT','target_weight']) == {D('.25')}
    assert r9.target_weight.tolist() == p.target_weight.tolist()


def test_causal_quantile_uses_only_prior_symbol_predictions_and_suffix_is_invariant():
    p,s,m = inputs()
    t=p.decision_time.unique()[30]
    p.loc[(p.decision_time==t)&(p.symbol=='SOLUSDT'),'probability']=.8
    r10,a = build_leader_targets(p,s,m,'R10')
    at = a[(a.decision_time==t)&(a.symbol=='SOLUSDT')].iloc[0]
    assert at.prior_points == 30 and at.confidence_cutoff == pytest.approx(.51)
    assert at.target_weight == D('.30')
    assert set(r10.loc[r10.decision_time<t,'target_weight']) <= {D('.10'),D('.25')}
    p.loc[p.decision_time>t,'probability']=.99
    m.loc[m.decision_time>t,'return_72h']=100
    changed,_ = build_leader_targets(p,s,m,'R10')
    pd.testing.assert_frame_equal(r10[r10.decision_time<=t],changed[changed.decision_time<=t])


def test_missing_history_favorable_and_neighbor_preserve_parent():
    p,s,m = inputs(2)
    m.loc[m.symbol=='BTCUSDT','history_valid']=False
    out,_=build_leader_targets(p,s,m,'R8')
    pd.testing.assert_frame_equal(p,out)
    m.history_valid=True
    s.allow_buy=True
    out,_=build_leader_targets(p,s,m,'R9')
    pd.testing.assert_frame_equal(p,out)
    s.allow_buy=False
    for v in ['R8','R9','R10']:
        out,_=build_leader_targets(p,s,m,v,promotion_weight=D('.25'))
        pd.testing.assert_frame_equal(p,out)


def test_future_availability_duplicate_and_label_columns_fail_closed():
    p,s,m=inputs(2)
    s.loc[0,'available_time'] += pd.Timedelta(1,unit='h')
    with pytest.raises(ValueError,match='future'):
        build_leader_targets(p,s,m,'R8')
    p,s,m=inputs(2)
    with pytest.raises(ValueError,match='duplicate'):
        build_leader_targets(pd.concat([p,p.iloc[[0]]]),s,m,'R8')
    p['label']=1
    with pytest.raises(ValueError,match='columns'):
        build_leader_targets(p,s,m,'R8')


def test_closed_momentum_cannot_use_current_or_future_candle():
    frames,_,cfg=fixture(hours=8,rising=True)
    start=pd.Timestamp(cfg.development_start)
    before=build_closed_momentum(frames)
    for frame in frames.values():
        frame.loc[(frame.open_time>=start)&(frame.row_role!='boundary'),'close']='10000'
    after=build_closed_momentum(frames)
    pd.testing.assert_frame_equal(before[before.decision_time<=start],after[after.decision_time<=start])
