"""ChromaDB-backed retrieval pozic + LRU cache na query embeddingy.

Při startu hydratuje Chromu z `positions_embeddings.jsonl` (žádné OpenAI volání).
Per-request volání: query embed → similarity search nad cosinem.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from cv_evaluator.config import settings
from cv_evaluator.models import ExtractedCV
from cv_evaluator.utils.logger import logger

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
EMBEDDINGS_PATH = DATA_DIR / "positions_embeddings.jsonl"
CHROMA_PATH = DATA_DIR / "chroma"
COLLECTION_NAME = "positions"

_QUERY_CACHE_MAX = 512

_vectorstore: Chroma | None = None
_embedder: OpenAIEmbeddings | None = None
_query_cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
_cache_hits = 0
_cache_misses = 0


# ---------- Initialization --------------------------------------------------

def initialize_embeddings() -> None:
    """Volá se při startu serveru (FastAPI lifespan). Hydratuje Chromu pokud je prázdná."""
    global _vectorstore, _embedder
    _embedder = OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.openai_api_key)
    vs = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_embedder,
        persist_directory=str(CHROMA_PATH),
        collection_metadata={"hnsw:space": "cosine"},
    )
    count = vs._collection.count()
    if count > 0:
        logger.info(f"ChromaDB načtena z disku – {count} pozic")
    else:
        _load_into_collection(vs)
    _vectorstore = vs


def _load_into_collection(vs: Chroma) -> None:
    if not EMBEDDINGS_PATH.exists():
        raise FileNotFoundError(
            f"Chybí {EMBEDDINGS_PATH}. Spusť: uv run python scripts/build_embeddings.py"
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

    vs._collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    logger.info(f"ChromaDB naplněna z {EMBEDDINGS_PATH.name} – {len(ids)} pozic")


# ---------- Query side ------------------------------------------------------

def find_matching_positions(extracted: ExtractedCV, k: int | None = None) -> list[dict]:
    if _vectorstore is None:
        raise RuntimeError("Vector store není inicializován – zavolej initialize_embeddings() při startu.")
    k = k or settings.embedding_topk

    query = _build_query(extracted)
    logger.info(f"Retrieval: query={query!r}, k={k}")

    embedding = _embed_query_cached(query)
    results = _vectorstore.similarity_search_by_vector_with_relevance_scores(embedding=embedding, k=k)

    matches = [
        {
            "position": doc.metadata["position"],
            "group": doc.metadata["group"],
            "duties_text": doc.page_content,
            "salary_low_monthly_czk": doc.metadata["salary_low_monthly_czk"],
            "salary_high_monthly_czk": doc.metadata["salary_high_monthly_czk"],
            "salary_after_5_years_monthly_czk": doc.metadata["salary_after_5_years_monthly_czk"],
            "salary_source": doc.metadata["salary_source"],
            "similarity": round(1 - distance, 3),
        }
        for doc, distance in results
    ]
    if matches:
        sims = [m["similarity"] for m in matches]
        logger.info(
            f"Retrieval: {len(matches)} matchů, similarity range {min(sims):.2f}-{max(sims):.2f}"
        )
    return matches


def _build_query(extracted: ExtractedCV) -> str:
    """Position-driven query – skills NEpoužíváme, jinak by analytik s 'TypeScript' v CV
    skončil mezi vývojáři. Skills doladí finalizer LLM uvnitř rozsahu."""
    parts = [extracted.current_role]
    if extracted.previous_roles:
        parts.append("Předchozí pozice: " + ", ".join(extracted.previous_roles[:3]))
    if extracted.industries:
        parts.append("Obor: " + ", ".join(extracted.industries[:2]))
    return ". ".join(parts)


def _embed_query_cached(query: str) -> list[float]:
    global _cache_hits, _cache_misses
    if _embedder is None:
        raise RuntimeError("Embedder není inicializován.")

    h = hashlib.md5(query.encode("utf-8")).hexdigest()
    cached = _query_cache.get(h)
    if cached is not None:
        _query_cache.move_to_end(h)
        _cache_hits += 1
        logger.info(f"Embedding cache hit (hits={_cache_hits}, misses={_cache_misses})")
        return list(cached)

    _cache_misses += 1
    logger.info(f"Embedding cache miss → volám {settings.embedding_model}")
    vec = _embedder.embed_query(query)
    _query_cache[h] = tuple(vec)
    if len(_query_cache) > _QUERY_CACHE_MAX:
        _query_cache.popitem(last=False)
    return vec
