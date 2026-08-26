/* ============================================================
   ui.js — DOM 헬퍼 (템플릿 문자열 기반, 프레임워크 없음)
   ============================================================ */

/** HTML 이스케이프 — 사용자 입력이 마크업으로 해석되지 않도록 */
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* 단일 파일 빌드에서는 페이지가 시작한 다운로드가 뷰어에서 차단된다.
   빌드 시 GENIE_STANDALONE 이 true 로 치환되면 아래 상수가 false 로 접히고,
   번들러가 다운로드 구현 자체를 산출물에서 제거한다.
   번들되지 않은 원본에서는 typeof 검사로 안전하게 true 가 된다. */
export const CAN_DOWNLOAD =
  typeof GENIE_STANDALONE === 'undefined' || !GENIE_STANDALONE;

export const h = (strings, ...vals) =>
  strings.reduce((out, s, i) => out + s + (i < vals.length ? (vals[i] ?? '') : ''), '');

export const qs  = (sel, root = document) => root.querySelector(sel);
export const qsa = (sel, root = document) => [...root.querySelectorAll(sel)];

/** 선택형 칩 그룹 */
export function chipGroup({ name, options, value, multi = false }) {
  const sel = multi ? new Set(value || []) : new Set([value]);
  return `<div class="chip-grid" data-chips="${esc(name)}" data-multi="${multi}">` +
    options.map(o => {
      const v = typeof o === 'object' ? o.id ?? o.value : o;
      const l = typeof o === 'object' ? o.label : o;
      return `<button type="button" class="chip" data-val="${esc(v)}"
        aria-pressed="${sel.has(v) || sel.has(String(v))}">${esc(l)}</button>`;
    }).join('') + '</div>';
}

/** 칩 그룹 이벤트 위임 바인딩 */
export function bindChips(root, onChange) {
  root.addEventListener('click', e => {
    const btn = e.target.closest('.chip');
    if (!btn) return;
    const group = btn.closest('[data-chips]');
    if (!group) return;
    const multi = group.dataset.multi === 'true';
    if (multi) {
      btn.setAttribute('aria-pressed', btn.getAttribute('aria-pressed') !== 'true');
    } else {
      group.querySelectorAll('.chip').forEach(c => c.setAttribute('aria-pressed', 'false'));
      btn.setAttribute('aria-pressed', 'true');
    }
    const vals = [...group.querySelectorAll('.chip[aria-pressed="true"]')].map(c => c.dataset.val);
    onChange(group.dataset.chips, multi ? vals : vals[0], group);
  });
}

/** 프롬프트 출력 박스 */
export function promptBox(title, body, id) {
  return `
  <div class="prompt-box" id="${esc(id)}">
    <div class="prompt-head">
      <span class="t">📋 ${esc(title)}</span>
      <span style="display:flex;gap:7px">
        <button class="btn btn-gold btn-sm" data-copy="${esc(id)}">복사</button>
        ${CAN_DOWNLOAD ? `<button class="btn btn-ghost btn-sm" data-dl="${esc(id)}">.txt</button>` : ''}
      </span>
    </div>
    <div class="prompt-body" data-prompt-text>${esc(body)}</div>
    <div class="prompt-foot">
      ⚡ 복사 후 ChatGPT / Claude / Gemini / Perplexity에 붙여넣으세요.
      웹 검색 기능을 켜면 실시간 데이터 분석이 가능합니다.
    </div>
  </div>`;
}

export function bindPromptBox(root) {
  root.addEventListener('click', async e => {
    const copyBtn = e.target.closest('[data-copy]');
    const dlBtn = CAN_DOWNLOAD ? e.target.closest('[data-dl]') : null;
    const box = copyBtn || dlBtn;
    if (!box) return;
    const id = box.dataset.copy || box.dataset.dl;
    const el = document.getElementById(id);
    const text = el?.querySelector('[data-prompt-text]')?.textContent || '';
    if (copyBtn) {
      try {
        await navigator.clipboard.writeText(text);
        toast('프롬프트를 복사했습니다');
      } catch {
        // 클립보드 권한 거부 시 선택 폴백
        const range = document.createRange();
        range.selectNodeContents(el.querySelector('[data-prompt-text]'));
        const sel = window.getSelection();
        sel.removeAllRanges(); sel.addRange(range);
        toast('Ctrl+C 로 복사하세요 (자동 복사 차단됨)');
      }
    } else if (CAN_DOWNLOAD) {
      const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `genie-${id}.txt`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }
  });
}

let toastTimer;
export function toast(msg) {
  let el = document.querySelector('.toast');
  if (!el) {
    el = document.createElement('div');
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  requestAnimationFrame(() => el.classList.add('show'));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}

/** 표 생성 헬퍼 */
export function table(headers, rows) {
  return `<div class="tbl-wrap"><table class="tbl">
    <thead><tr>${headers.map(hd => `<th>${hd}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div>`;
}

export function stat(k, v, n) {
  return `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v}</div>${n ? `<div class="n">${esc(n)}</div>` : ''}</div>`;
}
