"""도깨비 Streamlit entry: `streamlit run homepy/app/main.py`."""
from __future__ import annotations

import time

import streamlit as st

from homepy.app.api_client import ApiClient, ApiError, run

TITLE = "도깨비 — 부동산 투자 의사결정 시스템"
ICON = "🔱"

NAV_SECTIONS = {
    "📊 시장 분석": [
        ("시장 대시보드", "pages/01_market_dashboard.py"),
        ("시그널 보드", "pages/02_signal_board.py"),
        ("시장 모니터링", "pages/11_market_monitoring.py"),
    ],
    "🔍 투자 분석": [
        ("단지 심층 분석", "pages/03_deep_analysis.py"),
        ("시나리오 시뮬레이션", "pages/04_scenario_sim.py"),
        ("포트폴리오", "pages/07_portfolio.py"),
    ],
    "💰 시뮬레이션": [
        ("세금 시뮬레이션", "pages/05_tax_calculator.py"),
        ("대출 시뮬레이션", "pages/06_loan_calculator.py"),
        ("정책 시뮬레이션", "pages/12_policy_simulation.py"),
    ],
    "🧠 AI 분석": [
        ("자연어 질의", "pages/13_nlp_query.py"),
        ("멀티에이전트 토론", "pages/14_multiagent.py"),
    ],
    "⚙️ 시스템": [
        ("온톨로지 그래프", "pages/08_knowledge_graph.py"),
        ("파이프라인 상태", "pages/09_pipeline_monitor.py"),
        ("개선 대시보드", "pages/10_improvement_dashboard.py"),
    ],
}

ARCHITECTURE = [
    {"layer": "Frontend", "components": [
        {"name": "Streamlit", "desc": "14페이지 대시보드 UI", "port": 8501},
        {"name": "리포트 생성기", "desc": "PDF/HTML 투자 보고서", "port": None},
    ]},
    {"layer": "AI", "components": [
        {"name": "NLP 인터페이스", "desc": "자연어 → TypeQL 변환", "port": None},
        {"name": "멀티에이전트", "desc": "Bull/Bear/행동/정책 토론", "port": None},
    ]},
    {"layer": "ML", "components": [
        {"name": "LightGBM", "desc": "가격 예측 (SHAP 설명)", "port": None},
        {"name": "피처 엔진", "desc": "관계형 5 + 시계열 5 피처", "port": None},
    ]},
    {"layer": "Service", "components": [
        {"name": "FastAPI", "desc": "REST API (22 엔드포인트)", "port": 8000},
        {"name": "WebSocket", "desc": "실시간 시그널 스트림", "port": 8000},
    ]},
    {"layer": "Storage", "components": [
        {"name": "TypeDB", "desc": "온톨로지 지식 그래프", "port": 1729},
        {"name": "TimescaleDB", "desc": "시계열 데이터 저장", "port": 5432},
        {"name": "Redis", "desc": "캐시 + Pub/Sub", "port": 6379},
    ]},
    {"layer": "Infra", "components": [
        {"name": "Helm/K8s", "desc": "오케스트레이션 (HPA)", "port": None},
        {"name": "Docker Compose", "desc": "로컬 개발 환경", "port": None},
    ]},
]

MODULES = [
    {"name": "14팩터 스코어링", "plan": "C", "tests": 30, "desc": "투자 매력도 종합 평가"},
    {"name": "편향 탐지", "plan": "C", "tests": 25, "desc": "9가지 인지 편향 검출"},
    {"name": "시나리오 시뮬레이션", "plan": "D", "tests": 18, "desc": "Bull/Base/Bear 분석"},
    {"name": "ML 예측", "plan": "G", "tests": 20, "desc": "LightGBM + SHAP 가격 예측"},
    {"name": "NLP 쿼리", "plan": "G", "tests": 22, "desc": "자연어 → TypeQL 변환"},
    {"name": "멀티에이전트 토론", "plan": "G", "tests": 12, "desc": "4-Agent 투자 토론"},
    {"name": "데이터 파이프라인", "plan": "B", "tests": 42, "desc": "9개 공공데이터 ETL"},
    {"name": "이상 탐지/모니터링", "plan": "E", "tests": 28, "desc": "Z-score 이상 탐지"},
    {"name": "정책 시뮬레이션", "plan": "F", "tests": 32, "desc": "정책 영향 분석/백테스트"},
]

