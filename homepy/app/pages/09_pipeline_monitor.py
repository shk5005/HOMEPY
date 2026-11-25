import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

st.set_page_config(page_title="파이프라인 상태", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

BADGE = {"ok": "🟢 정상", "error": "🔴 오류"}
STAGES = ["원천(source)", "정제(cleaned)", "변환(transformed)", "적재(loaded)"]

st.title("파이프라인 상태")
try:
    status = run(client.get_pipeline_status())
except ApiError as exc:
    st.error(f"API 오류: {exc}")
    st.stop()

c1, c2 = st.columns(2)
c1.metric("총 적재 행 수", f"{status.get('total_rows', 0):,}")
c2.metric("최근 갱신", str(status.get("latest_ts") or "-"))

st.subheader("수집기 상태")
collectors = status.get("collectors", [])
if collectors:
    df = pd.DataFrame([{"이름": c["table"], "최근 실행": c.get("latest_ts") or "-",
                        "다음 예정": "-", "행 수": c["rows"],
                        "상태": BADGE.get(c["state"], c["state"])} for c in collectors])
    st.dataframe(df, hide_index=True)

    st.subheader("품질 게이트 이력")
    fig = go.Figure(go.Bar(
        x=[c["rows"] for c in collectors], y=[c["table"] for c in collectors], orientation="h",
        marker_color=["#2ecc71" if c["state"] == "ok" else "#e74c3c" for c in collectors]))
    fig.update_layout(xaxis_title="행 수 (초록=통과, 빨강=실패)", height=380)
    st.plotly_chart(fig)
else:
    st.info("수집기 정보가 없습니다.")

st.subheader("데이터 계보")
fig = go.Figure(go.Scatter(
    x=list(range(len(STAGES))), y=[0] * len(STAGES), mode="markers+text", text=STAGES,
    textposition="top center", marker=dict(size=28, color="#2980b9")))
for i in range(len(STAGES) - 1):
    fig.add_annotation(x=i + 1, y=0, ax=i, ay=0, xref="x", yref="y", axref="x", ayref="y",
                       showarrow=True, arrowhead=3)
fig.update_layout(height=200, xaxis_visible=False, yaxis_visible=False, showlegend=False)
st.plotly_chart(fig)
