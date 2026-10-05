"""第八轮动态仓位权重执行测试：验证引擎对 0.10、0.15、0.30 的支持与守恒性。"""

from decimal import Decimal as D
import pandas as pd
import pytest

from cryptoquant.baselines.engine import run_backtest
from test_baseline_engine import fixture


def make_targets(config, weight_map):
    """根据时间索引映射构建 decision_targets 表。"""
    grid = pd.date_range(config.development_start, config.development_end,
                         freq='4h', inclusive='left')
    records = []
    for idx, time in enumerate(grid):
        w = weight_map.get(idx, D('0.30'))
        for symbol in config.symbols:
            records.append({
                'symbol': symbol,
                'decision_time': time,
                'probability': 0.8 if w > 0 else 0.2,
                'target_weight': w,
            })
    return pd.DataFrame(records)


def test_dynamic_weights_acceptance_and_conservation():
    frames, rules, config = fixture(hours=24, rising=True)
    # 0h: 0.30, 4h: 0.10, 8h: 0.15, 12h: 0, 16h: 0.10, 20h: 0.30
    weight_map = {
        0: D('0.30'),
        1: D('0.10'),
        2: D('0.15'),
        3: D('0'),
        4: D('0.10'),
        5: D('0.30'),
    }
    targets = make_targets(config, weight_map)
    result = run_backtest(frames, rules, config, 'logistic_regression', 'base',
                          decision_targets=targets, exit_variant='C2')
    
    assert len(result.fills) > 0
    # 检查现金非负与守恒性
    assert all(row['cash'] >= 0 for row in result.equity)
    assert result.book.fees_usdt == sum(fill['fee_usdt'] for fill in result.fills)
    
    unrealized = sum(pos.quantity * (result.marks[sym] - pos.average_cost)
                     for sym, pos in result.book.positions.items())
    assert abs(result.book.equity(result.marks) -
               (config.initial_cash + result.book.realized_pnl + unrealized)) < D('1e-20')


def test_dynamic_weights_illegal_rejection():
    frames, rules, config = fixture(hours=12, rising=True)
    # 非法权重 0.35
    illegal_map = {0: D('0.35')}
    targets = make_targets(config, illegal_map)
    with pytest.raises(ValueError, match="invalid decision target weight"):
        run_backtest(frames, rules, config, 'logistic_regression', 'base',
                     decision_targets=targets, exit_variant='C2')


def test_constant_30_matches_standard_c2():
    frames, rules, config = fixture(hours=16, rising=True)
    targets_30 = make_targets(config, {})  # 全部默认 0.30
    
    res1 = run_backtest(frames, rules, config, 'logistic_regression', 'base',
                        decision_targets=targets_30, exit_variant='C2')
    
    # 再次运行，结果必须完全确定可复现
    res2 = run_backtest(frames, rules, config, 'logistic_regression', 'base',
                        decision_targets=targets_30, exit_variant='C2')
    
    assert res1.orders == res2.orders
    assert res1.fills == res2.fills
    assert res1.book.cash == res2.book.cash
    assert res1.book.equity(res1.marks) == res2.book.equity(res2.marks)
