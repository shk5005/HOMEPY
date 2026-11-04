import plotly.graph_objects as go
import streamlit as st

GRADE_COLORS = {"A": "#2ca02c", "B": "#1f77b4", "C": "#e6c619", "D": "#ff7f0e", "F": "#d62728"}


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def radar_chart(factors: list[dict], grade: str = "C", *, key: str | None = None) -> None:
    """Radar of factor `normalized` values (0-100); fill color follows the grade."""
    if not factors:
        st.info("팩터 데이터가 없습니다.")
        return
    color = GRADE_COLORS.get(str(grade).upper(), GRADE_COLORS["C"])
    names = [f["name"] for f in factors]
    values = [float(f.get("normalized", 0)) for f in factors]
    fig = go.Figure(go.Scatterpolar(
        r=values + values[:1], theta=names + names[:1], fill="toself",
        line=dict(color=color), fillcolor=_rgba(color, 0.35), name="점수",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False, margin=dict(l=40, r=40, t=20, b=20), height=420,
    )
    st.plotly_chart(fig, use_container_width=True, key=key)
