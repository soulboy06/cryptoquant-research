"""精确四小时标签与产物语义；理想交易答案不进入账户扣费。"""

from decimal import Decimal, InvalidOperation, localcontext
import math

GROSS_POLICY = 'gross_direction_v1'
NET_POLICY = 'net_positive_base_v1'
LABEL_POLICIES = (GROSS_POLICY, NET_POLICY)
BASE_FEE = Decimal('.001')
BASE_ADVERSE = Decimal('.0005')
LABEL_HORIZON_HOURS = 4
_CARD_KEYS = ('label_policy', 'label_cost_name', 'label_fee', 'label_adverse_price', 'label_horizon_hours')
_MANIFEST_TYPES = {'training_samples', 'model_training', 'model_validation', 'training_probabilities',
                   'research_prepared', 'research_samples', 'research_training', 'research_probabilities',
                   'research_evaluation', 'research_selection', 'research_comparison'}


def _finite_decimal(value, name):
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('invalid ' + name) from exc
    if not result.is_finite():
        raise ValueError('non-finite ' + name)
    return result


def label_metadata(policy, fee=None, adverse=None):
    """返回统一成本卡；gross没有成本，net仅允许冻结的base成本。"""
    if policy not in LABEL_POLICIES:
        raise ValueError('unknown label policy')
    if policy == GROSS_POLICY:
        if fee is not None or adverse is not None:
            raise ValueError('gross label policy must not carry costs')
        return dict(label_policy=policy, label_cost_name=None, label_fee=None,
                    label_adverse_price=None, label_horizon_hours=LABEL_HORIZON_HOURS)
    if fee is None or adverse is None:
        raise ValueError('net label policy requires base costs')
    fee, adverse = _finite_decimal(fee, 'fee'), _finite_decimal(adverse, 'adverse price')
    if not (0 <= fee < 1 and 0 <= adverse < 1) or (fee, adverse) != (BASE_FEE, BASE_ADVERSE):
        raise ValueError('net label policy requires exact base costs')
    return dict(label_policy=policy, label_cost_name='base', label_fee='0.001',
                label_adverse_price='0.0005', label_horizon_hours=LABEL_HORIZON_HOURS)


def validate_label_metadata(manifest, expected_policy=None):
    """旧自产的两类manifest才允许缺省gross；其余必须显式提供完整卡。"""
    kind = manifest.get('type')
    if kind not in _MANIFEST_TYPES:
        raise ValueError('unknown label metadata manifest type')
    if 'label_policy' not in manifest:
        if kind not in {'training_samples', 'model_training'} or any(k in manifest for k in _CARD_KEYS[1:]):
            raise ValueError('missing label policy metadata')
        # Explicit legacy branch: historical files are read without being rewritten.
        card = label_metadata(GROSS_POLICY)
    else:
        if not all(key in manifest for key in _CARD_KEYS):
            raise ValueError('incomplete label policy metadata')
        card = label_metadata(manifest['label_policy'], manifest['label_fee'], manifest['label_adverse_price'])
        if (manifest['label_cost_name'] != card['label_cost_name'] or
                type(manifest['label_horizon_hours']) is not int or
                manifest['label_horizon_hours'] != LABEL_HORIZON_HOURS):
            raise ValueError('label policy cost name or horizon mismatch')
        if card['label_policy'] == NET_POLICY and any(not isinstance(manifest[k], str) for k in ['label_fee', 'label_adverse_price']):
            raise ValueError('label policy costs must be decimal text')
    if expected_policy is not None and card['label_policy'] != expected_policy:
        raise ValueError('label policy mismatch')
    return card


def label_values(entry, exit, policy, fee=None, adverse=None):
    """保留gross浮点统计，使用精确有限乘积严格判断净收益的正负。"""
    card = label_metadata(policy, fee, adverse)
    entry, exit = _finite_decimal(entry, 'entry price'), _finite_decimal(exit, 'exit price')
    if entry <= 0 or exit <= 0:
        raise ValueError('nonpositive label price')
    # Product coefficients need sum(digits) precision; quotient subtraction also
    # needs room for the price magnitude gap. Never inherit the caller's rounding.
    precision = max(80, len(entry.as_tuple().digits) + len(exit.as_tuple().digits) +
                    abs(entry.adjusted() - exit.adjusted()) + 40)
    with localcontext() as ctx:
        ctx.prec = precision
        ctx.Emax = max(ctx.Emax, entry.adjusted() + precision, exit.adjusted() + precision)
        ctx.Emin = min(ctx.Emin, entry.as_tuple().exponent - precision, exit.as_tuple().exponent - precision)
        gross = float(exit / entry - 1)
        if not math.isfinite(gross):
            raise ValueError('non-finite label return')
        if policy == GROSS_POLICY:
            return dict(label_return=gross, label_net_return_text=None, label=int(exit > entry))
        fee, adverse = Decimal(card['label_fee']), Decimal(card['label_adverse_price'])
        numerator = exit * (1 - fee) ** 2 * (1 - adverse)
        denominator = entry * (1 + adverse)
        return dict(label_return=gross, label_net_return_text=str(numerator / denominator - 1),
                    label=int(numerator > denominator))
