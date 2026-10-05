"""闭合收盘触发与开盘执行之间的跳空、费用和冷却集成检查。"""

from decimal import Decimal as D

import pandas as pd
import pytest

from cryptoquant.baselines.engine import run_backtest
from test_baseline_engine import fixture


@pytest.mark.parametrize('cost_name', ['base', 'higher_execution', 'strict'])
def test_breakeven_gap_executes_at_next_open_with_costs_and_cooldown(cost_name):
    frames, rules, cfg = fixture(hours=12)
    start = pd.Timestamp(cfg.development_start)
    btc = frames['BTCUSDT']
    # 第2/3小时闭合收盘已达到激活线；第4小时开始前回落触发。
    btc.loc[btc.open_time.isin([start + pd.Timedelta(1, unit='h'),
                               start + pd.Timedelta(2, unit='h')]), 'close'] = '10.20'
    btc.loc[btc.open_time == start + pd.Timedelta(3, unit='h'), 'close'] = '10.02'
    # 触发线不等于成交价：次小时开盘跳空至9.50。
    btc.loc[btc.open_time == start + pd.Timedelta(4, unit='h'), 'open'] = '9.50'
    for index, row in btc.iloc[:-1].iterrows():
        btc.loc[index, 'high'] = str(max(D(row['open']), D(row['close'])))
        btc.loc[index, 'low'] = str(min(D(row['open']), D(row['close'])))
    targets = pd.DataFrame([
        dict(symbol=symbol, decision_time=start + pd.Timedelta(hour, unit='h'),
             probability=.9 if symbol == 'BTCUSDT' else .1,
             target_weight=cfg.weight_per_symbol if symbol == 'BTCUSDT' else D('0'))
        for hour in [0, 4, 8] for symbol in cfg.symbols
    ])
    result = run_backtest(frames, rules, cfg, 'logistic_regression', cost_name,
                          decision_targets=targets, exit_variant='C2')
    exits = [fill for fill in result.fills if fill['intent_reason'] == 'breakeven_exit']
    assert len(exits) == 1
    exit_fill = exits[0]
    cost = cfg.costs[cost_name]
    assert exit_fill['time'] == start + pd.Timedelta(4, unit='h')
    assert exit_fill['price'] == D('9.50') * (1 - cost.adverse_price)
    assert exit_fill['price'] < D('10.02')
    assert exit_fill['fee_usdt'] == exit_fill['notional'] * cost.fee
    assert result.book.realized_pnl < 0
    assert result.risk.breakeven_triggers == 1
    assert result.risk.floor_triggers == 0
    buys = [fill for fill in result.fills if fill['side'] == 'BUY']
    assert [fill['time'] for fill in buys] == [start, start + pd.Timedelta(8, unit='h')]
    assert result.book.fees_usdt == sum(fill['fee_usdt'] for fill in result.fills)
    assert all(row['cash'] >= 0 for row in result.equity)
    # 净值对账保留不可售尾差，避免把残余币忽略或再扣一次买入费。
    unrealized = sum(position.quantity * (result.marks[symbol] - position.average_cost)
                     for symbol, position in result.book.positions.items())
    assert abs(result.book.equity(result.marks) -
               (cfg.initial_cash + result.book.realized_pnl + unrealized)) < D('1e-20')
