from __future__ import annotations

import streamlit as st


def ha_status_panel(statuses: list[dict]) -> None:
    if not statuses:
        st.info("HA 상태 데이터 없음")
        return
    cols = st.columns(len(statuses))
    for col, s in zip(cols, statuses):
        healthy = bool(s.get("healthy"))
        icon = "✅" if healthy else "❌"
        col.metric(str(s.get("component", "?")), f"{icon} {'정상' if healthy else '이상'}")
        if s.get("role"):
            col.caption(f"역할: {s['role']}")
        lag = s.get("replica_lag_seconds")
        if lag is not None:
            col.caption(f"복제 지연: {lag}초")
