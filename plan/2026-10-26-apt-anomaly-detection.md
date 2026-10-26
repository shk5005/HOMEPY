# 아파트 실거래가 이상거래 탐지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Author:** shk5005
- **Status:** Draft <!-- Draft | Approved -->
- **Date:** 2026-10-26

**Goal:** 시군구·월 단위 국토부 아파트 매매 실거래 데이터를 수집해 거래별 이상거래 플래그(F1–F6)와 단지·면적 그룹별 기준 시세를 CSV로 출력하는 CLI를 만든다.

**Architecture:** 수집(원본 XML 스냅샷 보관) → 파싱 → 정제(Trade) → 플래그 → 기준 시세 → 리포트의 단방향 파이프라인이다. 수집을 뺀 모든 단계는 순수 함수이고, 입력은 스냅샷과 설정 파일뿐이다. 그래서 같은 입력이면 같은 CSV가 나온다. HTTP 호출은 함수로 주입하므로 테스트에서 네트워크를 쓰지 않는다.

**Tech Stack:** Python ≥ 3.11 (`tomllib`, `statistics`, `xml.etree`, `csv`, `decimal`), `requests`(수집만), `pytest`. pandas와 openpyxl은 쓰지 않는다. 계산은 그룹별 중위수뿐이고, 의존성이 적을수록 재현성을 지키기 쉽다.

**Spec:** [`spec/2026-10-26-apt-anomaly-detection.md`](../spec/2026-10-26-apt-anomaly-detection.md) · **Intent:** [`intent/2026-10-26-apt-anomaly-detection.md`](../intent/2026-10-26-apt-anomaly-detection.md)

> ⚠️ intent와 spec 모두 **Draft** 상태에서 작성한 계획이다. spec §6 설정값이 바뀌면 `config/anomaly.toml`만 고치면 된다. 코드 구조는 바뀌지 않는다.
> 코드값(`cdealType`, `dealingGbn`, `slerGbn`/`buyerGbn`)은 **미검증**이다. Task 0을 마치기 전에는 실제 데이터 결과를 신뢰하지 않는다.

## Global Constraints

- 가격은 항상 만원 단위 정수다. 원천 `dealAmount`의 원값을 쓰고, 화면 표시용 가공 값("8억 2천만원" 등)은 쓰지 않는다 (spec §3.2).
- 면적 구간 = 전용면적을 1㎡ 단위로 **반올림(half-up)** 한 값이다. Python `round()`(은행가 반올림)는 쓰지 않는다 (spec §2).
- 그룹 키 = `aptSeq` + 면적 구간. `aptSeq`가 비어 있으면 (`umdNm`, `jibun`, `aptNm`)으로 대체하고 `key_fallback=True`로 표시한다 (FR-2).
- 수집 시 `totalCount`와 수신 건수가 다르면 실패 처리한다 (FR-1).
- 결과물 문자열에 `불법`, `허위`, `작전`을 쓰지 않는다. F3 사유는 "통계적 이상치"로 시작한다 (spec §7).
- 무작위 요소를 쓰지 않는다. 모든 출력 행은 정렬 키를 고정해 같은 순서로 쓴다 (spec §7).
- 설정 기본값은 spec §6과 같다: `window_months=6`, `min_count=3`, `mad_k=3.0`, `flat_pct=0.15`, `exclude_direct=true`, `unsettled_months=2`.
- 서비스 키는 환경변수 `DATA_GO_KR_SERVICE_KEY`에서 읽고 커밋하지 않는다. `data/`와 `out/`은 git에서 제외한다.

## Review Focus

1. **API가 HTTP 200으로 오류를 돌려주는 경우** (잘못된 키, 호출 한도 초과 → `resultCode` ≠ 정상, 또는 `OpenAPI_ServiceResponse` XML). 0건으로 처리하지 말고 `ApiError`를 올려야 한다. → Task 2
2. **해당 월 거래가 0건이거나 1건인 응답** (`<items/>`가 비어 있거나 `<item>`이 하나뿐). 0건은 정상적으로 빈 결과로, 1건은 1건으로 처리한다. → Task 2
3. **`dealAmount`에 공백과 쉼표가 섞인 값** (`"  82,500"`) → 82500. → Task 4
4. **면적이 정확히 .5㎡인 거래** (84.5 → 85, 83.5 → 84). → Task 4
5. **월말 날짜 계산** (2026-08-31에서 6개월 전 → 2026-02-28, 2024-08-31에서 6개월 전 → 2024-02-29). 비교 창이 하루라도 밀리면 판정이 바뀐다. → Task 5

