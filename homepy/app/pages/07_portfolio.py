from datetime import date

import pandas as pd
import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

st.set_page_config(page_title="포트폴리오", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
st.session_state.setdefault("watchlist", [])
st.session_state.setdefault("holdings", {})
client = ApiClient(st.session_state["api_base_url"])

ALERT_SCORE = 40.0  # 총점이 이 값 미만이면 경고

st.title("포트폴리오")
tab_watch, tab_hold, tab_alert = st.tabs(["관심 단지", "보유 자산", "알림"])


def fetch_scores(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    try:
        return {s["complex_id"]: s for s in run(client.post_rank(ids))}
    except ApiError as exc:
        st.error(f"API 오류: {exc}")
        return {}


all_ids = sorted(set(st.session_state["watchlist"]) | set(st.session_state["holdings"]))
scores = fetch_scores(all_ids)

with tab_watch:
    c1, c2 = st.columns([3, 1])
    new_id = c1.text_input("단지 ID 추가", key="watch_new").strip()
    if c2.button("추가", disabled=not new_id) and new_id not in st.session_state["watchlist"]:
        st.session_state["watchlist"].append(new_id)
        st.rerun()
    if not st.session_state["watchlist"]:
        st.info("관심 단지가 없습니다.")
    for cid in list(st.session_state["watchlist"]):
        s = scores.get(cid)
        a, b, c, d = st.columns([2, 1, 1, 1])
        a.write(f"**{cid}**")
        b.metric("점수", "-" if not s else f"{s['total_score']:.1f}")
        c.metric("등급", "-" if not s else s["grade"])
        if d.button("삭제", key=f"rm_{cid}"):
            st.session_state["watchlist"].remove(cid)
            st.rerun()

with tab_hold:
    with st.form("add_holding"):
        f1, f2, f3, f4 = st.columns(4)
        hid = f1.text_input("단지 ID").strip()
        price = f2.number_input("매입가(만원)", min_value=0.0, step=1000.0)
        bought = f3.date_input("매입일", value=date.today())
        current = f4.number_input("현재 시세(만원)", min_value=0.0, step=1000.0)
        if st.form_submit_button("보유 자산 저장") and hid:
            st.session_state["holdings"][hid] = {"price": price, "date": bought, "current": current}
            st.rerun()
    rows = []
    for cid, h in st.session_state["holdings"].items():
        s = scores.get(cid)
        gain = h["current"] - h["price"]
        pct = gain / h["price"] * 100 if h["price"] else 0.0
        weak = [f["name"] for f in (s or {}).get("factors", []) if f.get("normalized", 50) < 40]
        rows.append({"단지": cid, "매입일": h["date"], "매입가": h["price"], "현재 시세": h["current"],
                     "평가손익": gain, "수익률(%)": round(pct, 2),
                     "등급": s["grade"] if s else "-", "부정 시그널": ", ".join(weak) or "-"})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        total_gain = sum(r["평가손익"] for r in rows)
        st.metric("총 평가손익(만원)", f"{total_gain:,.0f}")
    else:
        st.info("보유 자산이 없습니다.")

with tab_alert:
    alerts = [(cid, s) for cid, s in scores.items() if s["total_score"] < ALERT_SCORE]
    if not alerts:
        st.success("발생한 알림이 없습니다.")
    for cid, s in alerts:
        st.warning(f"{cid}: 총점 {s['total_score']:.1f} ({s['grade']}) — 기준 {ALERT_SCORE:.0f}점 미만")
