"""Deterministický rule-based scoring na 5 dimenzích.

Maxima: experience 35 + skills 25 + education 10 + role 15 + personality 15 = 100.
Skills jsou už tier-classified LLM-em v rámci extrakce.
"""
from __future__ import annotations

import unicodedata

from cv_evaluator.models import (
    EducationLevel,
    ExtractedCV,
    NormalizedSkill,
    PersonalityTraits,
    SeniorityScore,
    SkillTier,
)
from cv_evaluator.utils.logger import logger

__all__ = ["calculate_score"]


# ---------- Konstanty -------------------------------------------------------

MAX_EXPERIENCE = 35.0
MAX_SKILLS = 25.0
MAX_ROLE = 15.0
MAX_PERSONALITY = 15.0

TIER_WEIGHTS: dict[SkillTier, float] = {
    "expert": 3.0,
    "core": 1.0,
    "basic": 0.3,
    "unknown": 0.5,
}
SKILL_WEIGHT_CAP = 24.0  # ~8 expert skills → max

EDUCATION_SCORES: dict[EducationLevel, float] = {
    EducationLevel.HIGH_SCHOOL: 0.0,
    EducationLevel.BACHELOR: 7.0,
    EducationLevel.MASTER: 10.0,
    EducationLevel.PHD: 10.0,
}


def _strip_diacritics(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


# Předpočítáno bez diakritiky – stejná logika pokrývá "Vrchní" i "Vrchni".
_SENIOR_KEYWORDS = tuple(_strip_diacritics(k) for k in (
    "senior", "lead", "head", "principal", "chief", "architect", "director",
    "cto", "ceo", "cfo", "coo", "cio", "vp", "manager", "owner", "partner",
    "vedoucí", "ředitel", "ředitelka", "hlavní", "vrchní", "primář", "primářka",
    "stavbyvedoucí", "mistr", "supervisor", "šéfkuchař", "soudce", "advokát",
))
_MID_KEYWORDS = tuple(_strip_diacritics(k) for k in (
    "mid", "medior", "analyst", "engineer", "developer", "specialist",
    "consultant", "officer", "coordinator", "administrator",
    "specialista", "konzultant", "technik", "referent", "analytik",
    "účetní", "sestra", "lékař", "lékařka", "učitel", "učitelka",
    "projektant", "asistent", "asistentka",
))


# ---------- Public API ------------------------------------------------------

def calculate_score(extracted: ExtractedCV) -> SeniorityScore:
    exp = _score_experience(extracted.years_of_experience)
    skills = _score_skills(extracted.skills)
    edu = _score_education(extracted.education_level)
    role = _score_role(extracted.current_role, extracted.previous_roles)
    personality = _score_personality(extracted.personality_traits)
    total = exp + skills + edu + role + personality
    logger.info(
        f"Scorer: yoe={extracted.years_of_experience}→{exp:.1f}/35, "
        f"skills({len(extracted.skills)})→{skills:.1f}/25, "
        f"edu({extracted.education_level.value})→{edu:.1f}/10, "
        f"role({extracted.current_role!r})→{role:.1f}/15, "
        f"personality→{personality:.1f}/15"
    )

    return SeniorityScore(
        total=round(total, 1),
        experience_score=round(exp, 1),
        skills_score=round(skills, 1),
        education_score=round(edu, 1),
        role_seniority_score=round(role, 1),
        personality_score=round(personality, 1),
    )


# ---------- Dimensions ------------------------------------------------------

def _score_experience(years: float) -> float:
    if years >= 10:
        return MAX_EXPERIENCE
    return (years / 10.0) * MAX_EXPERIENCE


def _score_skills(skills: list[NormalizedSkill]) -> float:
    if not skills:
        return 0.0
    weighted = sum(TIER_WEIGHTS.get(s.tier, 0.5) for s in skills)
    return min(weighted, SKILL_WEIGHT_CAP) / SKILL_WEIGHT_CAP * MAX_SKILLS


def _score_education(level: EducationLevel) -> float:
    return EDUCATION_SCORES.get(level, 0.0)


def _score_role(current: str, previous: list[str]) -> float:
    """Aktuální role má větší váhu než historické (někdo bývalý senior je dnes junior PM)."""
    cur = _strip_diacritics(current.lower())
    if any(k in cur for k in _SENIOR_KEYWORDS):
        return MAX_ROLE
    if any(k in cur for k in _MID_KEYWORDS):
        return MAX_ROLE * 0.55

    history = [_strip_diacritics(r.lower()) for r in previous]
    if any(k in r for r in history for k in _SENIOR_KEYWORDS):
        return MAX_ROLE * 0.65
    if any(k in r for r in history for k in _MID_KEYWORDS):
        return MAX_ROLE * 0.35
    return MAX_ROLE * 0.20


def _score_personality(t: PersonalityTraits) -> float:
    """Diminishing returns per kategorii: max 6/3/3/3 = 15."""
    leadership = min(len(t.leadership_signals), 4) * 1.5
    initiative = min(len(t.initiative_signals), 3)
    collaboration = min(len(t.collaboration_signals), 3)
    growth = min(len(t.growth_signals), 3)
    return min(leadership + initiative + collaboration + growth, MAX_PERSONALITY)
