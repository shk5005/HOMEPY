import streamlit as st

ICONS = {"opportunity": "🟢", "risk": "🔴", "neutral": "⚪", "policy": "📜", "macro": "📈"}


def signal_card(signal: dict, *, key: str | None = None) -> None:
    """Render a signal: icon, target, score, evidence bullets (full chain in expander)."""
    icon = ICONS.get(str(signal.get("type", "neutral")), "⚪")
    evidence = signal.get("evidence") or []
    with st.container(border=True):
        left, right = st.columns([4, 1])
        left.markdown(f"**{icon} {signal.get('target', '-')}**  \n"
                      f"<small>{signal.get('type', '')} · {signal.get('district', '')}</small>",
                      unsafe_allow_html=True)
        right.metric("Score", f"{signal.get('score', 0):.1f}")
        for line in evidence[:3]:
            st.markdown(f"- {line}")
        if len(evidence) > 3:
            with st.expander(f"전체 근거 ({len(evidence)})"):
                for line in evidence:
                    st.markdown(f"- {line}")
