import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data"
tl = [
 # AI lane (anchor: ChatGPT)
 ("ai","2022-11-30","ChatGPT 공개 (사이클 기점)","기점","공개 기록","High"),
 ("ai","2023-05-24","엔비디아 매출 가이던스 쇼크, AI 반도체 랠리 본격화","Awareness","공개 기록","High"),
 ("ai","2025-01-21","스타게이트 데이터센터 투자 발표","Mania","공개 기록","High"),
 ("ai","2025-01-27","DeepSeek 쇼크, 엔비디아 하루 −17% (1차 매도)","1차 매도","공개 기록","High"),
 ("ai","2026-01-08","삼성전자·SK하이닉스 신용잔고 역대 최대","Mania","파이낸셜뉴스","Medium"),
 ("ai","2026-02-19","DRAM 가격 3개월 새 4배, 1Q 계약가 QoQ +90~95%","Mania","TrendForce·글로벌이코노믹","Medium"),
 ("ai","2026-03-31","Shiller CAPE 39.8, 닷컴 이후 최고","Mania","The Next Web","Medium"),
 ("ai","2026-06-30","미국 신용융자 $1.50T 사상 최대","Mania","FINRA 인용","Medium"),
 ("ai","2026-07-31","신용융자 월간 −$84.8B, 1997년 이후 최대 감소","경고","FINRA 차트 인용","Medium"),
 ("ai","2026-10-08","BofA: 기술주 순비중 37%, 현금 3.9% 매도 신호","Mania","BofA FMS 인용","Medium"),
 ("ai","2026-10-08","황승진 교수 채찍효과 영상 공개","참고","YouTube","High"),
 ("ai","2026-10-14","KOSPI 6,008.81","Mania","Investing.com","Medium"),
 ("ai","2026-10-21","10월 1~20일 반도체 수출 +222.5% 발표","Mania","관세청","High"),
 ("ai","2026-10-24","현재 (분석 시점)","현재","분석","High"),
 ("ai","2026-10-28","하이퍼스케일러 실적·capex 가이던스 (예정)","예정","일정 보도","Medium"),
 # dot-com lane (anchor: Netscape IPO)
 ("dot","1995-08-09","넷스케이프 IPO (사이클 기점)","기점","공개 기록","High"),
 ("dot","1996-12-05","그린스펀 '비이성적 과열' 경고","Awareness","공개 기록","High"),
 ("dot","1998-09-23","LTCM 구제, 연준 금리 인하 (1차 매도 후 재상승)","1차 매도","공개 기록","High"),
 ("dot","1999-12-31","Shiller CAPE 44.2 사상 최고","Mania","Shiller 데이터","High"),
 ("dot","2000-03-10","나스닥 정점 5,048.62","정점","공개 기록","High"),
 ("dot","2002-10-09","나스닥 바닥 1,114.11 (정점 대비 −78%)","절망","공개 기록","High"),
]
rows=[dict(id=f"{l}{i:02d}",lane=("AI 사이클" if l=="ai" else "닷컴 사이클"),date=d,event=e,stage=s,source=src,confidence=c) for i,(l,d,e,s,src,c) in enumerate(tl)]
json.dump({"rows":rows},open(OUT / "timeline.json", "w", encoding="utf-8"),ensure_ascii=False,indent=1)

pts=[(0,5,""),(8,9,""),(14,14,""),(18,11,"베어 트랩"),(22,15,""),(28,25,""),(32,30,""),(35,24,"1차 매도"),(38,26,""),
 (42,35,"대중 인지"),(46,48,""),(50,62,"열광"),(54,78,""),(57,92,"탐욕·망상"),(60,100,"정점"),(62,82,""),(64,87,"불 트랩"),
 (67,70,""),(70,55,"공포"),(73,44,""),(76,31,""),(79,21,"투매"),(82,17,""),(86,22,"절망"),(90,20,""),(95,24,""),(100,28,"평균 회귀")]
curve=[dict(x=x,y=y,label=l) for x,y,l in pts]
json.dump({"rows":curve},open(OUT / "cycle_curve.json", "w", encoding="utf-8"),ensure_ascii=False,indent=1)

ph=[dict(order=1,phase="바닥·회복",rule="가격 하락이 멈추고 재고 소진"),
    dict(order=2,phase="확장",rule="가격 상승, 상승률 가속"),
    dict(order=3,phase="후기 확장",rule="가격 상승 지속, 상승률 감속"),
    dict(order=4,phase="조정",rule="가격 하락 전환, 주문 취소·재고 증가"),
    dict(order=5,phase="침체",rule="가격 하락 가속, 감산")]
json.dump({"rows":ph},open(OUT / "mem_phases.json", "w", encoding="utf-8"),ensure_ascii=False,indent=1)
