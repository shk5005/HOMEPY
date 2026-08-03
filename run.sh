#!/usr/bin/env bash
# 토스증권 실데이터로 삼성전자(+피어) 분석 리포트를 생성하고 브라우저로 엽니다.
# 사용: ./run.sh                (삼성전자 A005930 + NVDA)
#       ./run.sh --domestic A005930,A000660 --overseas NVDA,AAPL
#       ./run.sh --demo         (네트워크 없이 샘플 미리보기)
set -euo pipefail
cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "❌ Python 3.9+ 가 필요합니다. https://python.org 에서 설치하세요."; exit 1
fi

# --demo 는 자격증명 없이 통과
NEED_CREDS=1
for a in "$@"; do [ "$a" = "--demo" ] && NEED_CREDS=0; done

if [ "$NEED_CREDS" = "1" ] && [ ! -f .env ] && [ -z "${TOSSINVEST_CLIENT_ID:-}" ]; then
  echo "토스증권 Open API 자격증명을 입력하세요 (WTS → 설정 → Open API)."
  read -r -p "  Client Id (tsck_live_...): " TOSSINVEST_CLIENT_ID
  read -r -s -p "  Client Secret (tssk_live_...): " TOSSINVEST_CLIENT_SECRET; echo
  export TOSSINVEST_CLIENT_ID TOSSINVEST_CLIENT_SECRET
fi

if [ "$#" -gt 0 ]; then
  "$PY" main.py "$@"
  # 인자에서 --out 값 추출 (없으면 main.py 기본값 out/report.html)
  OUT="out/report.html"
  prev=""
  for a in "$@"; do [ "$prev" = "--out" ] && OUT="$a"; prev="$a"; done
else
  OUT="out/samsung.html"
  "$PY" main.py --domestic A005930 --overseas NVDA --out "$OUT"
fi

# 리포트 열기 (실패해도 무시)
if [ -f "$OUT" ]; then
  echo "📈 리포트: $OUT"
  case "$(uname 2>/dev/null)" in
    Darwin) open "$OUT" 2>/dev/null || true ;;
    Linux)  xdg-open "$OUT" 2>/dev/null || true ;;
    *)      command -v start >/dev/null 2>&1 && start "$OUT" || true ;;
  esac
fi
