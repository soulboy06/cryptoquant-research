"""第十轮冻结机制：独立龙头与因果历史预测分位数。"""
from decimal import Decimal
import math

import numpy as np
import pandas as pd

SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT')
COLUMNS = ['symbol', 'decision_time', 'probability', 'target_weight']


def _utc(series):
    if str(getattr(series.dtype, 'tz', None)) != 'UTC' or series.isna().any():
        raise ValueError('nonmissing UTC timestamps required')


def build_leader_targets(parent, states, momentum, variant, *, promotion_weight=None):
    weight = Decimal('.30') if promotion_weight is None else Decimal(str(promotion_weight))
    if variant not in ('R8', 'R9', 'R10', 'R11') or weight not in (Decimal('.25'), Decimal('.30')):
        raise ValueError('unsupported frozen variant or promotion weight')
    if list(parent.columns) != COLUMNS:
        raise ValueError('parent columns must contain only trading fields')
    if parent.empty or parent.duplicated(['symbol','decision_time']).any():
        raise ValueError('empty or duplicate parent decisions')
    _utc(parent.decision_time)
    if not (parent.decision_time == parent.decision_time.dt.floor('4h')).all():
        raise ValueError('four-hour decisions required')
    required = {'symbol','decision_time','available_time','return_72h','return_24h','history_valid'}
    if not required.issubset(momentum.columns):
        raise ValueError('missing momentum columns')
    for frame in (states,momentum):
        _utc(frame.decision_time)
        if str(getattr(frame.available_time.dtype, 'tz', None)) != 'UTC':
            raise ValueError('UTC availability required')
        if (frame.available_time > frame.decision_time).any():
            raise ValueError('future availability forbidden')
    if states.decision_time.duplicated().any() or momentum.duplicated(['symbol','decision_time']).any():
        raise ValueError('duplicate state or momentum')
    for column in ('state_valid','allow_buy'):
        if not pd.api.types.is_bool_dtype(states[column].dtype) or states[column].isna().any():
            raise ValueError('state flags must be nonmissing booleans')
    if not pd.api.types.is_bool_dtype(momentum.history_valid.dtype):
        raise ValueError('momentum validity must be boolean')
    valid_m = momentum[momentum.history_valid]
    if valid_m.available_time.isna().any() or not np.isfinite(valid_m[['return_72h','return_24h']].to_numpy(dtype=float)).all():
        raise ValueError('valid momentum requires finite available history')
    keys=set(zip(parent.symbol,parent.decision_time))
    if not keys <= set(zip(momentum.symbol,momentum.decision_time)) or not set(parent.decision_time) <= set(states.decision_time):
        raise ValueError('incomplete aligned state or momentum')
    state_map=states.set_index('decision_time')
    mom=momentum.set_index(['decision_time','symbol'])
    histories={s:[] for s in SYMBOLS}
    records,audit=[],[]
    for time,group in parent.sort_values(['decision_time','symbol']).groupby('decision_time',sort=True):
        if set(group.symbol) != set(SYMBOLS):
            raise ValueError('complete three-symbol decision group required')
        state=state_map.loc[time]
        if state.state_valid and pd.isna(state.available_time):
            raise ValueError('valid state requires availability')
        if not state.state_valid and state.allow_buy:
            raise ValueError('invalid state cannot allow buys')
        favorable=bool(state.state_valid and state.allow_buy)
        full_history=bool(state.state_valid and all(mom.loc[(time,s)].history_valid for s in SYMBOLS))
        btc=float(mom.loc[(time,'BTCUSDT')].return_72h)
        alpha={s:full_history and float(mom.loc[(time,s)].return_72h)>0 and float(mom.loc[(time,s)].return_72h)>btc for s in SYMBOLS}
        leaders=[s for s in SYMBOLS if alpha[s]]
        top=min(leaders,key=lambda s:(-float(mom.loc[(time,s)].return_72h),s)) if leaders else None
        for row in group.itertuples(index=False):
            prob=row.probability
            if not pd.isna(prob) and (not math.isfinite(prob) or not 0<=prob<=1):
                raise ValueError('invalid model probability')
            prior=histories[row.symbol]
            cutoff=float(np.quantile(prior,.8)) if len(prior)>=30 else None
            confirm=bool(cutoff is not None and not pd.isna(prob) and prob>=cutoff)
            eligible=not favorable and full_history and alpha[row.symbol] and not pd.isna(prob) and prob>=.5
            promote=eligible and (row.symbol==top if variant=='R8' else row.symbol==top and float(mom.loc[(time,row.symbol)].return_24h)>0 if variant=='R9' else row.symbol==top and float(mom.loc[(time,row.symbol)].return_24h)<0 if variant=='R11' else confirm)
            original=row.target_weight
            if original is not None and not pd.isna(original) and Decimal(str(original)) not in (Decimal('0'),Decimal('.10'),Decimal('.25'),Decimal('.30')):
                raise ValueError('parent must be frozen repaired R6 weights')
            applied=weight if promote else original
            records.append(dict(symbol=row.symbol,decision_time=time,probability=prob,target_weight=applied))
            audit.append(dict(symbol=row.symbol,decision_time=time,probability=prob,target_weight=applied,
                              parent_weight=original,regime_state='favorable' if favorable else 'weak',
                              is_alpha_leader=bool(alpha[row.symbol]),is_top1=row.symbol==top,
                              return_24h=mom.loc[(time,row.symbol)].return_24h,
                              confidence_cutoff=cutoff,prior_points=len(prior),promoted=bool(promote)))
            if not pd.isna(prob):
                prior.append(float(prob))
    return pd.DataFrame(records,columns=COLUMNS),pd.DataFrame(audit)


def build_closed_momentum(frames):
    if set(frames)!=set(SYMBOLS):
        raise ValueError('three-symbol closed market history required')
    outputs=[]
    for symbol,frame in frames.items():
        _utc(frame.open_time)
        if frame.open_time.duplicated().any() or not frame.open_time.is_monotonic_increasing:
            raise ValueError('invalid market time order')
        prices=pd.to_numeric(frame.close,errors='coerce')
        observed=(frame.market_state=='observed') & prices.notna() & (prices>0)
        history=observed.rolling(744,min_periods=744).sum().eq(744)
        closed=prices.where(observed)
        outputs.append(pd.DataFrame(dict(symbol=symbol,
            decision_time=frame.open_time+pd.Timedelta(1,unit='h'),
            available_time=frame.available_time,
            return_72h=closed/closed.shift(72)-1,
            return_24h=closed/closed.shift(24)-1,
            history_valid=history)))
    return pd.concat(outputs,ignore_index=True).sort_values(['decision_time','symbol'],ignore_index=True)
