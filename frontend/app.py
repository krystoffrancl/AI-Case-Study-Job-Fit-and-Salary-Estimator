"""Streamlit UI pro AI Job Fit & Salary Estimator."""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = os.environ.get("API_URL", "http://backend:8000")
POLL_INTERVAL_S = 0.5
UPLOAD_TIMEOUT_S = 60.0
POLL_TIMEOUT_S = 10.0
MAX_POLL_ITERATIONS = 600  # 5 min při 0.5 s polling

PIPELINE: list[tuple[str, str]] = [
    ("received", "Příjem souboru"),
    ("parsing", "Parsování dokumentu"),
    ("extracting", "Extrakce profilu (LLM)"),
    ("scoring", "Hodnocení seniority"),
    ("estimating", "Hledání podobných pozic"),
    ("explaining", "Odhad mzdy a vysvětlení (LLM)"),
    ("done", "Hotovo"),
]
STAGE_INDEX = {stage: i for i, (stage, _) in enumerate(PIPELINE)}

EDUCATION_LABEL = {
    "high_school": "Středoškolské",
    "bachelor": "Bakalářské",
    "master": "Magisterské",
    "phd": "Doktorské",
}

SOURCE_LABEL = {
    "position": "konkrétní pozice",
    "category": "celá skupina",
}

TRAJECTORY_LABEL = {
    "ascending": ("📈", "Rostoucí trajektorie"),
    "stable": ("➡️", "Stabilní trajektorie"),
    "lateral": ("↔️", "Laterální pohyb"),
    "descending": ("📉", "Klesající trajektorie"),
    "unknown": ("❔", "Neurčená trajektorie"),
}

CONFIDENCE_LABEL = {
    "high": ("🟢", "Vysoká důvěra"),
    "medium": ("🟡", "Střední důvěra"),
    "low": ("🔴", "Nízká důvěra"),
}

LOG_LEVEL_COLOR = {
    "DEBUG": "#94a3b8",
    "INFO": "#38bdf8",
    "WARNING": "#f59e0b",
    "ERROR": "#ef4444",
    "CRITICAL": "#ef4444",
}

TIER_BADGE = {
    "expert": ("#fde047", "#854d0e"),  # zlatá
    "core": ("#bfdbfe", "#1e3a8a"),     # modrá
    "basic": ("#e2e8f0", "#475569"),    # šedá
    "unknown": ("#fce7f3", "#831843"),  # růžová – neznámé
}

ACCENT = "#3b82f6"
ACCENT_DARK = "#1e3a8a"
NEUTRAL = "#94a3b8"


# ----- API ----------------------------------------------------------------

def upload_cv(file_bytes: bytes, filename: str, content_type: str) -> str:
    files = {"file": (filename, file_bytes, content_type)}
    r = httpx.post(f"{API_URL}/api/v1/evaluate", files=files, timeout=UPLOAD_TIMEOUT_S)
    r.raise_for_status()
    return r.json()["job_id"]


