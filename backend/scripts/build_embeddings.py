"""Jednorázové vygenerování embeddingů pozic.

    cd backend && uv run python scripts/build_embeddings.py

Pro pozici bez `has_position_data` použije rozpětí celé profesní skupiny
(`category_low/high`) a zaznamená `salary_source: "category"`.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_openai import OpenAIEmbeddings

from cv_evaluator.config import settings

DATA_DIR = Path(__file__).parent.parent / "data"
SOURCE_PATH = DATA_DIR / "salaries.jsonl"
OUTPUT_PATH = DATA_DIR / "positions_embeddings.jsonl"
BATCH_SIZE = 100


def build_text(pos: dict) -> str:
    duties = " ".join(pos.get("duties", []))
    return f"{pos['position']} ({pos['group']}). {duties}".strip()


def build_salary_fields(pos: dict) -> dict | None:
    """Canonical low/high/after_5y + zdroj. None = pozice nemá žádný plat."""
    if pos.get("has_position_data"):
        return {
            "salary_low_monthly_czk": pos["p10_monthly_czk"],
            "salary_high_monthly_czk": pos["p90_monthly_czk"],
            "salary_after_5_years_monthly_czk": pos.get("after_5_years_monthly_czk") or 0,
            "salary_source": "position",
        }
    low, high = pos.get("category_low_monthly_czk"), pos.get("category_high_monthly_czk")
    if low is None or high is None:
        return None
    return {
        "salary_low_monthly_czk": low,
        "salary_high_monthly_czk": high,
        "salary_after_5_years_monthly_czk": pos.get("category_avg_monthly_czk") or 0,
        "salary_source": "category",
    }


def load_positions() -> list[tuple[dict, dict]]:
    pairs: list[tuple[dict, dict]] = []
    skipped = 0
    with open(SOURCE_PATH, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            salary = build_salary_fields(data)
            if salary is None:
                skipped += 1
                continue
            pairs.append((data, salary))
    if skipped:
        print(f"Přeskočeno {skipped} pozic bez platových dat.")
    return pairs


def main() -> None:
    if OUTPUT_PATH.exists():
        print(f"Soubor {OUTPUT_PATH} už existuje. Smaž ho ručně pro regeneraci.")
        return

    pairs = load_positions()
    texts = [build_text(p) for p, _ in pairs]
    print(f"Generuji embeddingy pro {len(pairs)} pozic v dávkách po {BATCH_SIZE}...")

    embedder = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )

    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        vectors.extend(embedder.embed_documents(batch))
        print(f"  {min(start + BATCH_SIZE, len(texts))}/{len(texts)}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for i, ((pos, salary), text, vec) in enumerate(zip(pairs, texts, vectors, strict=True)):
            record = {
                "id": str(i),
                "position": pos["position"],
                "group": pos["group"],
                **salary,
                "text": text,
                "embedding": vec,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    by_source: dict[str, int] = {}
    for _, salary in pairs:
        by_source[salary["salary_source"]] = by_source.get(salary["salary_source"], 0) + 1
    print(f"Hotovo – zapsáno do {OUTPUT_PATH} ({by_source})")


if __name__ == "__main__":
    main()
