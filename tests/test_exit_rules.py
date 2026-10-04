"""第六轮出场规则与持仓约束针对性测试：
1. 规则 A：8 小时最大持仓上限平仓，同 K 线禁止重买，平仓后 4 小时冷却；
2. 规则 B：浮盈达到 +1.20% 激活动态保本线（average_cost * 1.0025），回落触发平仓，平仓后 4 小时冷却；未激活前不触发；
3. 硬止损（-8%）与底线（50 USDT）优先级绝对高于出场规则；
4. 4 组变体（C0, C1, C2, C3）在 run_backtest 中正确配置并生效。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from pathlib import Path

import pandas as pd
import pytest

from cryptoquant.baselines.engine import BacktestResult, run_backtest
from cryptoquant.config import load_config
from cryptoquant.trading.ledger import Portfolio, amount
from cryptoquant.trading.risk import RiskState, SymbolState
from test_baseline_engine import fixture
from test_orders import COST, quote, rule

NOW = datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc)
SYMBOL = 'BTCUSDT'


def make_portfolio(cash='100', symbol=SYMBOL, qty='1', price='100'):
    p = Portfolio(cash, [symbol])
    p.apply_fill('BUY', symbol, qty, price, '0.001')
    return p


def test_rule_a_duration_exit_triggers_at_8h_blocks_same_bar_and_cooldown():
    """验证时限上限在精确第 8 小时触发平仓、同 K 线不可重买、并获得 4h 冷却。"""
    portfolio = make_portfolio()
    limits = rule(maximum='10')
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4, max_holding_hours=8)
    risk.register_buy(SYMBOL, portfolio, D('100'), limits, COST, NOW)

    # 1 ~ 7 小时：正常观察，持仓时长递增，不触发时限退出
    for h in range(1, 8):
        t = NOW + timedelta(hours=h)
        risk.observe(portfolio, {SYMBOL: D('100')}, {SYMBOL}, t)
        assert risk.states[SYMBOL].holding_hours == h
        assert risk.states[SYMBOL].pending is None
        assert risk.duration_triggers == 0

    # 第 8 小时：触发 max_duration_exit
    t8 = NOW + timedelta(hours=8)
    risk.observe(portfolio, {SYMBOL: D('100')}, {SYMBOL}, t8)
    assert risk.states[SYMBOL].holding_hours == 8
    assert risk.states[SYMBOL].pending == 'max_duration_exit'
    assert risk.duration_triggers == 1

    # 模拟在 t8 开盘撮合全平
    portfolio.apply_fill('SELL', SYMBOL, '0.999', '100', '0.001')
    risk.register_full_exit_fill(SYMBOL)
    done = risk.complete_exit_if_tail(SYMBOL, portfolio, quote('100'), limits, COST, t8)
    assert done is True
    assert risk.closed_cycles == 1
    assert risk.states[SYMBOL].pending is None
    assert risk.states[SYMBOL].exit_completed is True
    # 强制 4 小时冷却：cooldown_until 为 t8 + 4h = t12
    assert risk.states[SYMBOL].cooldown_until == t8 + timedelta(hours=4)

    # 验证 t8 开盘（同 K 线）禁止买入（如果是决策点也因 pending/cooldown 受控）
    # 在 t8 时 timestamp < cooldown_until
    assert not risk.can_buy(SYMBOL, t8)
    # 在 t9, t10, t11（非 4h 决策点）不可买
    assert not risk.can_buy(SYMBOL, NOW + timedelta(hours=9))
    # 在 t12（下一个 4h 决策点），冷却结束，允许重新评估买入
    t12 = NOW + timedelta(hours=12)
    assert risk.can_buy(SYMBOL, t12)


def test_rule_b_breakeven_stop_activation_and_trigger():
    """验证动态保本止损：浮盈未达 +1.20% 不激活，达到后激活，跌破 average_cost * 1.0025 触发退出。"""
    portfolio = make_portfolio(qty='1', price='100')
    cost_basis = portfolio.positions[SYMBOL].average_cost
    # cost_basis = 100 * (1 + 0) / (1 - 0.001) = 100 / 0.999 = 100.100100...
    limits = rule(maximum='10')
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4,
                     breakeven_activation=D('0.0120'), breakeven_ratio=D('0.0025'))
    risk.register_buy(SYMBOL, portfolio, D('100'), limits, COST, NOW)

    # 小幅上涨 +0.80%，低于 +1.20%，未激活
    t1 = NOW + timedelta(hours=1)
    p_sub = cost_basis * D('1.0080')
    risk.observe(portfolio, {SYMBOL: p_sub}, {SYMBOL}, t1)
    assert not risk.states[SYMBOL].breakeven_active
    assert risk.states[SYMBOL].pending is None

    # 价格回落到微利（低于保本线 1.0025），但因未曾激活，绝不误触保本退出
    t2 = NOW + timedelta(hours=2)
    p_flat = cost_basis * D('1.0010')
    risk.observe(portfolio, {SYMBOL: p_flat}, {SYMBOL}, t2)
    assert not risk.states[SYMBOL].breakeven_active
    assert risk.states[SYMBOL].pending is None
    assert risk.breakeven_triggers == 0

    # 价格冲高 +1.50%，超过 +1.20%，激活保本监控
    t3 = NOW + timedelta(hours=3)
    p_high = cost_basis * D('1.0150')
    risk.observe(portfolio, {SYMBOL: p_high}, {SYMBOL}, t3)
    assert risk.states[SYMBOL].breakeven_active is True
    assert risk.states[SYMBOL].pending is None

    # 价格回落至 cost_basis * 1.0024（跌破保本线 1.0025），触发 breakeven_exit
    t4 = NOW + timedelta(hours=4)
    p_fall = cost_basis * D('1.0024')
    risk.observe(portfolio, {SYMBOL: p_fall}, {SYMBOL}, t4)
    assert risk.states[SYMBOL].pending == 'breakeven_exit'
    assert risk.breakeven_triggers == 1

    # 撮合成交全平后，进入 4 小时冷却
    portfolio.apply_fill('SELL', SYMBOL, '0.999', '100.3', '0.001')
    risk.register_full_exit_fill(SYMBOL)
    risk.complete_exit_if_tail(SYMBOL, portfolio, quote('100.3'), limits, COST, t4)
    assert risk.states[SYMBOL].cooldown_until == t4 + timedelta(hours=4)
    assert not risk.can_buy(SYMBOL, t4)
    assert risk.can_buy(SYMBOL, t4 + timedelta(hours=4))


def test_hard_stop_loss_has_higher_priority_than_breakeven_and_duration():
    """验证当发生极端暴跌时，8% 硬止损具有最高优先级。"""
    portfolio = make_portfolio(qty='1', price='100')
    cost_basis = portfolio.positions[SYMBOL].average_cost
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4,
                     max_holding_hours=8, breakeven_activation=D('0.0120'), breakeven_ratio=D('0.0025'))
    risk.register_buy(SYMBOL, portfolio, D('100'), rule(), COST, NOW)

    # 先冲高激活保本
    t1 = NOW + timedelta(hours=1)
    risk.observe(portfolio, {SYMBOL: cost_basis * D('1.02')}, {SYMBOL}, t1)
    assert risk.states[SYMBOL].breakeven_active is True

    # 突发暴跌 -10%（跌破 -8% 硬止损）
    t2 = NOW + timedelta(hours=2)
    risk.observe(portfolio, {SYMBOL: cost_basis * D('0.89')}, {SYMBOL}, t2)
    assert risk.states[SYMBOL].pending == 'stop_loss'
    assert risk.stop_triggers == 1
    assert risk.breakeven_triggers == 0


def test_run_backtest_exit_variants_configuration():
    """验证 run_backtest 对 C0, C1, C2, C3 变体参数的正确映射与异常防御。"""
    frames, rules, cfg = fixture(hours=24)

    # 测试 C0（基准对照）
    res_c0 = run_backtest(frames, rules, cfg, 'buy_hold', 'base', period='development', window=None, exit_variant='C0')
    assert res_c0.exit_variant == 'C0'
    assert res_c0.risk.max_holding_hours is None
    assert res_c0.risk.breakeven_activation is None

    # 测试 C1（仅时限）
    res_c1 = run_backtest(frames, rules, cfg, 'buy_hold', 'base', period='development', window=None, exit_variant='C1')
    assert res_c1.exit_variant == 'C1'
    assert res_c1.risk.max_holding_hours == 8
    assert res_c1.risk.breakeven_activation is None

    # 测试 C2（仅保本）
    res_c2 = run_backtest(frames, rules, cfg, 'buy_hold', 'base', period='development', window=None, exit_variant='C2')
    assert res_c2.exit_variant == 'C2'
    assert res_c2.risk.max_holding_hours is None
    assert res_c2.risk.breakeven_activation == D('0.0120')
    assert res_c2.risk.breakeven_ratio == D('0.0025')

    # 测试 C3（组合方案）
    res_c3 = run_backtest(frames, rules, cfg, 'buy_hold', 'base', period='development', window=None, exit_variant='C3')
    assert res_c3.exit_variant == 'C3'
    assert res_c3.risk.max_holding_hours == 8
    assert res_c3.risk.breakeven_activation == D('0.0120')
    assert res_c3.risk.breakeven_ratio == D('0.0025')

    # 测试非法变体抛出 ValueError
    with pytest.raises(ValueError, match='unsupported exit variant'):
        run_backtest(frames, rules, cfg, 'buy_hold', 'base', period='development', window=None, exit_variant='C99')
