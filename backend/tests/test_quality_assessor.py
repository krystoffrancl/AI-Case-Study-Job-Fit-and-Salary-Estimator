"""Testy data quality scoringu."""
from __future__ import annotations

from cv_evaluator.models import (
    CareerTrajectory,
    EducationLevel,
    ExtractedCV,
    NormalizedSkill,
    PersonalityTraits,
)
from cv_evaluator.steps.quality_assessor import assess_quality


def test_high_quality_when_everything_present(senior_dev, sample_matches):
    quality = assess_quality(senior_dev, sample_matches)
    assert quality.confidence == "high"
    assert quality.score >= 0.75
    assert quality.warnings == []


def test_low_quality_with_no_experience_and_few_skills(office_worker):
    # Žádné matche → další signály padnou
    quality = assess_quality(office_worker, [])
    assert quality.confidence in ("low", "medium")
    assert quality.score < 0.75
    assert len(quality.warnings) >= 2


def test_warns_on_category_only_matches(senior_dev):
    matches = [
        {
            "position": "Generic Role",
            "group": "X",
            "salary_low_monthly_czk": 50000,
            "salary_high_monthly_czk": 80000,
            "salary_after_5_years_monthly_czk": 0,
            "salary_source": "category",
            "similarity": 0.6,
        }
    ]
    quality = assess_quality(senior_dev, matches)
    assert any("kategori" in w.lower() for w in quality.warnings)


def test_warns_on_high_unknown_tier_ratio(sample_matches):
    """Víc než 30 % skills s tier=unknown → warning."""
    cv = ExtractedCV(
        skills=[
            NormalizedSkill(name=f"Obskurní{i}", tier="unknown") for i in range(3)
        ] + [
            NormalizedSkill(name="Word", tier="basic"),
            NormalizedSkill(name="Excel", tier="basic"),
        ],
        years_of_experience=5,
        education_level=EducationLevel.BACHELOR,
        current_role="Operátor neznámého stroje",
        previous_roles=[],
        industries=[],
        languages=[],
        personality_traits=PersonalityTraits(),
        career_trajectory=CareerTrajectory(direction="stable"),
    )
    quality = assess_quality(cv, sample_matches)
    assert any("neurčen" in w.lower() for w in quality.warnings)
