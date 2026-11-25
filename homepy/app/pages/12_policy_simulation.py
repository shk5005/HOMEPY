import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run
from homepy.app.components import impact_chain

st.set_page_config(page_title="정책 시뮬레이션", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

st.title("정책 시뮬레이션")
st.caption("운영 데이터는 변경되지 않습니다 (읽기 전용 시뮬레이션).")

TYPES = {"세제 변경": "tax", "규제 지정/해제": "regulation",
         "금리 시나리오": "interest_rate", "공급 충격": "supply_shock"}

# 1. Input form
choice = st.selectbox("시뮬레이션 유형", list(TYPES))
policy_type = TYPES[choice]
params: dict = {}
if policy_type == "tax":
    params["acquisition_tax_rate"] = st.slider("취득세율", 0.0, 0.12, 0.03, 0.005)
    params["capital_gains_tax_rate"] = st.slider("양도세율", 0.0, 0.8, 0.4, 0.01)
    params["comprehensive_tax_rate"] = st.slider("종부세율", 0.0, 0.05, 0.01, 0.001)
elif policy_type == "regulation":
    params["district_code"] = st.text_input("지역 코드", "11680")
    params["regulation_type"] = st.selectbox(
        "규제 유형", ["speculation_zone", "adjustment_zone", "speculation_overheated"])
    params["action"] = st.radio("조치", ["designate", "release"], horizontal=True)
elif policy_type == "interest_rate":
    raw = st.text_input("금리 경로 (%, 쉼표 구분)", "3.5, 3.25, 3.0")
    try:
        params["rate_path"] = [float(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        st.error("숫자를 쉼표로 구분해 입력하세요.")
        st.stop()
else:
    params["district_code"] = st.text_input("지역 코드", "11680")
    params["units"] = st.number_input("공급 호수", 0, 100000, 5000, 500)

if st.button("시뮬레이션 실행", type="primary"):
    try:
        st.session_state["policy_result"] = run(client.post_policy(policy_type, params))
    except ApiError as exc:
        st.error(f"API 오류: {exc}")

# 2. Impact summary
result = st.session_state.get("policy_result")
if result:
    st.subheader("영향 요약")
    c1, c2, c3 = st.columns(3)
    c1.metric("변경 전 점수", f"{result['score_before']:.2f}")
    c2.metric("변경 후 점수", f"{result['score_after']:.2f}")
    c3.metric("변화량", f"{result['delta']:+.2f}", delta=f"{result['delta']:+.2f}")
    for e in result.get("direct_effects", []):
        st.markdown(f"- {e}")
    st.table([{"영향 지역": d} for d in result.get("affected_districts", [])])

    # 3. Impact chain
    st.subheader("영향 체인")
    impact_chain(result.get("impact_chain", []), policy_label=choice, delta=result["delta"])

# 4. Backtest
with st.expander("정책 백테스팅"):
    name = st.text_input("정책명", "2020 부동산 대책")
    pdate = st.date_input("시행일")
    if st.button("백테스트 실행"):
        try:
            bt = run(client.post_policy_backtest(name, pdate.isoformat(), {}))
        except ApiError as exc:
            st.error(f"API 오류: {exc}")
        else:
            st.metric("정확도", f"{bt['accuracy_score'] * 100:.0f}%")
            st.markdown("**누락 요인**")
            for f in bt.get("missed_factors", []) or ["-"]:
                st.markdown(f"- {f}")
            st.json({"시뮬레이션": bt["simulated_impact"], "실제": bt["actual_market_response"]})
