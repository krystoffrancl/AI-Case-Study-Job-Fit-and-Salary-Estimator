"""Jednoduché eval metriky: Jaccard, MAE, in-range, distance-to-range."""
from __future__ import annotations

from collections.abc import Iterable


def jaccard_similarity(predicted: Iterable[str], truth: Iterable[str]) -> float:
    p = {s.lower().strip() for s in predicted if s and s.strip()}
    t = {s.lower().strip() for s in truth if s and s.strip()}
    if not (p | t):
        return 0.0
    return len(p & t) / len(p | t)


def in_range(value: float, low: float, high: float) -> bool:
    return low <= value <= high


def distance_to_range(value: float, low: float, high: float) -> float:
    if value < low:
        return low - value
    if value > high:
        return value - high
    return 0.0


def mae(predicted: float, truth: float) -> float:
    return abs(predicted - truth)


def aggregate(metric_dicts: list[dict]) -> dict:
    """Spočítá průměr / sumu pro každý klíč napříč records."""
    if not metric_dicts:
        return {}
    keys = set().union(*(d.keys() for d in metric_dicts))
    out: dict[str, float] = {}
    for key in keys:
        values = [d[key] for d in metric_dicts if key in d]
        if not values:
            continue
        if all(isinstance(v, bool) for v in values):
            out[f"{key}_pct"] = round(sum(values) / len(values) * 100, 1)
        else:
            try:
                out[f"{key}_avg"] = round(sum(values) / len(values), 3)
            except TypeError:
                pass
    return out
