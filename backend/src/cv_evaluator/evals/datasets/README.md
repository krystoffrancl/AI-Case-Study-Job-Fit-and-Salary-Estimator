# Golden eval dataset

17 ručně anotovaných CV pokrývajících:

| ID | Profil | Praxe | Education | Cílový rozsah seniority |
|---|---|---|---|---|
| cv_001 | Senior Backend Engineer (fintech) | 9 | master | 70-95 |
| cv_002 | Junior Python Developer | 1.5 | bachelor | 20-40 |
| cv_003 | Senior Data Analyst | 8 | master | 60-85 |
| cv_004 | Administrativní pracovnice | 4 | high_school | 10-35 |
| cv_005 | Marketing Manager | 10 | master | 60-85 |
| cv_006 | DevOps Engineer | 7 | bachelor | 60-85 |
| cv_007 | Obchodní zástupce | 9 | high_school | 30-55 |
| cv_008 | ML Engineer (PhD) | 5 | phd | 60-85 |
| cv_009 | Frontend Developer | 5 | bachelor | 40-65 |
| cv_010 | HR Specialist | 6 | master | 35-60 |
| cv_011 | Principal Software Architect | 19 | master | 85-100 |
| cv_012 | Career changer (učitelka -> data) | 1 | master | 20-45 |
| cv_013 | Vrchní sestra JIP | 14 | bachelor | 60-85 |
| cv_014 | Stavbyvedoucí | 13 | master | 65-85 |
| cv_015 | Senior Účetní / Controller | 15 | master | 65-85 |
| cv_016 | Šéfkuchař (fine-dining) | 14 | high_school | 55-80 |
| cv_017 | Řidič kamionu mezinárodní | 11 | high_school | 25-50 |

## Schéma

```jsonl
{
  "id": "cv_001",
  "raw_text": "...",
  "ground_truth": {
    "skills": ["...", ...],
    "years_of_experience": 9.0,
    "education_level": "master",
    "current_role": "Senior Backend Engineer",
    "expected_seniority_range": [70, 95],
    "expected_salary_range": [85000, 140000],
    "expected_trajectory": "ascending",
    "should_have_growth_plan": true
  }
}
```

## Jak byly vytvořeny

CVs jsou syntetické – sestavené tak, aby pokrývaly:
- **Distribuci seniority**: junior, mid, senior, principal
- **Diverzifikované obory**: backend, frontend, devops, data, ML, marketing, HR, sales, admin
- **Edge cases**: career changer (lateral trajectory), high-school role, PhD ML engineer
- **Education distribution**: high_school, bachelor, master, phd

Ground truth ranges jsou definované expert intuicí (autor case study) –
nebyly odvozeny z platy.cz percentilů, aby evals nebyly self-fulfilling.

## Použití

```bash
make eval        # spustí celý eval, vyrobí markdown report
```
