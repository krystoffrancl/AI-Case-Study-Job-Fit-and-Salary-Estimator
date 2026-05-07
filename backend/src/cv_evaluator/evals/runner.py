"""End-to-end eval runner.

    uv run python -m cv_evaluator.evals.runner [--no-judge] [--limit N]

Generuje markdown report do `evals/reports/`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import datetime
from pathlib import Path

from cv_evaluator.evals import metrics
from cv_evaluator.models import CVData, Report
from cv_evaluator.services.cost_tracker import cost_tracker
from cv_evaluator.services.embeddings import find_matching_positions, initialize_embeddings
from cv_evaluator.steps.extractor import extract_cv_data
from cv_evaluator.steps.finalizer import finalize_report
from cv_evaluator.steps.growth_target import compute_growth_target
from cv_evaluator.steps.quality_assessor import assess_quality
from cv_evaluator.steps.salary_anchor import compute_anchor
from cv_evaluator.steps.scorer import calculate_score
from cv_evaluator.utils.logger import logger

EVALS_DIR = Path(__file__).parent
DATASET_PATH = EVALS_DIR / "datasets" / "golden_cvs.jsonl"
REPORTS_DIR = EVALS_DIR / "reports"


def load_dataset() -> list[dict]:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def run_pipeline(cv_id: str, raw_text: str) -> Report:
    """Identický pipeline jako routes.process_cv, jen volaný přímo (bez UploadFile)."""
    cv_data = CVData(raw_text=raw_text, filename=f"{cv_id}.txt")
    extracted = await extract_cv_data(cv_data, job_id=cv_id)
    score = calculate_score(extracted)
    matches = find_matching_positions(extracted)
    anchor = compute_anchor(score, matches, trajectory=extracted.career_trajectory)
    growth_target = compute_growth_target(anchor, extracted)
    final = await finalize_report(
        extracted=extracted,
        score=score,
        matches=matches,
        anchor=anchor,
        growth_target=growth_target,
        job_id=cv_id,
    )
    return Report(
        extracted=extracted,
        seniority=score,
        salary=final.salary,
        salary_anchor=anchor,
        explanation=final.explanation,
        growth_plan=final.growth_plan,
        matches=matches,
        data_quality=assess_quality(extracted, matches),
        cost=cost_tracker.summary(cv_id),
    )


def evaluate_record(report: Report, gt: dict) -> dict:
    extracted = report.extracted
    seniority_lo, seniority_hi = gt["expected_seniority_range"]
    salary_lo, salary_hi = gt["expected_salary_range"]
    salary_mid = (report.salary.min_czk + report.salary.max_czk) / 2
    skill_names = [s.name for s in extracted.skills]

    return {
        "skills_jaccard": metrics.jaccard_similarity(skill_names, gt["skills"]),
        "yoe_mae": metrics.mae(extracted.years_of_experience, gt["years_of_experience"]),
        "education_match": extracted.education_level.value == gt["education_level"],
        "trajectory_match": extracted.career_trajectory.direction == gt.get("expected_trajectory"),
        "seniority_in_range": metrics.in_range(report.seniority.total, seniority_lo, seniority_hi),
        "seniority_distance": metrics.distance_to_range(report.seniority.total, seniority_lo, seniority_hi),
        "salary_in_range": metrics.in_range(salary_mid, salary_lo, salary_hi),
        "salary_distance": metrics.distance_to_range(salary_mid, salary_lo, salary_hi),
        "has_growth_plan": report.growth_plan is not None,
        "growth_plan_steps": len(report.growth_plan.steps) if report.growth_plan else 0,
        "data_quality_score": report.data_quality.score if report.data_quality else 0.0,
    }


async def maybe_judge(report: Report, raw_text: str) -> dict | None:
    """LLM-as-judge je volitelný. Pokud selže, vrátíme None (eval pokračuje)."""
    try:
        from cv_evaluator.evals.llm_judge import judge

        ai_output = json.dumps(
            {
                "explanation": report.explanation.model_dump(),
                "growth_plan": report.growth_plan.model_dump() if report.growth_plan else None,
            },
            ensure_ascii=False,
            indent=2,
        )
        verdict = await judge(raw_text, ai_output)
        return {
            "judge_specificity": verdict.scores.specificity,
            "judge_actionability": verdict.scores.actionability,
            "judge_grounding": verdict.scores.factual_grounding,
            "judge_consistency": verdict.scores.consistency,
            "judge_overall": verdict.overall,
        }
    except Exception as e:
        logger.warning(f"LLM judge failed: {e}")
        return None


def format_report(records: list[dict], aggregates: dict) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# Eval report — {ts}",
        "",
        f"**Dataset**: {DATASET_PATH.name}, **N**: {len(records)}",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        *(f"| `{k}` | {aggregates[k]} |" for k in sorted(aggregates)),
        "",
        "## Per-CV results",
        "",
        "| ID | Seniority (pred/range) | Salary mid (pred/range) | Skills J | YoE MAE | Edu | Traj | Growth | Quality | Cost (Kč) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in records:
        m = r["metrics"]
        lines.append(
            f"| {r['id']} "
            f"| {r['predicted_seniority']:.0f} / {r['expected_seniority']} "
            f"| {r['predicted_salary_mid']:,} / {r['expected_salary']} "
            f"| {m['skills_jaccard']:.2f} "
            f"| {m['yoe_mae']:.1f} "
            f"| {'✓' if m['education_match'] else '✗'} "
            f"| {'✓' if m['trajectory_match'] else '✗'} "
            f"| {'✓' if m['has_growth_plan'] else '✗'} "
            f"| {m['data_quality_score']:.2f} "
            f"| {r['cost_czk']:.3f} |"
        )

    total = sum(r["cost_czk"] for r in records)
    avg = statistics.mean(r["cost_czk"] for r in records) if records else 0
    lines.extend([
        "",
        "## Total cost",
        "",
        f"- **Total**: {total:.3f} Kč napříč {len(records)} CVs",
        f"- **Průměr per CV**: {avg:.3f} Kč",
    ])
    return "\n".join(lines)


async def run(limit: int | None = None, judge_enabled: bool = True) -> Path:
    initialize_embeddings()
    dataset = load_dataset()
    if limit:
        dataset = dataset[:limit]

    records: list[dict] = []
    metric_dicts: list[dict] = []

    for entry in dataset:
        cv_id = entry["id"]
        gt = entry["ground_truth"]
        logger.info(f"=== Eval [{cv_id}] ===")
        try:
            report = await run_pipeline(cv_id, entry["raw_text"])
        except Exception as e:
            logger.exception(f"Pipeline crash u {cv_id}: {e}")
            continue

        m = evaluate_record(report, gt)
        if judge_enabled:
            judge_metrics = await maybe_judge(report, entry["raw_text"])
            if judge_metrics:
                m.update(judge_metrics)

        metric_dicts.append(m)
        records.append({
            "id": cv_id,
            "metrics": m,
            "predicted_seniority": report.seniority.total,
            "expected_seniority": f"{gt['expected_seniority_range'][0]}-{gt['expected_seniority_range'][1]}",
            "predicted_salary_mid": int((report.salary.min_czk + report.salary.max_czk) / 2),
            "expected_salary": f"{gt['expected_salary_range'][0]:,}-{gt['expected_salary_range'][1]:,}",
            "cost_czk": report.cost.total_czk if report.cost else 0,
        })

    md = format_report(records, metrics.aggregate(metric_dicts))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"{datetime.now():%Y_%m_%d_%H%M}_eval.md"
    out_path.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n>>> Report uložen do {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-judge", action="store_true", help="Vypne LLM-as-judge.")
    parser.add_argument("--limit", type=int, help="Vyhodnoť jen prvních N CVs.")
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit, judge_enabled=not args.no_judge))


if __name__ == "__main__":
    main()
