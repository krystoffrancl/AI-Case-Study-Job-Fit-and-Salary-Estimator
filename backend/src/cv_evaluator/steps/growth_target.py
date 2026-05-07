"""Najde cílovou roli pro +30 % mzdu pomocí sémantické similarity, ne token matchování.

Algoritmus:
1. Vector search nad celou DB najde top-K pozic blízkých uživatelově profilu (current_role
   + previous_roles + industries).
2. Filtr: pozice musí dosahovat target salary v `high` nebo `after_5_years`.
3. Pick: nejvíc similar (= nejrealističtější přechod).

Proč ne token affinity: "IT analytik v bance" by trefil "Dealer/Trader" přes slovo "bank"
v duties – sémanticky úplně jiný obor. Embedding to rozliší.
"""
from __future__ import annotations

from dataclasses import dataclass

from cv_evaluator.config import settings
from cv_evaluator.models import ExtractedCV, SalaryAnchor
from cv_evaluator.services.embeddings import find_matching_positions
from cv_evaluator.utils.logger import logger


@dataclass
class GrowthTargetContext:
    target_salary_czk: int
    target_role: str
    target_group: str
    target_high_czk: int
    target_after5_czk: int
    similarity: float  # cosine similarity k uživatelovu profilu (0..1)
    target_duties: str  # raw text povinností – LLM z toho odvodí skill gaps
    user_skills_already_relevant: list[str]


def compute_growth_target(
    anchor: SalaryAnchor,
    extracted: ExtractedCV,
    multiplier: float | None = None,
) -> GrowthTargetContext | None:
    multiplier = multiplier or settings.growth_multiplier
    target = int(round(anchor.center_czk * multiplier))
    logger.info(
        f"Growth target: hledám sémanticky blízkou roli s platem >= {target:,} CZK "
        f"(anchor.center * {multiplier})"
    )

    candidates = find_matching_positions(extracted, k=settings.growth_search_k)
    if not candidates:
        logger.warning("Growth target: žádní vector search kandidáti")
        return None

    reachable = [
        c for c in candidates
        if max(c["salary_high_monthly_czk"], c.get("salary_after_5_years_monthly_czk") or 0) >= target
    ]
    logger.info(
        f"Growth target: {len(reachable)}/{len(candidates)} sémanticky blízkých rolí "
        f"dosahuje cílové mzdy"
    )
    if not reachable:
        return None

    # candidates jsou už seřazené podle similarity descending → reachable[0] je nejvíc similar
    best = reachable[0]
    logger.info(
        f"Growth target: vybráno {best['position']!r} (similarity={best['similarity']}, "
        f"high={best['salary_high_monthly_czk']:,}, after5={best.get('salary_after_5_years_monthly_czk') or 0:,})"
    )

    return GrowthTargetContext(
        target_salary_czk=target,
        target_role=best["position"],
        target_group=best["group"],
        target_high_czk=best["salary_high_monthly_czk"],
        target_after5_czk=best.get("salary_after_5_years_monthly_czk") or 0,
        similarity=best["similarity"],
        target_duties=best.get("duties_text", ""),
        user_skills_already_relevant=_overlap_skills(extracted, best.get("duties_text", "")),
    )


def _overlap_skills(extracted: ExtractedCV, target_duties: str) -> list[str]:
    """Skills uživatele, které se už vyskytují v target duties – pro UI a LLM jako pozitivní signál."""
    if not target_duties:
        return []
    haystack = target_duties.lower()
    return [s.name for s in extracted.skills if s.name.lower() in haystack]
