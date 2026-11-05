import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

st.set_page_config(page_title="자연어 질의", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"], timeout=60.0)

st.title("자연어 질의")
st.caption("자연어를 읽기 전용 TypeQL로 변환해 온톨로지를 조회합니다.")

query = st.text_input("질의", placeholder="강남구에서 저평가된 단지", max_chars=500)

if st.button("조회", type="primary", disabled=not query.strip()):
    try:
        st.session_state["nlp_result"] = run(client.post_nlp_query(query.strip()))
    except ApiError as exc:
        st.session_state.pop("nlp_result", None)
        st.error(f"API 오류: {exc}")

res = st.session_state.get("nlp_result")
if res:
    with st.expander("생성된 TypeQL"):
        st.code(res["generated_typeql"], language="sql")
    rows = res.get("results", [])
    c1, c2 = st.columns(2)
    c1.metric("결과 수", len(rows))
    c2.metric("실행 시간", f"{res['execution_time_ms']:.0f} ms")
    if rows:
        st.dataframe(rows, use_container_width=True)
        st.subheader("상세 분석")
        for i, row in enumerate(rows[:20]):
            cid = row.get("id") or row.get("complex_id")
            if cid:
                if st.button(f"{cid} 심층 분석 (멀티에이전트)", key=f"deep_{i}"):
                    st.session_state["debate_complex_id"] = str(cid)
                    st.switch_page("pages/14_multiagent.py")
    else:
        st.info("결과가 없습니다.")
