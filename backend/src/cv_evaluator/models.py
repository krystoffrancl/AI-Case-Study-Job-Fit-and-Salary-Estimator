from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class EducationLevel(str, Enum):
    HIGH_SCHOOL = "high_school"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class CVData(BaseModel):
    raw_text: str
    filename: str


class ExtractedCV(BaseModel):
    skills: list[str]
    years_of_experience: float = Field(ge=0, le=50)
    education_level: EducationLevel
    current_role: str = Field(
        description="Aktuální (nebo nejnovější) pracovní pozice uchazeče."
    )
    previous_roles: list[str] = Field(
        default_factory=list,
        description="Všechny předchozí pozice v anti-chronologickém pořadí (nejnovější první). Prázdný seznam, pokud uchazeč nemá pracovní historii.",
    )
    industries: list[str]
    languages: list[str]


class SeniorityScore(BaseModel):
    total: float = Field(ge=0, le=100)
    experience_score: float = Field(ge=0, le=40)
    skills_score: float = Field(ge=0, le=30)
    education_score: float = Field(ge=0, le=15)
    seniority_score: float = Field(ge=0, le=15)


class SalaryEstimate(BaseModel):
    min_czk: int = Field(ge=0)
    max_czk: int = Field(ge=0)

    def model_post_init(self, __context: Any) -> None:
        if self.max_czk < self.min_czk:
            raise ValueError("max_czk musí být větší než min_czk")


class Explanation(BaseModel):
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[str]


class FinalAnalysis(BaseModel):
    """Výstup posledního LLM volání – odhad platu + vysvětlení dohromady."""
    salary: SalaryEstimate
    explanation: Explanation


class Report(BaseModel):
    extracted: ExtractedCV
    seniority: SeniorityScore
    salary: SalaryEstimate
    explanation: Explanation
    matches: list[dict] = []


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