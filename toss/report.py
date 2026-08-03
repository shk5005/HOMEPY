"""토스 Open API 인사이트 대시보드 렌더러.

교차 분석 패널(모멘텀×변동성 스캐터, 매수/매도 압력, 거래대금·시총 랭킹,
52주 위치, 상세 표)을 자체 완결형 HTML 로 생성합니다. 외부 리소스 미사용.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def build_report(sections: list[dict], mode: str = "live", usdkrw: float | None = None) -> dict:
    return {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "mode": mode,
        "usdkrw": usdkrw,
        "sections": sections,
    }


def build_html(report: dict) -> str:
    data_json = json.dumps(report, ensure_ascii=False)
    generated = report.get("generated_at") or datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    return (_TEMPLATE
            .replace("__DATA__", data_json)
            .replace("__GENERATED__", generated)
            .replace("__MODE__", report.get("mode", "live")))


_TEMPLATE = r"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>토스 Open API 주식 인사이트</title>
<style>
:root{
  --bg:#F4F6F9; --surface:#FFFFFF; --surface-2:#EEF2F7; --surface-3:#F7F9FC;
  --ink:#0E1726; --muted:#5A6B84; --faint:#8794A9; --line:#E5EAF1;
  --accent:#3182F6; --accent-2:#7A5AF8; --up:#F04452; --down:#3182F6; --flat:#94A2B6;
  --good:#15B36B; --warn:#F5A524;
  --shadow:0 1px 2px rgba(16,24,40,.04),0 10px 28px rgba(16,24,40,.06);
  --radius:18px;
  --mono:'SFMono-Regular','JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
  --sans:'Pretendard',-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','Segoe UI',Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#080B11; --surface:#121822; --surface-2:#1A212D; --surface-3:#0F151E;
  --ink:#E9EEF6; --muted:#93A0B4; --faint:#5F6D82; --line:#232C3A;
  --accent:#4C93FF; --accent-2:#9B7DFF; --up:#FF5A66; --down:#4C93FF; --flat:#5F6D82;
  --good:#2ED58A; --warn:#FFC24B;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 12px 32px rgba(0,0,0,.4);
}}
:root[data-theme="light"]{--bg:#F4F6F9;--surface:#FFFFFF;--surface-2:#EEF2F7;--surface-3:#F7F9FC;--ink:#0E1726;--muted:#5A6B84;--faint:#8794A9;--line:#E5EAF1;--accent:#3182F6;--accent-2:#7A5AF8;--up:#F04452;--down:#3182F6;--flat:#94A2B6;--good:#15B36B;--warn:#F5A524;--shadow:0 1px 2px rgba(16,24,40,.04),0 10px 28px rgba(16,24,40,.06);}
:root[data-theme="dark"]{--bg:#080B11;--surface:#121822;--surface-2:#1A212D;--surface-3:#0F151E;--ink:#E9EEF6;--muted:#93A0B4;--faint:#5F6D82;--line:#232C3A;--accent:#4C93FF;--accent-2:#9B7DFF;--up:#FF5A66;--down:#4C93FF;--flat:#5F6D82;--good:#2ED58A;--warn:#FFC24B;--shadow:0 1px 2px rgba(0,0,0,.3),0 12px 32px rgba(0,0,0,.4);}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased;line-height:1.45}
.wrap{max-width:1240px;margin:0 auto;padding:0 20px 80px}
.tnum{font-variant-numeric:tabular-nums}
.mono{font-family:var(--mono)}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)}

header.top{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--bg) 85%,transparent);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.top-in{max-width:1240px;margin:0 auto;padding:13px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:11px;margin-right:auto}
.mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,var(--accent),var(--accent-2));display:grid;place-items:center;color:#fff;font-weight:800;font-size:15px;box-shadow:0 3px 12px rgba(49,130,246,.4)}
.brand h1{font-size:16px;margin:0;font-weight:700;letter-spacing:-.01em}
.brand .sub{font-size:12px;color:var(--muted)}
.pill{font-size:11px;font-weight:700;padding:4px 9px;border-radius:999px}
.pill.live{background:color-mix(in srgb,var(--up) 14%,transparent);color:var(--up)}
.pill.demo{background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent)}
.meta{font-size:12px;color:var(--muted)}
.icon-btn{border:1px solid var(--line);background:var(--surface);color:var(--muted);width:34px;height:34px;border-radius:10px;cursor:pointer;display:grid;place-items:center;font-size:15px}
.icon-btn:hover{color:var(--ink);border-color:var(--accent)}

.hero{padding:30px 0 6px}
.hero h2{font-size:clamp(23px,3.6vw,34px);margin:0 0 8px;letter-spacing:-.025em;text-wrap:balance;font-weight:800}
.hero p{margin:0;color:var(--muted);max-width:66ch;font-size:14px}
.src{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.src span{font-size:11.5px;font-weight:600;color:var(--muted);background:var(--surface-2);padding:4px 10px;border-radius:8px}

.tabs{display:flex;gap:6px;margin:22px 0 18px;background:var(--surface-2);padding:5px;border-radius:12px;width:fit-content}
.tab{border:0;background:transparent;color:var(--muted);font-family:inherit;font-size:14px;font-weight:600;padding:8px 20px;border-radius:9px;cursor:pointer}
.tab[aria-selected="true"]{background:var(--surface);color:var(--ink);box-shadow:var(--shadow)}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow)}
.kpi .k{font-size:12px;color:var(--muted)}
.kpi .v{font-size:23px;font-weight:800;margin-top:4px;letter-spacing:-.01em}
.kpi .v small{font-size:12px;font-weight:600;color:var(--faint)}

.panels{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:18px 18px 16px;box-shadow:var(--shadow);min-width:0}
.panel.wide{grid-column:1/-1}
.p-head{display:flex;align-items:baseline;gap:8px;margin-bottom:4px}
.p-head h3{margin:0;font-size:15px;font-weight:700;letter-spacing:-.01em}
.p-head .tag{font-size:11px;color:var(--faint);font-weight:600}
.p-sub{font-size:12px;color:var(--muted);margin:0 0 14px}

/* scatter */
.scatter-wrap{position:relative}
canvas.scatter{width:100%;height:340px;display:block}
.tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--bg);font-size:11.5px;padding:6px 9px;border-radius:8px;opacity:0;transform:translate(-50%,-120%);white-space:nowrap;z-index:5;font-weight:600}
.tip b{color:var(--bg)}

/* ranking / pressure rows */
.rows{display:flex;flex-direction:column;gap:9px}
.row{display:grid;grid-template-columns:96px 1fr auto;align-items:center;gap:10px;font-size:13px}
.row .nm{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.row .val{font-weight:700;text-align:right;white-space:nowrap}
.bar{height:9px;border-radius:5px;background:var(--surface-2);overflow:hidden;position:relative}
.bar>i{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,var(--accent),var(--accent-2))}
/* diverging (imbalance) */
.dv{height:14px;background:var(--surface-2);border-radius:7px;position:relative;overflow:hidden}
.dv .mid{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--faint);opacity:.5}
.dv>i{position:absolute;top:0;bottom:0;border-radius:7px}
.dv>i.buy{left:50%;background:var(--up)}
.dv>i.sell{right:50%;background:var(--down)}

/* position track */
.pos{display:grid;grid-template-columns:96px 1fr 44px;align-items:center;gap:10px;font-size:13px}
.track{height:8px;border-radius:4px;background:linear-gradient(90deg,color-mix(in srgb,var(--down) 30%,var(--surface-2)),var(--surface-2),color-mix(in srgb,var(--up) 30%,var(--surface-2)));position:relative}
.track .mk{position:absolute;top:-3px;width:3px;height:14px;border-radius:2px;background:var(--ink);transform:translateX(-50%)}

.scroll{overflow-x:auto;border-radius:12px}
table{border-collapse:collapse;width:100%;min-width:760px;font-size:13px}
th,td{padding:9px 12px;text-align:right;white-space:nowrap;border-top:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:12px;cursor:pointer;user-select:none}
th:hover{color:var(--ink)}
td:first-child,th:first-child{text-align:left}
tbody tr:hover{background:var(--surface-3)}
.badge{font-size:11px;font-weight:800;padding:2px 8px;border-radius:999px}
.badge.up{background:color-mix(in srgb,var(--up) 14%,transparent)}
.badge.down{background:color-mix(in srgb,var(--down) 14%,transparent)}
.badge.flat{background:var(--surface-2);color:var(--muted)}

/* sector rows */
.srow{display:grid;grid-template-columns:1fr auto;gap:4px 12px;padding:10px 0;border-top:1px solid var(--line)}
.srow:first-child{border-top:0}
.srow .st{font-weight:700;font-size:13.5px}
.srow .cnt{font-size:11px;color:var(--faint);font-weight:600;margin-left:6px}
.srow .met{font-size:12px;color:var(--muted);text-align:right;white-space:nowrap}
.srow .sbar{grid-column:1/-1;height:7px;border-radius:4px;background:var(--surface-2);overflow:hidden}
.srow .sbar>i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--accent),var(--accent-2))}

/* radar */
.radar-wrap{display:grid;place-items:center}
canvas#radar{width:100%;max-width:360px;height:320px}
.legend{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px;justify-content:center}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--muted);cursor:pointer}
.chip .dot{width:9px;height:9px;border-radius:50%;background:var(--faint)}
.chip[aria-pressed="true"]{color:var(--ink);border-color:transparent;background:var(--surface-2)}

.empty{color:var(--faint);font-size:13px;padding:18px 0;text-align:center}
.note{margin-top:30px;padding:16px 18px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);color:var(--muted);font-size:12.5px;line-height:1.7}
.note b{color:var(--ink)} .note code{font-family:var(--mono);font-size:11.5px;background:var(--surface-2);padding:1px 6px;border-radius:5px}
footer{margin-top:24px;text-align:center;color:var(--faint);font-size:12px}
@media (max-width:820px){.panels{grid-template-columns:1fr}.panel.wide{grid-column:auto}}
</style>

<header class="top">
  <div class="top-in">
    <div class="brand">
      <div class="mark">T</div>
      <div><h1>토스 Open API 인사이트</h1><div class="sub">국내 KRX · 국외 US</div></div>
    </div>
    <span class="pill __MODE__" id="modePill"></span>
    <span class="meta" id="fxMeta"></span>
    <span class="meta">__GENERATED__</span>
    <button class="icon-btn" id="themeBtn" title="테마 전환" aria-label="테마 전환">◐</button>
  </div>
</header>

<div class="wrap">
  <section class="hero">
    <h2>토스 API 데이터로 읽는 시장 인사이트</h2>
    <p>현재가·호가·캔들·기업정보·환율을 교차 분석해, 개별 종목 너머의 흐름 —
       자금 쏠림, 매수·매도 압력, 위험 대비 모멘텀, 환효과, 가격 위치 — 을 한 화면에 정리합니다.
       투자 참고용이며 투자자문이 아닙니다.</p>
    <div class="src">
      <span>현재가 → 등락·거래대금·상하한</span>
      <span>호가 → 매수/매도 압력·스프레드</span>
      <span>캔들 → 모멘텀·변동성·추세</span>
      <span>기업정보 → 시가총액</span>
      <span>환율 → 원화환산·환효과</span>
    </div>
  </section>

  <div class="tabs" id="tabs" role="tablist"></div>
  <div class="kpis" id="kpis"></div>

  <div class="panels">
    <div class="panel wide">
      <div class="p-head"><h3>위험 대비 모멘텀</h3><span class="tag">캔들</span></div>
      <p class="p-sub">가로 = 20일 수익률, 세로 = 연율 변동성, 점 크기 = 거래대금, 색 = 종합 신호. 오른쪽·아래일수록 "낮은 위험에 높은 모멘텀".</p>
      <div class="scatter-wrap"><canvas class="scatter" id="scatter"></canvas><div class="tip" id="tip"></div></div>
    </div>

    <div class="panel">
      <div class="p-head"><h3>매수·매도 압력</h3><span class="tag">호가</span></div>
      <p class="p-sub">호가 잔량 불균형. 오른쪽(빨강)=매수 우위, 왼쪽(파랑)=매도 우위.</p>
      <div class="rows" id="pressure"></div>
    </div>

    <div class="panel">
      <div class="p-head"><h3>거래대금 상위</h3><span class="tag">현재가 × 거래량</span></div>
      <p class="p-sub">자금이 몰린 종목. 국외는 원화 환산.</p>
      <div class="rows" id="turnover"></div>
    </div>

    <div class="panel">
      <div class="p-head"><h3>시가총액</h3><span class="tag">현재가 × 발행주식수</span></div>
      <p class="p-sub">기업 규모. 국외는 원화 환산.</p>
      <div class="rows" id="mktcap"></div>
    </div>

    <div class="panel">
      <div class="p-head"><h3>52주 위치 · 일중 위치</h3><span class="tag">현재가</span></div>
      <p class="p-sub">막대 위 표식 = 52주 범위 내 현재가 위치(%). 오른쪽 값 = 오늘 저가~고가 중 위치.</p>
      <div class="rows" id="position"></div>
    </div>
  </div>

  <div class="panels" style="margin-top:16px">
    <div class="panel">
      <div class="p-head"><h3>섹터별 분석</h3><span class="tag">기업정보 · 캔들</span></div>
      <p class="p-sub">업종별 평균 등락·신호와 거래대금 비중. 자금과 모멘텀이 어느 섹터에 쏠렸는지.</p>
      <div class="rows" id="sectors"></div>
    </div>
    <div class="panel">
      <div class="p-head"><h3>경쟁사 비교 · 레이더</h3><span class="tag">종합 프로파일</span></div>
      <p class="p-sub">7개 축을 섹션 내 백분위(0~100)로 정규화. 칩을 눌러 비교 종목을 바꾸세요.</p>
      <div class="radar-wrap"><canvas id="radar"></canvas></div>
      <div class="legend" id="radarLegend"></div>
    </div>
  </div>

  <div class="panel wide" style="margin-top:16px">
    <div class="p-head"><h3>종목 상세</h3><span class="tag">헤더 클릭 시 정렬</span></div>
    <div class="scroll"><table id="tbl"></table></div>
  </div>

  <div class="note" id="note"></div>
  <footer>toss-stock-analysis · 자체 생성 정적 리포트 · 외부 리소스 미사용</footer>
</div>

<script>
const DATA = __DATA__;
const $ = (s,el=document)=>el.querySelector(s);
const cssv = n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();

$('#themeBtn').onclick = ()=>{
  const cur = document.documentElement.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  document.documentElement.setAttribute('data-theme', cur==='dark'?'light':'dark');
  drawScatter(); drawRadar();
};
$('#modePill').textContent = DATA.mode==='demo' ? '● 샘플 데이터' : '● 라이브';
$('#fxMeta').textContent = DATA.usdkrw ? ('USD/KRW ' + Math.round(DATA.usdkrw).toLocaleString()) : '';

/* ---- format helpers ---- */
const sym={USD:'$',KRW:'₩'};
function fmtP(v,cur){ if(v==null||isNaN(v))return'—'; const d=cur==='USD'?2:0; return (sym[cur]||'')+Number(v).toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}); }
function pct(v){ if(v==null||isNaN(v))return'—'; return (v>=0?'+':'')+Number(v).toFixed(2)+'%'; }
function dcls(v){ if(v==null||isNaN(v)||v===0)return'flat'; return v>0?'up':'down'; }
function krwC(v){ if(v==null||isNaN(v))return'—'; if(v>=1e12)return(v/1e12).toFixed(1)+'조'; if(v>=1e8)return Math.round(v/1e8).toLocaleString()+'억'; if(v>=1e4)return Math.round(v/1e4).toLocaleString()+'만'; return Math.round(v).toLocaleString(); }

/* ---- tabs ---- */
const tabsEl=$('#tabs');
DATA.sections.forEach((s,i)=>{
  const b=document.createElement('button'); b.className='tab'; b.textContent=s.title;
  b.setAttribute('role','tab'); b.setAttribute('aria-selected',i===0?'true':'false');
  b.onclick=()=>{[...tabsEl.children].forEach(x=>x.setAttribute('aria-selected','false'));b.setAttribute('aria-selected','true');render(i);};
  tabsEl.appendChild(b);
});

let CUR=null, ITEMS=[], sortKey='score', sortDir=-1;
function render(idx){
  const sec=DATA.sections[idx]; CUR=sec.currency; ITEMS=sec.items.slice();
  renderKPIs(sec); renderPressure(); renderRank('turnover',x=>x.derived?.turnover_krw,krwC);
  renderRank('mktcap',x=>x.derived?.market_cap_krw,krwC); renderPosition();
  renderSectors(); setupRadar(); renderTable(); requestAnimationFrame(drawScatter);
}

function renderKPIs(sec){
  const it=sec.items;
  const ups=it.filter(x=>x.price?.change_rate>0).length, downs=it.filter(x=>x.price?.change_rate<0).length;
  const avg=it.reduce((a,x)=>a+(x.price?.change_rate||0),0)/(it.length||1);
  const sc=it.map(x=>x.analysis?.signal?.score).filter(v=>v!=null);
  const aScore=sc.length?Math.round(sc.reduce((a,b)=>a+b,0)/sc.length):null;
  const tot=it.reduce((a,x)=>a+(x.derived?.turnover_krw||0),0);
  const strong=it.slice().sort((a,b)=>(b.analysis?.signal?.score??-99)-(a.analysis?.signal?.score??-99))[0];
  const cards=[
    ['종목 수', it.length, ''],
    ['상승 / 하락', `<span class="up">${ups}</span> / <span class="down">${downs}</span>`,''],
    ['평균 등락률', `<span class="${dcls(avg)}">${pct(avg)}</span>`,''],
    ['평균 신호', aScore==null?'—':`<span class="${aScore>0?'up':aScore<0?'down':'flat'}">${aScore>0?'+':''}${aScore}</span>`,'−100~+100'],
    ['총 거래대금', krwC(tot), tot?'원':''],
    ['최강 종목', strong?`${strong.name}`:'—', strong?`신호 ${strong.analysis?.signal?.score>0?'+':''}${strong.analysis?.signal?.score}`:''],
  ];
  $('#kpis').innerHTML=cards.map(([k,v,s])=>`<div class="kpi"><div class="k">${k}</div><div class="v">${v} ${s?`<small>${s}</small>`:''}</div></div>`).join('');
}

function renderPressure(){
  const el=$('#pressure');
  const arr=ITEMS.filter(x=>x.derived?.imbalance!=null).sort((a,b)=>b.derived.imbalance-a.derived.imbalance);
  if(!arr.length){el.innerHTML='<div class="empty">호가 데이터 없음</div>';return;}
  el.innerHTML=arr.map(x=>{
    const im=x.derived.imbalance, w=Math.min(50,Math.abs(im)*50);
    const bar=im>=0?`<i class="buy" style="width:${w}%"></i>`:`<i class="sell" style="width:${w}%"></i>`;
    return `<div class="row"><span class="nm" title="${x.name}">${x.name}</span>
      <div class="dv"><div class="mid"></div>${bar}</div>
      <span class="val ${dcls(im)}">${(im>=0?'+':'')+(im*100).toFixed(0)}</span></div>`;
  }).join('');
}

function renderRank(id,getv,fmt){
  const el=$('#'+id);
  const arr=ITEMS.filter(x=>getv(x)!=null).sort((a,b)=>getv(b)-getv(a)).slice(0,8);
  if(!arr.length){el.innerHTML='<div class="empty">데이터 없음</div>';return;}
  const mx=getv(arr[0])||1;
  el.innerHTML=arr.map(x=>`<div class="row"><span class="nm" title="${x.name}">${x.name}</span>
    <div class="bar"><i style="width:${Math.max(3,getv(x)/mx*100)}%"></i></div>
    <span class="val">${fmt(getv(x))}</span></div>`).join('');
}

function renderPosition(){
  const el=$('#position');
  const arr=ITEMS.filter(x=>x.analysis?.pos_52w!=null).sort((a,b)=>b.analysis.pos_52w-a.analysis.pos_52w);
  if(!arr.length){el.innerHTML='<div class="empty">데이터 없음</div>';return;}
  el.innerHTML=arr.map(x=>{
    const p=x.analysis.pos_52w, intr=x.derived?.intraday_pos;
    return `<div class="pos"><span class="nm" title="${x.name}">${x.name}</span>
      <div class="track"><div class="mk" style="left:${Math.max(1,Math.min(99,p))}%"></div></div>
      <span class="val tnum">${p.toFixed(0)}%${intr!=null?` <span class="flat" style="font-size:11px">·${intr.toFixed(0)}</span>`:''}</span></div>`;
  }).join('');
}

/* ---- sectors ---- */
function renderSectors(){
  const el=$('#sectors'); const g={};
  ITEMS.forEach(x=>{const s=x.sector||'기타';(g[s]=g[s]||[]).push(x);});
  const tot=ITEMS.reduce((a,x)=>a+(x.derived?.turnover_krw||0),0)||1;
  const arr=Object.entries(g).map(([s,its])=>{
    const chg=its.reduce((a,x)=>a+(x.price?.change_rate||0),0)/its.length;
    const sc=its.map(x=>x.analysis?.signal?.score).filter(v=>v!=null);
    const sig=sc.length?Math.round(sc.reduce((a,b)=>a+b,0)/sc.length):null;
    const turn=its.reduce((a,x)=>a+(x.derived?.turnover_krw||0),0);
    return {s,n:its.length,chg,sig,turn,share:turn/tot*100};
  }).sort((a,b)=>b.turn-a.turn);
  el.innerHTML=arr.map(r=>`<div class="srow">
    <div><span class="st">${r.s}</span><span class="cnt">${r.n}종목</span></div>
    <div class="met">등락 <b class="${dcls(r.chg)}">${pct(r.chg)}</b> · 신호 <b class="${r.sig>0?'up':r.sig<0?'down':'flat'}">${r.sig==null?'—':(r.sig>0?'+':'')+r.sig}</b> · 대금 ${r.share.toFixed(0)}%</div>
    <div class="sbar"><i style="width:${Math.max(2,r.share)}%"></i></div>
  </div>`).join('');
}

/* ---- radar (경쟁사 비교) ---- */
const RADAR_AXES=[
  ['모멘텀',x=>x.analysis?.ret_20d],
  ['저변동성',x=>x.analysis?.volatility!=null?-x.analysis.volatility:null],
  ['거래대금',x=>x.derived?.turnover_krw],
  ['시가총액',x=>x.derived?.market_cap_krw],
  ['상대강도',x=>x.analysis?.rsi14],
  ['52주위치',x=>x.analysis?.pos_52w],
  ['매수압력',x=>x.derived?.imbalance],
];
const RADAR_PAL=['#3182F6','#F04452','#7A5AF8','#15B36B','#F5A524','#00B8D9'];
let radarSel=new Set(), radarPct=[];
function pctRank(vals,v){ if(v==null)return null; const u=vals.filter(x=>x!=null); if(!u.length)return null;
  const le=u.filter(x=>x<=v).length; return le/u.length*100; }
function setupRadar(){
  // 축별 백분위 사전 계산
  radarPct=RADAR_AXES.map(([_,g])=>{const vals=ITEMS.map(g);return ITEMS.map(x=>pctRank(vals,g(x)));});
  // 기본 선택: 거래대금 상위 3
  radarSel=new Set(ITEMS.slice().sort((a,b)=>(b.derived?.turnover_krw||0)-(a.derived?.turnover_krw||0)).slice(0,3).map(x=>x.code));
  const lg=$('#radarLegend');
  lg.innerHTML=ITEMS.map((x,i)=>`<button class="chip" data-code="${x.code}" aria-pressed="${radarSel.has(x.code)}">
    <span class="dot" data-i="${i}"></span>${x.name}</button>`).join('');
  lg.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{const cd=c.dataset.code;
    if(radarSel.has(cd))radarSel.delete(cd);else{if(radarSel.size>=5)return;radarSel.add(cd);}
    c.setAttribute('aria-pressed',radarSel.has(cd)); paintChips(); drawRadar();});
  paintChips(); requestAnimationFrame(drawRadar);
}
function paintChips(){
  const sel=[...radarSel];
  $('#radarLegend').querySelectorAll('.chip').forEach(c=>{
    const idx=sel.indexOf(c.dataset.code);
    c.querySelector('.dot').style.background = idx>=0 ? RADAR_PAL[idx%RADAR_PAL.length] : 'var(--faint)';
  });
}
function drawRadar(){
  const cv=$('#radar'); if(!cv)return; const dpr=devicePixelRatio||1;
  const w=cv.clientWidth||340, h=320; cv.width=w*dpr; cv.height=h*dpr;
  const ctx=cv.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,w,h);
  const cx=w/2, cy=h/2+6, R=Math.min(w,h)/2-38, N=RADAR_AXES.length;
  const ang=i=>-Math.PI/2 + i/N*2*Math.PI;
  const line=cssv('--line'), faint=cssv('--faint');
  // rings
  ctx.strokeStyle=line;ctx.fillStyle=faint;ctx.font='10px '+cssv('--mono');
  for(let r=1;r<=4;r++){ctx.globalAlpha=.6;ctx.beginPath();
    for(let i=0;i<=N;i++){const a=ang(i%N),rr=R*r/4;const x=cx+Math.cos(a)*rr,y=cy+Math.sin(a)*rr;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();ctx.globalAlpha=1;}
  // spokes + labels
  ctx.textAlign='center';ctx.textBaseline='middle';
  RADAR_AXES.forEach((ax,i)=>{const a=ang(i);const x=cx+Math.cos(a)*R,y=cy+Math.sin(a)*R;
    ctx.strokeStyle=line;ctx.globalAlpha=.6;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(x,y);ctx.stroke();ctx.globalAlpha=1;
    const lx=cx+Math.cos(a)*(R+20),ly=cy+Math.sin(a)*(R+16);
    ctx.fillStyle=cssv('--muted');ctx.font='600 11px '+cssv('--sans');ctx.fillText(ax[0],lx,ly);});
  // series
  const sel=[...radarSel];
  sel.forEach((code,si)=>{const it=ITEMS.find(x=>x.code===code);if(!it)return;
    const idx=ITEMS.indexOf(it);const col=RADAR_PAL[si%RADAR_PAL.length];
    ctx.beginPath();
    RADAR_AXES.forEach((_,i)=>{const v=(radarPct[i][idx]??0)/100;const a=ang(i);
      const x=cx+Math.cos(a)*R*v,y=cy+Math.sin(a)*R*v;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});
    ctx.closePath();ctx.fillStyle=col+'24';ctx.fill();ctx.strokeStyle=col;ctx.lineWidth=2;ctx.stroke();
    RADAR_AXES.forEach((_,i)=>{const v=(radarPct[i][idx]??0)/100;const a=ang(i);
      const x=cx+Math.cos(a)*R*v,y=cy+Math.sin(a)*R*v;ctx.beginPath();ctx.arc(x,y,2.6,0,7);ctx.fillStyle=col;ctx.fill();});
  });
  if(!sel.length){ctx.fillStyle=faint;ctx.font='13px '+cssv('--sans');ctx.fillText('칩을 선택하세요',cx,cy);}
}

/* ---- detail table ---- */
const COLS=[
  ['종목',x=>x.name,'name'],['섹터',x=>x.sector||'—','sector'],['현재가',x=>fmtP(x.price?.last,CUR),'last'],
  ['등락',x=>`<span class="${dcls(x.price?.change_rate)}">${pct(x.price?.change_rate)}</span>`,'chg'],
  ['거래대금',x=>krwC(x.derived?.turnover_krw),'turn'],['시총',x=>krwC(x.derived?.market_cap_krw),'cap'],
  ['호가',x=>x.derived?.imbalance!=null?`<span class="${dcls(x.derived.imbalance)}">${(x.derived.imbalance>=0?'+':'')+(x.derived.imbalance*100).toFixed(0)}</span>`:'—','imb'],
  ['RSI',x=>x.analysis?.rsi14!=null?x.analysis.rsi14.toFixed(0):'—','rsi'],
  ['20일%',x=>`<span class="${dcls(x.analysis?.ret_20d)}">${pct(x.analysis?.ret_20d)}</span>`,'r20'],
  ['변동성',x=>x.analysis?.volatility!=null?x.analysis.volatility.toFixed(0)+'%':'—','vol'],
  ['52주%',x=>x.analysis?.pos_52w!=null?x.analysis.pos_52w.toFixed(0)+'%':'—','p52'],
  ['신호',x=>{const s=x.analysis?.signal;return s?`<span class="badge ${s.score>0?'up':s.score<0?'down':'flat'} ${s.score>0?'up':s.score<0?'down':''}">${s.label} ${s.score>0?'+':''}${s.score}</span>`:'—';},'score'],
];
const SORTV={name:x=>x.name,sector:x=>x.sector||'',last:x=>x.price?.last,chg:x=>x.price?.change_rate,turn:x=>x.derived?.turnover_krw,
  cap:x=>x.derived?.market_cap_krw,imb:x=>x.derived?.imbalance,rsi:x=>x.analysis?.rsi14,
  r20:x=>x.analysis?.ret_20d,vol:x=>x.analysis?.volatility,p52:x=>x.analysis?.pos_52w,score:x=>x.analysis?.signal?.score};
function renderTable(){
  const t=$('#tbl');
  const rows=ITEMS.slice().sort((a,b)=>{
    const va=SORTV[sortKey]?.(a), vb=SORTV[sortKey]?.(b);
    if(va==null)return 1; if(vb==null)return -1;
    if(typeof va==='string')return sortDir*va.localeCompare(vb);
    return sortDir*(va-vb);
  });
  t.innerHTML='<thead><tr>'+COLS.map(c=>`<th data-k="${c[2]}">${c[0]}${sortKey===c[2]?(sortDir<0?' ▾':' ▴'):''}</th>`).join('')+'</tr></thead>'
    +'<tbody>'+rows.map(x=>'<tr>'+COLS.map(c=>`<td>${c[1](x)}</td>`).join('')+'</tr>').join('')+'</tbody>';
  t.querySelectorAll('th').forEach(th=>th.onclick=()=>{const k=th.dataset.k; if(sortKey===k)sortDir*=-1;else{sortKey=k;sortDir=-1;} renderTable();});
}

/* ---- scatter ---- */
let pts=[];
function drawScatter(){
  const cv=$('#scatter'), tip=$('#tip'); const dpr=devicePixelRatio||1;
  const w=cv.clientWidth||600, h=340; cv.width=w*dpr; cv.height=h*dpr;
  const ctx=cv.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,w,h);
  const data=ITEMS.filter(x=>x.analysis?.ret_20d!=null&&x.analysis?.volatility!=null);
  const pad={l:44,r:16,t:14,b:34};
  const xs=data.map(d=>d.analysis.ret_20d), ys=data.map(d=>d.analysis.volatility);
  if(!data.length){ctx.fillStyle=cssv('--faint');ctx.font='13px sans-serif';ctx.textAlign='center';ctx.fillText('데이터 없음',w/2,h/2);pts=[];return;}
  let xmin=Math.min(0,...xs),xmax=Math.max(0,...xs); const xpad=(xmax-xmin)*0.12||1; xmin-=xpad;xmax+=xpad;
  let ymin=0,ymax=Math.max(...ys)*1.12||1;
  const X=v=>pad.l+(v-xmin)/(xmax-xmin)*(w-pad.l-pad.r);
  const Y=v=>h-pad.b-(v-ymin)/(ymax-ymin)*(h-pad.t-pad.b);
  const line=cssv('--line'), muted=cssv('--faint');
  // grid
  ctx.strokeStyle=line;ctx.lineWidth=1;ctx.fillStyle=muted;ctx.font='11px '+cssv('--mono');ctx.textAlign='center';
  for(let i=0;i<=4;i++){const gx=pad.l+i/4*(w-pad.l-pad.r);ctx.globalAlpha=.5;ctx.beginPath();ctx.moveTo(gx,pad.t);ctx.lineTo(gx,h-pad.b);ctx.stroke();ctx.globalAlpha=1;ctx.fillText((xmin+i/4*(xmax-xmin)).toFixed(0)+'%',gx,h-pad.b+16);}
  ctx.textAlign='right';
  for(let i=0;i<=4;i++){const gy=h-pad.b-i/4*(h-pad.t-pad.b);ctx.globalAlpha=.5;ctx.beginPath();ctx.moveTo(pad.l,gy);ctx.lineTo(w-pad.r,gy);ctx.stroke();ctx.globalAlpha=1;ctx.fillText((ymin+i/4*(ymax-ymin)).toFixed(0),pad.l-6,gy+3);}
  // zero-x line
  ctx.strokeStyle=muted;ctx.globalAlpha=.6;ctx.beginPath();ctx.moveTo(X(0),pad.t);ctx.lineTo(X(0),h-pad.b);ctx.stroke();ctx.globalAlpha=1;
  // points
  const turns=data.map(d=>d.derived?.turnover_krw||0); const tmax=Math.max(...turns,1);
  pts=data.map(d=>{
    const sc=d.analysis?.signal?.score??0;
    const col=sc>15?cssv('--up'):sc<-15?cssv('--down'):cssv('--flat');
    const r=6+Math.sqrt((d.derived?.turnover_krw||0)/tmax)*16;
    const px=X(d.analysis.ret_20d),py=Y(d.analysis.volatility);
    ctx.beginPath();ctx.arc(px,py,r,0,7);ctx.fillStyle=col+'2E';ctx.fill();
    ctx.beginPath();ctx.arc(px,py,r,0,7);ctx.strokeStyle=col;ctx.lineWidth=1.8;ctx.stroke();
    ctx.beginPath();ctx.arc(px,py,2.2,0,7);ctx.fillStyle=col;ctx.fill();
    return {px,py,r,d};
  });
  // labels for top-3 turnover
  ctx.fillStyle=cssv('--ink');ctx.font='700 11px '+cssv('--sans');ctx.textAlign='center';
  data.map((d,i)=>({d,t:turns[i]})).sort((a,b)=>b.t-a.t).slice(0,3).forEach(({d})=>{
    const p=pts.find(p=>p.d===d); if(p)ctx.fillText(d.name,p.px,p.py-p.r-4);
  });
  cv.onmousemove=e=>{const rc=cv.getBoundingClientRect();const mx=e.clientX-rc.left,my=e.clientY-rc.top;
    let hit=null;for(const p of pts){if(Math.hypot(p.px-mx,p.py-my)<=p.r+2){hit=p;break;}}
    if(hit){const a=hit.d.analysis;tip.innerHTML=`<b>${hit.d.name}</b> · 20일 ${pct(a.ret_20d)} · 변동성 ${a.volatility.toFixed(0)}% · 거래대금 ${krwC(hit.d.derived?.turnover_krw)}`;
      tip.style.left=hit.px+'px';tip.style.top=hit.py+'px';tip.style.opacity=1;}else tip.style.opacity=0;};
  cv.onmouseleave=()=>tip.style.opacity=0;
}
addEventListener('resize',()=>requestAnimationFrame(()=>{drawScatter();drawRadar();}));

$('#note').innerHTML = DATA.mode==='demo'
  ? '<b>샘플(오프라인) 미리보기입니다.</b> 실제 시세가 아닌 UI 확인용 합성 데이터입니다. 저장소의 <code>./run.sh</code>(또는 <code>python main.py</code>)를 본인 PC에서 실행하면 토스 Open API에 연결해 실데이터로 이 대시보드를 생성합니다.'
  : '<b>데이터 출처.</b> 현재가/호가/캔들/기업정보/환율 = 토스 Open API. 호가·발행주식수·환율은 응답에 포함될 때만 채워지며, 누락 시 해당 패널은 "데이터 없음"으로 표시됩니다. 모든 지표는 참고용이며 투자자문이 아닙니다.';

render(0);
</script>
"""
