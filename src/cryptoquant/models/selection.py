"""仅按预定base验证交易成绩筛选；失败与不合格候选全部保留。"""

from decimal import Decimal


def qualification(summary):
    if summary.get('period') != 'validation' or summary.get('cost') != 'base':
        raise ValueError('selection requires base validation results')
    reasons = []
    if Decimal(str(summary['net_return'])) <= 0:
        reasons.append('net_return_not_positive')
    if Decimal(str(summary['max_drawdown'])) > Decimal('.25'):
        reasons.append('max_drawdown_exceeds_25_percent')
    if summary['floor_triggers'] != 0:
        reasons.append('equity_floor_triggered')
    if summary['closed_cycles'] < 30:
        reasons.append('fewer_than_30_closed_cycles')
    return dict(qualified=not reasons, failure_reasons=reasons)


def select_candidate(candidates):
    rows = []
    for candidate in candidates:
        row = dict(candidate)
        if row.get('status', 'complete') != 'complete':
            row.update(qualified=False, failure_reasons=['experiment_failed'])
        else:
            row.update(qualification(row['summary']))
        rows.append(row)
    qualified = [x for x in rows if x['qualified']]
    def key(row):
        summary = row['summary']
        return (-Decimal(str(summary['final_equity'])), Decimal(str(summary['max_drawdown'])),
                Decimal(str(summary['turnover_usdt'])), Decimal(str(row['C'])), -Decimal(str(row['threshold'])))
    selected = min(qualified, key=key) if qualified else None
    return dict(candidates=rows, selected=selected, ranking='final_equity desc, drawdown asc, turnover asc, C asc, threshold desc',
                eligibility='base validation: return>0, drawdown<=25%, floor=0, closed_cycles>=30')
