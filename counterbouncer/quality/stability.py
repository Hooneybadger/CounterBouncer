import math
import statistics as stats


def summarize(values):
    values = list(values)
    if any(not math.isfinite(x) for x in values):
        raise ValueError('nonfinite observation')
    if not values:
        return {'n': 0, 'median': None, 'mad': None, 'cv': None, 'outlier_indices': []}
    median = stats.median(values)
    mad = stats.median(abs(x - median) for x in values)
    mean = stats.mean(values)
    cv = stats.stdev(values) / abs(mean) if len(values) > 1 and mean != 0 else None
    # Modified z score. MAD=0 has no estimable scale, so do not invent outliers.
    outliers = [i for i, x in enumerate(values) if mad > 0 and .67448975 * abs(x - median) / mad > 3.5]
    return {'n': len(values), 'median': median, 'mad': mad, 'mean': mean,
            'cv': cv, 'outlier_indices': outliers}
