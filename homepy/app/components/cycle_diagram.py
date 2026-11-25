import plotly.graph_objects as go

PHASES = ["recovery", "expansion", "peak", "contraction"]


def build_cycle_figure(phase: str | None, indicators: dict | None = None) -> go.Figure:
    """Polar 4-phase wheel (recovery -> expansion -> peak -> contraction) with a marker on `phase`."""
    fig = go.Figure(go.Barpolar(
        r=[1] * 4, theta=[45 + 90 * i for i in range(4)], width=[88] * 4,
        text=PHASES, hovertext=[f"{p}" for p in PHASES],
        marker_color=["#7fb3d5" if p != phase else "#e67e22" for p in PHASES],
        marker_line_color="white", marker_line_width=2, showlegend=False,
    ))
    if phase in PHASES:
        fig.add_trace(go.Scatterpolar(
            r=[0.6], theta=[45 + 90 * PHASES.index(phase)], mode="markers+text",
            marker=dict(size=18, color="#c0392b"), text=["▶ 현재"], textposition="top center",
            hovertext=[", ".join(f"{k}={v}" for k, v in (indicators or {}).items() if v is not None)],
            showlegend=False))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=False, range=[0, 1]),
                   angularaxis=dict(tickmode="array", tickvals=[45 + 90 * i for i in range(4)],
                                    ticktext=PHASES, direction="clockwise", rotation=90)),
        margin=dict(l=20, r=20, t=20, b=20), height=320)
    return fig


def cycle_diagram(phase: str | None, indicators: dict | None = None) -> None:
    import streamlit as st
    st.plotly_chart(build_cycle_figure(phase, indicators), width="stretch")