추가로 `dealingGbn`이 빈 값인 과거 데이터는 "직거래"가 아니라 "미상"으로 처리한다. 그 결과 F2가 붙지 않는다. → Task 4

---

## File Structure

```
pyproject.toml                 # 패키지·의존성·pytest 설정
.gitignore                     # data/, out/, __pycache__/
config/anomaly.toml            # spec §6 설정값 + 코드값 매핑 (버전 표기)
docs/data-fields.md            # Task 0 결과: 필드·코드값 검증 기록
homepy/__init__.py
homepy/__main__.py             # python -m homepy → cli.main()
homepy/config.py               # Settings, load_settings
homepy/parse.py                # XML 페이지 → Page, ApiError
homepy/collect.py              # 페이지 수집, 스냅샷 저장/로드, 재수집 규칙
homepy/trades.py               # Trade, normalize (정제·중복 제거)
homepy/dates.py                # months_before, month_end, month_range
homepy/flags.py                # Flag, FlaggedTrade, assign_flags
homepy/baseline.py             # GroupMonth, compute_baselines
homepy/report.py               # CSV/JSON 출력
homepy/cli.py                  # run 명령
tests/fixtures/*.xml           # 손으로 만든 소형 응답
tests/test_*.py                # 모듈별 테스트
```

---

### Task 0: 필드·코드값 검증 (수작업, 사람이 수행)

코드 Task 1–7과는 병렬로 진행할 수 있다. **Task 8 전에 반드시 끝내야 한다.**

- [ ] **Step 1:** data.go.kr에서 「국토교통부_아파트 매매 실거래가 상세 자료」(15126468) 활용 신청을 하고, **Decoding 키**를 `DATA_GO_KR_SERVICE_KEY`에 설정한다. `requests`가 URL 인코딩을 다시 하므로 Encoding 키를 쓰면 키 오류가 난다.
- [ ] **Step 2:** 기술문서를 내려받아 엔드포인트, `numOfRows` 최대값, 정상 `resultCode`, 그리고 `cdealType`·`dealingGbn`·`slerGbn`·`buyerGbn`의 코드값을 확인한다.
- [ ] **Step 3:** 강남구 11680 2026-09를 한 번 호출해 원본 XML에서 위 필드의 실제 값을 확인한다.
- [ ] **Step 4:** 결과를 `docs/data-fields.md`에 기록한다(필드, 의미, 코드값, 출처, 확인일). 기본값과 다르면 `config/anomaly.toml`의 `[codes]`와 `[api]`를 고치고 `version`을 올린다.
- [ ] **Step 5:** 커밋한다: `git commit -m "docs: record verified MOLIT trade API field codes"`

### Task 1: 프로젝트 골격과 설정

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `config/anomaly.toml`, `homepy/__init__.py`, `homepy/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Settings:
      version: str
      window_months: int = 6
      min_count: int = 3
      mad_k: float = 3.0
      flat_pct: float = 0.15
      exclude_direct: bool = True
      unsettled_months: int = 2
      cancelled_codes: tuple[str, ...] = ("O",)       # 미검증 (Task 0)
      direct_codes: tuple[str, ...] = ("직거래",)      # 미검증
      corporate_codes: tuple[str, ...] = ("법인",)     # 미검증
      success_codes: tuple[str, ...] = ("00", "000")  # 미검증
      page_size: int = 1000                           # 미검증
      def as_dict(self) -> dict  # run.json에 그대로 기록
  def load_settings(path: Path) -> Settings
  ```
- TOML 구조: 최상위 `version`, `[thresholds]`(window_months, min_count, mad_k, flat_pct, exclude_direct, unsettled_months), `[codes]`(cancelled, direct, corporate), `[api]`(success_codes, page_size). 각 항목 옆에 spec §6 근거와 "미검증" 주석을 단다. `version = "2026-10-26-draft"`.

