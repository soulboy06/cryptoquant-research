"""验证可配置的 Dust 执行政策（retain_mark_to_market vs writeoff_zero_recovery）。

严格测试：
1. retain_mark_to_market（Cycle Fix Only）：
   - 真实退出后，小于 step_size 的零头保留在账户持仓中；
   - 不产生已实现亏损，realized_pnl 不扣除零头成本；
   - 零头按最新标记价格计入账户权益 equity；
   - closed_cycles 正常结转 +1，不被零头阻碍；
   - 零头本身不构成新的独立周期（cycle_open 为 False，exit_completed 为 True）；
   - 后续买入时，零头与新仓位按加权平均成本合并；
   - 严格满足资金与未实现盈亏守恒：initial_cash + realized_pnl + unrealized_pnl == equity。
2. writeoff_zero_recovery（Cycle Fix + Writeoff，即 post_exit_sub_step_writeoff_v1）：
   - 真实退出后，小于 step_size 的零头实际清零；
   - 零头原成本全额计入已实现亏损（realized_pnl -= cost）；
   - 独立发出 dust_written_off 审计事件；
   - 持仓完全清零。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import pytest

from cryptoquant.config import Cost
from cryptoquant.data.rules import MarketRules
from cryptoquant.trading.ledger import Portfolio, ZERO
from cryptoquant.trading.orders import Intent, simulate_fill
from cryptoquant.trading.risk import RiskState

UTC = timezone.utc
NOW = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
COST = Cost(D('0.001'), D('0.0005'))


def make_rules():
    # 模拟真实 BTCUSDT 精度：step_size = 0.00001, min_notional = 10
    return MarketRules(
        symbol='BTCUSDT',
        step_size=D('0.00001'),
        min_quantity=D('0.00001'),
        max_quantity=D('10000'),
        min_notional=D('10'),
        max_notional=None,
        average_price_minutes=(5,),
    )


def test_retain_mark_to_market_policy_preserves_dust_and_conserves_equity():
    rules = make_rules()
    book = Portfolio('100', ['BTCUSDT'])
    initial_cash = book.cash

    # 1. 采用 retain_mark_to_market 策略初始化 RiskState
    risk = RiskState(['BTCUSDT'], D('50'), D('0.08'), 4, dust_policy='retain_mark_to_market')
    assert risk.dust_policy == 'retain_mark_to_market'

    # 2. 开仓买入 0.00021 BTC @ 50,000 USDT（名义金额 10.50 USDT）
    # 扣除 0.1% 手续费后，实际获得 0.00020979 BTC
    book.apply_fill('BUY', 'BTCUSDT', D('0.00021'), D('50000'), COST.fee)
    risk.register_buy('BTCUSDT', book, D('50000'), rules, COST, NOW)
    
    held_qty = book.positions['BTCUSDT'].quantity
    avg_cost = book.positions['BTCUSDT'].average_cost
    assert held_qty == D('0.00020979')
    assert risk.states['BTCUSDT'].cycle_open is True

    # 3. 正常平仓卖出可交易部分（按 step_size 0.00001 舍入，可卖 0.00020 BTC @ 52,000 USDT）
    sell_qty = D('0.00020')
    price_sell = D('52000')
    book.apply_fill('SELL', 'BTCUSDT', sell_qty, price_sell, COST.fee)
    risk.register_full_exit_fill('BTCUSDT')

    # 剩余 sub-step 零头: 0.00000979 BTC (< step_size 0.00001)
    residual_dust = book.positions['BTCUSDT'].quantity
    assert residual_dust == D('0.00020979') - D('0.00020')
    assert ZERO < residual_dust < rules.step_size

    # 调用 complete_exit_if_tail
    quote_exit = {'open': str(price_sell), 'market_state': 'observed'}
    done = risk.complete_exit_if_tail('BTCUSDT', book, quote_exit, rules, COST, NOW + timedelta(hours=4))
    assert done is True

    # === retain_mark_to_market 关键断言 ===
    # (a) 零头未被清零，仍保留在持仓中
    assert book.positions['BTCUSDT'].quantity == residual_dust
    # (b) 平均成本保持不变
    assert book.positions['BTCUSDT'].average_cost == avg_cost
    # (c) 发出了 dust_retained 审计事件，未发出 dust_written_off
    retained_events = [e for e in risk.events if e['event'] == 'dust_retained']
    written_off_events = [e for e in risk.events if e['event'] == 'dust_written_off']
    assert len(retained_events) == 1
    assert len(written_off_events) == 0
    assert retained_events[0]['policy'] == 'retain_mark_to_market'
    assert retained_events[0]['quantity'] == residual_dust
    # (d) 周期正确关闭
    assert risk.closed_cycles == 1
    assert risk.states['BTCUSDT'].cycle_open is False
    assert risk.states['BTCUSDT'].exit_completed is True

    # (e) 资金与会计恒等式完全守恒（无任何零头核销损失）：
    mark_current = D('53000')
    equity = book.equity({'BTCUSDT': mark_current})
    unrealized_pnl = residual_dust * (mark_current - avg_cost)
    assert equity == book.cash + residual_dust * mark_current
    assert abs(equity - (initial_cash + book.realized_pnl + unrealized_pnl)) < D('1e-20')

    # 4. 后续再次开仓：零头必须与新仓位平滑合并，不重置或丢失成本
    t_next = NOW + timedelta(hours=12)
    book.apply_fill('BUY', 'BTCUSDT', D('0.00020'), D('53000'), COST.fee)
    risk.register_buy('BTCUSDT', book, D('53000'), rules, COST, t_next)
    
    # 新周期开启
    assert risk.states['BTCUSDT'].cycle_open is True
    assert risk.states['BTCUSDT'].exit_completed is False
    # 持仓数量 = 原零头 + 新买入净额
    expected_new_qty = residual_dust + D('0.00020') * (1 - COST.fee)
    assert book.positions['BTCUSDT'].quantity == expected_new_qty


def test_writeoff_zero_recovery_policy_destroys_dust_and_charges_realized_loss():
    rules = make_rules()
    book = Portfolio('100', ['BTCUSDT'])

    # 1. 采用 writeoff_zero_recovery 策略初始化 RiskState
    risk = RiskState(['BTCUSDT'], D('50'), D('0.08'), 4, dust_policy='writeoff_zero_recovery')
    assert risk.dust_policy == 'writeoff_zero_recovery'

    # 2. 开仓买入
    book.apply_fill('BUY', 'BTCUSDT', D('0.00021'), D('50000'), COST.fee)
    risk.register_buy('BTCUSDT', book, D('50000'), rules, COST, NOW)

    # 3. 平仓并调用 complete_exit_if_tail
    sell_qty = D('0.00020')
    price_sell = D('52000')
    book.apply_fill('SELL', 'BTCUSDT', sell_qty, price_sell, COST.fee)
    risk.register_full_exit_fill('BTCUSDT')

    quote_exit = {'open': str(price_sell), 'market_state': 'observed'}
    pnl_before = book.realized_pnl
    done = risk.complete_exit_if_tail('BTCUSDT', book, quote_exit, rules, COST, NOW + timedelta(hours=4))
    assert done is True

    # === writeoff_zero_recovery 关键断言 ===
    # (a) 持仓数量被彻底清零
    assert book.positions['BTCUSDT'].quantity == ZERO
    assert book.positions['BTCUSDT'].average_cost == ZERO
    # (b) 零头成本被扣为已实现损失
    assert book.realized_pnl < pnl_before
    assert book.dust_writeoff_cost > ZERO
    # (c) 发出 dust_written_off 审计事件
    written_off_events = [e for e in risk.events if e['event'] == 'dust_written_off']
    assert len(written_off_events) == 1
    assert written_off_events[0]['policy'] == 'post_exit_sub_step_writeoff_v1'
    # (d) 周期正确关闭
    assert risk.closed_cycles == 1
    assert risk.states['BTCUSDT'].cycle_open is False
