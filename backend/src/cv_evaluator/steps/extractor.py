from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from cv_evaluator.config import OPENAI_API_KEY
from cv_evaluator.models import CVData, ExtractedCV
from cv_evaluator.prompts.extractor import HUMAN_PROMPT, SYSTEM_PROMPT
from cv_evaluator.utils.logger import logger


def get_chain():
    """Používá `with_structured_output` (OpenAI Structured Outputs / strict json_schema)
    místo PydanticOutputParseru – ten u gpt-4.1-nano občas vrací schema místo instance."""
    model = ChatOpenAI(
        model="gpt-4.1-nano",
        temperature=0,
        api_key=SecretStr(OPENAI_API_KEY),
    ).with_structured_output(ExtractedCV)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT),
    ])

    return prompt | model


async def extract_cv_data(cv_data: CVData) -> ExtractedCV:
    chain = get_chain()
    result = await chain.ainvoke({"cv_text": cv_data.raw_text})
    assert isinstance(result, ExtractedCV)
    logger.info(f"Extrahovaná data: {result}")
    return result
