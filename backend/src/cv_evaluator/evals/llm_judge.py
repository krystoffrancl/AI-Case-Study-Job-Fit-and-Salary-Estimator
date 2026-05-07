"""LLM-as-judge: kvalitativní známkování vysvětlení a growth planu (1-5 ve 4 dimenzích)."""
from __future__ import annotations

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from cv_evaluator.config import settings


class JudgeScores(BaseModel):
    specificity: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    factual_grounding: int = Field(ge=1, le=5)
    consistency: int = Field(ge=1, le=5)


class JudgeVerdict(BaseModel):
    scores: JudgeScores
    reasoning: str = Field(description="2-4 věty proč tyto skóre.")
    overall: Literal["pass", "borderline", "fail"]


SYSTEM = """Jsi senior HR profesionál, který hodnotí AI-generované vysvětlení k odhadu mzdy.
Známkuj 1 (špatné) - 5 (excelentní) ve čtyřech dimenzích:

1. **specificity**: cituje konkrétní fakta z CV (firma, projekt, technologie, certifikace)?
   1 = jen obecné fráze; 5 = přesné odkazy na CV.

2. **actionability**: jsou doporučení/kroky měřitelné?
   1 = "buď lepší", "rozvíjej se"; 5 = "získej AWS Cert za 3 měsíce, ~6h týdně".

3. **factual_grounding**: vyplývá vše z předaných dat (CV + matche), nebo si AI vymýšlí?
   1 = halucinace, neexistující fakta; 5 = vše dohledatelné v podkladech.

4. **consistency**: doporučení / kroky jsou v souladu se zjištěnými slabinami?
   1 = doporučuje opačně než slabiny říkají; 5 = perfektní soulad.

Vrať `overall`:
- "pass" pokud min(scores) >= 3 AND avg >= 3.5
- "fail" pokud min(scores) <= 1 OR avg < 2.5
- "borderline" jinak"""

HUMAN = """## CV (raw)
{cv_text}

## AI vysvětlení a růstový plán
{ai_output}

Ohodnoť ve formátu JudgeVerdict."""


def build_judge_chain():
    model = ChatOpenAI(
        model=settings.judge_model,
        temperature=0,
        api_key=settings.openai_api_key,
    ).with_structured_output(JudgeVerdict)
    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM), ("human", HUMAN)])
    return prompt | model


async def judge(cv_text: str, ai_output: str) -> JudgeVerdict:
    chain = build_judge_chain()
    result = await chain.ainvoke({"cv_text": cv_text, "ai_output": ai_output})
    assert isinstance(result, JudgeVerdict)
    return result
