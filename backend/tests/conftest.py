from __future__ import annotations

import os

# Test fixtures nesmí potřebovat reálný OpenAI klíč.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-unit-tests")

import pytest

from cv_evaluator.models import (
    CareerTrajectory,
    EducationLevel,
    ExtractedCV,
    NormalizedSkill,
    PersonalityTraits,
)


def _ns(name: str, tier: str = "core", category: str | None = None) -> NormalizedSkill:
    return NormalizedSkill(name=name, tier=tier, category=category)  # type: ignore[arg-type]


@pytest.fixture
def senior_dev() -> ExtractedCV:
    return ExtractedCV(
        skills=[
            _ns("Python", "core", "language"),
            _ns("Kubernetes", "expert", "devops"),
            _ns("Terraform", "expert", "devops"),
            _ns("AWS", "expert", "cloud"),
            _ns("Kafka", "expert", "data"),
            _ns("PostgreSQL", "core", "database"),
            _ns("Docker", "core", "devops"),
            _ns("gRPC", "expert", "backend"),
        ],
        years_of_experience=8.0,
        education_level=EducationLevel.MASTER,
        current_role="Senior Backend Engineer",
        previous_roles=["Backend Engineer", "Junior Developer"],
        industries=["fintech"],
        languages=["čeština", "angličtina"],
        personality_traits=PersonalityTraits(
            leadership_signals=["Vedl tým 4 vývojářů", "Mentoroval 2 juniory"],
            initiative_signals=["AWS SAA cert (2024)"],
            collaboration_signals=["Prezentoval na PyCon CZ"],
            growth_signals=["Junior -> Senior za 3 roky"],
        ),
        career_trajectory=CareerTrajectory(
            direction="ascending", years_to_senior=3.0, role_diversity=1
        ),
    )


@pytest.fixture
def office_worker() -> ExtractedCV:
    return ExtractedCV(
        skills=[
            _ns("Word", "basic", "office"),
            _ns("Excel", "basic", "office"),
            _ns("PowerPoint", "basic", "office"),
            _ns("Outlook", "basic", "office"),
        ],
        years_of_experience=2.0,
        education_level=EducationLevel.HIGH_SCHOOL,
        current_role="Administrativní pracovník",
        previous_roles=[],
        industries=["administrativa"],
        languages=["čeština"],
        personality_traits=PersonalityTraits(),
        career_trajectory=CareerTrajectory(direction="stable"),
    )


@pytest.fixture
def junior_dev() -> ExtractedCV:
    return ExtractedCV(
        skills=[
            _ns("Python", "core", "language"),
            _ns("FastAPI", "core", "backend"),
            _ns("PostgreSQL", "core", "database"),
            _ns("Docker", "core", "devops"),
            _ns("Git", "core", "tooling"),
        ],
        years_of_experience=1.0,
        education_level=EducationLevel.BACHELOR,
        current_role="Junior Backend Developer",
        previous_roles=["Stážista"],
        industries=["e-commerce"],
        languages=["čeština", "angličtina"],
        personality_traits=PersonalityTraits(
            initiative_signals=["Vlastní portfolio na GitHubu"],
        ),
        career_trajectory=CareerTrajectory(direction="ascending"),
    )


@pytest.fixture
def pizzaiolo() -> ExtractedCV:
    """Edge case: profesi, kterou jsme nikdy v žádné taxonomii neměli –
    LLM-based tier classification musí fungovat i tady. Test používá ručně
    klasifikované skills (simulace LLM výstupu)."""
    return ExtractedCV(
        skills=[
            _ns("Výroba neapolské pizzy", "core", "hospitality"),
            _ns("Práce s dřevěnou pecí", "core", "hospitality"),
            _ns("48h fermentace těsta", "expert", "hospitality"),
            _ns("HACCP", "core", "hospitality"),
            _ns("AVPN certifikace", "expert", "hospitality"),
            _ns("Italská kuchyně", "core", "hospitality"),
        ],
        years_of_experience=6.0,
        education_level=EducationLevel.HIGH_SCHOOL,
        current_role="Hlavní pizzař",
        previous_roles=["Pizzař", "Pomocný kuchař"],
        industries=["fine-dining italian"],
        languages=["čeština", "italština"],
        personality_traits=PersonalityTraits(
            leadership_signals=["Vede tým 3 pizzařů"],
            growth_signals=["3 měsíční stáž v Neapoli (2022)"],
        ),
        career_trajectory=CareerTrajectory(
            direction="ascending", years_to_senior=4.0
        ),
    )


@pytest.fixture
def sample_matches() -> list[dict]:
    return [
        {
            "position": "Backend Developer",
            "group": "IT - vývoj software",
            "salary_low_monthly_czk": 60000,
            "salary_high_monthly_czk": 100000,
            "salary_after_5_years_monthly_czk": 130000,
            "salary_source": "position",
            "similarity": 0.85,
        },
        {
            "position": "Software Engineer",
            "group": "IT - vývoj software",
            "salary_low_monthly_czk": 55000,
            "salary_high_monthly_czk": 95000,
            "salary_after_5_years_monthly_czk": 125000,
            "salary_source": "position",
            "similarity": 0.78,
        },
        {
            "position": "Programátor",
            "group": "IT - vývoj software",
            "salary_low_monthly_czk": 50000,
            "salary_high_monthly_czk": 90000,
            "salary_after_5_years_monthly_czk": 115000,
            "salary_source": "position",
            "similarity": 0.70,
        },
    ]