- [ ] **Step 1: 실패하는 테스트 작성**
  ```python
  def test_load_default_config_matches_spec():
      s = load_settings(Path("config/anomaly.toml"))
      assert (s.window_months, s.min_count, s.mad_k, s.flat_pct) == (6, 3, 3.0, 0.15)
      assert s.exclude_direct is True and s.unsettled_months == 2
      assert s.version == "2026-10-26-draft"

  def test_unknown_key_rejected(tmp_path):   # 오타 난 설정이 조용히 기본값이 되지 않게
      p = tmp_path / "c.toml"; p.write_text('version="x"\n[thresholds]\nmad_kk=2\n')
      with pytest.raises(ValueError, match="mad_kk"):
          load_settings(p)
  ```
- [ ] **Step 2:** `pytest tests/test_config.py -v` 실행 → FAIL (모듈 없음)
- [ ] **Step 3:** `pyproject.toml`(이름 `homepy`, `requires-python = ">=3.11"`, 의존성 `requests`, dev 의존성 `pytest`), `.gitignore`, `config/anomaly.toml`, `homepy/config.py`를 구현한다. 모르는 키가 있으면 키 이름을 담아 `ValueError`를 올린다.
- [ ] **Step 4:** `pip install -e ".[dev]" && pytest tests/test_config.py -v` → PASS
- [ ] **Step 5:** `git add -A && git commit -m "feat: project skeleton and versioned anomaly settings"`

### Task 2: 응답 파싱

**Files:**
- Create: `homepy/parse.py`, `tests/fixtures/page_two_items.xml`, `tests/fixtures/page_empty.xml`, `tests/fixtures/page_one_item.xml`, `tests/fixtures/error_result_code.xml`, `tests/fixtures/error_service_response.xml`
- Test: `tests/test_parse.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Page:
      total_count: int
      items: tuple[dict[str, str], ...]   # <item>의 자식 태그 → 앞뒤 공백 제거한 텍스트 (빈 태그는 "")
  class ApiError(Exception): ...
  def parse_page(xml: bytes, success_codes: tuple[str, ...]) -> Page
  ```
- 픽스처 형식: `<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header><body><items><item>…</item></items><numOfRows>…</numOfRows><pageNo>1</pageNo><totalCount>…</totalCount></body></response>`. 인증 오류 형식: `<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>…`. 두 형식 모두 Task 0에서 실제 응답과 대조한다.

- [ ] **Step 1: 실패하는 테스트 작성**
  ```python
  def test_two_items():
      p = parse_page(read("page_two_items.xml"), ("000",))
      assert p.total_count == 2 and len(p.items) == 2
      assert p.items[0]["dealAmount"] == "82,500"      # 정제는 Task 4의 일

  def test_empty_month_is_zero_not_error():
      p = parse_page(read("page_empty.xml"), ("000",))
      assert p.total_count == 0 and p.items == ()

  def test_single_item():
      assert len(parse_page(read("page_one_item.xml"), ("000",)).items) == 1

  @pytest.mark.parametrize("name", ["error_result_code.xml", "error_service_response.xml"])
  def test_api_errors_raise(name):
      with pytest.raises(ApiError):
          parse_page(read(name), ("000",))

  def test_malformed_xml_raises_api_error():
      with pytest.raises(ApiError):
          parse_page(b"<html>gateway timeout", ("000",))
  ```
- [ ] **Step 2:** `pytest tests/test_parse.py -v` → FAIL
- [ ] **Step 3:** `parse_page`를 `xml.etree.ElementTree`로 구현한다. 파싱 실패, `OpenAPI_ServiceResponse` 루트, `resultCode`가 `success_codes`에 없는 경우는 모두 `ApiError(메시지)`로 올린다.
- [ ] **Step 4:** `pytest tests/test_parse.py -v` → PASS
- [ ] **Step 5:** `git commit -m "feat: parse trade API pages with explicit error detection"`

### Task 3: 수집과 스냅샷

**Files:**
- Create: `homepy/collect.py`, `homepy/dates.py`
- Test: `tests/test_collect.py`, `tests/test_dates.py`

