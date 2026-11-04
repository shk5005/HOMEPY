import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run
from homepy.app.components.signal_card import signal_card

st.set_page_config(page_title="시그널 보드", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

st.title("시그널 보드")
st.caption("단지 점수 요인(factor)을 시그널로 변환해 표시합니다.")

with st.sidebar:
    ids_text = st.text_input("단지 ID (쉼표 구분)", "C001")
    types = st.multiselect("시그널 유형", ["opportunity", "risk", "neutral"],
                           default=["opportunity", "risk", "neutral"])
    district = st.text_input("지역 필터 (부분 일치)", "")
    min_conf = st.slider("최소 신뢰도(점수)", 0, 100, 0)


def to_signals(scores: list[dict]) -> list[dict]:
    out = []
    for s in scores:
        for f in s.get("factors", []):
            n = f.get("normalized", 0)
            out.append({
                "type": "opportunity" if n >= 0.66 else "risk" if n <= 0.33 else "neutral",
                "target": f"{s['complex_id']} · {f['name']}",
                "district": s.get("district", ""),
                "score": n * 100,
                "evidence": f.get("evidence", []),
            })
    return out


ids = [i.strip() for i in ids_text.split(",") if i.strip()]
signals: list[dict] = []
if ids:
    try:
        signals = to_signals(run(client.post_score(ids)))
    except ApiError as exc:
        st.error(f"API 연결 실패: {exc}")

signals = [s for s in signals if s["type"] in types and s["score"] >= min_conf
           and district.lower() in s["district"].lower()]
if not signals:
    st.info("조건에 맞는 시그널이 없습니다.")
for row in range(0, len(signals), 3):
    cols = st.columns(3)
    for col, sig in zip(cols, signals[row:row + 3]):
        with col:
            signal_card(sig)
