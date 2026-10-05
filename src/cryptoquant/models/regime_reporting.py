"""第七轮精确冻结评价：三窗为独立账户，少交易不能自行判成功。"""
from decimal import Decimal, localcontext

WINDOWS = ('W1', 'W2', 'R2025')
COSTS = ('base', 'higher_execution', 'strict')
PARAMETER_CARD = dict(regime_variant='R1', label_policy='net_positive_base_v1', C='0.1', threshold='0.50',
                      exit_variant='C2', breakeven_activation='0.0120', breakeven_ratio='0.0025',
                      cooldown_hours=4, stop_loss='0.08', initial_cash='100', equity_floor='50',
                      weight_per_symbol='0.30', adx_period=14, adx_min=20, ema_period=72,
                      slope_hours=24, history_hours=744, regime_symbol='BTCUSDT')


def decimal_metric(row, name):
    value = Decimal(str(row[name]))
    if not value.is_finite():
        raise ValueError(f'nonfinite metric: {name}')
    return value


def _matrix(rows):
    if set(rows) != set(WINDOWS):
        raise ValueError('requires complete three-window matrix')
    return rows


def combined_weekly(rows):
    _matrix(rows)
    with localcontext() as ctx:
        ctx.prec = 50
        growth, hours = Decimal(1), Decimal(0)
        for row in rows.values():
            if row.get('status') != 'complete':
                return None
            factor = 1 + decimal_metric(row, 'net_return')
            duration = decimal_metric(row, 'total_window_hours')
            if factor <= 0 or duration <= 0:
                raise ValueError('invalid return factor or window hours')
            growth *= factor
            hours += duration
        return growth ** (Decimal(168) / hours) - 1


def _common(rows, max_dd=None):
    failed = []
    for window, row in _matrix(rows).items():
        if row.get('status') != 'complete':
            failed.append(f'{window}:status=complete')
            continue
        if decimal_metric(row, 'floor_triggers') != 0:
            failed.append(f'{window}:floor_triggers=0')
        if decimal_metric(row, 'closed_cycles') < 30:
            failed.append(f'{window}:closed_cycles>=30')
        if max_dd is not None and decimal_metric(row, 'max_drawdown') > max_dd:
            failed.append(f'{window}:max_drawdown<={max_dd}')
    return failed


def evaluate_base(rows, r0):
    _matrix(r0)
    failed = _common(rows, Decimal('.25'))
    for window in ('W1', 'W2'):
        row = rows[window]
        if row.get('status') != 'complete':
            continue
        threshold = Decimal(0) if window == 'W1' else Decimal('.20')
        net = decimal_metric(row, 'net_return')
        if (net <= threshold if window == 'W1' else net < threshold):
            failed.append(f'{window}:net_return>0' if window == 'W1' else 'W2:net_return>=0.20')
        if decimal_metric(row, 'max_drawdown') > decimal_metric(r0[window], 'max_drawdown') + Decimal('.015'):
            failed.append(f'{window}:max_drawdown<=R0+0.015')
    row = rows['R2025']
    if row.get('status') == 'complete':
        if decimal_metric(row, 'net_return') <= decimal_metric(r0['R2025'], 'net_return'):
            failed.append('R2025:net_return>R0')
        if decimal_metric(row, 'max_drawdown') >= decimal_metric(r0['R2025'], 'max_drawdown'):
            failed.append('R2025:max_drawdown<R0')
    new_g, old_g = combined_weekly(rows), combined_weekly(r0)
    if new_g is None or new_g <= old_g:
        failed.append('combined_g_week>R0')
    return dict(eligible=not failed, failed_checks=failed, combined_g_week=new_g, r0_combined_g_week=old_g,
                r2025_above_minus_five_percent=row.get('status') == 'complete' and decimal_metric(row, 'net_return') > Decimal('-.05'),
                parameter_card=dict(PARAMETER_CARD), weekly_target='0.015',
                target_achieved=new_g is not None and new_g >= Decimal('.015'))


def evaluate_pressure(rows, r0, cost):
    if cost not in ('higher_execution', 'strict'):
        raise ValueError('pressure requires higher_execution or strict')
    _matrix(r0)
    failed = _common(rows)
    thresholds, dd = ({'W1': Decimal('.01'), 'W2': Decimal('.20')}, Decimal('.09')) if cost == 'higher_execution' else ({'W1': Decimal('-.01'), 'W2': Decimal('.15')}, Decimal('.10'))
    for window, minimum in thresholds.items():
        if rows[window].get('status') != 'complete':
            continue
        if decimal_metric(rows[window], 'net_return') < minimum:
            failed.append(f'{window}:net_return>={minimum}')
        if decimal_metric(rows[window], 'max_drawdown') > dd:
            failed.append(f'{window}:max_drawdown<={dd}')
    if rows['R2025'].get('status') == 'complete':
        if decimal_metric(rows['R2025'], 'net_return') <= decimal_metric(r0['R2025'], 'net_return'):
            failed.append('R2025:net_return>R0')
        if decimal_metric(rows['R2025'], 'max_drawdown') > decimal_metric(r0['R2025'], 'max_drawdown'):
            failed.append('R2025:max_drawdown<=R0')
    return dict(cost=cost, passed=not failed, failed_checks=failed, combined_g_week=combined_weekly(rows),
                r0_combined_g_week=combined_weekly(r0))


def render_report(title, data):
    """可审核原始数字保存在JSON；中文报告不将历史选择称新盲测。"""
    import json
    return '\n'.join([f'# {title}', '',
        '来源与接口：已核对冻结配置、状态、模型、R0输入SHA及有限预算；执行接口小型合成等价证据不代表全年账户重跑。', '',
        '历史相对改善与代价：按冻结门槛评价收益、回撤、交易周期、手续费与阻断买单；减少交易不单独判为成功，止损记录全部保留。', '',
        '收益目标：长期几何平均周净收益1.5%单列；三窗独立100 USDT账户的几何合成不是三年连续账户。', '',
        '2023、2024、2025全部为已查看研究／选择数据，没有新独立样本外或实时模拟证明。2026继续封存；未接真实账户、借款、合约或付费部署。', '',
        '原第六轮strict W2 EXP-119 +14.9816541437466%未达15%，原失败保留。', '',
        '详细精确结果与失格项：', '', '```json', json.dumps(data, ensure_ascii=False, indent=2, default=str), '```', ''])
