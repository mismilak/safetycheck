// Shared helpers: safe templating, API client, formatters, modal, toast, alarm detail dialog.

// ---------- safe HTML templating (auto-escapes interpolations) ----------
class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
export const raw = (s) => new Raw(s);
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
const fmt = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(fmt).join('') : v == null || v === false ? '' : esc(v));
export const html = (strings, ...vals) => new Raw(strings.reduce((o, s, i) => o + s + (i < vals.length ? fmt(vals[i]) : ''), ''));
export const render = (el, tpl) => { el.innerHTML = fmt(tpl); return el; };
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const icon = (n, cls = '') => raw(`<svg class="i ${cls}" aria-hidden="true"><use href="/static/icons/sprite.svg#i-${n}"/></svg>`);

// ---------- state / events ----------
export const state = { user: null, cams: [], status: null, openCount: 0, ws: false };
export const bus = new EventTarget();
export const emit = (type, detail) => bus.dispatchEvent(new CustomEvent(type, { detail }));
export const on = (type, fn) => { const h = (e) => fn(e.detail); bus.addEventListener(type, h); return () => bus.removeEventListener(type, h); };
export const can = (p) => !!state.user && state.user.permissions.includes(p);

export class ApiError extends Error { constructor(msg, status) { super(msg); this.status = status; } }
export async function api(path, { method = 'GET', body, blob } = {}) {
  const opt = { method, credentials: 'same-origin', headers: { 'X-SC': '1' } };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(path, opt); } catch { throw new ApiError('ارتباط با سرور برقرار نشد', 0); }
  if (res.status === 401 && !path.startsWith('/api/auth/login')) emit('unauth');
  if (!res.ok) {
    let msg = 'خطا در انجام عملیات';
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : msg; } catch { /* ignore */ }
    throw new ApiError(msg, res.status);
  }
  return blob ? res.blob() : res.status === 204 ? null : res.json();
}

// ---------- Persian formatting ----------
const NF = new Intl.NumberFormat('fa-IR');
export const fa = (n) => (n == null || Number.isNaN(n) ? '—' : NF.format(n));
export const fa1 = (n) => (n == null ? '—' : new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(n));
const DF = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { year: 'numeric', month: '2-digit', day: '2-digit' });
const DFS = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { month: 'short', day: 'numeric' });
const TF = new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const RF = new Intl.RelativeTimeFormat('fa', { numeric: 'auto' });
export const fdate = (iso) => DF.format(new Date(iso));
export const fdateShort = (iso) => DFS.format(new Date(iso));
export const ftime = (iso) => TF.format(new Date(iso));
export const fdt = (iso) => (iso ? `${fdate(iso)} ${ftime(iso)}` : '—');
export function ago(iso) {
  const s = Math.round((new Date(iso) - Date.now()) / 1000);
  const a = Math.abs(s);
  if (a < 60) return RF.format(s, 'second');
  if (a < 3600) return RF.format(Math.round(s / 60), 'minute');
  if (a < 86400) return RF.format(Math.round(s / 3600), 'hour');
  return RF.format(Math.round(s / 86400), 'day');
}
export const tzOffset = () => new Date().getTimezoneOffset();
export function dayRange(days) { // [from, to) ISO in UTC covering the last `days` local days incl. today
  const s = new Date(); s.setHours(0, 0, 0, 0); s.setDate(s.getDate() - (days - 1));
  const e = new Date(); e.setHours(24, 0, 0, 0);
  return { frm: s.toISOString(), to: e.toISOString() };
}

export const KIND = { no_helmet: 'بدون کلاه ایمنی', no_vest: 'بدون لباس کار', no_both: 'بدون کلاه و لباس کار' };
export const SEVERITY = { high: 'بالا', medium: 'متوسط' };
export const STATUS = { new: 'جدید', ack: 'رسیدگی شد', false_positive: 'هشدار کاذب' };
export const statusBadge = (s) => html`<span class="badge ${s === 'new' ? 'danger' : s === 'ack' ? 'safe' : ''}">${STATUS[s] || s}</span>`;
export const sevBadge = (s) => html`<span class="badge ${s === 'high' ? 'danger' : 'warn'}">${icon('triangle-alert')} ${SEVERITY[s] || s}</span>`;
export const kindLabel = (k) => KIND[k] || k;

// ---------- modal / toast ----------
export function openModal({ title, body, footer, wide = false, onClose }) {
  const prev = document.activeElement;
  const ov = document.createElement('div');
  ov.className = 'overlay';
  ov.innerHTML = `<div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
    <div class="modal-h"><h3>${esc(title)}</h3><button class="iconbtn" data-close aria-label="بستن"><svg class="i"><use href="/static/icons/sprite.svg#i-x"/></svg></button></div>
    <div class="modal-b"></div>${footer ? '<div class="modal-f"></div>' : ''}</div>`;
  const b = $('.modal-b', ov);
  render(b, body);
  if (footer) render($('.modal-f', ov), footer);
  const close = () => { ov.remove(); document.removeEventListener('keydown', key); prev?.focus?.(); onClose?.(); };
  const key = (e) => { if (e.key === 'Escape') close(); };
  ov.addEventListener('mousedown', (e) => { if (e.target === ov) close(); });
  ov.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) close(); });
  document.addEventListener('keydown', key);
  document.body.appendChild(ov);
  ($('input,select,textarea', b) || $('[data-close]', ov)).focus({ preventScroll: true });
  return { el: ov, body: b, foot: $('.modal-f', ov), close };
}

