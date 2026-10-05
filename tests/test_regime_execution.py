"""共同BTC许可只拦BUY；使用小型合成账户检查时间、持仓与风险。"""

from dataclasses import replace
from decimal import Decimal as D

import pandas as pd
import pytest

from cryptoquant.baselines.engine import run_backtest
from test_baseline_engine import fixture


def targets(config, weights=None):
    grid = pd.date_range(config.development_start, config.development_end,
                         freq='4h', inclusive='left')
    return pd.DataFrame([
        dict(symbol=symbol, decision_time=time, probability=.9 if weight else .1,
             target_weight=weight)
        for index, time in enumerate(grid) for symbol in config.symbols
        for weight in [weights[index].get(symbol, D('0')) if weights is not None
                       else config.weight_per_symbol]
    ])


def permissions(config, allowed=None):
    grid = pd.date_range(config.development_start, config.development_end,
                         freq='4h', inclusive='left')
    return pd.DataFrame(dict(decision_time=grid, available_time=grid,
                             state_valid=True,
                             allow_buy=[True] * len(grid) if allowed is None else allowed))


def evaluate(frames, rules, config, *, decision_targets=None, buy_permission=None):
    return run_backtest(frames, rules, config, 'logistic_regression', 'base',
                        decision_targets=targets(config) if decision_targets is None else decision_targets,
                        exit_variant='C2', buy_permission=buy_permission)


def assert_same_account(first, second):
    for field in ['orders', 'fills', 'equity', 'signals', 'marks']:
        assert getattr(first, field) == getattr(second, field)
    assert vars(first.book) == vars(second.book)
    assert vars(first.risk) == vars(second.risk)


def assert_conservation(result, config):
    assert result.book.fees_usdt == sum(fill['fee_usdt'] for fill in result.fills)
    assert all(row['cash'] >= 0 for row in result.equity)
    unrealized = sum(position.quantity * (result.marks[symbol] - position.average_cost)
                     for symbol, position in result.book.positions.items())
    assert abs(result.book.equity(result.marks) -
               (config.initial_cash + result.book.realized_pnl + unrealized)) < D('1e-20')


def test_none_and_all_allowed_are_identical_and_filter_does_not_persist():
    frames, rules, config = fixture(hours=12, rising=True)
    original = run_backtest(frames, rules, config, 'logistic_regression', 'base',
                            decision_targets=targets(config), exit_variant='C2')
    assert_same_account(original, evaluate(frames, rules, config))
    assert_same_account(original, evaluate(frames, rules, config,
                                          buy_permission=permissions(config)))
    blocked = evaluate(frames, rules, config,
                       buy_permission=permissions(config, [False] * 3))
    assert not blocked.fills
    assert_same_account(original, evaluate(frames, rules, config))


def test_common_permission_blocks_three_symbols_without_changing_targets_or_money():
    frames, rules, config = fixture(hours=12)
    permit = permissions(config, [False] * 3)
    permit.loc[1, 'state_valid'] = False  # 无效预热也必须明确禁买。
    result = evaluate(frames, rules, config, buy_permission=permit)
    reference = evaluate(frames, rules, config)
    assert len(result.orders) == 9
    assert all(row['side'] == 'BUY' and not row['accepted'] and
               row['reason'] == 'regime_blocked' and row['quantity'] == row['price'] == 0
               and row['intent_reason'] == 'rebalance' for row in result.orders)
    assert {row['symbol'] for row in result.orders} == set(config.symbols)
    assert [row['requested_quantity'] for row in result.orders[:3]] == [
        row['requested_quantity'] for row in reference.orders[:3]]
    assert all(row['weight'] == config.weight_per_symbol for row in result.signals)
    assert result.book.cash == config.initial_cash and result.book.fees_usdt == 0
    assert not result.fills and all(position.quantity == 0 for position in result.book.positions.values())


