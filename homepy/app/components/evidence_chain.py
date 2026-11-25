import streamlit as st


def _render(node, depth: int = 0) -> None:
    if isinstance(node, str):
        st.markdown(f"- {node}")
        return
    claim = node.get("claim", "-")
    source = node.get("source")
    ts = node.get("timestamp")
    children = node.get("children") or []
    meta = " · ".join(str(x) for x in (source, ts) if x)
    if not children:
        st.markdown(f"- {claim}" + (f"  \n  <small>{meta}</small>" if meta else ""),
                    unsafe_allow_html=True)
        if node.get("url"):
            st.markdown(f"  [원본 데이터]({node['url']})")
        return
    with st.expander(claim + (f"  ({meta})" if meta else ""), expanded=depth == 0):
        for child in children:
            _render(child, depth + 1)


def evidence_chain(chain: list) -> None:
    """Render an evidence chain: plain strings or nested {claim, source, timestamp, children, url}."""
    if not chain:
        st.info("근거 체인이 없습니다.")
        return
    for node in chain:
        _render(node)
