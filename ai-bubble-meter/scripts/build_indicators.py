import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data"
def lin(raw, normal, extreme):
    s = (raw-normal)/(extreme-normal)*100
    return round(max(0, min(100, s)))
I = []
def add(id, layer, layer_w, name, metric, raw, unit, normal, extreme, conf, src, url, asof, note, score=None, rule=None):
    sc = score if score is not None else lin(raw, normal, extreme)
    I.append(dict(id=id, layer=layer, name=name, metric=metric, raw=raw, unit=unit,
        normal=normal, extreme=extreme, score=sc, layer_weight=layer_w,
        rule=rule or f"선형 환산: (값-정상 {normal})/(극단 {extreme}-정상)×100, 0~100 절단",
        confidence=conf, source=src, url=url, as_of=asof, note=note))
L1="1 최종수요·수익화"; L2="2 주문·가수요"; L3="3 상류 가격"; L4="4 한국 말단 증폭"; L5="5 밸류에이션·집중"; L6="6 심리·포지셔닝"; L7="7 레버리지·신용"
add("capex_rev", L1, 20, "AI 투자 대비 매출 괴리", "2026 하이퍼스케일러 capex ≈ $800B ÷ 추세 초과 클라우드 매출 ≈ $70B", 11.4, "배", 3, 15, "Low",
    "Goldman 종합(2차 인용)", "https://mashop.app/blog/ai-bubble-five-indicators", "2026-10",
    "정상 3배·극단 15배는 분석자 가정. Sequoia는 2026 AI 인프라 $1.5T에 매출 $3T 필요로 추정")
add("double_order", L2, 15, "중복·무한정 주문 증거", "Unimicron: 경쟁 패키징 방식에 병렬 중복주문 / 메모리 'open-ended orders'", 70, "정성점", 0, 100, "Low",
    "404K SEMI-AI Brief (2026-10-22)", "https://404kresearch.substack.com/p/404k-semi-ai-evening-brief-october-a15", "2026-10-22",
    "공급사 1곳의 발언. 가수요 규모를 정량화한 자료는 없음", score=70, rule="정성 평가: 직접 증거 1건 + 정황 다수 = 70")
add("lead_time", L2, 15, "GPU 조달 리드타임", "평균 36~52주 (중앙값 44주)", 44, "주", 12, 52, "Low",
    "CBRE IM(벤더 블로그 인용)", "https://vexxhost.com/blog/gpu-capacity-crisis-ai-infrastructure-2026/", "2026",
    "리드타임이 길수록 쇼티지 게이밍(부풀린 주문) 유인 증가. 정상 12주는 분석자 가정")
add("dram_decel", L3, 15, "DRAM 계약가 상승률 둔화", "QoQ 1Q ~93% → 2Q ~80% → 3Q ~40% → 4Q ~20%(전망)", 20, "% QoQ", 0, 100, "Medium",
    "TrendForce(The Elec·StockHub 인용)", "https://www.stockhub.kr/en/news/news_b7244c205001", "2026-10-20",
    "가격 수준은 여전히 상승(쇼티지)이나 3분기 연속 감속 + LTA 가격상한 적용. 채찍효과 후기 전형", score=75,
    rule="정성 평가: 상승 지속(+)·2계 미분 3분기 음(−) = 사이클 후반 75")
add("kr_export", L4, 10, "한국 반도체 수출 증가율", "10월 1~20일 반도체 수출 $275억, 전년비", 222.5, "% YoY", 10, 250, "High",
    "관세청 잠정치 (2026-10-21)", "https://www.kita.net/board/totalTradeNews/totalTradeNewsDetail.do?no=105481&siteId=1", "2026-10-20",
    "조업일수 13일 vs 10.5일 효과 포함. 가격 효과가 물량보다 큼. 정상·극단은 분석자 가정")
add("kr_share", L4, 10, "수출 중 반도체 비중", "10월 1~20일 반도체 비중", 44.7, "%", 20, 50, "High",
    "관세청 잠정치 (2026-10-21)", "https://www.kita.net/board/totalTradeNews/totalTradeNewsDetail.do?no=105481&siteId=1", "2026-10-20",
    "채찍 끝단(상류) 집중도. 정상 20%는 2010년대 수준 가정")
add("cape", L5, 15, "S&P500 Shiller CAPE", "CAPE (1881년 이후 99퍼센타일)", 40.72, "배", 17, 44.2, "Medium",
    "AI Bubble Tracker", "https://brutus-gr.github.io/ai-bubble-tracker/", "2026-10-19",
    "극단 44.2 = 1999년 12월 닷컴 정점. 정상 17은 장기 중앙값 근사")
add("top5", L5, 15, "S&P500 상위 5종목 비중", "상위 5개 기업 시총 비중", 30, "%", 15, 30, "Medium",
    "The Next Web 외", "https://thenextweb.com/news/ai-stocks-dot-com-bubble-comparison-market-outlook", "2026",
    "'반세기 최고' = 정의상 상한. 정상 15%는 분석자 가정")