**Interfaces:**
- Consumes: `parse_page`, `Page`, `ApiError` (Task 2), `Settings` (Task 1)
- Produces:
  ```python
  # dates.py
  def months_before(d: date, n: int) -> date        # 일(day)은 해당 월 말일로 clamp
  def month_end(ym: str) -> date                    # "2026-02" → 2026-02-28
  def month_range(start: str, end: str) -> list[str] # 양 끝 포함, "YYYY-MM"

  # collect.py
  ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"  # Task 0에서 확인
  Getter = Callable[[str, dict[str, str]], bytes]   # (url, params) → 응답 본문
  class IncompleteCollection(Exception):
      expected: int; received: int
  @dataclass(frozen=True)
  class Snapshot:
      lawd_cd: str; month: str; fetched_on: date; pages: tuple[bytes, ...]
  def fetch_month(lawd_cd: str, month: str, service_key: str, get: Getter, settings: Settings) -> tuple[bytes, ...]
  def save_snapshot(root: Path, snap: Snapshot) -> Path
  def load_latest(root: Path, lawd_cd: str, month: str) -> Snapshot | None
  def ensure_months(root: Path, lawd_cd: str, months: list[str], service_key: str | None,
                    get: Getter, settings: Settings, today: date) -> list[Snapshot]
  def requests_getter(url: str, params: dict[str, str]) -> bytes   # timeout=30, raise_for_status
  ```
- 요청 파라미터: `serviceKey`, `LAWD_CD`, `DEAL_YMD`("YYYYMM"), `pageNo`, `numOfRows`(=`settings.page_size`).
- 스냅샷 경로: `{root}/{lawd_cd}/{YYYY-MM}/{fetched_on:%Y%m%d}/page_{n:03d}.xml`, 같은 폴더에 `manifest.json`(`total_count`, `received`, `pages`). 저장은 임시 폴더에 쓴 뒤 rename하는 원자적 방식으로 한다. 중간에 실패하면 반쯤 쓴 스냅샷이 남지 않는다.
- 재수집 규칙 (spec §7): 스냅샷이 없거나, `month_end(month) >= months_before(today, settings.unsettled_months)`이면 다시 받는다. 그 밖의 월은 저장된 최신 스냅샷을 쓴다. `service_key`가 `None`이면(오프라인 모드) 수집이 필요한 월이 있을 때 `RuntimeError`를 올린다.

- [ ] **Step 1: 실패하는 테스트 작성**
  ```python
  # test_dates.py
  @pytest.mark.parametrize("d,n,expected", [
      (date(2026, 8, 31), 6, date(2026, 2, 28)),
      (date(2024, 8, 31), 6, date(2024, 2, 29)),
      (date(2026, 3, 15), 6, date(2025, 9, 15)),
  ])
  def test_months_before(d, n, expected): assert months_before(d, n) == expected
  def test_month_range(): assert month_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]

  # test_collect.py — fake getter가 pageNo별로 픽스처 XML을 돌려준다
  def test_paginates_until_total(): ...       # total 3, page_size 2 → 호출 2회, pages 길이 2
  def test_short_collection_raises():         # total 3인데 2페이지째 0건
      with pytest.raises(IncompleteCollection) as e: fetch_month(...)
      assert (e.value.expected, e.value.received) == (3, 2)
  def test_settled_month_not_refetched(tmp_path): ...   # 2026-01 스냅샷 존재, today=2026-10-26 → getter 호출 0회
  def test_unsettled_month_refetched(tmp_path): ...     # 2026-09 스냅샷 존재 → 다시 호출, 새 날짜 폴더 생성
  def test_load_latest_picks_newest_date(tmp_path): ...
  def test_offline_missing_month_raises(tmp_path): ...  # service_key=None, 스냅샷 없음 → RuntimeError
  ```
- [ ] **Step 2:** `pytest tests/test_dates.py tests/test_collect.py -v` → FAIL
- [ ] **Step 3:** `dates.py`와 `collect.py`를 구현한다. 수집 루프: `pageNo=1`부터 시작해 누적 수신 건수가 `total_count`에 도달하면 멈춘다. 어떤 페이지가 0건이면 `IncompleteCollection`을 올린다.
- [ ] **Step 4:** 같은 명령 → PASS
- [ ] **Step 5:** `git commit -m "feat: complete-or-fail collection with dated raw snapshots"`

### Task 4: 정제 (Trade)

**Files:**
- Create: `homepy/trades.py`
- Test: `tests/test_trades.py`

