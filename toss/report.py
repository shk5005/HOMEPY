"""분석 결과를 자체 완결형 인터랙티브 HTML 대시보드로 렌더링.

외부 리소스/폰트/스크립트를 전혀 사용하지 않으므로(CSP 안전) 파일 하나만 있으면
어디서든 열립니다. 차트는 순수 canvas 로 그립니다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def build_html(report: dict) -> str:
    data_json = json.dumps(report, ensure_ascii=False)
    generated = report.get("generated_at") or datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    mode = report.get("mode", "live")
    return _TEMPLATE.replace("__DATA__", data_json).replace("__GENERATED__", generated).replace("__MODE__", mode)


def build_report(sections: list[dict], mode: str = "live") -> dict:
    return {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "mode": mode,
        "sections": sections,
    }


_TEMPLATE = r"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>토스증권 국내·국외 주식 분석</title>
<style>
:root{
  --bg:#F5F7FA; --surface:#FFFFFF; --surface-2:#F0F3F7;
  --ink:#0F1826; --muted:#5C6B82; --faint:#8A97AC; --line:#E6EAF0;
  --accent:#3182F6; --up:#F04452; --down:#3182F6; --flat:#8A97AC;
  --shadow:0 1px 2px rgba(16,24,40,.04),0 8px 24px rgba(16,24,40,.06);
  --radius:16px;
  --mono:'SFMono-Regular','JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
  --sans:'Pretendard',-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','Segoe UI',Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0A0D13; --surface:#131822; --surface-2:#1B222E;
  --ink:#E8EDF5; --muted:#94A0B3; --faint:#66738A; --line:#232B39;
  --accent:#4C93FF; --up:#FF5A66; --down:#4C93FF; --flat:#66738A;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35);
}}
:root[data-theme="light"]{
  --bg:#F5F7FA; --surface:#FFFFFF; --surface-2:#F0F3F7;
  --ink:#0F1826; --muted:#5C6B82; --faint:#8A97AC; --line:#E6EAF0;
  --accent:#3182F6; --up:#F04452; --down:#3182F6; --flat:#8A97AC;
  --shadow:0 1px 2px rgba(16,24,40,.04),0 8px 24px rgba(16,24,40,.06);
}
:root[data-theme="dark"]{
  --bg:#0A0D13; --surface:#131822; --surface-2:#1B222E;
  --ink:#E8EDF5; --muted:#94A0B3; --faint:#66738A; --line:#232B39;
  --accent:#4C93FF; --up:#FF5A66; --down:#4C93FF; --flat:#66738A;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;line-height:1.45}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 72px}
.tnum{font-variant-numeric:tabular-nums}
.mono{font-family:var(--mono)}

header.top{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 86%,transparent);
  backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.top-in{max-width:1180px;margin:0 auto;padding:14px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:11px;margin-right:auto}
.mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,var(--accent),#1B64DA);
  display:grid;place-items:center;color:#fff;font-weight:800;font-size:15px;box-shadow:0 3px 10px rgba(49,130,246,.35)}
.brand h1{font-size:16px;margin:0;letter-spacing:-.01em;font-weight:700}
.brand .sub{font-size:12px;color:var(--muted)}
.pill{font-size:11px;font-weight:700;padding:4px 9px;border-radius:999px;letter-spacing:.02em}
.pill.live{background:color-mix(in srgb,var(--up) 14%,transparent);color:var(--up)}
.pill.demo{background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent)}
.meta{font-size:12px;color:var(--muted)}
.icon-btn{border:1px solid var(--line);background:var(--surface);color:var(--muted);width:34px;height:34px;
  border-radius:10px;cursor:pointer;display:grid;place-items:center;font-size:15px}
.icon-btn:hover{color:var(--ink);border-color:var(--accent)}

.hero{padding:30px 0 8px}
.hero h2{font-size:clamp(22px,3.4vw,32px);margin:0 0 6px;letter-spacing:-.02em;text-wrap:balance;font-weight:800}
.hero p{margin:0;color:var(--muted);max-width:60ch;font-size:14px}

.tabs{display:flex;gap:6px;margin:22px 0 18px;background:var(--surface-2);padding:5px;border-radius:12px;width:fit-content}
.tab{border:0;background:transparent;color:var(--muted);font-family:inherit;font-size:14px;font-weight:600;
  padding:8px 18px;border-radius:9px;cursor:pointer}
.tab[aria-selected="true"]{background:var(--surface);color:var(--ink);box-shadow:var(--shadow)}

.breadth{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:22px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:15px 17px;box-shadow:var(--shadow)}
.stat .k{font-size:12px;color:var(--muted);letter-spacing:.02em}
.stat .v{font-size:24px;font-weight:800;margin-top:5px;letter-spacing:-.01em}
.stat .v small{font-size:13px;font-weight:600;color:var(--faint)}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:18px;
  box-shadow:var(--shadow);display:flex;flex-direction:column;gap:13px}
.card-head{display:flex;align-items:flex-start;gap:10px}
.card-head .nm{font-weight:700;font-size:16px;letter-spacing:-.01em}
.card-head .cd{font-size:12px;color:var(--faint)}
.sig{margin-left:auto;font-size:12px;font-weight:800;padding:4px 10px;border-radius:999px;white-space:nowrap}
.price-row{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.price{font-size:27px;font-weight:800;letter-spacing:-.02em}
.chg{font-size:14px;font-weight:700}
.spark{width:100%;height:64px;display:block}
.metrics{display:grid;grid-template-columns:1fr 1fr;gap:9px 16px;font-size:13px}
.metric{display:flex;justify-content:space-between;gap:8px;border-bottom:1px dashed var(--line);padding-bottom:6px}
.metric .l{color:var(--muted)}
.metric .r{font-weight:700}
.range{margin-top:2px}
.range .track{height:6px;border-radius:3px;background:var(--surface-2);position:relative;overflow:hidden}
.range .fill{position:absolute;top:0;bottom:0;left:0;background:linear-gradient(90deg,var(--down),var(--accent),var(--up))}
.range .lab{display:flex;justify-content:space-between;font-size:11px;color:var(--faint);margin-top:4px}
.reasons{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-size:11px;padding:3px 8px;border-radius:7px;background:var(--surface-2);color:var(--muted);font-weight:600}

details.tbl{margin-top:26px;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
details.tbl>summary{cursor:pointer;padding:15px 18px;font-weight:700;font-size:14px;list-style:none}
details.tbl>summary::-webkit-details-marker{display:none}
details.tbl>summary::before{content:"▸ ";color:var(--faint)}
details.tbl[open]>summary::before{content:"▾ "}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:640px;font-size:13px}
th,td{padding:10px 14px;text-align:right;white-space:nowrap;border-top:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:12px;position:sticky;top:0;background:var(--surface)}
td:first-child,th:first-child{text-align:left}

.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)}
.sig.up{background:color-mix(in srgb,var(--up) 14%,transparent);color:var(--up)}
.sig.down{background:color-mix(in srgb,var(--down) 14%,transparent);color:var(--down)}
.sig.flat{background:var(--surface-2);color:var(--muted)}

.note{margin-top:34px;padding:16px 18px;border:1px solid var(--line);border-radius:var(--radius);
  background:var(--surface);color:var(--muted);font-size:12.5px;line-height:1.6}
.note b{color:var(--ink)}
footer{margin-top:26px;text-align:center;color:var(--faint);font-size:12px}
@media (max-width:520px){.metrics{grid-template-columns:1fr}}
</style>

<header class="top">
  <div class="top-in">
    <div class="brand">
      <div class="mark">T</div>
      <div>
        <h1>토스증권 주식 분석</h1>
        <div class="sub">국내 KRX · 국외 US</div>
      </div>
    </div>
    <span class="pill __MODE__" id="modePill"></span>
    <span class="meta" id="genAt">__GENERATED__</span>
    <button class="icon-btn" id="themeBtn" title="테마 전환" aria-label="테마 전환">◐</button>
  </div>
</header>

<div class="wrap">
  <section class="hero">
    <h2>국내·국외 종목 한눈에 분석</h2>
    <p>토스증권 Open API 시세·캔들 데이터를 기반으로 이동평균·RSI·MACD·모멘텀·변동성을 계산해
       종목별 추세 신호를 정리했습니다. 투자 참고용이며 투자자문이 아닙니다.</p>
  </section>

  <div class="tabs" id="tabs" role="tablist"></div>
  <div class="breadth" id="breadth"></div>
  <div class="grid" id="grid"></div>
  <details class="tbl" id="tblWrap"><summary>비교 표 (정렬 가능한 원자료)</summary>
    <div class="scroll"><table id="tbl"></table></div>
  </details>

  <div class="note" id="note"></div>
  <footer>toss-stock-analysis · 자체 생성 정적 리포트 · 외부 리소스 미사용</footer>
</div>

<script>
const DATA = __DATA__;
const $ = (s,el=document)=>el.querySelector(s);

/* ---- theme ---- */
const themeBtn = $('#themeBtn');
themeBtn.onclick = ()=>{
  const cur = document.documentElement.getAttribute('data-theme')
     || (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  const next = cur==='dark'?'light':'dark';
  document.documentElement.setAttribute('data-theme',next);
  redrawSparks();
};

/* ---- helpers ---- */
const cssv = n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function fmt(v,cur){
  if(v==null||isNaN(v)) return '—';
  const dec = cur==='USD' ? 2 : 0;
  return Number(v).toLocaleString('ko-KR',{minimumFractionDigits:dec,maximumFractionDigits:dec});
}
function pct(v){ if(v==null||isNaN(v)) return '—'; return (v>=0?'+':'')+Number(v).toFixed(2)+'%'; }
function dirClass(v){ if(v==null||isNaN(v)||v===0) return 'flat'; return v>0?'up':'down'; }
const sym = {USD:'$', KRW:'₩'};

$('#modePill').textContent = DATA.mode==='demo' ? '● 샘플 데이터' : '● 라이브';

/* ---- tabs ---- */
const tabsEl = $('#tabs');
DATA.sections.forEach((s,i)=>{
  const b=document.createElement('button');
  b.className='tab'; b.textContent=s.title; b.setAttribute('role','tab');
  b.setAttribute('aria-selected', i===0?'true':'false');
  b.onclick=()=>{ [...tabsEl.children].forEach(x=>x.setAttribute('aria-selected','false'));
    b.setAttribute('aria-selected','true'); render(i); };
  tabsEl.appendChild(b);
});

let sparkJobs=[];
function render(idx){
  const sec = DATA.sections[idx];
  const cur = sec.currency;
  renderBreadth(sec,cur);
  renderCards(sec,cur);
  renderTable(sec,cur);
  requestAnimationFrame(redrawSparks);
}

function renderBreadth(sec,cur){
  const items=sec.items;
  const ups=items.filter(x=>x.price.change_rate>0).length;
  const downs=items.filter(x=>x.price.change_rate<0).length;
  const avg=items.reduce((a,x)=>a+(x.price.change_rate||0),0)/(items.length||1);
  const scores=items.map(x=>x.analysis?.signal?.score).filter(v=>v!=null);
  const avgScore=scores.length?Math.round(scores.reduce((a,b)=>a+b,0)/scores.length):null;
  const el=$('#breadth');
  el.innerHTML='';
  const stats=[
    ['종목 수', items.length, ''],
    ['상승 / 하락', `<span class="up">${ups}</span> / <span class="down">${downs}</span>`, ''],
    ['평균 등락률', `<span class="${dirClass(avg)}">${pct(avg)}</span>`, ''],
    ['평균 신호점수', avgScore==null?'—':`<span class="${avgScore>0?'up':avgScore<0?'down':'flat'}">${avgScore>0?'+':''}${avgScore}</span>`, '−100~+100'],
  ];
  stats.forEach(([k,v,s])=>{
    const d=document.createElement('div'); d.className='stat';
    d.innerHTML=`<div class="k">${k}</div><div class="v">${v} ${s?`<small>${s}</small>`:''}</div>`;
    el.appendChild(d);
  });
}

function renderCards(sec,cur){
  const grid=$('#grid'); grid.innerHTML=''; sparkJobs=[];
  sec.items.forEach(it=>{
    const p=it.price, a=it.analysis||{}, sg=a.signal||{};
    const dc=dirClass(p.change_rate);
    const sigCls = sg.score>15?'up':sg.score<-15?'down':'flat';
    const card=document.createElement('div'); card.className='card';
    const reasons=(sg.reasons||[]).slice(0,4).map(r=>`<span class="chip">${r}</span>`).join('');
    const pos = a.pos_52w;
    card.innerHTML=`
      <div class="card-head">
        <div>
          <div class="nm">${it.name||it.code}</div>
          <div class="cd mono">${it.code}${p.market?' · '+p.market:''}</div>
        </div>
        <span class="sig ${sigCls}">${sg.label||'—'} ${sg.score!=null?(sg.score>0?'+':'')+sg.score:''}</span>
      </div>
      <div class="price-row">
        <span class="price tnum">${sym[cur]||''}${fmt(p.last,cur)}</span>
        <span class="chg tnum ${dc}">${pct(p.change_rate)} ${p.change!=null?`(${p.change>0?'+':''}${fmt(p.change,cur)})`:''}</span>
      </div>
      <canvas class="spark"></canvas>
      <div class="metrics">
        ${metric('RSI(14)', a.rsi14!=null?a.rsi14.toFixed(0):'—', a.rsi14>=70?'up':a.rsi14<=30?'down':'')}
        ${metric('20일선 대비', ma(p.last,a.sma20))}
        ${metric('60일선 대비', ma(p.last,a.sma60))}
        ${metric('연율변동성', a.volatility!=null?a.volatility.toFixed(0)+'%':'—')}
        ${metric('20일수익률', pct(a.ret_20d), dirClass(a.ret_20d))}
        ${metric('60일수익률', pct(a.ret_60d), dirClass(a.ret_60d))}
      </div>
      ${pos!=null?`<div class="range">
        <div class="track"><div class="fill" style="width:${Math.max(2,Math.min(100,pos))}%"></div></div>
        <div class="lab"><span>52주최저 ${fmt(a.lo_52w,cur)}</span><span>${pos.toFixed(0)}%</span><span>${fmt(a.hi_52w,cur)} 최고</span></div>
      </div>`:''}
      <div class="reasons">${reasons}</div>`;
    grid.appendChild(card);
    sparkJobs.push({canvas:card.querySelector('.spark'), series:it.candles||[], dir:dc});
  });
}
function metric(l,r,cls=''){ return `<div class="metric"><span class="l">${l}</span><span class="r ${cls}">${r}</span></div>`; }
function ma(last,m){ if(last==null||m==null) return '—'; const d=(last/m-1)*100; return `<span class="${dirClass(d)}">${pct(d)}</span>`; }

function renderTable(sec,cur){
  const t=$('#tbl');
  const cols=[['종목','name'],['코드','code'],['현재가','last'],['등락률','change_rate'],
    ['RSI','rsi14'],['20일%','ret_20d'],['60일%','ret_60d'],['변동성','volatility'],['52주%','pos_52w'],['신호','score']];
  let head='<thead><tr>'+cols.map(c=>`<th>${c[0]}</th>`).join('')+'</tr></thead>';
  let rows=sec.items.map(it=>{
    const p=it.price,a=it.analysis||{},sg=a.signal||{};
    return `<tr>
      <td>${it.name||it.code}</td><td class="mono">${it.code}</td>
      <td class="tnum">${sym[cur]||''}${fmt(p.last,cur)}</td>
      <td class="tnum ${dirClass(p.change_rate)}">${pct(p.change_rate)}</td>
      <td class="tnum">${a.rsi14!=null?a.rsi14.toFixed(0):'—'}</td>
      <td class="tnum ${dirClass(a.ret_20d)}">${pct(a.ret_20d)}</td>
      <td class="tnum ${dirClass(a.ret_60d)}">${pct(a.ret_60d)}</td>
      <td class="tnum">${a.volatility!=null?a.volatility.toFixed(0)+'%':'—'}</td>
      <td class="tnum">${a.pos_52w!=null?a.pos_52w.toFixed(0)+'%':'—'}</td>
      <td class="tnum ${sg.score>0?'up':sg.score<0?'down':'flat'}">${sg.score!=null?(sg.score>0?'+':'')+sg.score:'—'}</td>
    </tr>`;
  }).join('');
  t.innerHTML=head+'<tbody>'+rows+'</tbody>';
}

/* ---- sparklines ---- */
function drawSpark(canvas, series, dir){
  const vals=series.map(c=>c.close).filter(v=>v!=null);
  const dpr=devicePixelRatio||1, w=canvas.clientWidth||300, h=64;
  canvas.width=w*dpr; canvas.height=h*dpr;
  const ctx=canvas.getContext('2d'); ctx.scale(dpr,dpr); ctx.clearRect(0,0,w,h);
  if(vals.length<2) return;
  const mn=Math.min(...vals), mx=Math.max(...vals), rng=(mx-mn)||1, pad=6;
  const col = dir==='up'?cssv('--up'):dir==='down'?cssv('--down'):cssv('--flat');
  const X=i=>pad+i*(w-2*pad)/(vals.length-1);
  const Y=v=>h-pad-(v-mn)/rng*(h-2*pad);
  // area
  const g=ctx.createLinearGradient(0,0,0,h);
  g.addColorStop(0,col+'33'); g.addColorStop(1,col+'00');
  ctx.beginPath(); ctx.moveTo(X(0),Y(vals[0]));
  vals.forEach((v,i)=>ctx.lineTo(X(i),Y(v)));
  ctx.lineTo(X(vals.length-1),h-pad); ctx.lineTo(X(0),h-pad); ctx.closePath();
  ctx.fillStyle=g; ctx.fill();
  // line
  ctx.beginPath(); ctx.moveTo(X(0),Y(vals[0]));
  vals.forEach((v,i)=>ctx.lineTo(X(i),Y(v)));
  ctx.strokeStyle=col; ctx.lineWidth=1.8; ctx.lineJoin='round'; ctx.stroke();
  // endpoint
  ctx.beginPath(); ctx.arc(X(vals.length-1),Y(vals[vals.length-1]),2.6,0,7); ctx.fillStyle=col; ctx.fill();
}
function redrawSparks(){ sparkJobs.forEach(j=>drawSpark(j.canvas,j.series,j.dir)); }
addEventListener('resize',()=>requestAnimationFrame(redrawSparks));

/* ---- note ---- */
$('#note').innerHTML = DATA.mode==='demo'
  ? '<b>샘플(오프라인) 미리보기입니다.</b> 실제 시세가 아니라 UI 확인용 예시 데이터입니다. '
    +'저장소의 <span class="mono">python main.py</span> 를 본인 PC에서 실행하면 토스증권 Open API에 연결해 '
    +'실데이터로 이 리포트를 다시 생성합니다.'
  : '<b>안내.</b> 토스증권 Open API 데이터 기반 자동 계산 결과입니다. 지표는 참고용이며 투자 판단·손익 책임은 본인에게 있습니다. 투자자문이 아닙니다.';

render(0);
</script>
"""