def test_restricted_owned_position_blocks_top_up_but_keeps_probability_sell():
    frames, rules, config = fixture(hours=12)
    start = pd.Timestamp(config.development_start)
    btc = frames['BTCUSDT']
    btc.loc[btc.open_time >= start + pd.Timedelta(4, unit='h'), 'open'] = '9.8'
    btc.loc[(btc.open_time >= start + pd.Timedelta(4, unit='h')) &
            btc.row_role.ne('boundary'), ['close', 'high', 'low']] = '9.8'
    signal = targets(config, [{'BTCUSDT': config.weight_per_symbol},
                              {symbol: config.weight_per_symbol for symbol in config.symbols},
                              {'ETHUSDT': config.weight_per_symbol, 'SOLUSDT': config.weight_per_symbol}])
    result = evaluate(frames, rules, config, decision_targets=signal,
                      buy_permission=permissions(config, [True, False, False]))
    at_four = [row for row in result.orders if row['time'] == start + pd.Timedelta(4, unit='h')]
    assert len(at_four) == 3 and all(row['reason'] == 'regime_blocked' for row in at_four)
    assert all(row['requested_quantity'] > 0 for row in at_four)
    snapshots = {row['time']: row for row in result.equity if row['phase'] == 'open'}
    assert snapshots[start]['BTCUSDT_quantity'] == snapshots[start + pd.Timedelta(4, unit='h')]['BTCUSDT_quantity']
    sells = [row for row in result.fills if row['intent_reason'] == 'strategy_exit']
    assert len(sells) == 1 and sells[0]['symbol'] == 'BTCUSDT'
    assert sells[0]['time'] == start + pd.Timedelta(8, unit='h')
    assert not result.risk.stop_triggers and not result.risk.breakeven_triggers
    assert_conservation(result, config)


def test_permission_cannot_override_close_triggered_c2_exit_and_cooldown():
    frames, rules, config = fixture(hours=16)
    start = pd.Timestamp(config.development_start)
    btc = frames['BTCUSDT']
    for hour, close in [(1, '10.20'), (2, '10.20'), (3, '10.02')]:
        btc.loc[btc.open_time == start + pd.Timedelta(hour, unit='h'), 'close'] = close
    btc.loc[btc.open_time == start + pd.Timedelta(4, unit='h'), 'open'] = '9.5'
    signal = targets(config, [{'BTCUSDT': config.weight_per_symbol}] * 4)
    # 出场点和冷却后首个决策点都受限；下一许可点仍可买回。
    result = evaluate(frames, rules, config, decision_targets=signal,
                      buy_permission=permissions(config, [True, False, False, True]))
    exits = [row for row in result.fills if row['intent_reason'] == 'breakeven_exit']
    assert len(exits) == 1 and exits[0]['time'] == start + pd.Timedelta(4, unit='h')
    assert exits[0]['price'] == D('9.5') * (1 - config.costs['base'].adverse_price)
    assert [row['time'] for row in result.fills if row['side'] == 'BUY'] == [
        start, start + pd.Timedelta(12, unit='h')]
    assert not [row for row in result.orders if row['time'] == start + pd.Timedelta(4, unit='h')
                and row['reason'] == 'regime_blocked']  # 原风险退出优先，无同根重买意图。
    assert any(row['time'] == start + pd.Timedelta(8, unit='h') and
               row['reason'] == 'regime_blocked' for row in result.orders)
    assert result.risk.breakeven_triggers == 1
    assert_conservation(result, config)


