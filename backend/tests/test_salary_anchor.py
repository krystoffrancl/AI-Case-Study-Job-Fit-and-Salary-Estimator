"""Testy salary anchoru – determinismus, range a trajectory modifier."""
from __future__ import annotations

from cv_evaluator.models import CareerTrajectory, SeniorityScore
from cv_evaluator.steps.salary_anchor import compute_anchor


def _score(total: float) -> SeniorityScore:
    """Pomocná: vyrobí validní SeniorityScore s daným totalem."""
    return SeniorityScore(
        total=total,
        experience_score=min(total * 0.35, 35),
        skills_score=min(total * 0.25, 25),
        education_score=min(total * 0.10, 10),
        role_seniority_score=min(total * 0.15, 15),
        personality_score=min(total * 0.15, 15),
    )


def test_anchor_is_deterministic(sample_matches):
    score = _score(70.0)
    a1 = compute_anchor(score, sample_matches)
    a2 = compute_anchor(score, sample_matches)
    assert a1.center_czk == a2.center_czk
    assert a1.min_czk == a2.min_czk
    assert a1.max_czk == a2.max_czk


def test_low_score_maps_below_high(sample_matches):
    score = _score(30.0)
    anchor = compute_anchor(score, sample_matches)
    # max(low) ≈ 60k, max(high) ≈ 100k. Score 30 → mezi nimi, blíž k low.
    assert anchor.center_czk < 90000


def test_high_score_maps_above_high(sample_matches):
    score = _score(85.0)
    anchor = compute_anchor(score, sample_matches)
    # Score 85 → blíž k after_5_years (~125k)
    assert anchor.center_czk >= 100000


def test_descending_trajectory_lowers_anchor(sample_matches):
    score = _score(70.0)
    base = compute_anchor(score, sample_matches)
    descending = compute_anchor(
        score, sample_matches, trajectory=CareerTrajectory(direction="descending")
    )
    assert descending.center_czk < base.center_czk


def test_drift_band_is_symmetric(sample_matches):
    score = _score(60.0)
    anchor = compute_anchor(score, sample_matches)
    # Default 10 % drift
    assert anchor.min_czk < anchor.center_czk < anchor.max_czk
    drift_low = anchor.center_czk - anchor.min_czk
    drift_high = anchor.max_czk - anchor.center_czk
    assert abs(drift_low - drift_high) <= 1  # rounding tolerance
