from __future__ import annotations

from collections import Counter

import plotly.graph_objects as go


def _empty(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    fig.update_layout(xaxis={"visible": False}, yaxis={"visible": False})
    return fig


def anomaly_heatmap(anomalies: list[dict]) -> go.Figure:
    if not anomalies:
        return _empty("데이터 없음")
    counts: Counter = Counter()
    for a in anomalies:
        day = str(a.get("detected_at", ""))[:10]
        counts[(day, a.get("district_code", "?"))] += 1
    dates = sorted({d for d, _ in counts})
    districts = sorted({c for _, c in counts})
    z = [[counts.get((d, c), 0) for d in dates] for c in districts]
    fig = go.Figure(go.Heatmap(x=dates, y=districts, z=z, colorscale="Reds",
                               colorbar={"title": "건수"}))
    fig.update_layout(xaxis_title="날짜", yaxis_title="지역코드", yaxis={"type": "category"})
    return fig
