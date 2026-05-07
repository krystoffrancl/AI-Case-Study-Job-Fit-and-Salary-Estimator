"""Critical-path testy pro deterministický scorer."""
from __future__ import annotations

from cv_evaluator.models import (
    CareerTrajectory,
    EducationLevel,
    ExtractedCV,
    NormalizedSkill,
    PersonalityTraits,
)
from cv_evaluator.steps.scorer import calculate_score


def _minimal_cv(
    role: str,
    skills: list[NormalizedSkill] | None = None,
    yoe: float = 5,
    education: EducationLevel = EducationLevel.MASTER,
    traits: PersonalityTraits | None = None,
) -> ExtractedCV:
    return ExtractedCV(
        skills=skills or [NormalizedSkill(name="X", tier="unknown")],
        years_of_experience=yoe,
        education_level=education,
        current_role=role,
        previous_roles=[],
        industries=[],
        languages=[],
        personality_traits=traits or PersonalityTraits(),
        career_trajectory=CareerTrajectory(direction="ascending"),
    )


def test_senior_dev_with_expert_skills_scores_high(senior_dev):
    score = calculate_score(senior_dev)
    assert score.total >= 70
    assert score.role_seniority_score == 15
    assert score.experience_score >= 25
    assert score.skills_score >= 18  # 5 expert + 3 core
    assert score.education_score == 10
    assert score.personality_score >= 4


def test_office_worker_scores_low(office_worker):
    score = calculate_score(office_worker)
    assert score.skills_score < 3  # 4× basic = 1.2 weighted
    assert score.total < 25
    assert score.personality_score == 0


def test_junior_dev_scores_in_middle(junior_dev):
    score = calculate_score(junior_dev)
    assert 10 <= score.total <= 45


def test_score_dimensions_sum_matches_total(senior_dev):
    score = calculate_score(senior_dev)
    components = (
        score.experience_score + score.skills_score + score.education_score
        + score.role_seniority_score + score.personality_score
    )
    assert abs(components - score.total) < 0.5


def test_pizzaiolo_scores_meaningfully(pizzaiolo):
    """Edge case: profese mimo IT. LLM klasifikuje skill tier, scorer funguje stejně."""
    score = calculate_score(pizzaiolo)
    assert score.skills_score >= 8
    assert score.role_seniority_score == 15  # "Hlavní pizzař" → keyword "hlavní"
    assert score.total >= 45


def test_non_it_senior_roles_recognized_in_czech():
    """České senior keywords (i bez diakritiky) musí dostat plný role_seniority."""
    roles = [
        "Vrchní sestra JIP", "Vrchni sestra",
        "Stavbyvedoucí", "Stavbyvedouci",
        "Šéfkuchař", "Sefkuchar",
        "Hlavní účetní", "Ředitel marketingu",
    ]
    for role in roles:
        score = calculate_score(_minimal_cv(role))
        assert score.role_seniority_score == 15, f"Role {role!r}: {score.role_seniority_score}"


def test_max_score_caps_at_100():
    extreme = ExtractedCV(
        skills=[NormalizedSkill(name=f"skill{i}", tier="expert") for i in range(20)],
        years_of_experience=20,
        education_level=EducationLevel.PHD,
        current_role="Principal Engineer / Architect",
        previous_roles=["Senior Engineer", "Lead Developer"],
        industries=[],
        languages=[],
        personality_traits=PersonalityTraits(
            leadership_signals=["a"] * 5,
            initiative_signals=["a"] * 4,
            collaboration_signals=["a"] * 4,
            growth_signals=["a"] * 4,
        ),
        career_trajectory=CareerTrajectory(direction="ascending"),
    )
    score = calculate_score(extreme)
    assert score.total <= 100
    assert score.skills_score <= 25
    assert score.personality_score <= 15
