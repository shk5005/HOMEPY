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


def codes(pairs):
    return [c for c, _ in pairs]


def name_map(pairs):
    return {c: n for c, n in pairs}
