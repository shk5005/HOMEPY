"""HOMEPY Streamlit entry: `streamlit run homepy/app/main.py`."""
import streamlit as st

TITLE = "HOMEPY — 부동산 투자 의사결정 시스템"

# (label, page path or None when not built yet)
NAV = [
    ("시장 대시보드", "pages/01_market_dashboard.py"),
    ("시그널 보드", "pages/02_signal_board.py"),
    ("단지 분석", "pages/03_deep_analysis.py"),
    ("투자 판단", None),
    ("시나리오 시뮬레이션", "pages/04_scenario_sim.py"),
    ("세금 시뮬레이션", "pages/05_tax_calculator.py"),
    ("대출 시뮬레이션", "pages/06_loan_calculator.py"),
    ("온톨로지 그래프", None),
    ("파이프라인 상태", None),
]


def init_state() -> None:
    st.session_state.setdefault("api_base_url", "http://localhost:8000")


def sidebar() -> None:
    with st.sidebar:
        st.header("HOMEPY")
        for label, path in NAV:
            if path:
                st.page_link(path, label=label)
            else:
                st.caption(f"{label} (준비 중)")
        st.divider()
        st.text_input("API URL", key="api_base_url")


def main() -> None:
    st.set_page_config(page_title=TITLE, page_icon="🏠", layout="wide")
    init_state()
    sidebar()
    st.title(TITLE)
    st.write("왼쪽 메뉴에서 페이지를 선택하세요. 시장 대시보드와 시그널 보드를 사용할 수 있습니다.")


main()
