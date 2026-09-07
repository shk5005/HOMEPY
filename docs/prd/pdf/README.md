# PRD 보고서 PDF 빌드

## 산출물
- `PRD_전쟁금리_운용규칙_v1.0.pdf` — A4 8쪽, 한글 임베드

## 재생성
```bash
pip install playwright
python3 build_pdf.py prd-report.html 출력파일.pdf
```

## 환경 메모
- 렌더러: Playwright + Chromium(`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`)
- 한글 폰트: 시스템에 Noto/나눔이 없어 **WenQuanYi Zen Hei** 사용
  (Hangul 11,172자 전수 커버 확인). Google Fonts는 프록시 차단(403).
  나눔고딕·Pretendard 설치 시 `prd-report.html`의 font-family 앞에 추가하면 품질이 개선된다.
- 페이지 번호는 Playwright `footer_template`으로 삽입(Chromium은 CSS @page margin box 미지원).
