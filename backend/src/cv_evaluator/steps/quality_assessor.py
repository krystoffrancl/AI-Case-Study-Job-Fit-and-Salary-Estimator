"""Sanity check výstupů – signál uživateli, jak moc odhadu důvěřovat."""
from __future__ import annotations

from cv_evaluator.models import DataQuality, ExtractedCV
from cv_evaluator.utils.logger import logger


def assess_quality(extracted: ExtractedCV, matches: list[dict]) -> DataQuality:
    signals: list[bool] = []
    warnings: list[str] = []

    def check(ok: bool, warning: str) -> None:
        signals.append(ok)
        if not ok:
            warnings.append(warning)

    check(extracted.years_of_experience >= 1, "Krátká nebo žádná pracovní zkušenost.")
    check(
        len(extracted.skills) >= 5,
        f"Identifikováno jen {len(extracted.skills)} dovedností v CV.",
    )

    top_sim = matches[0]["similarity"] if matches else 0.0
    check(
        top_sim >= 0.55,
        f"Nízká shoda nejbližší pozice v databázi ({top_sim:.2f}). Odhad může být méně přesný.",
    )

    has_position_source = bool(matches) and any(m["salary_source"] == "position" for m in matches)
    check(
        has_position_source,
        "Plat odvozen jen z obecných kategorií (chybějící percentily konkrétní pozice).",
    )

    if extracted.skills:
        unknown_ratio = sum(1 for s in extracted.skills if s.tier == "unknown") / len(extracted.skills)
        check(
            unknown_ratio <= 0.3,
            f"{int(unknown_ratio * 100)} % dovedností má neurčený tier – "
            f"profil je pro automatické posouzení neobvyklý.",
        )

    score = sum(signals) / len(signals) if signals else 0.0
    confidence = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    logger.info(
        f"Quality assessor: {sum(signals)}/{len(signals)} signálů OK → "
        f"{confidence} ({score:.2f}), {len(warnings)} varování"
    )
    return DataQuality(confidence=confidence, score=round(score, 2), warnings=warnings)
