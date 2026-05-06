from cv_evaluator.models import ExtractedCV, SeniorityScore, EducationLevel

EDUCATION_SCORES = {
    EducationLevel.HIGH_SCHOOL: 0,
    EducationLevel.BACHELOR: 10,
    EducationLevel.MASTER: 15,
    EducationLevel.PHD: 15,
}


def calculate_score(extracted: ExtractedCV) -> SeniorityScore:
    experience_score = _score_experience(extracted.years_of_experience)
    skills_score = _score_skills(extracted.skills)
    education_score = _score_education(extracted.education_level)
    seniority_score = _score_seniority(extracted.current_role, extracted.previous_roles)

    total = experience_score + skills_score + education_score + seniority_score

    return SeniorityScore(
        total=round(total, 1),
        experience_score=experience_score,
        skills_score=skills_score,
        education_score=education_score,
        seniority_score=seniority_score,
    )


def _score_experience(years: float) -> float:
    if years >= 10:
        return 40.0
    return round((years / 10) * 40, 1)


def _score_skills(skills: list[str]) -> float:
    count = len(skills)
    if count >= 20:
        return 30.0
    return round((count / 20) * 30, 1)


def _score_education(education_level: EducationLevel) -> float:
    return float(EDUCATION_SCORES.get(education_level, 0))


def _score_seniority(current_role: str, previous_roles: list[str]) -> float:
    """Aktuální role má větší váhu než historické – někdo dříve senior je dnes
    juniorský konzultant a opačně. Pokud aktuální role nedává jasný signál,
    podíváme se i do historie (slabší váha)."""
    senior_keywords = ["senior", "lead", "head", "principal", "architect", "director", "cto", "vp"]
    mid_keywords = ["mid", "medior", "analyst", "engineer", "developer"]

    current = current_role.lower()
    if any(k in current for k in senior_keywords):
        return 15.0
    if any(k in current for k in mid_keywords):
        return 8.0

    history = [r.lower() for r in previous_roles]
    if any(k in r for r in history for k in senior_keywords):
        return 10.0  # slabší váha – kariéru posunul jinam
    if any(k in r for r in history for k in mid_keywords):
        return 5.0

    return 3.0