API_ENDPOINTS = [
    ("GET", "/market/macro/summary", "거시경제 요약"),
    ("GET", "/market/cycle/{code}", "사이클 분석"),
    ("POST", "/analysis/score", "14팩터 스코어링"),
    ("POST", "/analysis/verdict/{id}", "최종 판정"),
    ("POST", "/simulation/scenario/{id}", "시나리오 분석"),
    ("POST", "/simulation/tax", "세금 시뮬레이션"),
    ("POST", "/simulation/loan", "대출 시뮬레이션"),
    ("POST", "/simulation/policy", "정책 영향 분석"),
    ("POST", "/simulation/policy/backtest", "정책 백테스트"),
    ("GET", "/ontology/graph/{id}", "지식 그래프"),
    ("GET", "/ontology/entity/{type}", "엔티티 조회"),
    ("POST", "/portfolio/rank", "단지 랭킹"),
    ("POST", "/nlp/query", "자연어 쿼리"),
    ("POST", "/reports/generate", "투자 보고서"),
    ("POST", "/reports/debate", "에이전트 토론"),
    ("GET", "/pipeline/status", "파이프라인 상태"),
    ("GET", "/pipeline/verification/accuracy", "데이터 정확도"),
    ("GET", "/pipeline/monitoring/anomalies", "이상 탐지"),
    ("GET", "/pipeline/monitoring/alerts", "알림 조회"),
    ("GET", "/pipeline/monitoring/early-warnings", "조기 경보"),
    ("GET", "/pipeline/ha/status", "HA 상태"),
]


def init_state() -> None:
    st.session_state.setdefault("api_base_url", "http://localhost:8000")


def sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🔱 도깨비")
        st.caption("부동산 투자 의사결정 시스템")
        st.divider()
        for section, pages in NAV_SECTIONS.items():
            st.markdown(f"**{section}**")
            for label, path in pages:
                st.page_link(path, label=label)
            st.write("")
        st.divider()
        st.text_input("API URL", key="api_base_url")


