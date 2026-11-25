# HOMEPY

아파트 실거래가 이상거래 탐지. 국토부 아파트 매매 실거래 데이터를 수집해 거래별 이상거래 플래그와
단지·면적 그룹별 기준 시세를 CSV로 낸다.

문서 흐름: [`intent/`](intent/) → [`spec/`](spec/) → [`plan/`](plan/) → 코드

> ⚠️ API 엔드포인트와 코드값(`cdealType`, `dealingGbn`, `slerGbn`/`buyerGbn`)은 아직 **미검증**이다.
> plan Task 0에서 확인하기 전에는 실데이터 결과를 신뢰하지 않는다.

## 설치

```bash
pip install -e ".[dev]"
pytest
```

## 서비스 키

data.go.kr에서 「국토교통부_아파트 매매 실거래가 상세 자료」 활용 신청 후 **Decoding 키**를 설정한다.
키는 커밋하지 않는다.

```bash
export DATA_GO_KR_SERVICE_KEY="..."
```

## 실행

```bash
python -m homepy run --lawd 11680 --from 2026-01 --to 2026-09
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--lawd` | (필수) | 시군구 코드 5자리 |
| `--from`, `--to` | (필수) | 출력할 계약월 범위 `YYYY-MM` |
| `--config` | `config/anomaly.toml` | 임계값·코드값 설정 |
| `--raw` | `data/raw` | 원본 스냅샷 폴더 |
| `--out` | `out/<lawd>` | 출력 폴더 |
| `--offline` | | 수집하지 않고 저장된 스냅샷만 사용 (재현 실행용) |

- 비교 창을 채우려고 `--from`보다 `window_months`개월 앞에서부터 받는다.
- 신고가 끝난 달(미확정 기간 밖)은 이미 받았으면 다시 호출하지 않는다.
- 받은 건수가 `totalCount`와 다르면 실패한다 (종료 코드 1).

## 출력

| 파일 | 내용 |
|---|---|
| `trades.csv` | 거래별 플래그·사유·비교 중위가·괴리율 |
| `groups.csv` | 단지·면적·월별 기준 시세, 정상/전체 건수, 플래그별 건수 |
| `run.json` | 설정값, 사용한 스냅샷 수집일, `as_of`, 실행 시각 |

플래그: F1 해제 · F2 직거래 · F3 통계적 이상치 · F4 판정 보류 · F5 법인 관련 · F6 미확정 기간.
플래그는 통계적·형식적으로 특이한 거래라는 뜻일 뿐, 불법 여부 판단이 아니다.
같은 스냅샷과 같은 설정이면 `trades.csv`, `groups.csv`는 바이트 단위로 같다.
