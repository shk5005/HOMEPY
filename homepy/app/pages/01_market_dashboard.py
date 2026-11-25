import pandas as pd
import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run
from homepy.app.components.cycle_diagram import cycle_diagram
from homepy.app.components.regulation_map import regulation_map

st.set_page_config(page_title="시장 대시보드", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

# Static reference districts (no regulation endpoint yet).
DISTRICTS = {
    "11680": ("강남구", 37.5172, 127.0473, "speculation-overheated"),
    "11650": ("서초구", 37.4837, 127.0324, "speculation-overheated"),
    "11710": ("송파구", 37.5145, 127.1059, "speculation-overheated"),
    "11440": ("마포구", 37.5663, 126.9019, "adjusted-target"),
    "11350": ("노원구", 37.6542, 127.0568, "non-regulated"),
}

st.title("시장 대시보드")
try:
    macro = run(client.get_macro_summary())
except ApiError as exc:
    st.error(f"API 연결 실패: {exc}")
    macro = {}


def card(col, label, key, suffix=""):
    v = macro.get(key)
    col.metric(label, "-" if v is None else f"{v:,.2f}{suffix}")


left, center, right = st.columns([1, 1.2, 1.2])
with left:
    st.subheader("거시 지표")
    card(st, "기준금리", "base_rate", "%")
    card(st, "주담대 금리", "mortgage_rate", "%")
    card(st, "원/달러", "usd_krw")
    card(st, "CPI YoY", "cpi_change_yoy_pct", "%")
    card(st, "GDP 성장률", "gdp_growth", "%")
with center:
    st.subheader("사이클 위치")
    code = st.selectbox("지역", list(DISTRICTS), format_func=lambda c: f"{DISTRICTS[c][0]} ({c})")
    cycle = {}
    try:
        cycle = run(client.get_cycle(code))
    except ApiError as exc:
        st.warning(f"사이클 조회 실패: {exc}")
    cycle_diagram(cycle.get("phase"), cycle.get("indicators"))
    st.caption(f"현재 국면: {cycle.get('phase') or '알 수 없음'}")
with right:
    st.subheader("규제지역")
    regulation_map([{"name": n, "lat": la, "lon": lo, "zone": z} for n, la, lo, z in DISTRICTS.values()])

st.subheader("주요 시그널 요약")
ind = (cycle.get("indicators") or {})
if ind:
    st.dataframe(pd.DataFrame([{"indicator": k, "value": v} for k, v in ind.items()]), hide_index=True)
else:
    st.info("표시할 시그널이 없습니다.")
