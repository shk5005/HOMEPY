import pandas as pd
import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

st.set_page_config(page_title="세금 시뮬레이션", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

st.title("세금 시뮬레이션")
OWNERS = {"1주택": 1, "2주택": 2, "3주택+": 3, "법인": 1}
AREAS = {"조정대상지역": "regulated", "비규제지역": "non_regulated"}

with st.form("tax"):
    c1, c2 = st.columns(2)
    price = c1.number_input("취득가 (원)", min_value=1, value=1_000_000_000, step=10_000_000)
    sale_price = c2.number_input("양도가 (원, 0=미양도)", min_value=0, value=0, step=10_000_000)
    buyer = c1.selectbox("구분", list(OWNERS))
    area = c2.selectbox("지역", list(AREAS))
    holding = c1.number_input("보유 기간 (년)", min_value=0.0, value=2.0, step=0.5)
    residence = c2.number_input("거주 기간 (년)", min_value=0.0, value=0.0, step=0.5)
    assessed = st.number_input("공시가격 (원, 0=미입력)", min_value=0, value=0, step=10_000_000)
    submitted = st.form_submit_button("계산")

if not submitted:
    st.stop()

payload = {
    "price": int(price), "holding_years": float(holding),
    "buyer_type": "corporate" if buyer == "법인" else "individual",
    "owner_count": OWNERS[buyer], "area_type": AREAS[area],
}
if sale_price:
    payload["sale_price"] = int(sale_price)
if assessed:
    payload["assessed_values"] = [int(assessed)]
try:
    res = run(client.post_tax(payload))
except ApiError as exc:
    st.error(f"API 오류: {exc}")
    st.stop()
if residence:
    st.caption(f"거주 기간 {residence}년은 참고용이며 API 계산에는 전달되지 않습니다.")

st.metric("총 세금", f"{res.get('total_tax', 0):,}원")
for label, key in [("취득세", "acquisition_tax"), ("양도소득세", "capital_gains_tax"),
                   ("종합부동산세", "comprehensive_tax")]:
    st.subheader(label)
    d = res.get(key)
    if not d:
        st.caption("해당 없음")
        continue
    st.dataframe(pd.DataFrame([{"항목": k, "값": str(v)} for k, v in d.items()]),
                 hide_index=True, use_container_width=True)
