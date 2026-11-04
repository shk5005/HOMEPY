import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run
from homepy.app.components.bias_warning import bias_warning
from homepy.app.components.evidence_chain import evidence_chain
from homepy.app.components.radar_chart import GRADE_COLORS, radar_chart

st.set_page_config(page_title="단지 심층 분석", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

st.title("단지 심층 분석")
complex_id = st.text_input("단지 ID", value=st.session_state.get("complex_id", ""),
                           placeholder="예: apt-001").strip()
if not complex_id:
    st.info("단지 ID를 입력하세요.")
    st.stop()
st.session_state["complex_id"] = complex_id

try:
    scores = run(client.post_score([complex_id]))
    verdict = run(client.post_verdict(complex_id))
except ApiError as exc:
    st.error(f"API 오류: {exc}")
    st.stop()

score = scores[0] if scores else {}
grade = score.get("grade", "-")
left, center, right = st.columns([1.2, 1.5, 1])
with left:
    st.subheader("14팩터 레이더")
    color = GRADE_COLORS.get(str(grade).upper(), "#888")
    st.markdown(f"<span style='background:{color};color:#fff;padding:4px 12px;"
                f"border-radius:6px;font-weight:bold'>등급 {grade}</span>", unsafe_allow_html=True)
    st.metric("종합 점수", f"{score.get('total_score', 0):.1f}")
    radar_chart(score.get("factors", []), grade)
with center:
    st.subheader("투자 판단")
    st.markdown(f"### {verdict.get('verdict', '-')}  (신뢰도: {verdict.get('confidence', '-')})")
    st.markdown("**핵심 사실**")
    for fact in verdict.get("core_facts", []):
        st.markdown(f"- {fact}")
    st.success(f"**강세 근거**: {verdict.get('strongest_bull_case', '-')}")
    st.error(f"**약세 근거**: {verdict.get('strongest_bear_case', '-')}")
    st.markdown(f"**숨은 변수**: {verdict.get('hidden_variable', '-')}")
    st.markdown(f"**주요 리스크**: {verdict.get('primary_risk', '-')}")
    st.warning(f"**킬 스위치**: {verdict.get('kill_switch', '-')}")
    if verdict.get("scenario_summary"):
        st.markdown(f"**시나리오 요약**: {verdict['scenario_summary']}")
    st.markdown("**관찰 데이터**")
    for item in verdict.get("watchlist_data", []):
        st.markdown(f"- {item}")
with right:
    st.subheader("편향 경고")
    bias_warning(verdict.get("bias_warnings", []))

with st.expander("근거 체인", expanded=False):
    evidence_chain(verdict.get("evidence_chain", []))
