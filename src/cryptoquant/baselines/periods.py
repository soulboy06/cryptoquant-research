"""公开可评价期间；保留测试不能从参数绕过冻结流程。"""


def period_bounds(config, period, *, window=None):
    if period == 'development':
        bounds = config.development_start, config.development_end
    elif period == 'validation':
        bounds = config.validation_start, config.validation_end
    else:
        raise ValueError('unsupported evaluation period; test requires separate freeze workflow')
    if window is None:
        return bounds
    # Import here keeps the legacy default independent of research configuration.
    from cryptoquant.models.research_config import RESEARCH_WINDOWS
    if not isinstance(window, str) or window not in RESEARCH_WINDOWS:
        raise ValueError('unsupported research window')
    fixed = RESEARCH_WINDOWS[window]
    if fixed.period != period:
        raise ValueError('research window period mismatch')
    if not bounds[0] <= fixed.start < fixed.end <= bounds[1]:
        raise ValueError('research window must be contained in original partition')
    return fixed.start, fixed.end
