import json

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from cv_evaluator.config import OPENAI_API_KEY
from cv_evaluator.models import ExtractedCV, FinalAnalysis, SeniorityScore
from cv_evaluator.prompts.finalizer import HUMAN_PROMPT, SYSTEM_PROMPT
from cv_evaluator.utils.logger import logger


def _get_chain():
    model = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.2,
        api_key=SecretStr(OPENAI_API_KEY),
    ).with_structured_output(FinalAnalysis)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT),
    ])
    return prompt | model


async def finalize_report(
    extracted: ExtractedCV,
    score: SeniorityScore,
    matches: list[dict],
) -> FinalAnalysis:
    chain = _get_chain()
    result = await chain.ainvoke({
        "profile_json": json.dumps(extracted.model_dump(), ensure_ascii=False, indent=2),
        "score_json": json.dumps(score.model_dump(), ensure_ascii=False, indent=2),
        "matches_json": json.dumps(matches, ensure_ascii=False, indent=2),
    })
    assert isinstance(result, FinalAnalysis)
    logger.info(
        f"Finalizer: salary {result.salary.min_czk}–{result.salary.max_czk} CZK, "
        f"strengths={len(result.explanation.strengths)}, "
        f"weaknesses={len(result.explanation.weaknesses)}"
    )
    return result
