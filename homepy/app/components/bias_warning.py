import streamlit as st

SEVERITY_LABEL = {"high": "높음", "medium": "중간", "low": "낮음"}


def bias_warning(warnings: list[dict]) -> None:
    """Colored alert per bias: error for high, warning for medium, info otherwise."""
    if not warnings:
        st.success("감지된 편향이 없습니다.")
        return
    for w in warnings:
        sev = str(w.get("severity", "low")).lower()
        body = (f"**{w.get('bias_type', '-')}** [{SEVERITY_LABEL.get(sev, sev)}]\n\n"
                f"{w.get('description', '')}\n\n"
                f"- 근거: {w.get('evidence', '-')}\n"
                f"- 완화 방안: {w.get('mitigation', '-')}")
        if sev == "high":
            st.error(body)
        elif sev == "medium":
            st.warning(body)
        else:
            st.info(body)