def get_status(job_id: str) -> dict[str, Any]:
    r = httpx.get(f"{API_URL}/api/v1/status/{job_id}", timeout=POLL_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def get_logs(job_id: str, since: int = 0) -> dict[str, Any]:
    """Vrátí log entries od indexu `since` (incremental polling)."""
    r = httpx.get(
        f"{API_URL}/api/v1/logs/{job_id}",
        params={"since": since},
        timeout=POLL_TIMEOUT_S,
    )
    r.raise_for_status()
    return r.json()


# ----- formatters ---------------------------------------------------------

def fmt_czk(value: int | float) -> str:
    return f"{int(value):,} Kč".replace(",", " ")


def fmt_czk_short(value: int | float) -> str:
    return f"{int(value):,}".replace(",", " ")


# ----- progress ----------------------------------------------------------

def render_pipeline_progress(container, current_status: str) -> None:
    cur_idx = STAGE_INDEX.get(current_status, -1)
    lines: list[str] = []
    for i, (_, label) in enumerate(PIPELINE):
        if cur_idx == STAGE_INDEX["done"] and i == cur_idx:
            lines.append(f"✅ **{label}**")
        elif i < cur_idx:
            lines.append(f"✅ {label}")
        elif i == cur_idx:
            lines.append(f"⏳ **{label}**")
        else:
            lines.append(f"◻️ {label}")
    container.markdown("\n\n".join(lines))


# ----- charts -------------------------------------------------------------

def chart_salary_range(est_low: int, est_high: int, matches: list[dict]) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=["<b>Tvůj odhad</b>"],
        x=[est_high - est_low],
        base=[est_low],
        orientation="h",
        marker=dict(color=ACCENT, line=dict(color=ACCENT_DARK, width=1)),
        text=f"{fmt_czk_short(est_low)} – {fmt_czk_short(est_high)} Kč",
        textposition="inside",
        textfont=dict(color="white", size=13),
        hoverinfo="skip",
        showlegend=False,
    ))

    for m in reversed(matches):
        low = m["salary_low_monthly_czk"]
        high = m["salary_high_monthly_czk"]
        is_position = m["salary_source"] == "position"
        bar_color = "rgba(59, 130, 246, 0.35)" if is_position else "rgba(148, 163, 184, 0.45)"
        line_color = ACCENT if is_position else NEUTRAL
        label = f"{m['position']} <span style='color:{NEUTRAL}'>· {m['similarity']:.2f}</span>"

        fig.add_trace(go.Bar(
            y=[label],
            x=[high - low],
            base=[low],
            orientation="h",
            marker=dict(color=bar_color, line=dict(color=line_color, width=1)),
            text=f"{fmt_czk_short(low)} – {fmt_czk_short(high)}",
            textposition="inside",
            textfont=dict(size=12),
            hovertemplate=(
                f"<b>{m['position']}</b> ({m['group']})<br>"
                f"Rozpětí: {fmt_czk(low)} – {fmt_czk(high)}<br>"
                f"Zdroj: {SOURCE_LABEL.get(m['salary_source'], m['salary_source'])}<br>"
                f"Shoda: {m['similarity']:.2f}<extra></extra>"
            ),
            showlegend=False,
        ))

    fig.update_layout(
        height=80 + 45 * (1 + len(matches)),
        margin=dict(t=20, b=30, l=10, r=10),
        xaxis=dict(
            title="Měsíční mzda (Kč)",
            separatethousands=True,
            tickformat=",",
            gridcolor="rgba(148, 163, 184, 0.2)",
            zerolinecolor="rgba(148, 163, 184, 0.4)",
        ),
        yaxis=dict(autorange="reversed"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        bargap=0.35,
    )
    return fig


def chart_seniority_gauge(total: float) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=total,
        number={"suffix": " / 100", "font": {"size": 32}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": NEUTRAL},
            "bar": {"color": ACCENT, "thickness": 0.7},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 30], "color": "rgba(239, 68, 68, 0.18)"},
                {"range": [30, 70], "color": "rgba(245, 158, 11, 0.18)"},
                {"range": [70, 100], "color": "rgba(34, 197, 94, 0.20)"},
            ],
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(
        height=240,
        margin=dict(t=30, b=10, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_seniority_breakdown(seniority: dict) -> go.Figure:
    cats = [
        ("Praxe", seniority["experience_score"], 35),
        ("Skills", seniority["skills_score"], 25),
        ("Vzdělání", seniority["education_score"], 10),
        ("Role", seniority["role_seniority_score"], 15),
        ("Osobnost", seniority["personality_score"], 15),
    ]
    labels = [c[0] for c in cats]
    actual = [c[1] for c in cats]
    maxes = [c[2] for c in cats]
    pcts = [a / m * 100 if m else 0 for a, m in zip(actual, maxes)]
    text_labels = [f"{a:.0f} / {m}" for a, m in zip(actual, maxes)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[100] * len(labels),
        y=labels,
        orientation="h",
        marker_color="rgba(148, 163, 184, 0.15)",
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Bar(
        x=pcts,
        y=labels,
        orientation="h",
        marker=dict(color=ACCENT, line=dict(color=ACCENT_DARK, width=0.5)),
        text=text_labels,
        textposition="outside",
        textfont=dict(size=12),
        showlegend=False,
        hovertemplate="%{y}: %{text}<extra></extra>",
    ))
    fig.update_layout(
        barmode="overlay",
        height=280,
        margin=dict(t=20, b=10, l=10, r=40),
        xaxis=dict(range=[0, 115], visible=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=13)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        bargap=0.4,
    )
    return fig


# ----- result rendering ---------------------------------------------------

def render_quality_badge(quality: dict | None) -> None:
    if not quality:
        return
    icon, label = CONFIDENCE_LABEL.get(quality["confidence"], ("❔", "Neurčeno"))
    pct = int(quality["score"] * 100)
    warnings = quality.get("warnings") or []
    tooltip = " | ".join(warnings) if warnings else "Žádná upozornění"

    st.markdown(
        f"""
        <div style="
            display: inline-flex; align-items: center; gap: 8px;
            padding: 6px 14px; border-radius: 999px;
            background: rgba(148, 163, 184, 0.15);
            font-size: 13px; margin: 0 0 12px 0;
            color: #475569;
        " title="{tooltip}">
            {icon} <strong>{label}</strong> <span style="opacity:0.7">· {pct}% kvality dat</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if warnings:
        with st.expander("⚠️ Upozornění ke kvalitě dat", expanded=False):
            for w in warnings:
                st.markdown(f"- {w}")


def render_salary(salary: dict, anchor: dict | None, matches: list[dict]) -> None:
    low, high = salary["min_czk"], salary["max_czk"]
    mid = (low + high) // 2

    anchor_note = ""
    if anchor:
        anchor_note = (
            f"Reprodukovatelný odhad · kotva {fmt_czk(anchor['center_czk'])} "
            f"· {anchor.get('method', '')}"
        )

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {ACCENT_DARK} 0%, {ACCENT} 100%);
            border-radius: 16px;
            padding: 36px 32px;
            color: white;
            text-align: center;
            margin: 8px 0 24px 0;
            box-shadow: 0 6px 20px rgba(59, 130, 246, 0.25);
        ">
            <div style="font-size: 12px; text-transform: uppercase; letter-spacing: 2px; opacity: 0.85; margin-bottom: 14px; font-weight: 600;">
                Odhadované měsíční mzdové rozpětí
            </div>
            <div style="font-size: 46px; font-weight: 700; letter-spacing: -1px; line-height: 1.1;">
                {fmt_czk(low)} &nbsp;–&nbsp; {fmt_czk(high)}
            </div>
            <div style="font-size: 13px; opacity: 0.75; margin-top: 12px; letter-spacing: 0.5px;">
                Střed odhadu: {fmt_czk(mid)} &nbsp;·&nbsp; rozpětí {fmt_czk_short(high - low)} Kč
            </div>
            <div style="font-size: 11px; opacity: 0.6; margin-top: 8px; letter-spacing: 0.3px;">
                {anchor_note}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if matches:
        st.markdown("##### Tvůj odhad vs. nejpodobnější pozice z databáze")
        st.plotly_chart(
            chart_salary_range(low, high, matches),
            use_container_width=True,
            config={"displayModeBar": False},
        )


def render_seniority(seniority: dict) -> None:
    col_gauge, col_break = st.columns([1, 1.6], gap="large")
    with col_gauge:
        st.markdown("##### Celkové skóre")
        st.plotly_chart(
            chart_seniority_gauge(seniority["total"]),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    with col_break:
        st.markdown("##### Rozpis hodnocení (5 dimenzí)")
        st.plotly_chart(
            chart_seniority_breakdown(seniority),
            use_container_width=True,
            config={"displayModeBar": False},
        )


def normalized_skills_html(skills: list[dict]) -> str:
    if not skills:
        return "<em style='color:#94a3b8'>(žádné dovednosti nezjištěny)</em>"
    chips = []
    for s in skills:
        bg, fg = TIER_BADGE.get(s.get("tier", "unknown"), TIER_BADGE["unknown"])
        tier_label = s.get("tier", "unknown")
        chips.append(
            f"<span title='Tier: {tier_label}' style='"
            f"background: {bg};"
            f"color: {fg};"
            f"padding: 4px 12px;"
            f"border-radius: 14px;"
            f"margin: 3px 4px 3px 0;"
            f"display: inline-block;"
            f"font-size: 0.85em;"
            f"font-weight: 500;"
            f"border: 1px solid rgba(0,0,0,0.05);"
            f"'>{s['name']}</span>"
        )
    return "".join(chips)


def skills_pills_html(skills: list[str]) -> str:
    if not skills:
        return "<em style='color:#94a3b8'>(žádné dovednosti nezjištěny)</em>"
    return "".join(
        f"<span style='"
        f"background: rgba(59, 130, 246, 0.12);"
        f"color: {ACCENT_DARK};"
        f"padding: 4px 12px;"
        f"border-radius: 14px;"
        f"margin: 3px 4px 3px 0;"
        f"display: inline-block;"
        f"font-size: 0.85em;"
        f"font-weight: 500;"
        f"border: 1px solid rgba(59, 130, 246, 0.25);"
        f"'>{s}</span>"
        for s in skills
    )


def render_profile(extracted: dict) -> None:
    skills = extracted.get("skills", [])
    with st.container(border=True):
        col_left, col_right = st.columns([3, 2], gap="large")

        with col_left:
            st.markdown(
                f"<div style='font-size:11px;text-transform:uppercase;"
                f"letter-spacing:1.5px;color:{NEUTRAL};font-weight:600;"
                f"margin-bottom:4px'>Aktuální pozice</div>"
                f"<div style='font-size:20px;font-weight:600;margin-bottom:16px'>"
                f"{extracted['current_role']}</div>",
                unsafe_allow_html=True,
            )

            prev = extracted.get("previous_roles") or []
            if prev:
                st.markdown(
                    f"<div style='font-size:11px;text-transform:uppercase;"
                    f"letter-spacing:1.5px;color:{NEUTRAL};font-weight:600;"
                    f"margin-bottom:4px'>Předchozí role</div>"
                    f"<div style='margin-bottom:16px'>{', '.join(prev)}</div>",
                    unsafe_allow_html=True,
                )

            edu = EDUCATION_LABEL.get(extracted["education_level"], extracted["education_level"])
            mcol1, mcol2 = st.columns(2)
            mcol1.metric("Praxe", f"{extracted['years_of_experience']} let")
            mcol2.metric("Vzdělání", edu)

            if extracted.get("industries"):
                st.markdown(f"**Obory:** {', '.join(extracted['industries'])}")
            if extracted.get("languages"):
                st.markdown(f"**Jazyky:** {', '.join(extracted['languages'])}")

            traj = extracted.get("career_trajectory") or {}
            traj_dir = traj.get("direction", "unknown")
            icon, label = TRAJECTORY_LABEL.get(traj_dir, ("❔", "Neurčeno"))
            extras: list[str] = []
            if traj.get("years_to_senior"):
                extras.append(f"do senior za {traj['years_to_senior']} let")
            if traj.get("role_diversity") is not None:
                extras.append(f"diverzita rolí: {traj['role_diversity']}")
            extras_str = (" · " + " · ".join(extras)) if extras else ""
            st.markdown(
                f"<div style='margin-top:10px;font-size:13px;color:#475569'>"
                f"{icon} <strong>{label}</strong>{extras_str}</div>",
                unsafe_allow_html=True,
            )

        with col_right:
            st.markdown(
                f"<div style='font-size:11px;text-transform:uppercase;"
                f"letter-spacing:1.5px;color:{NEUTRAL};font-weight:600;"
                f"margin-bottom:8px'>Skills ({len(skills)})</div>",
                unsafe_allow_html=True,
            )
            st.markdown(normalized_skills_html(skills), unsafe_allow_html=True)
            st.markdown(
                "<div style='font-size:11px; color:#94a3b8; margin-top:8px'>"
                "🟡 expert · 🔵 core · ⚪ basic · 🟣 unknown</div>",
                unsafe_allow_html=True,
            )


def render_personality(traits: dict | None) -> None:
    if not traits:
        return
    sections = [
        ("👑", "Lídršip", traits.get("leadership_signals") or []),
        ("🚀", "Iniciativa", traits.get("initiative_signals") or []),
        ("🤝", "Spolupráce", traits.get("collaboration_signals") or []),
        ("🌱", "Růst / učení", traits.get("growth_signals") or []),
    ]
    if not any(s[2] for s in sections):
        return

    cols = st.columns(2, gap="medium")
    for i, (emoji, title, items) in enumerate(sections):
        col = cols[i % 2]
        with col:
            with st.container(border=True):
                st.markdown(f"##### {emoji} {title}")
                if items:
                    for it in items:
                        st.markdown(f"- {it}")
                else:
                    st.markdown(
                        f"<span style='color:{NEUTRAL};font-size:13px'>"
                        f"<em>(žádné konkrétní signály v CV)</em></span>",
                        unsafe_allow_html=True,
                    )


def render_growth_plan(plan: dict | None) -> None:
    if not plan:
        st.info(
            "Růstový plán k +30 % mzdě se nevygeneroval. Možné důvody: "
            "uchazeč je v top mzdovém pásmu nebo nebyla nalezena vhodná cílová role."
        )
        return

    target = plan["target_salary_czk"]
    role = plan["target_role"]
    timeline = plan.get("timeline_months", 0)
    rationale = plan.get("rationale", "")

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #166534 0%, #22c55e 100%);
            border-radius: 14px;
            padding: 24px 28px;
            color: white;
            margin: 8px 0 18px 0;
            box-shadow: 0 4px 14px rgba(34, 197, 94, 0.20);
        ">
            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.85; font-weight: 600;">
                Cílová role · timeline {timeline} měsíců
            </div>
            <div style="font-size: 24px; font-weight: 700; margin: 6px 0 4px 0;">
                {role}
            </div>
            <div style="font-size: 28px; font-weight: 700;">
                cíl: {fmt_czk(target)}
            </div>
            <div style="font-size: 13px; opacity: 0.85; margin-top: 8px; line-height: 1.45;">
                {rationale}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    gaps = plan.get("skill_gaps") or []
    if gaps:
        st.markdown("##### 🎯 Skill gaps")
        st.markdown(skills_pills_html(gaps), unsafe_allow_html=True)

    steps = plan.get("steps") or []
    if steps:
        st.markdown("##### 📋 Konkrétní kroky")
        for i, s in enumerate(steps, 1):
            with st.container(border=True):
                st.markdown(
                    f"**{i}. {s['action']}**  \n"
                    f"<span style='color:{NEUTRAL};font-size:13px'>"
                    f"⏱ {s['timeline_months']} měsíců · ✓ {s['expected_outcome']}</span>",
                    unsafe_allow_html=True,
                )


def render_matches_table(matches: list[dict]) -> None:
    if not matches:
        return
    rows = []
    for m in matches:
        after_5y = m.get("salary_after_5_years_monthly_czk") or 0
        rows.append({
            "Pozice": m["position"],
            "Skupina": m["group"],
            "Spodní hranice": fmt_czk(m["salary_low_monthly_czk"]),
            "Horní hranice": fmt_czk(m["salary_high_monthly_czk"]),
            "Po 5 letech": fmt_czk(after_5y) if after_5y else "—",
            "Zdroj dat": SOURCE_LABEL.get(m["salary_source"], m["salary_source"]),
            "Shoda": f"{m['similarity']:.2f}",
        })
    st.dataframe(rows, hide_index=True, use_container_width=True)


def render_explanation(explanation: dict) -> None:
    summary = explanation.get("summary", "")
    if summary:
        st.markdown(
            f"""
            <div style="
                background: rgba(59, 130, 246, 0.08);
                border-left: 4px solid {ACCENT};
                padding: 16px 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                font-size: 15px;
                line-height: 1.55;
            ">{summary}</div>
            """,
            unsafe_allow_html=True,
        )

    col_s, col_w = st.columns(2, gap="large")
    with col_s:
        with st.container(border=True):
            st.markdown("##### ✓ Silné stránky")
            for s in explanation.get("strengths", []):
                st.markdown(f"- {s}")
    with col_w:
        with st.container(border=True):
            st.markdown("##### △ Slabiny")
            for w in explanation.get("weaknesses", []):
                st.markdown(f"- {w}")

    recs = explanation.get("recommendations", [])
    if recs:
        with st.container(border=True):
            st.markdown("##### → Doporučení pro další růst")
            for r in recs:
                st.markdown(f"- {r}")


def _format_log_entry_html(entry: dict) -> str:
    color = LOG_LEVEL_COLOR.get(entry.get("level", "INFO"), "#cbd5e1")
    ts = entry.get("ts", "")[11:23]  # vezme HH:MM:SS.mmm z ISO timestampu
    level = entry.get("level", "INFO").ljust(7)
    message = (entry.get("message", "") or "").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f"<div>"
        f"<span style='color:#64748b'>{ts}</span> "
        f"<span style='color:{color};font-weight:600'>{level}</span> "
        f"<span style='color:#e2e8f0'>{message}</span>"
        f"</div>"
    )


def render_log_console(container, entries: list[dict], height_px: int = 320) -> None:
    """Render log entries jako tmavá konzole. `container` = st.empty() nebo st přímo."""
    if not entries:
        body = "<div style='color:#64748b;font-style:italic'>(žádné logy zatím)</div>"
    else:
        body = "".join(_format_log_entry_html(e) for e in entries)
    container.markdown(
        f"""
        <div style="
            background: #0f172a;
            color: #e2e8f0;
            border-radius: 8px;
            padding: 12px 14px;
            font-family: ui-monospace, 'JetBrains Mono', 'Fira Code', Consolas, monospace;
            font-size: 12.5px;
            line-height: 1.55;
            max-height: {height_px}px;
            overflow-y: auto;
            border: 1px solid #1e293b;
        ">{body}</div>
        """,
        unsafe_allow_html=True,
    )


def render_cost_footer(cost: dict | None) -> None:
    if not cost:
        return
    czk = cost.get("total_czk", 0)
    calls = cost.get("calls", 0)
    by_model = cost.get("by_model") or {}
    breakdown = ", ".join(f"{m}: ${v:.4f}" for m, v in by_model.items())
    st.markdown(
        f"<div style='text-align:center;color:{NEUTRAL};font-size:12px;"
        f"margin-top:24px;padding-top:16px;border-top:1px solid rgba(148, 163, 184, 0.15)'>"
        f"💸 Náklady na tento odhad: <strong>{czk:.3f} Kč</strong> "
        f"({calls} LLM volání) · {breakdown}</div>",
        unsafe_allow_html=True,
    )


def section_header(emoji: str, title: str, caption: str | None = None) -> None:
    st.markdown(
        f"<h3 style='margin: 32px 0 4px 0; font-weight: 600;'>"
        f"{emoji}&nbsp;&nbsp;{title}</h3>",
        unsafe_allow_html=True,
    )
    if caption:
        st.markdown(
            f"<div style='color:{NEUTRAL};font-size:13px;margin-bottom:14px'>"
            f"{caption}</div>",
            unsafe_allow_html=True,
        )


def render_report(report: dict) -> None:
    render_quality_badge(report.get("data_quality"))

    section_header("💰", "Odhad měsíční mzdy")
    render_salary(
        report["salary"],
        report.get("salary_anchor"),
        report.get("matches", []),
    )

    section_header(
        "🚀",
        "Cesta k +30 % mzdě",
        "Konkrétní cílová role a kroky odvozené z databáze pozic.",
    )
    render_growth_plan(report.get("growth_plan"))

    section_header(
        "📊",
        "Seniority",
        "Rule-based skóre kombinující praxi, dovednosti, vzdělání, roli a osobnostní rysy.",
    )
    render_seniority(report["seniority"])

    section_header(
        "🧑",
        "Profil uchazeče",
        "Extrahováno z CV strukturovaným LLM voláním (canonical názvy + tier klasifikace).",
    )
    render_profile(report["extracted"])

    section_header(
        "✨",
        "Osobnostní rysy",
        "Konkrétní signály identifikované v CV, ne obecná hodnocení.",
    )
    render_personality((report.get("extracted") or {}).get("personality_traits"))

    if report.get("matches"):
        section_header(
            "🎯",
            "Detail nejpodobnějších pozic",
            "Vector retrieval z 722 pozic v ChromaDB (cosine similarity).",
        )
        render_matches_table(report["matches"])

    section_header("📝", "Vysvětlení")
    render_explanation(report["explanation"])

    render_cost_footer(report.get("cost"))


# ----- main ---------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Job Fit & Salary Estimator",
        page_icon="🧠",
        layout="wide",
    )

    st.markdown(
        """
        <style>
        .block-container { padding-top: 2rem; max-width: 1100px; }
        h1 { font-weight: 700; letter-spacing: -0.5px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("# 🧠 AI Job Fit & Salary Estimator")
    st.markdown(
        f"<p style='color:{NEUTRAL};font-size:15px;margin-bottom:24px'>"
        f"Nahraj CV (PDF/DOCX) a získej odhad pozice, seniority, mzdy a růstový plán k +30 %. "
        f"Pipeline: parser → LLM extrakce (s tier classification) → 5D scoring → "
        f"ChromaDB retrieval → deterministická salary anchor → LLM finalizér.</p>",
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "CV (PDF nebo DOCX, max 10 MB)",
        type=["pdf", "docx"],
    )

    submit = st.button(
        "🚀 Spustit analýzu",
        type="primary",
        disabled=uploaded is None,
        use_container_width=True,
    )

    if not submit or uploaded is None:
        return

    try:
        with st.spinner("Nahrávám soubor..."):
            job_id = upload_cv(uploaded.getvalue(), uploaded.name, uploaded.type or "")
    except httpx.HTTPStatusError as e:
        st.error(f"Backend odmítl soubor: {e.response.status_code} – {e.response.text}")
        return
    except httpx.HTTPError as e:
        st.error(f"Chyba při komunikaci s backendem: {e}")
        return

    st.toast(f"Úloha přijata: `{job_id}`", icon="✅")

    report: dict | None = None
    error: str | None = None
    log_entries: list[dict] = []
    next_log_offset = 0

    with st.status("Zpracování probíhá...", expanded=True) as status:
        progress_box = st.empty()
        st.markdown(
            "<div style='font-size:11px;color:#94a3b8;margin:8px 0 4px 0;"
            "text-transform:uppercase;letter-spacing:1.2px'>"
            "🖥 Backend konzole (live)</div>",
            unsafe_allow_html=True,
        )
        log_box = st.empty()

        for _ in range(MAX_POLL_ITERATIONS):
            try:
                data = get_status(job_id)
                log_resp = get_logs(job_id, since=next_log_offset)
                new_entries = log_resp.get("entries", [])
                if new_entries:
                    log_entries.extend(new_entries)
                    next_log_offset = log_resp.get("next", next_log_offset + len(new_entries))
            except httpx.HTTPError as e:
                status.update(label="Chyba při dotazování statusu", state="error")
                error = str(e)
                break

            current = data["status"]
            render_pipeline_progress(progress_box, current)
            render_log_console(log_box, log_entries[-30:], height_px=240)

            if current == "done":
                status.update(label="Hotovo", state="complete")
                report = data["result"]
                break
            if current == "failed":
                status.update(label="Backend pipeline selhala", state="error")
                error = data.get("error") or "Neznámá chyba"
                break

            time.sleep(POLL_INTERVAL_S)
        else:
            status.update(label="Časový limit", state="error")
            error = "Polling překročil maximum (5 min)."

    # Finální fetch – chytne logy které dorazily mezi posledním pollem a DONE/FAILED.
    try:
        final_logs = get_logs(job_id, since=next_log_offset).get("entries", [])
        if final_logs:
            log_entries.extend(final_logs)
    except httpx.HTTPError:
        pass

    # Plný log expandér – vždy viditelný (i při chybě).
    with st.expander(f"🖥 Backend konzole · {len(log_entries)} zpráv · job_id `{job_id}`",
                     expanded=False):
        render_log_console(st, log_entries, height_px=460)

    if error:
        st.error(error)
        return
    if report is None:
        return

    render_report(report)


if __name__ == "__main__":
    main()
