import json
from pathlib import Path

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from cv_evaluator.config import OPENAI_API_KEY
from cv_evaluator.models import ExtractedCV
from cv_evaluator.utils.logger import logger

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
EMBEDDINGS_PATH = DATA_DIR / "positions_embeddings.jsonl"
CHROMA_PATH = DATA_DIR / "chroma"
COLLECTION_NAME = "positions"
EMBEDDING_MODEL = "text-embedding-3-small"

_vectorstore: Chroma | None = None


def _build_embedder() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        api_key=SecretStr(OPENAI_API_KEY),
    )


def _load_into_collection(vs: Chroma) -> None:
    if not EMBEDDINGS_PATH.exists():
        raise FileNotFoundError(
            f"Chybí {EMBEDDINGS_PATH}. Spusť nejdřív: uv run python scripts/build_embeddings.py"
        )

    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    with open(EMBEDDINGS_PATH, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            ids.append(r["id"])
            embeddings.append(r["embedding"])
            documents.append(r["text"])
            metadatas.append({
                "position": r["position"],
                "group": r["group"],
                "salary_low_monthly_czk": r["salary_low_monthly_czk"],
                "salary_high_monthly_czk": r["salary_high_monthly_czk"],
                "salary_after_5_years_monthly_czk": r["salary_after_5_years_monthly_czk"],
                "salary_source": r["salary_source"],
            })

    vs._collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    logger.info(f"ChromaDB naplněna z {EMBEDDINGS_PATH.name} – {len(ids)} pozic")


def initialize_embeddings() -> None:
    global _vectorstore

    vs = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_build_embedder(),
        persist_directory=str(CHROMA_PATH),
        collection_metadata={"hnsw:space": "cosine"},
    )

    count = vs._collection.count()
    if count > 0:
        logger.info(f"ChromaDB načtena z disku – {count} pozic")
    else:
        _load_into_collection(vs)

    _vectorstore = vs


def _build_query(extracted: ExtractedCV) -> str:
    """Postaví query primárně z pozic, ne ze skills.

    Korpus v Chromě je "{position} ({group}). {duties}", takže query musí
    být taky position-driven – jinak skills jako 'TypeScript' přetáhnou
    matching k vývojářským pozicím i když uchazeč je analytik. Skills se
    používají v druhém LLM volání pro zpřesnění platu uvnitř rozsahu.
    """
    parts = [extracted.current_role]
    if extracted.previous_roles:
        parts.append("Předchozí pozice: " + ", ".join(extracted.previous_roles[:3]))
    if extracted.industries:
        parts.append("Obor: " + ", ".join(extracted.industries[:2]))
    return ". ".join(parts)


def find_matching_positions(extracted: ExtractedCV, k: int = 3) -> list[dict]:
    if _vectorstore is None:
        raise RuntimeError(
            "Vector store není inicializován – initialize_embeddings() musí běžet při startu."
        )

    query = _build_query(extracted)
    logger.info(f"Hledám pozice pro: {query}")

    results = _vectorstore.similarity_search_with_score(query=query, k=k)

    matches = []
    for doc, distance in results:
        meta = doc.metadata
        matches.append({
            "position": meta["position"],
            "group": meta["group"],
            "salary_low_monthly_czk": meta["salary_low_monthly_czk"],
            "salary_high_monthly_czk": meta["salary_high_monthly_czk"],
            "salary_after_5_years_monthly_czk": meta["salary_after_5_years_monthly_czk"],
            "salary_source": meta["salary_source"],
            "similarity": round(1 - distance, 3),
        })
    return matches
