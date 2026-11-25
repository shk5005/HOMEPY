import streamlit as st
import streamlit.components.v1 as components

from homepy.app.api_client import ApiClient, ApiError, run
from homepy.app.components.knowledge_graph import TYPE_COLORS, build_graph_html

st.set_page_config(page_title="온톨로지 그래프", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

st.title("온톨로지 그래프")
complex_id = st.text_input("단지 ID", value=st.session_state.get("complex_id", "")).strip()
if not complex_id:
    st.info("단지 ID를 입력하세요.")
    st.stop()

try:
    graph = run(client.get_graph(complex_id))
except ApiError as exc:
    st.error(f"API 오류: {exc}")
    st.stop()

if not graph.get("nodes"):
    st.info("표시할 그래프 데이터가 없습니다.")
    st.stop()

st.caption("범례: " + ", ".join(TYPE_COLORS))
st.caption(f"노드 {len(graph['nodes'])}개 / 엣지 {len(graph.get('edges', []))}개")
components.html(build_graph_html(graph), height=620, scrolling=True)