add("nvda_pe", L5, 15, "엔비디아 선행 PER (반대지표)", "12개월 선행 PER 약 17~20배 (중앙 18.5)", 18.5, "배", 10, 60, "Low",
    "Motley Fool·Stocktwits(2026 중반)", "https://www.fool.com/investing/2026/07/11/nvidias-forward-pe-has-actually-fallen-as-its-stoc/", "2026-07",
    "이익이 주가보다 빨리 증가 = 버블 반대 증거. 10월 수치 미확인")
add("bofa_tech", L6, 10, "펀드매니저 기술주 순비중", "BofA FMS 기술주 순 오버웨이트 (2020.8 이후 최대)", 37, "% 순", 5, 45, "Medium",
    "BofA FMS 2026-10 (2차 인용)", "https://cryptobriefing.com/bofa-survey-fund-managers-overweight-tech/", "2026-10-08",
    "반도체 롱 = 가장 붐비는 거래(most crowded trade)")
add("bofa_cash", L6, 10, "펀드매니저 현금 비중 (역)", "BofA FMS 현금 비중 (4.0% 미만 = 매도 신호)", 3.9, "%", 4.8, 3.5, "Medium",
    "BofA FMS 2026-10 (2차 인용)", "https://cryptobriefing.com/bofa-survey-fund-managers-overweight-tech/", "2026-10-08",
    "현금이 낮을수록 점수 높음")
add("bubble_aware", L6, 10, "버블 인식 확산 (역발상)", "'2027년 AI 버블 온다' 45% vs 반대 42%", 45, "%", 0, 100, "Medium",
    "BofA FMS 2026-10 (2차 인용)", "https://cryptobriefing.com/bofa-survey-fund-managers-overweight-tech/", "2026-10-08",
    "행동경제학: 다수가 버블을 의심하는 동안은 최종 도취 국면이 아님. 버블 점수를 낮추는 방향", score=40,
    rule="정성 평가: 의견 양분 = 도취 미완 40")
add("margin", L7, 15, "미국 신용융자(마진) 잔고", "6월 $1.50T 사상 최대 → 7월 −$84.8B 사상 최대 감소", 65, "정성점", 0, 100, "Medium",
    "FINRA(First Trust·차트 인용)", "https://www.ftportfolios.com/Commentary/EconomicResearch/2026/10/15/margin-debt-continues-to-climb", "2026-08",
    "명목 기록이나 시총 대비는 역사적 범위(First Trust). 한국 삼성·하이닉스 신용잔고는 증권사 한도 축소로 감소 중", score=65,
    rule="정성 평가: 명목 최고·비율 정상 = 65")
add("debt_capex", L7, 15, "capex 중 부채조달 비중", "하이퍼스케일러 증분부채/capex: FY24 9% → 2026 중반 32%", 32, "%", 10, 50, "Medium",
    "Pinetree Macro 외", "https://pinetreemacroresearch.substack.com/p/the-ai-capex-bubble-bigger-than-you", "2026 중반",
    "현금흐름 투자 → 부채 투자 전환. 닷컴 통신망 과잉투자의 경로")
add("orcl_cds", L7, 15, "오라클 5년 CDS", "AI 인프라 부채 대표 신용 스프레드", 295, "bp", 60, 400, "Low",
    "AI Bubble Tracker", "https://brutus-gr.github.io/ai-bubble-tracker/", "2026-10-19",
    "단일 트래커 수치. 정상 60bp는 분석자 가정. 신규 AI 회사채 발행 프리미엄 12bp(2025년 2bp)")
json.dump({"rows": I}, open(OUT / "indicators.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

dram = [dict(quarter="1Q26", low=90, high=95, kind="실적 추정", source="TrendForce via The Elec"),
        dict(quarter="2Q26", low=80, high=80, kind="실적 추정", source="TrendForce via StockHub (사전 전망 58~63%)"),
        dict(quarter="3Q26", low=40, high=40, kind="실적 추정", source="TrendForce via StockHub"),
        dict(quarter="4Q26", low=15, high=20, kind="전망", source="TrendForce 9/30 (HBM 포함 15~20%), 10/20 보도 ~20%")]
json.dump({"rows": dram}, open(OUT / "dram.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
chain = [dict(stage="GDP (최종 경제)", pct=2, order=1), dict(stage="PC 수요", pct=5, order=2),
         dict(stage="반도체 수요", pct=20, order=3), dict(stage="반도체 장비 수요", pct=50, order=4)]
json.dump({"rows": chain}, open(OUT / "chain.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
kospi = [dict(date="2026-10-14", close=6008.81), dict(date="2026-10-19", close=5695.97), dict(date="2026-10-23", close=5550.30)]
json.dump({"rows": kospi}, open(OUT / "kospi.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# preview composite
from collections import defaultdict
g=defaultdict(list)
for r in I: g[r["layer"]].append(r)
tot=0; wsum=0
for k,v in sorted(g.items()):
    m=sum(x["score"] for x in v)/len(v); w=v[0]["layer_weight"]; tot+=m*w; wsum+=w
    print(k, round(m,1), w, [(x["id"],x["score"]) for x in v])
print("composite", round(tot/wsum,1))
