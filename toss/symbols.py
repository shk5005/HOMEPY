"""기본 관심종목 (국내 KRX / 국외 US).

토스 Open API 종목코드 형식
  · 국내: 'A' + 6자리 종목코드   예) 삼성전자 A005930
  · 미국: 티커 심볼 또는 'US...' 형태  예) NVDA, AAPL
필요에 맞게 수정하거나 CLI 인자로 덮어쓰세요.
"""

DOMESTIC = [
    ("A005930", "삼성전자"),
    ("A000660", "SK하이닉스"),
    ("A373220", "LG에너지솔루션"),
    ("A005380", "현대차"),
    ("A035420", "NAVER"),
    ("A035720", "카카오"),
    ("A005490", "POSCO홀딩스"),
    ("A068270", "셀트리온"),
]

OVERSEAS = [
    ("NVDA", "NVIDIA"),
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("TSLA", "Tesla"),
    ("AMZN", "Amazon"),
    ("GOOGL", "Alphabet"),
    ("META", "Meta"),
    ("AVGO", "Broadcom"),
]


# 섹터 분류(기본 관심종목 기준). live 모드에서는 기업정보 API 의 업종이 있으면
# 그것을 우선 사용하고, 없으면 이 표로 보완, 그래도 없으면 "기타".
SECTORS = {
    # 국내
    "A005930": "반도체", "A000660": "반도체",
    "A373220": "2차전지", "A005490": "소재·철강",
    "A005380": "자동차", "A068270": "바이오",
    "A035420": "인터넷·플랫폼", "A035720": "인터넷·플랫폼",
    # 국외
    "NVDA": "반도체", "AVGO": "반도체",
    "AAPL": "하드웨어", "MSFT": "소프트웨어",
    "GOOGL": "인터넷·플랫폼", "META": "인터넷·플랫폼",
    "AMZN": "이커머스·클라우드", "TSLA": "자동차",
}


def sector_of(code: str) -> str:
    return SECTORS.get(code, "기타")


def codes(pairs):
    return [c for c, _ in pairs]


def name_map(pairs):
    return {c: n for c, n in pairs}