**Interfaces:**
- Consumes: `Settings`, `Page.items`의 dict
- Produces:
  ```python
  @dataclass(frozen=True)
  class Trade:
      trade_id: str          # sha1(정렬된 원본 필드 JSON)의 앞 12자리. 원본이 같으면 id도 같다
      group_key: str         # f"{aptSeq}|{area_band}" 또는 f"{umdNm}|{jibun}|{aptNm}|{area_band}"
      key_fallback: bool
      apt_name: str; umd_name: str
      area_m2: Decimal; area_band: int
      deal_date: date
      price_manwon: int
      floor: int | None
      dealing_type: str      # 원값. 빈 값이면 "미상"
      cancelled: bool        # cdealType ∈ settings.cancelled_codes
      seller_type: str; buyer_type: str
  def parse_amount(s: str) -> int          # 공백·쉼표 제거
  def area_band(area: Decimal) -> int      # ROUND_HALF_UP
  def normalize(items: Iterable[dict[str, str]], settings: Settings) -> list[Trade]
  ```
- 중복 제거 (spec FR-2를 plan에서 확정): **모든 원본 필드가 같은 행만** 같은 거래로 보고 하나만 남긴다(= 같은 `trade_id`). 실제로 다른 두 거래를 하나로 합치는 것이 행 하나를 더 두는 것보다 위험하므로, 일부 필드만 같은 경우는 제거하지 않는다.
- 반환 순서: `(group_key, deal_date, trade_id)`로 정렬한다.

- [ ] **Step 1: 실패하는 테스트 작성**
  ```python
  def test_parse_amount(): assert parse_amount("  82,500") == 82500
  @pytest.mark.parametrize("a,b", [("84.5", 85), ("83.5", 84), ("84.49", 84), ("59.97", 60)])
  def test_area_band_half_up(a, b): assert area_band(Decimal(a)) == b
  def test_group_key_uses_aptSeq(): assert t.group_key == "11680-123|85" and not t.key_fallback
  def test_group_key_fallback_when_aptSeq_blank(): assert t.group_key == "개포동|187|개포주공5단지|83" and t.key_fallback
  def test_cancelled_from_code(): ...        # cdealType="O" → True, "" → False
  def test_blank_dealing_type_is_unknown(): assert t.dealing_type == "미상"
  def test_exact_duplicates_removed_partial_kept(): ...   # 완전 동일 2행 → 1, 층만 다른 2행 → 2
  def test_output_sorted(): ...
  ```
- [ ] **Step 2:** `pytest tests/test_trades.py -v` → FAIL
- [ ] **Step 3:** `trades.py`를 구현한다. 계약일은 `dealYear`/`dealMonth`/`dealDay`로 만들고, 층은 빈 값이면 `None`으로 둔다.
- [ ] **Step 4:** 같은 명령 → PASS
- [ ] **Step 5:** `git commit -m "feat: normalize raw items into deterministic Trade records"`

### Task 5: 플래그 (F1–F6)

**Files:**
- Create: `homepy/flags.py`
- Test: `tests/test_flags.py`

**Interfaces:**
- Consumes: `Trade` (Task 4), `Settings`, `months_before` (Task 3)
- Produces:
  ```python
  class Flag(str, Enum):
      F1 = "F1"; F2 = "F2"; F3 = "F3"; F4 = "F4"; F5 = "F5"; F6 = "F6"
  def excluded_flags(settings: Settings) -> frozenset[Flag]   # {F1, F3} ∪ ({F2} if exclude_direct)
  @dataclass(frozen=True)
  class FlaggedTrade:
      trade: Trade
      flags: tuple[Flag, ...]          # 코드 순 정렬
      reasons: tuple[str, ...]         # flags와 같은 순서
      comparison_median_manwon: int | None
      deviation: float | None          # price / comparison_median − 1, 소수 4자리 반올림
      comparison_count: int
  def assign_flags(trades: Sequence[Trade], settings: Settings, as_of: date) -> list[FlaggedTrade]
  ```
