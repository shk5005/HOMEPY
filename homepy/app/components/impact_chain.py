"""Impact chain visualization: policy -> direct effects -> indirect effects -> score.

Pure HTML/CSS (no Pyvis/networkx dependency). `build_impact_chain_html` is a
pure function so it is testable without Streamlit; `impact_chain` renders it.
"""
from __future__ import annotations

from html import escape

COLORS = {"policy": "#d62728", "direct": "#ff7f0e", "indirect": "#e6c619",
          "score_up": "#2ca02c", "score_down": "#d62728"}


def _node(label: str, color: str, sub: str = "") -> str:
    dark = color == COLORS["indirect"]
    fg = "#222" if dark else "#fff"
    sub_html = f'<div style="font-size:11px;opacity:.85">{escape(sub)}</div>' if sub else ""
    return (f'<div class="node" style="background:{color};color:{fg}">'
            f'<b>{escape(label)}</b>{sub_html}</div>')


def _edge(magnitude) -> str:
    return f'<div class="edge">&#8595; {escape(str(magnitude))}</div>'


def build_impact_chain_html(chain: list[dict], *, policy_label: str = "정책 변경",
                            delta: float | None = None) -> str:
    """Render the chain as a vertical flow of colored nodes with magnitude-labeled edges."""
    parts = [_node(policy_label, COLORS["policy"])]
    for i, step in enumerate(sorted(chain, key=lambda s: s.get("order", 0))):
        order = int(step.get("order", i + 1))
        color = COLORS["direct"] if order <= 1 else COLORS["indirect"]
        kind = "직접 효과" if order <= 1 else f"{order}차 효과"
        parts.append(_edge(step.get("magnitude", "")))
        parts.append(_node(str(step.get("effect", "-")), color, kind))
    if delta is not None:
        parts.append(_edge(f"{delta:+.2f}"))
        parts.append(_node(f"점수 변화 {delta:+.2f}",
                           COLORS["score_up"] if delta >= 0 else COLORS["score_down"]))
    style = ("<style>.chain{display:flex;flex-direction:column;align-items:center;"
             "font-family:sans-serif}.node{padding:8px 16px;border-radius:8px;"
             "min-width:260px;text-align:center}.edge{color:#666;font-size:12px;"
             "padding:2px}</style>")
    return f'{style}<div class="chain">{"".join(parts)}</div>'


def impact_chain_text(chain: list[dict]) -> str:
    """Plain-text fallback."""
    return "\n".join(f"{s.get('order', i + 1)}. {s.get('effect', '-')} ({s.get('magnitude', '')})"
                     for i, s in enumerate(chain))


def impact_chain(chain: list[dict], *, policy_label: str = "정책 변경",
                 delta: float | None = None, height: int = 420) -> None:
    import streamlit as st

    if not chain:
        st.info("영향 체인 데이터가 없습니다.")
        return
    try:
        import streamlit.components.v1 as components
        components.html(build_impact_chain_html(chain, policy_label=policy_label, delta=delta),
                        height=height, scrolling=True)
    except Exception:  # noqa: BLE001 - fall back to text
        st.text(impact_chain_text(chain))
