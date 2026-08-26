#!/usr/bin/env node
/* ============================================================
   build.mjs — 단일 HTML 번들 생성

   ES 모듈 8개 + CSS 를 하나의 .html 로 합친다. 두 가지를 낸다.

     dist/genie.html           완결된 HTML 문서 — 파일을 그냥 열면 뜬다
     dist/genie.artifact.html  body 내용만 — Artifact 발행용 (head는 호스트가 감쌈)

   출력은 전부 ASCII 로 이스케이프한다.
   한글이 원문 그대로 들어가면, 문서가 UTF-8 로 해석되지 않는 환경에서
   바이트가 깨져 정규식 문자범위(예: 가-힣)까지 망가진다. 실제로 그 한 줄
   때문에 번들 전체가 파싱 단계에서 죽었다. ASCII 로 구우면 호스트가
   charset 을 어떻게 주든 결과가 같다.

     node build.mjs
     node build.mjs --out dist/genie.html
   ============================================================ */

import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve, join } from 'node:path';

const argv = process.argv.slice(2);
const outArg = argv.indexOf('--out');
const OUT = resolve(outArg >= 0 ? argv[outArg + 1] : 'dist/genie.html');
const OUT_ARTIFACT = join(dirname(OUT), 'genie.artifact.html');

const NON_ASCII = /[\u0080-\uFFFF]/g;

/** HTML 본문/속성용 — 숫자 문자 참조 */
const asciiHtml = s => s.replace(NON_ASCII,
  c => `&#x${c.codePointAt(0).toString(16).toUpperCase()};`);

/** CSS용 — 6자리 고정폭 이스케이프(뒤에 공백을 붙이지 않아도 안전) */
const asciiCss = s => s.replace(NON_ASCII,
  c => '\\' + c.codePointAt(0).toString(16).toUpperCase().padStart(6, '0'));

const hasNonAscii = s => new RegExp(NON_ASCII.source).test(s);

/** JS용 — \uXXXX 는 문자열·템플릿·정규식·주석 어디에 들어가도 의미가 같다.
    esbuild 의 charset:'ascii' 는 문자열만 굽고 정규식 리터럴과 주석은 남기므로
    (예: /^[가-힣]/) 번들 후 한 번 더 훑는다. */
const asciiJs = s => s.replace(NON_ASCII,
  c => '\\u' + c.codePointAt(0).toString(16).toUpperCase().padStart(4, '0'));

/* ---------- 1) ES 모듈 그래프를 IIFE 하나로 ---------- */
const bundled = await build({
  entryPoints: ['assets/js/app.js'],
  bundle: true,
  format: 'iife',
  target: ['es2020'],
  charset: 'ascii',       // 비ASCII를 \uXXXX 로 — charset 의존을 없앤다
  // 뷰어가 페이지발 다운로드를 막으므로, 다운로드 구현을 죽은 코드로 만들어 제거한다
  define: { GENIE_STANDALONE: 'true' },
  // minify 를 켜야 esbuild 가 죽은 가지를 실제로 제거한다.
  // (읽을 수 있는 원본은 저장소에 그대로 있고, 이건 산출물이다)
  minify: true,
  legalComments: 'none',
  write: false,
  logLevel: 'warning'
});
const js = asciiJs(bundled.outputFiles[0].text);
if (hasNonAscii(js)) throw new Error('JS 에 비ASCII 문자가 남았습니다');

/* ---------- 2) CSS: 주석 제거 후 이스케이프 ---------- */
const cssRaw = await readFile('assets/css/genie.css', 'utf8');
const css = asciiCss(cssRaw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\n{3,}/g, '\n\n').trim());

/* ---------- 3) index.html 의 마크업 재사용 (구조 중복 방지) ---------- */
const indexHtml = await readFile('index.html', 'utf8');
const m = indexHtml.match(/<body>([\s\S]*?)<script/);
if (!m) throw new Error('index.html 에서 body 마크업을 찾지 못했습니다');
const markup = asciiHtml(m[1].trim());

/* title·description 만 평문 UTF-8 로 둔다.
   이 둘은 발행 도구가 파일에서 읽어 갤러리 이름으로 쓰는 메타데이터라,
   엔티티로 인코딩하면 그대로 노출될 위험이 있다. 파일 자체는 UTF-8 이므로
   파서는 정확히 읽는다. 본문·CSS·JS 는 아래에서 전부 ASCII 로 굽는다. */
const TITLE = '지니 주식투자비서';
const DESC  = '일반 투자자가 빠지는 함정 5가지를 AI가 강제 차단하도록 설계한 주식 분석 파이프라인.';

const parts = `<style>
${css}
</style>

${markup}

<script>window.GENIE_STANDALONE=true;</script>
<script>
${js}
</script>`;

/* ---------- 4) Artifact 용: head 는 호스트가 감싸므로 내용만 ---------- */
const artifact = `<title>${TITLE}</title>
<meta name="description" content="${DESC}">
${parts}
`;

/* ---------- 5) 로컬용: 완결된 문서 ---------- */
const standalone = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${TITLE}</title>
<meta name="description" content="${DESC}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#x1F9DE;</text></svg>">
</head>
<body>
${parts}
</body>
</html>
`;

for (const [path, html] of [[OUT, standalone], [OUT_ARTIFACT, artifact]]) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, html, 'utf8');
}

const kb = n => (n / 1024).toFixed(1) + ' KB';
console.log(`OK ${OUT}  ${kb(standalone.length)}  (완결 문서 — 그냥 열면 실행)`);
console.log(`OK ${OUT_ARTIFACT}  ${kb(artifact.length)}  (Artifact 발행용)`);
console.log(`   JS ${kb(js.length)} · CSS ${kb(css.length)} · 마크업 ${kb(markup.length)}`);
console.log(`   본문 비ASCII 잔존: ${hasNonAscii(parts) ? 'X 있음' : 'OK 없음 (charset 무관)'}`);
