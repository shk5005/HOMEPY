"""Page 10: Improvement Dashboard (verification, calibration, system health)."""
from datetime import datetime
from importlib import metadata

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

st.set_page_config(page_title="개선 대시보드", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
st.session_state.setdefault("accuracy_history", [])
st.session_state.setdefault("rejected_proposals", set())
st.session_state.setdefault("applied_records", [])
client = ApiClient(st.session_state["api_base_url"])

BADGE = {"ok": "🟢 정상", "degraded": "🟡 저하", "error": "🔴 오류"}
TRACKED_PACKAGES = ["fastapi", "streamlit", "plotly", "pandas", "numpy", "httpx", "pydantic",
                    "asyncpg", "typedb-driver"]

st.title("개선 대시보드")


def _fetch(coro, label):
    try:
        return run(coro)
    except ApiError as exc:
        st.warning(f"{label}: API 오류 ({exc})")
        return None


accuracy = _fetch(client.get_verification_accuracy(), "추론 정확도")
proposals = _fetch(client.get_verification_proposals(), "보정 제안")
health = _fetch(client.get_verification_health(), "시스템 상태")

# 1. System health summary
st.header("1. 시스템 상태 요약")
components = {c["name"]: c for c in (health or {}).get("components", [])}
cols = st.columns(4)
for col, name in zip(cols, ["inference", "pipeline", "typedb", "timescaledb"]):
    comp = components.get(name)
    col.metric(name, BADGE.get(comp["status"], comp["status"]) if comp else "⚪ 데이터 없음")
if health:
    c1, c2 = st.columns(2)
    c1.metric("데이터 품질 경고", health.get("data_quality_alerts", 0))
    c2.metric("24시간 자동 복구 이벤트", health.get("recovery_events_24h", 0))

# 2. Inference accuracy trend
st.header("2. 추론 정확도 추이")
if accuracy:
    history = st.session_state["accuracy_history"]
    if not history or history[-1]["computed_at"] != accuracy["computed_at"]:
        history.append(accuracy)
if st.session_state["accuracy_history"]:
    hist = st.session_state["accuracy_history"]
    xs = [h["computed_at"] for h in hist]
    fig = go.Figure()
    fig.add_scatter(x=xs, y=[h["direction_accuracy"] for h in hist], name="방향 정확도(%)")
    fig.add_scatter(x=xs, y=[h["signal_hit_rate"] for h in hist], name="시그널 적중률(%)")
    fig.update_layout(yaxis_title="%", height=320)
    st.plotly_chart(fig)
    st.caption(f"최근 백테스트 판정 수: {hist[-1]['total_verdicts']}")
else:
    st.info("백테스트 결과가 없습니다.")

# 3. Calibration proposals
st.header("3. 보정 제안")
open_props = [p for p in (proposals or [])
              if p["proposal_id"] not in st.session_state["rejected_proposals"]]
if not open_props:
    st.info("대기 중인 보정 제안이 없습니다.")
for p in open_props:
    with st.expander(f"[{p['category']}] {p['proposal_id']} - {p['status']}"):
        st.write(p["rationale"])
        a, b = st.columns(2)
        a.json(p["current_values"])
        b.json(p["proposed_values"])
        ok_col, no_col = st.columns(2)
        if ok_col.button("승인", key=f"approve-{p['proposal_id']}"):
            try:
                rec = run(client.approve_proposal(p["proposal_id"]))
                st.session_state["applied_records"].append(rec)
                st.success(f"적용됨: {rec['record_id']}")
            except ApiError as exc:
                st.error(f"승인 실패: {exc}")
        if no_col.button("거절", key=f"reject-{p['proposal_id']}"):
            st.session_state["rejected_proposals"].add(p["proposal_id"])
            st.rerun()

# 4. Data quality heatmap
st.header("4. 데이터 품질 히트맵")
st.info("소스 x 날짜 품질 점수 API가 아직 제공되지 않습니다. "
        f"현재 데이터 품질 경고 수: {(health or {}).get('data_quality_alerts', 0)}")

# 5. Performance dashboard
st.header("5. 성능 대시보드")
if components:
    fig = go.Figure(go.Bar(x=list(components), y=[c["latency_p95"] for c in components.values()],
                           name="p95 (ms)"))
    fig.update_layout(yaxis_title="응답 시간 p95 (ms)", height=320)
    st.plotly_chart(fig)
else:
    st.info("성능 지표가 없습니다.")

# 6. Recovery history
st.header("6. 복구 이력")
st.metric("최근 24시간 자동 복구", (health or {}).get("recovery_events_24h", 0))
st.caption("상세 이벤트 목록 API는 아직 제공되지 않습니다.")

# 7. Improvement timeline
st.header("7. 개선 타임라인")
applied = st.session_state["applied_records"]
if applied:
    fig = go.Figure(go.Scatter(
        x=[datetime.fromisoformat(r["timestamp"]) for r in applied],
        y=[r["category"] for r in applied], mode="markers+text",
        text=[r["component"] for r in applied], textposition="top center"))
    fig.update_layout(height=300)
    st.plotly_chart(fig)
else:
    st.info("이번 세션에서 적용된 개선 기록이 없습니다.")

# 8. Tech stack health
st.header("8. 기술 스택 상태")
rows = []
for pkg in TRACKED_PACKAGES:
    try:
        rows.append({"패키지": pkg, "버전": metadata.version(pkg), "취약점": "미확인"})
    except metadata.PackageNotFoundError:
        rows.append({"패키지": pkg, "버전": "-", "취약점": "미설치"})
st.dataframe(pd.DataFrame(rows), hide_index=True)
