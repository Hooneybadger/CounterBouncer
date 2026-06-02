ORDER = {'ACCEPT': 0, 'DEGRADED': 1, 'REJECT': 2}


def verdict(reasons):
    return {'verdict': max((r['severity'] for r in reasons), key=ORDER.get, default='ACCEPT'),
            'reasons': reasons}


def reason(code, severity, **evidence):
    return {'code': code, 'severity': severity, 'evidence': evidence}