- 판정 규칙 (spec §5와 FR-3을 그대로 옮긴 것):
  - **비교 집합** = 같은 `group_key`, `months_before(t.deal_date, window_months) <= d <= t.deal_date`, 자기 자신 제외, `cancelled`가 아니고, (`exclude_direct`이면) 직거래가 아닌 거래.
  - F1: `cancelled`. F2: `dealing_type ∈ direct_codes`. F5: 매도자 또는 매수자가 `corporate_codes`에 속함. F6: `deal_date >= months_before(as_of, unsettled_months)`.
  - 비교 집합이 `min_count` 미만이면 → F4, F3 판정은 하지 않는다.
  - 그 밖의 경우 F3는 아래 알고리즘으로 판정한다(모든 거래 대상. F1·F2 거래에도 서술용으로 판정한다):
    ```python
    logs = [math.log(p) for p in comparison_prices]
    m = statistics.median(logs)
    mad = statistics.median(abs(x - m) for x in logs)
    if mad == 0:
        outlier = abs(price / math.exp(m) - 1) > settings.flat_pct
    else:
        outlier = abs(math.log(price) - m) > settings.mad_k * 1.4826 * mad
    comparison_median_manwon = int(Decimal(math.exp(m)).quantize(0, ROUND_HALF_UP))
    ```
  - 사유 문구(고정): F1 `"해제 신고된 거래"`, F2 `"직거래"`, F3 `"통계적 이상치 (기준 대비 {deviation:+.1%})"`, F4 `"비교 거래 {n}건 < 최소 {min_count}건, 판정 보류"`, F5 `"법인 관련 (매도: {seller}, 매수: {buyer})"`, F6 `"미확정 기간 거래 (신고·해제 반영 전일 수 있음)"`.

- [ ] **Step 1: 실패하는 테스트 작성** (헬퍼 `mk(price, d, **kw) -> Trade`로 같은 그룹 거래를 만든다)
  ```python
  def test_outlier_by_mad():          # 비교 100,000/101,000/99,000/100,500, 대상 130,000 → F3
  def test_not_outlier_within_band(): # 같은 비교 집합, 대상 102,000 → F3 없음, deviation == 0.0175 (102,000 / 100,250 − 1)
  def test_mad_zero_uses_flat_pct():  # 비교 3건 모두 100,000, 대상 114,000 → F3 없음; 116,000 → F3
  def test_insufficient_comparison_is_F4_not_F3():   # 비교 2건 → flags == (F4,)
  def test_cancelled_and_direct_excluded_from_comparison(): # 해제 2건 + 정상 2건 → 비교 2건 → F4
  def test_direct_included_when_setting_off(): ...
  def test_window_boundary_month_end():  # 대상 2026-08-31, 2026-02-28 거래는 포함, 2026-02-27 거래는 제외
  def test_self_excluded_same_day_others_included(): ...
  def test_F6_relative_to_as_of():     # as_of 2026-10-26 → 2026-08-26 이후 거래만 F6
  def test_reason_wording_has_no_forbidden_terms():
      for r in all_reasons: assert not any(w in r for w in ("불법", "허위", "작전"))
  def test_deterministic(): assert assign_flags(ts, s, d) == assign_flags(list(reversed(ts)), s, d)
  ```
- [ ] **Step 2:** `pytest tests/test_flags.py -v` → FAIL
- [ ] **Step 3:** `flags.py`를 구현한다. 그룹별로 묶고, 그룹 안에서 날짜순으로 정렬한 뒤, 거래마다 비교 집합을 구한다. 그룹당 거래가 수백 건 수준이므로 O(n²)도 허용한다.
- [ ] **Step 4:** 같은 명령 → PASS
- [ ] **Step 5:** `git commit -m "feat: rule-based anomaly flags F1-F6 with MAD outlier test"`

### Task 6: 기준 시세 (GroupMonth)

**Files:**
- Create: `homepy/baseline.py`
- Test: `tests/test_baseline.py`

**Interfaces:**
- Consumes: `FlaggedTrade`, `Flag`, `excluded_flags` (Task 5), `month_end`, `month_range`, `months_before` (Task 3)
- Produces:
  ```python
  @dataclass(frozen=True)
  class GroupMonth:
      group_key: str; apt_name: str; umd_name: str; area_band: int; key_fallback: bool
      month: str                                  # "YYYY-MM"
      baseline_median_manwon: int | None          # None = 산출 불가
      normal_count: int; total_count: int
      flag_counts: tuple[tuple[Flag, int], ...]   # F1..F6 순서 고정, 0 포함
      unsettled: bool
  def compute_baselines(flagged: Sequence[FlaggedTrade], settings: Settings,
                        months: Sequence[str], as_of: date) -> list[GroupMonth]
  ```
