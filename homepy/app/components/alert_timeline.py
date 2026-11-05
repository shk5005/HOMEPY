from __future__ import annotations

import plotly.graph_objects as go

LEVELS = ["WATCH", "ADVISORY", "WARNING", "CRITICAL"]
LEVEL_COLORS = {"WATCH": "blue", "ADVISORY": "gold", "WARNING": "orange", "CRITICAL": "red"}


def alert_timeline(alerts: list[dict]) -> go.Figure:
    fig = go.Figure()
    if not alerts:
        fig.add_annotation(text="데이터 없음", x=0.5, y=0.5, xref="paper", yref="paper",
                           showarrow=False)
        fig.update_layout(xaxis={"visible": False}, yaxis={"visible": False})
        return fig
    for level in LEVELS:
        subset = [a for a in alerts if a.get("level") == level]
        if not subset:
            continue
        fig.add_trace(go.Scatter(
            x=[a.get("created_at") for a in subset],
            y=[level] * len(subset),
            mode="markers",
            name=level,
            marker={"color": LEVEL_COLORS[level], "size": 12},
            text=[a.get("title", "") for a in subset],
            hovertemplate="%{x}<br>%{text}<extra>" + level + "</extra>",
        ))
    fig.update_layout(xaxis_title="발생 시각", yaxis_title="등급",
                      yaxis={"categoryorder": "array", "categoryarray": LEVELS})
    return fig
