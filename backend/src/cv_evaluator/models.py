"""Pydantic schémata pro celou pipeline.

Field descriptions slouží i jako instrukce pro LLM přes `with_structured_output`,
proto jsou rozepsanější než běžně.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EducationLevel(str, Enum):
    HIGH_SCHOOL = "high_school"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class CVData(BaseModel):
    raw_text: str
    filename: str


# ---------- Personality / soft skills ---------------------------------------

class PersonalityTraits(BaseModel):
    """4 kategorie konkrétních signálů z CV (citace/parafráze, ne hodnocení)."""

    leadership_signals: list[str] = Field(
        default_factory=list,
        description="Vedení týmu, mentoring, projekty s impactem.",
    )
    initiative_signals: list[str] = Field(
        default_factory=list,
        description="Vlastní projekty, certifikace mimo zaměstnání, side projekty.",
    )
    collaboration_signals: list[str] = Field(
        default_factory=list,
        description="Cross-functional projekty, prezentace, open source, komunita.",
    )
    growth_signals: list[str] = Field(
        default_factory=list,
        description="Rychlé povýšení, kurzy, přechod na novou technologii.",
    )


# ---------- Career trajectory -----------------------------------------------

TrajectoryDirection = Literal["ascending", "stable", "lateral", "descending", "unknown"]


class CareerTrajectory(BaseModel):
    direction: TrajectoryDirection = Field(
        description=(
            "ascending = jasný růst seniority, stable = stejná úroveň, "
            "lateral = změny oborů bez růstu, descending = sestup, "
            "unknown = krátká nebo nečitelná historie."
        )
    )
    years_to_senior: float | None = Field(
        default=None,
        description="Počet let do první senior role. None pokud uchazeč ještě senior není.",
    )
    role_diversity: int = Field(
        default=0, ge=0,
        description="Počet různých typů rolí v kariéře.",
    )


# ---------- Skills ----------------------------------------------------------

SkillTier = Literal["expert", "core", "basic", "unknown"]


class NormalizedSkill(BaseModel):
    """Skill s canonical názvem a tier klasifikací (přiřazuje LLM podle kontextu)."""

    name: str = Field(description="Canonical název ('Python', 'Kubernetes', 'EKG').")
    tier: SkillTier = Field(default="unknown")
    category: str | None = Field(
        default=None,
        description="Volitelný tag pro UI ('language', 'devops', 'healthcare').",
    )


# ---------- Extracted CV ----------------------------------------------------

class ExtractedCV(BaseModel):
    skills: list[NormalizedSkill] = Field(
        description=(
            "Tvrdé profesní dovednosti s canonical názvem a tierem. "
            "LLM klasifikuje tier podle kontextu role uchazeče."
        ),
    )
    years_of_experience: float = Field(ge=0, le=50)
    education_level: EducationLevel
    current_role: str = Field(description="Aktuální (nebo nejnovější) pozice.")
    previous_roles: list[str] = Field(
        default_factory=list,
        description="Předchozí pozice, anti-chronologicky. Prázdný seznam pokud žádná.",
    )
    industries: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    personality_traits: PersonalityTraits = Field(default_factory=PersonalityTraits)
    career_trajectory: CareerTrajectory = Field(
        default_factory=lambda: CareerTrajectory(direction="unknown")
    )


# ---------- Seniority score -------------------------------------------------

class SeniorityScore(BaseModel):
    total: float = Field(ge=0, le=100)
    experience_score: float = Field(ge=0, le=35)
    skills_score: float = Field(ge=0, le=25)
    education_score: float = Field(ge=0, le=10)
    role_seniority_score: float = Field(ge=0, le=15)
    personality_score: float = Field(ge=0, le=15)


# ---------- Salary ----------------------------------------------------------

class SalaryAnchor(BaseModel):
    """Deterministicky spočtená kotva. Finalizer LLM smí ±drift_pct upravit."""

    center_czk: int = Field(ge=0)
    min_czk: int = Field(ge=0)
    max_czk: int = Field(ge=0)
    method: str

    def model_post_init(self, __context: Any) -> None:
        if self.max_czk < self.min_czk:
            raise ValueError("max_czk musí být >= min_czk")


class SalaryEstimate(BaseModel):
    min_czk: int = Field(ge=0)
    max_czk: int = Field(ge=0)

    def model_post_init(self, __context: Any) -> None:
        if self.max_czk < self.min_czk:
            raise ValueError("max_czk musí být >= min_czk")


# ---------- Growth plan -----------------------------------------------------

class GrowthPlanStep(BaseModel):
    action: str = Field(description="Měřitelná akce (ne 'zlepšit X').")
    timeline_months: int = Field(ge=1, le=60)
    expected_outcome: str = Field(description="Ověřitelný výstup (cert, projekt, …).")


class GrowthPlan(BaseModel):
    """Cesta k +30 % mzdě – MUST HAVE ze zadání."""

    target_salary_czk: int = Field(ge=0)
    target_role: str
    timeline_months: int = Field(ge=3, le=60)
    skill_gaps: list[str]
    steps: list[GrowthPlanStep] = Field(description="3-5 kroků.")
    rationale: str = Field(description="1-3 věty: proč tato cílová role a kroky.")


# ---------- Explanation -----------------------------------------------------

class Explanation(BaseModel):
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[str]


class FinalAnalysis(BaseModel):
    """Výstup finalizer LLM: plat + vysvětlení + růstový plán."""

    salary: SalaryEstimate
    explanation: Explanation
    growth_plan: GrowthPlan


# ---------- Data quality + cost ---------------------------------------------

ConfidenceLevel = Literal["high", "medium", "low"]


class DataQuality(BaseModel):
    confidence: ConfidenceLevel
    score: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class CostSummary(BaseModel):
    total_usd: float = 0.0
    total_czk: float = 0.0
    calls: int = 0
    by_model: dict[str, float] = Field(default_factory=dict)


# ---------- Final report + job ----------------------------------------------

class Report(BaseModel):
    extracted: ExtractedCV
    seniority: SeniorityScore
    salary: SalaryEstimate
    salary_anchor: SalaryAnchor | None = None
    explanation: Explanation
    growth_plan: GrowthPlan | None = None
    matches: list[dict] = Field(default_factory=list)
    data_quality: DataQuality | None = None
    cost: CostSummary | None = None


class JobStatus(str, Enum):
    RECEIVED = "received"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    SCORING = "scoring"
    ESTIMATING = "estimating"
    EXPLAINING = "explaining"
    DONE = "done"
    FAILED = "failed"


class Job(BaseModel):
    id: str
    status: JobStatus
    result: Report | None = None
    error: str | None = None
