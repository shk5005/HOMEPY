"""Page 11: Market Monitoring Dashboard (anomalies, alerts, early warnings, HA)."""
from __future__ import annotations

import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run
from homepy.app.components.alert_timeline import LEVELS, alert_timeline
from homepy.app.components.anomaly_heatmap import anomaly_heatmap
from homepy.app.components.ha_status_panel import ha_status_panel

st.set_page_config(page_title="시장 모니터링", layout="wide")
st.session_state.setdefault("api_base_url", "http://localhost:8000")
client = ApiClient(st.session_state["api_base_url"])

st.title("시장 모니터링 대시보드")


def _fetch(coro, label):
    try:
        return run(coro)
    except ApiError as exc:
        st.warning(f"{label}: API 오류 ({exc})")
        return None


# 1. Anomaly heatmap
st.header("1. 이상 탐지 히트맵")
days = st.slider("조회 기간(일)", min_value=1, max_value=90, value=7)
anomalies = _fetch(client.get_monitoring_anomalies(days), "이상 탐지") or []
left, right = st.columns([3, 1])
left.plotly_chart(anomaly_heatmap(anomalies), use_container_width=True)
right.metric("탐지 건수", len(anomalies))
with st.expander("이상 탐지 상세"):
    st.dataframe(anomalies, use_container_width=True)

# 2. Alert timeline
st.header("2. 알림 타임라인")
levels = st.multiselect("알림 등급", LEVELS, default=LEVELS)
alerts = _fetch(client.get_monitoring_alerts(days), "알림") or []
alerts = [a for a in alerts if a.get("level") in levels]
st.plotly_chart(alert_timeline(alerts), use_container_width=True)
with st.expander("알림 상세"):
    st.dataframe(alerts, use_container_width=True)

# 3. Early warning signals
st.header("3. 조기경보 신호")
signals = _fetch(client.get_early_warnings(), "조기경보") or []
if signals:
    for sig in signals:
        with st.expander(str(sig.get("signal_type", sig.get("name", "신호")))):
            st.json(sig)
else:
    st.info("활성 조기경보 신호가 없습니다 (TypeDB 연결 필요).")

# 4. HA system status
st.header("4. HA 시스템 상태")
ha_status_panel(_fetch(client.get_ha_status(), "HA 상태") or [])