def check_api_health(client: ApiClient) -> dict:
    checks = {}
    try:
        t0 = time.monotonic()
        run(client.get_pipeline_status())
        checks["api"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except ApiError:
        checks["api"] = {"status": "error", "latency_ms": None}
    return checks


def render_kpis(health: dict) -> None:
    cols = st.columns(6)
    api_ok = health.get("api", {}).get("status") == "ok"
    latency = health.get("api", {}).get("latency_ms")

    cols[0].metric("API 상태", "정상 🟢" if api_ok else "오류 🔴")
    cols[1].metric("응답 시간", f"{latency}ms" if latency else "—")
    cols[2].metric("API 엔드포인트", f"{len(API_ENDPOINTS)}개")
    cols[3].metric("Streamlit 페이지", "14개")
    cols[4].metric("테스트 통과", f"{sum(m['tests'] for m in MODULES):,}개")
    cols[5].metric("구현 계획", "7/7 완료")


def render_architecture() -> None:
    st.subheader("시스템 아키텍처")
    layer_colors = {
        "Frontend": "#06b6d4", "AI": "#ec4899", "ML": "#f59e0b",
        "Service": "#10b981", "Storage": "#6366f1", "Infra": "#8b5cf6",
    }
    for layer_info in ARCHITECTURE:
        layer = layer_info["layer"]
        color = layer_colors.get(layer, "#888")
        cols = st.columns([0.15, 0.85])
        with cols[0]:
            st.markdown(
                f'<div style="background:{color};color:#fff;padding:6px 12px;'
                f'border-radius:6px;text-align:center;font-weight:600;'
                f'font-size:0.85rem;margin-top:4px">{layer}</div>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            comp_cols = st.columns(len(layer_info["components"]))
            for i, comp in enumerate(layer_info["components"]):
                with comp_cols[i]:
                    port_str = f" (:{comp['port']})" if comp["port"] else ""
                    st.markdown(
                        f'<div style="background:var(--secondary-background-color,#f0f2f6);'
                        f'padding:8px 12px;border-radius:6px;border-left:3px solid {color}">'
                        f'<strong>{comp["name"]}</strong>{port_str}<br>'
                        f'<span style="font-size:0.8rem;opacity:0.7">{comp["desc"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )


def render_modules() -> None:
    st.subheader("핵심 모듈")
    cols_per_row = 3
    for i in range(0, len(MODULES), cols_per_row):
        row_modules = MODULES[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for j, mod in enumerate(row_modules):
            with cols[j]:
                st.markdown(
                    f'<div style="background:var(--secondary-background-color,#f0f2f6);'
                    f'padding:12px;border-radius:8px;margin-bottom:8px">'
                    f'<strong>{mod["name"]}</strong>'
                    f' <span style="font-size:0.75rem;background:#6366f1;color:#fff;'
                    f'padding:1px 6px;border-radius:10px">Plan {mod["plan"]}</span><br>'
                    f'<span style="font-size:0.85rem;opacity:0.7">{mod["desc"]}</span><br>'
                    f'<span style="font-size:0.8rem">✅ {mod["tests"]} tests</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def render_endpoints() -> None:
    with st.expander("API 엔드포인트 (22개)", expanded=False):
        search = st.text_input("검색", placeholder="엔드포인트 검색...", key="ep_search")
        filtered = API_ENDPOINTS
        if search:
            q = search.lower()
            filtered = [(m, p, d) for m, p, d in API_ENDPOINTS
                        if q in p.lower() or q in d.lower()]
        header = st.columns([0.1, 0.45, 0.45])
        header[0].markdown("**Method**")
        header[1].markdown("**Path**")
        header[2].markdown("**설명**")
        for method, path, desc in filtered:
            cols = st.columns([0.1, 0.45, 0.45])
            badge_color = "#166534" if method == "POST" else "#1d4ed8"
            badge_bg = "#dcfce7" if method == "POST" else "#dbeafe"
            cols[0].markdown(
                f'<span style="background:{badge_bg};color:{badge_color};'
                f'padding:1px 6px;border-radius:3px;font-weight:600;'
                f'font-size:0.75rem">{method}</span>',
                unsafe_allow_html=True,
            )
            cols[1].code(f"/api/v1{path}", language=None)
            cols[2].write(desc)


def render_quick_start() -> None:
    st.subheader("빠른 시작")
    st.markdown("""
```bash
# 1. 인프라 시작
docker compose up -d

# 2. 스키마 초기화
python scripts/bootstrap_schema.py

# 3. FastAPI 서버
uvicorn homepy.api.main:app --reload --port 8000

# 4. Streamlit 앱
streamlit run homepy/app/main.py --server.port 8501
```
    """)


def main() -> None:
    st.set_page_config(page_title=TITLE, page_icon=ICON, layout="wide")
    init_state()
    sidebar()

    st.markdown(
        '<h1 style="display:flex;align-items:center;gap:12px">'
        '🔱 <span>도깨비</span></h1>',
        unsafe_allow_html=True,
    )
    st.caption("TypeDB 온톨로지 + TimescaleDB 시계열 기반 부동산 투자 의사결정 시스템")

    client = ApiClient(st.session_state["api_base_url"])
    health = check_api_health(client)

    render_kpis(health)
    st.divider()

    tab_arch, tab_modules, tab_api, tab_start = st.tabs(
        ["🏗️ 아키텍처", "🧩 핵심 모듈", "🔌 API", "🚀 빠른 시작"]
    )

    with tab_arch:
        render_architecture()

    with tab_modules:
        render_modules()

    with tab_api:
        render_endpoints()

    with tab_start:
        render_quick_start()


main()
