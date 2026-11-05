import plotly.graph_objects as go
import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

st.set_page_config(page_title="대출 시뮬레이션", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

st.title("대출 시뮬레이션")
AREAS = {"조정대상지역": "regulated", "비규제지역": "non_regulated"}

with st.form("loan"):
    c1, c2 = st.columns(2)
    price = c1.number_input("주택 가격 (원)", min_value=1, value=800_000_000, step=10_000_000)
    income = c2.number_input("연 소득 (원)", min_value=1, value=100_000_000, step=1_000_000)
    debt = c1.number_input("기존 대출 연간 원리금 (원)", min_value=0, value=0, step=1_000_000)
    area = c2.selectbox("지역", list(AREAS))
    rate = c1.number_input("금리 (%)", min_value=0.1, max_value=30.0, value=4.5, step=0.1)
    term = c2.number_input("대출 기간 (년)", min_value=1, max_value=50, value=30)
    first = st.checkbox("생애최초 구입자")
    submitted = st.form_submit_button("계산")

if not submitted:
    st.stop()

try:
    res = run(client.post_loan({
        "price": int(price), "income": int(income), "existing_debt": int(debt),
        "area_type": AREAS[area], "interest_rate": rate / 100, "term_years": int(term),
        "first_time_buyer": first,
    }))
except ApiError as exc:
    st.error(f"API 오류: {exc}")
    st.stop()

max_loan = res["max_borrowable"]
monthly = res["monthly_payment"]
c1, c2, c3 = st.columns(3)
c1.metric("최대 대출 가능액", f"{max_loan:,}원")
c2.metric("월 상환액", f"{monthly:,}원")
c3.metric("총 이자 비용", f"{max(monthly * int(term) * 12 - max_loan, 0):,}원")
st.info(f"제한 요인: **{res['binding_constraint']}**  (LTV 한도 {res['ltv_limit']}, DSR 한도 {res['dsr_limit']})")

fig = go.Figure(go.Bar(
    x=["LTV 한도", "DSR 한도"], y=[res["ltv_cap_amount"], res["dsr_cap_amount"]],
    marker_color=["#d62728" if "ltv" in res["binding_constraint"].lower() else "#1f77b4",
                  "#d62728" if "dsr" in res["binding_constraint"].lower() else "#1f77b4"],
))
fig.update_layout(title="한도별 대출 가능액 (빨강 = 제한 요인)", height=300)
st.plotly_chart(fig, use_container_width=True)

# Monthly schedule (equal payment): yearly principal vs interest.
r = rate / 100 / 12
n = int(term) * 12
bal, years_p, years_i = float(max_loan), [], []
for y in range(int(term)):
    p_sum = i_sum = 0.0
    for _ in range(12):
        i = bal * r
        p = monthly - i
        bal = max(bal - p, 0)
        p_sum += p
        i_sum += i
    years_p.append(p_sum)
    years_i.append(i_sum)
sched = go.Figure([
    go.Bar(name="원금", x=list(range(1, int(term) + 1)), y=years_p),
    go.Bar(name="이자", x=list(range(1, int(term) + 1)), y=years_i),
])
sched.update_layout(barmode="stack", title="연도별 상환 구성", xaxis_title="연차", height=350)
st.plotly_chart(sched, use_container_width=True)
