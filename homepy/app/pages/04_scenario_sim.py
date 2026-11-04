import plotly.graph_objects as go
import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

st.set_page_config(page_title="시나리오 시뮬레이션", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

st.title("시나리오 시뮬레이션")
complex_id = st.text_input("단지 ID", value=st.session_state.get("complex_id", "")).strip()
if not complex_id:
    st.info("단지 ID를 입력하세요.")
    st.stop()
st.session_state["complex_id"] = complex_id

try:
    data = run(client.post_scenario(complex_id))
except ApiError as exc:
    st.error(f"API 오류: {exc}")
    st.stop()

ICONS = {"bull": "🟢", "base": "🔵", "bear": "🔴"}
scenarios = data.get("scenarios", [])
cols = st.columns(max(len(scenarios), 1))
for col, sc in zip(cols, scenarios):
    with col, st.container(border=True):
        name = str(sc.get("name", "-"))
        st.subheader(f"{ICONS.get(name.lower(), '⚪')} {name}")
        st.metric("확률", f"{sc.get('probability', 0) * 100:.0f}%")
        st.markdown(f"**예상 결과**: {sc.get('expected_outcome', '-')}")
        st.markdown("**조건**")
        for c in sc.get("conditions", []):
            st.markdown(f"- {c}")
        st.markdown("**선행 지표**")
        for c in sc.get("leading_indicators", []):
            st.markdown(f"- {c}")
        st.markdown("**무효화 조건**")
        for c in sc.get("invalidation_conditions", []):
            st.markdown(f"- {c}")

sens = data.get("sensitivity", [])
st.subheader("민감도 분석")
if not sens:
    st.info("민감도 데이터가 없습니다.")
    st.stop()

width = max(len(s["perturbations"]) for s in sens)
z = [list(s["score_impacts"]) + [None] * (width - len(s["score_impacts"])) for s in sens]
x = [f"수준 {i + 1}" for i in range(width)]
fig = go.Figure(go.Heatmap(z=z, x=x, y=[s["variable"] for s in sens],
                           colorscale="RdYlGn", zmid=0, colorbar=dict(title="점수 영향")))
fig.update_layout(height=120 + 50 * len(sens), margin=dict(l=20, r=20, t=20, b=20))
st.plotly_chart(fig, use_container_width=True)

st.subheader("변수 조정 (실시간 점수 변화)")
total = 0.0
for s in sens:
    perts, impacts = s["perturbations"], s["score_impacts"]
    if not perts:
        continue
    pairs = sorted(zip(perts, impacts))
    lo, hi = pairs[0][0], pairs[-1][0]
    base = s.get("base_value", 0)
    if lo == hi:
        st.caption(f"{s['variable']}: 조정 범위 없음")
        continue
    val = st.slider(f"{s['variable']} (기준값 {base})", float(lo), float(hi),
                    float(min(max(base, lo), hi)), key=f"sl_{s['variable']}")
    impact = pairs[-1][1]
    for (p0, i0), (p1, i1) in zip(pairs, pairs[1:]):
        if p0 <= val <= p1:
            impact = i0 if p1 == p0 else i0 + (i1 - i0) * (val - p0) / (p1 - p0)
            break
    else:
        if val <= lo:
            impact = pairs[0][1]
    total += impact
    st.caption(f"점수 영향: {impact:+.2f}")
st.metric("총 점수 변화 (선형 보간 추정)", f"{total:+.2f}")