- 월 M의 창 = M을 포함한 직전 `window_months`개 **달력 월** 전체(예: N=6, M=2026-09 → 2026-04-01부터 2026-09-30까지). 정상 거래 = `excluded_flags(settings)`에 속한 플래그가 없는 거래. F4·F5·F6는 정상에 포함된다. 정상 거래가 `min_count` 미만이면 `baseline_median_manwon=None`.
- 중위수는 `statistics.median(가격)`을 `ROUND_HALF_UP`으로 정수화한다. `unsettled = month_end(M) >= months_before(as_of, unsettled_months)`.
- 행은 창 안에 거래가 1건 이상 있는 (그룹, 월)만 만든다. 정렬 순서는 `(group_key, month)`.

- [ ] **Step 1: 실패하는 테스트 작성**
  ```python
  def test_median_excludes_F1_F3_F2(): ...        # 정상 100,000/102,000/104,000 + F3 150,000 → 102,000, normal 3, total 4
  def test_even_count_half_up(): ...              # 정상 100,000/100,001/100,002/100,004 → 100,002 (100,001.5 반올림)
  def test_below_min_count_is_none(): assert row.baseline_median_manwon is None and row.normal_count == 2
  def test_window_is_calendar_months(): ...       # 2026-03-31 거래는 2026-09 창에서 빠지고, 2026-04-01 거래는 포함
  def test_flag_counts_include_zeros(): assert [f for f, _ in row.flag_counts] == list(Flag)
  def test_unsettled_month(): ...                 # as_of 2026-10-26 → 2026-09 unsettled, 2026-07 아님
  ```
- [ ] **Step 2:** `pytest tests/test_baseline.py -v` → FAIL
- [ ] **Step 3:** `baseline.py`를 구현한다.
- [ ] **Step 4:** 같은 명령 → PASS
- [ ] **Step 5:** `git commit -m "feat: per-group monthly baseline price from normal trades"`

### Task 7: 리포트와 CLI