def test_risk_rejection_precedes_regime_and_floor_remains_permanent():
    frames, rules, config = fixture(hours=12)
    start = pd.Timestamp(config.development_start)
    btc = frames['BTCUSDT']
    btc.loc[btc.open_time == start + pd.Timedelta(1, unit='h'), ['close', 'low']] = '8'
    signal = targets(config, [{'BTCUSDT': config.weight_per_symbol}] * 3)
    result = evaluate(frames, rules, config, decision_targets=signal,
                      buy_permission=permissions(config, [True, False, True]))
    stops = [row for row in result.fills if row['intent_reason'] == 'stop_loss']
    assert len(stops) == 1 and stops[0]['time'] == start + pd.Timedelta(2, unit='h')
    rejected = [row for row in result.orders if row['time'] == start + pd.Timedelta(4, unit='h')]
    assert len(rejected) == 1 and rejected[0]['reason'] == 'risk_blocked'
    assert_conservation(result, config)

    for frame in frames.values():
        frame.loc[frame.open_time == start + pd.Timedelta(1, unit='h'), ['close', 'low']] = '4'
    floor = evaluate(frames, rules, config,
                     buy_permission=permissions(config, [True, False, True]))
    assert floor.risk.locked and floor.risk.floor_triggers == 1
    assert len([row for row in floor.fills if row['side'] == 'BUY']) == 3
    exits = [row for row in floor.fills if row['intent_reason'] == 'floor']
    assert len(exits) == 3 and all(row['time'] == start + pd.Timedelta(2, unit='h') for row in exits)
    assert not [row for row in floor.orders if row['reason'] == 'regime_blocked']
    assert_conservation(floor, config)


def test_empty_permission_is_rejected_even_without_any_four_hour_decisions():
    frames, rules, config = fixture(hours=1)
    # 合法01:00→02:00 UTC账户窗口，根本没有4h决策点。
    shift = pd.Timedelta(1, unit='h')
    empty_permission = permissions(config).iloc[:0]
    config = replace(config, development_start=config.development_start + shift,
                     development_end=config.development_end + shift,
                     validation_start=config.validation_start + shift)
    for frame in frames.values():
        frame['open_time'] += shift
        frame['available_time'] += shift
    empty_targets = pd.DataFrame(columns=['symbol', 'decision_time', 'probability', 'target_weight'])
    unfiltered = evaluate(frames, rules, config, decision_targets=empty_targets)
    assert not unfiltered.orders and unfiltered.book.cash == config.initial_cash
    with pytest.raises(ValueError, match='empty buy permission'):
        evaluate(frames, rules, config, decision_targets=empty_targets,
                 buy_permission=empty_permission)


def test_permission_requires_complete_causal_utc_clock_and_boolean_flags():
    frames, rules, config = fixture(hours=12)
    valid = permissions(config)
    bad_tables = [valid.iloc[:0], valid.iloc[:-1], pd.concat([valid, valid.iloc[:1]]),
                  valid.assign(label=1), valid.drop(columns='state_valid')]
    extra = valid.iloc[-1:].copy()
    extra['decision_time'] += pd.Timedelta(4, unit='h')
    extra['available_time'] = extra['decision_time']
    bad_tables.append(pd.concat([valid, extra]))
    for column in ['decision_time', 'available_time']:
        bad_tables.append(valid.assign(**{column: pd.NaT}))
        bad_tables.append(valid.assign(**{column: valid[column].dt.tz_localize(None)}))
        bad_tables.append(valid.assign(**{column: valid[column].dt.tz_convert('Asia/Shanghai')}))
    off_grid = valid.copy()
    off_grid['decision_time'] += pd.Timedelta(1, unit='h')
    bad_tables.append(off_grid)
    for column in ['state_valid', 'allow_buy']:
        bad_tables.append(valid.assign(**{column: 1}))
        bad_tables.append(valid.assign(**{column: 'true'}))
        missing = valid.copy()
        missing[column] = missing[column].astype('boolean')
        missing.loc[0, column] = pd.NA
        bad_tables.append(missing)
    bad_tables.extend([valid.assign(available_time=valid.decision_time + pd.Timedelta(1, unit='ns')),
                       valid.assign(state_valid=False),
                       valid.assign(state_valid=False, allow_buy=False,
                                    available_time=valid.decision_time + pd.Timedelta(1, unit='h'))])
    for table in bad_tables:
        with pytest.raises(ValueError, match='buy permission'):
            evaluate(frames, rules, config, buy_permission=table)


def test_non_model_strategies_reject_permission_even_if_empty():
    frames, rules, config = fixture(hours=4)
    for strategy in ['buy_hold', 'ema_trend']:
        for permit in [permissions(config), permissions(config).iloc[:0]]:
            with pytest.raises(ValueError, match='buy permission'):
                run_backtest(frames, rules, config, strategy, 'base', buy_permission=permit)
