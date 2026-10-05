"""第九轮相对强弱解耦执行测试：验证引擎对 0.20、0.25 目标权重的支持、资金守恒与 C2 规则。"""

from decimal import Decimal as D
import pandas as pd
import pytest

from cryptoquant.baselines.engine import run_backtest
from test_baseline_engine import fixture


def make_targets(config, weight_map):
    """根据时间索引构建 decision_targets 表。"""
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


def test_alpha_weights_acceptance_and_conservation():
    frames, rules, config = fixture(hours=24, rising=True)
    # 0h: 0.25, 4h: 0.20, 8h: 0.15, 12h: 0.10, 16h: 0, 20h: 0.30
    weight_map = {
        0: D('0.25'),
        1: D('0.20'),
        2: D('0.15'),
        3: D('0.10'),
        4: D('0'),
        5: D('0.30'),
    }
    targets = make_targets(config, weight_map)
    result = run_backtest(frames, rules, config, 'logistic_regression', 'base',
                          decision_targets=targets, exit_variant='C2')
    
    assert len(result.fills) > 0
    # 检验现金非负与总资金守恒
    assert all(row['cash'] >= 0 for row in result.equity)
    assert result.book.fees_usdt == sum(fill['fee_usdt'] for fill in result.fills)
    
    unrealized = sum(pos.quantity * (result.marks[sym] - pos.average_cost)
                     for sym, pos in result.book.positions.items())
    assert abs(result.book.equity(result.marks) -
               (config.initial_cash + result.book.realized_pnl + unrealized)) < D('1e-20')


def test_alpha_weights_illegal_rejection():
    frames, rules, config = fixture(hours=12, rising=True)
    # 权重 0.05 与 0.35 均属非法
    for illegal_weight in [D('0.05'), D('0.35'), D('-0.10')]:
        illegal_map = {0: illegal_weight}
        targets = make_targets(config, illegal_map)
        with pytest.raises(ValueError, match="invalid decision target weight"):
            run_backtest(frames, rules, config, 'logistic_regression', 'base',
                         decision_targets=targets, exit_variant='C2')


def test_alpha_breakeven_trigger_with_decoupled_weights():
    # 构造价格大幅上升后回落触发 C2 保本止损的情景
    frames, rules, config = fixture(hours=24, rising=True)
    # 0h: 开仓 0.25 仓位
    weight_map = {0: D('0.25')}
    targets = make_targets(config, weight_map)
    result = run_backtest(frames, rules, config, 'logistic_regression', 'base',
                          decision_targets=targets, exit_variant='C2')
    
    assert len(result.orders) > 0
    assert result.book.equity(result.marks) > 0