**Files:**
- Create: `homepy/report.py`, `homepy/cli.py`, `homepy/__main__.py`
- Modify: `README.md` (실행 방법 섹션 추가)
- Test: `tests/test_report.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1–6 전부
- Produces:
  ```python
  TRADE_COLUMNS = ("trade_id", "group_key", "key_fallback", "apt_name", "umd_name", "area_m2", "area_band",
                   "deal_date", "price_manwon", "floor", "dealing_type", "cancelled", "seller_type", "buyer_type",
                   "flags", "reasons", "comparison_count", "comparison_median_manwon", "deviation")
  GROUP_COLUMNS = ("group_key", "apt_name", "umd_name", "area_band", "key_fallback", "month",
                   "baseline_median_manwon", "normal_count", "total_count",
                   "F1", "F2", "F3", "F4", "F5", "F6", "unsettled")
  def write_trades_csv(path: Path, rows: Sequence[FlaggedTrade]) -> None
  def write_groups_csv(path: Path, rows: Sequence[GroupMonth]) -> None
  def write_run_json(path: Path, settings: Settings, snapshots: Sequence[Snapshot],
                     as_of: date, run_at: datetime) -> None
  def main(argv: list[str] | None = None) -> int
  ```
- CSV 형식: `utf-8-sig`(엑셀에서 한글이 깨지지 않게), `lineterminator="\n"`. 다중 값은 `;`로 잇는다. `None`은 빈 칸, bool은 `true`/`false`로 쓴다. spec FR-5의 "CSV/엑셀"은 엑셀에서 바로 열리는 CSV로 충족한다. xlsx는 생성 시각 메타데이터 때문에 바이트 단위 재현이 어려워 Phase 1에서 제외한다.
- `run.json`: `settings.as_dict()`, 월별 `fetched_on`, `as_of`, `run_at`, `homepy` 버전. 재현성 비교(spec §8-5)는 **CSV 두 파일**로 한다. `run.json`은 `run_at` 때문에 실행마다 달라진다.
- CLI:
  ```
  python -m homepy run --lawd 11680 --from 2026-01 --to 2026-09 \
      [--config config/anomaly.toml] [--raw data/raw] [--out out/11680] [--offline]
  ```
  - 수집 범위 = `[from − window_months개월, to]`. 비교 창에 쓸 과거 데이터까지 받는다. 출력은 계약월이 `[from, to]`에 드는 거래·그룹만 한다.
  - `as_of` = 사용한 스냅샷들의 `fetched_on` 중 최댓값.
  - `--offline`은 `service_key=None`. 키가 없고 `--offline`도 아니면 종료 코드 2와 함께 안내 메시지를 낸다.
  - 출력: `{out}/trades.csv`, `{out}/groups.csv`, `{out}/run.json`

- [ ] **Step 1: 실패하는 테스트 작성**
  ```python
  def test_trades_csv_header_and_bom(tmp_path): ...     # 첫 3바이트 == b"\xef\xbb\xbf", 헤더 == TRADE_COLUMNS
  def test_none_and_bool_formatting(tmp_path): ...
  def test_cli_offline_end_to_end(tmp_path):            # tests/fixtures로 만든 스냅샷 트리 → 3개 파일 생성, 종료 코드 0
  def test_cli_reproducible(tmp_path):
      main([... "--out", str(a)]); main([... "--out", str(b)])
      for f in ("trades.csv", "groups.csv"): assert (a / f).read_bytes() == (b / f).read_bytes()
  def test_cli_outputs_only_requested_months(tmp_path): ...
  def test_cli_missing_key_exit_2(monkeypatch, tmp_path): ...
  ```
- [ ] **Step 2:** `pytest tests/test_report.py tests/test_cli.py -v` → FAIL
- [ ] **Step 3:** `report.py`, `cli.py`, `__main__.py`를 구현한다(`argparse`). README에 설치 방법, 서비스 키 설정, 실행 예, 출력 파일 설명을 추가한다.
- [ ] **Step 4:** `pytest -v` (전체) → PASS
- [ ] **Step 5:** `git commit -m "feat: CSV report and run CLI"`

### Task 8: 실데이터 검증 (spec §8, 사람과 함께 수행)

전제: Task 0 완료, `DATA_GO_KR_SERVICE_KEY` 설정.

- [ ] **Step 1 (수집 검증):** 시군구 3곳(예: 강남구 11680, 노원구 11350, 성남 분당구 41135) × 3개월로 실행한다. `manifest.json`의 `total_count == received`를 확인하고, 국토부 실거래가 공개시스템 화면과 거래 10건을 대조한다.
- [ ] **Step 2 (필드 검증):** `trades.csv`에서 `dealing_type`·`seller_type`·`buyer_type`의 값 분포와 `미상` 비율, 그리고 `cancelled=true` 비율을 `docs/data-fields.md`에 기록한다.
- [ ] **Step 3 (재현성):** 같은 스냅샷으로 `--offline` 실행을 두 번 하고 `cmp`로 CSV를 비교한다 → 차이 없음.
- [ ] **Step 4 (플래그 품질):** F3 50건과 비F3 50건을 단지 규모·가격대별로 층화해 추출하고, 수기 판정 결과를 `docs/validation-2026-xx.md`에 기록한다. 임계값을 조정할 때 쓴 표본과 이 표본은 분리한다.
- [ ] **Step 5 (기준선):** 수작업 방식과 CLI 방식의 단지당 소요 시간을 각각 3단지씩 기록한다.
- [ ] **Step 6:** 결과를 커밋하고, 필요하면 `config/anomaly.toml`의 `version`을 올린다.

---

## Spec 대응표

| Spec | Task |
|---|---|
| FR-1 수집, 원본 보관, totalCount 대조 | 2, 3 |
| FR-2 정제, 그룹 키, 대체 키, 중복 | 4 |
| FR-3 플래그 F1–F6 | 5 |
| §5 MAD 규칙, MAD=0 대체 | 5 |
| FR-4 기준 시세, 산출 불가 | 6 |
| FR-5 출력 + 메타데이터 | 7 |
| §6 설정값 버전 관리 | 1 |
| §7 재현성, API 한도(완료 월은 재호출하지 않음), 표현 원칙 | 3, 5, 7 |
| §8 검증 계획 1–5 | 0, 8 |
