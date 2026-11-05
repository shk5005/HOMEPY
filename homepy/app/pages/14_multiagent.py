import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

st.set_page_config(page_title="멀티에이전트 토론", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"], timeout=180.0)

st.title("멀티에이전트 토론")
st.caption("Bull / Bear / Behavioral / Policy 에이전트가 4라운드로 토론합니다.")

complex_id = st.text_input("단지 ID", st.session_state.get("debate_complex_id", ""))

if st.button("토론 시작", type="primary", disabled=not complex_id.strip()):
    with st.spinner("토론 진행 중..."):
        try:
            st.session_state["debate_result"] = run(client.post_debate(complex_id.strip()))
            st.session_state["debate_for"] = complex_id.strip()
        except ApiError as exc:
            st.session_state.pop("debate_result", None)
            st.error(f"API 오류: {exc}")

res = st.session_state.get("debate_result")
if res:
    rounds = res.get("rounds", [])
    # Agent cards: latest output per agent (skip cross-agent keys like "A->B").
    st.subheader("에이전트 관점")
    latest: dict[str, str] = {}
    for r in rounds:
        for name, text in r["agent_outputs"].items():
            if "->" not in name:
                latest[name] = text
    cols = st.columns(max(len(latest), 1))
    for col, (name, text) in zip(cols, latest.items()):
        with col.container(border=True):
            st.markdown(f"**{name}**")
            st.write(text)

    # Consensus meter
    st.subheader("합의 수준")
    dissent = len(res.get("dissenting_views", []))
    total = max(len(latest), 1)
    agree = max(total - dissent, 0)
    st.progress(agree / total, text=f"{agree}/{total} 에이전트 동의")
    if res.get("consensus_reached"):
        st.success(f"합의 도달: {res.get('final_verdict')}")
    else:
        st.warning("합의 미달 - 소수 의견 존재")
    for d in res.get("dissenting_views", []):
        st.markdown(f"- **{d['agent_name']}** ({d['verdict']}, {d['confidence'] * 100:.0f}%): "
                    + "; ".join(d.get("key_arguments", [])))

    # Transcript
    st.subheader("토론 기록")
    for r in rounds:
        with st.expander(f"라운드 {r['round_number']}"):
            for name, text in r["agent_outputs"].items():
                st.markdown(f"**{name}**")
                st.write(text)

    # Report download
    st.subheader("리포트")
    if st.button("PDF 리포트 생성"):
        try:
            st.session_state["debate_pdf"] = run(client.post_report_generate(
                st.session_state.get("debate_for", complex_id), "pdf", True))
        except ApiError as exc:
            st.error(f"API 오류: {exc}")
    if st.session_state.get("debate_pdf"):
        st.download_button("PDF 다운로드", st.session_state["debate_pdf"],
                           file_name="homepy_report.pdf", mime="application/pdf")
