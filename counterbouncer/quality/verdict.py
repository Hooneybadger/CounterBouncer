INTEGRITY_ORDER = {'VALID': 0, 'DEGRADED': 1, 'INVALID': 2}
CONTEXT_ORDER = {'CONTROLLED': 0, 'CONTAMINATED': 1, 'UNKNOWN': 2}
INTEGRITY_FROM_LEGACY = {'ACCEPT': 'VALID', 'REJECT': 'INVALID'}
USABILITY = {
    ('VALID', 'CONTROLLED'): 'COMPARABLE',
    ('VALID', 'CONTAMINATED'): 'VALID_BUT_CONTAMINATED',
    ('VALID', 'UNKNOWN'): 'VALID_BUT_UNKNOWN_CONTEXT',
    ('DEGRADED', 'CONTROLLED'): 'DEGRADED_COUNTERS',
    ('DEGRADED', 'CONTAMINATED'): 'DEGRADED_AND_CONTAMINATED',
    ('DEGRADED', 'UNKNOWN'): 'DEGRADED_AND_UNKNOWN_CONTEXT',
    ('INVALID', 'CONTROLLED'): 'UNUSABLE',
    ('INVALID', 'CONTAMINATED'): 'UNUSABLE',
    ('INVALID', 'UNKNOWN'): 'UNUSABLE',
}


def collapse(integrity, context):
    if integrity == 'INVALID':
        return 'REJECT'
    if integrity == 'VALID' and context == 'CONTROLLED':
        return 'ACCEPT'
    return 'DEGRADED'


def reason(code, severity, axis='integrity', **evidence):
    return {'code': code, 'axis': axis, 'severity': severity, 'evidence': evidence}


def normalize_reason(item):
    item = dict(item)
    axis = item.get('axis', 'integrity')
    severity = item['severity']
    if axis == 'integrity':
        severity = INTEGRITY_FROM_LEGACY.get(severity, severity)
        if severity not in INTEGRITY_ORDER:
            raise ValueError(f'unknown integrity severity {severity}')
    elif axis == 'context':
        if severity not in CONTEXT_ORDER:
            raise ValueError(f'unknown context severity {severity}')
    else:
        raise ValueError(f'unknown axis {axis}')
    return {'code': item['code'], 'axis': axis, 'severity': severity,
            'evidence': dict(item.get('evidence') or {})}


def assemble(reasons):
    reasons = [normalize_reason(item) for item in reasons]
    integrity = max((item['severity'] for item in reasons if item['axis'] == 'integrity'),
                    key=INTEGRITY_ORDER.get, default='VALID')
    context = max((item['severity'] for item in reasons if item['axis'] == 'context'),
                  key=CONTEXT_ORDER.get, default='CONTROLLED')
    return {
        'integrity': integrity,
        'context': context,
        'usability': USABILITY[(integrity, context)],
        'verdict': collapse(integrity, context),
        'reasons': reasons,
    }


# v1 name: one-axis dict. Still returns ACCEPT/DEGRADED/REJECT plus the two axes.
def verdict(reasons):
    return assemble(reasons)
