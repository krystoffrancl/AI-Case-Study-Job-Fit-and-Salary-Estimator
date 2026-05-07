"""Deterministická kotva pro odhad mzdy.

Algoritmus:
1. Vážený průměr low/high/after-5y přes top-k matche (váha = similarity).
2. Center umístíme dle seniority skóre: 0-50 mezi low-high, 50-100 mezi high-after5.
3. Trajectory upraví ±3-8 %.
4. Finalizer LLM smí výsledek vychýlit jen v rámci ±anchor_drift_pct.

Výhoda: stejné CV → stejný plat. LLM jen vysvětluje a jemně doladí.
"""
from __future__ import annotations

import numpy as np

from cv_evaluator.config import settings
from cv_evaluator.models import CareerTrajectory, SalaryAnchor, SeniorityScore
from cv_evaluator.utils.logger import logger


def compute_anchor(
    score: SeniorityScore,
    matches: list[dict],
    trajectory: CareerTrajectory | None = None,
) -> SalaryAnchor:
    if not matches:
        return SalaryAnchor(center_czk=40000, min_czk=35000, max_czk=50000, method="fallback")

    weights = np.array([max(m.get("similarity", 0.0), 0.01) for m in matches], dtype=float)
    lows = np.array([m["salary_low_monthly_czk"] for m in matches], dtype=float)
    highs = np.array([m["salary_high_monthly_czk"] for m in matches], dtype=float)
    # after_5y může být 0 (chybějící data) → fallback na high
    after5_raw = np.array(
        [m.get("salary_after_5_years_monthly_czk") or m["salary_high_monthly_czk"] for m in matches],
        dtype=float,
    )
    after5 = np.where(after5_raw > 0, after5_raw, highs)

    base_low = float(np.average(lows, weights=weights))
    base_high = float(np.average(highs, weights=weights))
    base_after5 = float(np.average(after5, weights=weights))

    if score.total <= 50:
        center = base_low + (base_high - base_low) * (score.total / 50.0)
        method = f"score {score.total:.0f} → mezi low a high"
    else:
        center = base_high + (base_after5 - base_high) * ((score.total - 50.0) / 50.0)
        method = f"score {score.total:.0f} → mezi high a po-5-letech"

    if trajectory is not None:
        center, note = _apply_trajectory(center, trajectory)
        if note:
            method += f"; {note}"

    drift = settings.anchor_drift_pct
    anchor = SalaryAnchor(
        center_czk=int(round(center)),
        min_czk=int(round(center * (1.0 - drift))),
        max_czk=int(round(center * (1.0 + drift))),
        method=method,
    )
    logger.info(f"Salary anchor: {anchor.center_czk} CZK ({anchor.min_czk}–{anchor.max_czk}, {method})")
    return anchor


def _apply_trajectory(center: float, t: CareerTrajectory) -> tuple[float, str]:
    if t.direction == "ascending":
        if t.years_to_senior is not None and t.years_to_senior < 4:
            return center * 1.08, "rychlý postup +8 %"
        return center * 1.04, "rostoucí trajektorie +4 %"
    if t.direction == "descending":
        return center * 0.92, "klesající trajektorie -8 %"
    if t.direction == "lateral":
        return center * 0.97, "laterální pohyb -3 %"
    return center, ""
