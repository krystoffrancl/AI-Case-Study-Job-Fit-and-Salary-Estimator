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
MAX_POLL_ITERATIONS = 600  # 5 minut při 0.5s

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
    """Horizontální bar chart: tvůj odhad nahoře, pod ním rozsahy matchnutých pozic."""
    fig = go.Figure()

    # samotný odhad – sytá výplň
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

    # corpus matche – průhlednější
    for m in reversed(matches):  # první match nahoře hned pod odhadem
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
        ("Praxe", seniority["experience_score"], 40),
        ("Skills", seniority["skills_score"], 30),
        ("Vzdělání", seniority["education_score"], 15),
        ("Role", seniority["seniority_score"], 15),
    ]
    labels = [c[0] for c in cats]
    actual = [c[1] for c in cats]
    maxes = [c[2] for c in cats]
    pcts = [a / m * 100 for a, m in zip(actual, maxes)]
    text_labels = [f"{a:.0f} / {m}" for a, m in zip(actual, maxes)]

    fig = go.Figure()
    # background "max" bar (faint)
    fig.add_trace(go.Bar(
        x=[100] * len(labels),
        y=labels,
        orientation="h",
        marker_color="rgba(148, 163, 184, 0.15)",
        showlegend=False,
        hoverinfo="skip",
    ))
    # actual value
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
        height=240,
        margin=dict(t=20, b=10, l=10, r=40),
        xaxis=dict(range=[0, 115], visible=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=13)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        bargap=0.4,
    )
    return fig


# ----- result rendering ---------------------------------------------------

def render_salary(salary: dict, matches: list[dict]) -> None:
    low, high = salary["min_czk"], salary["max_czk"]
    mid = (low + high) // 2

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
        st.markdown("##### Rozpis hodnocení")
        st.plotly_chart(
            chart_seniority_breakdown(seniority),
            use_container_width=True,
            config={"displayModeBar": False},
        )


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

        with col_right:
            st.markdown(
                f"<div style='font-size:11px;text-transform:uppercase;"
                f"letter-spacing:1.5px;color:{NEUTRAL};font-weight:600;"
                f"margin-bottom:8px'>Skills ({len(extracted.get('skills', []))})</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                skills_pills_html(extracted.get("skills", [])),
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
    section_header("💰", "Odhad měsíční mzdy")
    render_salary(report["salary"], report.get("matches", []))

    section_header("📊", "Seniority", "Rule-based skóre kombinující praxi, dovednosti, vzdělání a roli.")
    render_seniority(report["seniority"])

    section_header("🧑", "Profil uchazeče", "Extrahováno z CV strukturovaným LLM voláním.")
    render_profile(report["extracted"])

    if report.get("matches"):
        section_header("🎯", "Detail nejpodobnějších pozic", "Vector retrieval z 722 pozic v ChromaDB (cosine similarity).")
        render_matches_table(report["matches"])

    section_header("📝", "Vysvětlení")
    render_explanation(report["explanation"])


# ----- main ---------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Job Fit & Salary Estimator",
        page_icon="🧠",
        layout="wide",
    )

    # Mírné CSS odlehčení – širší text-areu pro hlavní obsah
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
        f"Nahraj CV (PDF/DOCX) a získej odhad pozice, seniority a měsíční mzdy v ČR. "
        f"Pipeline: parser → LLM extrakce → scoring → ChromaDB retrieval → LLM finalizér.</p>",
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

    # --- upload ---
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

    # --- polling ---
    report: dict | None = None
    error: str | None = None

    with st.status("Zpracování probíhá...", expanded=True) as status:
        progress_box = st.empty()
        for _ in range(MAX_POLL_ITERATIONS):
            try:
                data = get_status(job_id)
            except httpx.HTTPError as e:
                status.update(label="Chyba při dotazování statusu", state="error")
                error = str(e)
                break

            current = data["status"]
            render_pipeline_progress(progress_box, current)

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

    if error:
        st.error(error)
        return
    if report is None:
        return

    render_report(report)


if __name__ == "__main__":
    main()