export function confirmDialog(message, { okText = 'تأیید', danger = false } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const m = openModal({
      title: 'تأیید عملیات', body: html`<p>${message}</p>`,
      footer: html`<button class="btn ${danger ? 'danger' : 'primary'}" data-ok>${okText}</button><button class="btn" data-close>انصراف</button>`,
      onClose: () => { if (!done) resolve(false); },
    });
    $('[data-ok]', m.el).addEventListener('click', () => { done = true; resolve(true); m.close(); });
  });
}

let toastBox;
export function toast(message, { type = 'info', img, ttl = 5000, onClick } = {}) {
  if (!toastBox) { toastBox = document.createElement('div'); toastBox.className = 'toasts'; toastBox.setAttribute('aria-live', 'polite'); document.body.appendChild(toastBox); }
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `${img ? `<img src="${esc(img)}" alt="">` : ''}<div class="grow">${message instanceof Raw ? message.s : esc(message)}</div>`;
  if (onClick) { t.style.cursor = 'pointer'; t.addEventListener('click', () => { onClick(); t.remove(); }); }
  toastBox.appendChild(t);
  while (toastBox.children.length > 4) toastBox.firstChild.remove();
  setTimeout(() => t.remove(), ttl);
}

// ---------- alarm sound / desktop notification ----------
let actx;
export const soundOn = () => localStorage.getItem('sc-sound') === '1';
export function setSound(on) {
  localStorage.setItem('sc-sound', on ? '1' : '0');
  if (on) {
    try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); actx.resume(); beep(); } catch { /* unsupported */ }
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
  }
}
export function beep(high = true) {
  if (!actx || !soundOn()) return;
  const t0 = actx.currentTime;
  [0, 0.22, 0.44].slice(0, high ? 3 : 1).forEach((d, i) => {
    const o = actx.createOscillator(), g = actx.createGain();
    o.type = 'square'; o.frequency.value = i % 2 ? 660 : 880;
    g.gain.setValueAtTime(0.0001, t0 + d); g.gain.exponentialRampToValueAtTime(0.18, t0 + d + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + d + 0.18);
    o.connect(g).connect(actx.destination); o.start(t0 + d); o.stop(t0 + d + 0.2);
  });
}
export function notifyDesktop(title, body) {
  if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
    try { new Notification(title, { body, icon: '/static/icons/icon-192.png', tag: 'sc-alarm' }); } catch { /* ignore */ }
  }
}

// ---------- alarm detail dialog (used by live feed and alarms page) ----------
export async function openAlarm(id, onChange) {
  let a;
  try { a = await api(`/api/alarms/${id}`); } catch (e) { toast(e.message, { type: 'danger' }); return; }
  const canHandle = can('alarms.handle'), canDel = can('alarms.delete');
  const view = (al) => html`
    <img class="evidence" src="/api/alarms/${al.id}/image" alt="تصویر شاهد تخلف" loading="lazy">
    <dl class="kv">
      <dt>تخلف</dt><dd>${kindLabel(al.kind)} ${sevBadge(al.severity)}</dd>
      <dt>دوربین</dt><dd>${al.camera}</dd>
      <dt>زمان</dt><dd class="num">${fdt(al.created_at)} <span class="muted">(${ago(al.created_at)})</span></dd>
      <dt>مدت تخلف</dt><dd class="num">${fa1(al.duration)} ثانیه</dd>
      <dt>وضعیت</dt><dd>${statusBadge(al.status)} ${al.handled_by ? html`<span class="muted">توسط ${al.handled_by} — ${fdt(al.handled_at)}</span>` : ''}</dd>
    </dl>
    <div class="field"><label for="al-note">یادداشت</label>
      <textarea id="al-note" class="input" rows="2" maxlength="1000" ${canHandle ? '' : 'disabled'}>${al.note}</textarea></div>`;
  const foot = (al) => html`
    ${canHandle && al.status !== 'ack' ? html`<button class="btn primary" data-st="ack">${icon('check')} رسیدگی شد</button>` : ''}
    ${canHandle && al.status !== 'false_positive' ? html`<button class="btn" data-st="false_positive">${icon('flag')} هشدار کاذب</button>` : ''}
    ${canHandle && al.status !== 'new' ? html`<button class="btn ghost" data-st="new">بازگشایی</button>` : ''}
    ${canHandle ? html`<button class="btn ghost" data-save>${icon('save')} ذخیره یادداشت</button>` : ''}
    ${canDel ? html`<button class="btn danger sp" data-del>${icon('trash-2')}</button>` : ''}`;
  const m = openModal({ title: `آلارم شماره ${fa(a.id)}`, body: view(a), footer: foot(a), wide: true });
  const refresh = (al) => { a = al; render(m.body, view(al)); render(m.foot, foot(al)); onChange?.(al); };
  m.el.addEventListener('click', async (e) => {
    const st = e.target.closest('[data-st]'), save = e.target.closest('[data-save]'), del = e.target.closest('[data-del]');
    try {
      if (st) refresh(await api(`/api/alarms/${a.id}`, { method: 'PATCH', body: { status: st.dataset.st, note: $('#al-note', m.el).value } }));
      else if (save) { refresh(await api(`/api/alarms/${a.id}`, { method: 'PATCH', body: { note: $('#al-note', m.el).value } })); toast('یادداشت ذخیره شد', { type: 'safe', ttl: 2000 }); }
      else if (del && await confirmDialog('این آلارم و تصاویر آن برای همیشه حذف شود؟', { danger: true, okText: 'حذف' })) {
        await api(`/api/alarms/${a.id}`, { method: 'DELETE' }); m.close(); onChange?.(null);
      }
    } catch (err) { toast(err.message, { type: 'danger' }); }
  });
}

export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
