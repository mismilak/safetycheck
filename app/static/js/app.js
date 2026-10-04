import { $, $$, api, bus, can, emit, esc, fa, html, icon, kindLabel, notifyDesktop, beep, on, openAlarm, openModal, raw, render, setSound,
  soundOn, state, toast, ApiError } from './ui.js';

const ROUTES = [
  { path: '/', id: 'live', title: 'پایش زنده', icon: 'video', perm: 'live.view' },
  { path: '/alarms', id: 'alarms', title: 'آلارم‌ها', icon: 'bell-ring', perm: 'alarms.view', badge: true },
  { path: '/stats', id: 'stats', title: 'آمار و تحلیل', icon: 'chart-column', perm: 'stats.view' },
  { path: '/reports', id: 'reports', title: 'گزارش‌ها', icon: 'file-spreadsheet', perm: 'reports.export' },
  { path: '/cameras', id: 'cameras', title: 'دوربین‌ها', icon: 'camera', perm: 'cameras.manage' },
  { path: '/users', id: 'users', title: 'کاربران و دسترسی', icon: 'users', perm: 'users.manage' },
  { path: '/settings', id: 'settings', title: 'تنظیمات', icon: 'settings', perm: 'settings.view' },
  { path: '/profile', id: 'profile', title: 'حساب من', icon: 'user-round', perm: null, hidden: true },
];
const app = $('#app');
let brand = 'سیف‌چک';
let cleanup = null, routeToken = 0, installEvt = null;

window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); installEvt = e; emit('installable'); });
export const install = async () => { if (!installEvt) return false; installEvt.prompt(); await installEvt.userChoice; installEvt = null; return true; };
export const canInstall = () => !!installEvt;

if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));

// ---------------------------------------------------------------- boot
async function boot() {
  try { brand = (await api('/api/public')).org_name || brand; } catch { /* offline */ }
  try { state.user = await api('/api/auth/me'); } catch (e) {
    if (e.status === 0 && !navigator.onLine) { render(app, html`<div class="splash"><span>اتصال برقرار نیست</span><button class="btn primary" onclick="location.reload()">تلاش دوباره</button></div>`); return; }
    return showLogin();
  }
  await Promise.all([loadCams(), loadStatus(), loadOpenCount()]);
  buildShell();
  connectWS();
  window.addEventListener('hashchange', route);
  route();
  if (state.user.must_change_password) forcePassword();
}

async function loadCams() { try { state.cams = await api('/api/cameras'); } catch { state.cams = []; } }
async function loadStatus() { try { state.status = await api('/api/system/status'); } catch { /* ignore */ } renderStatus(); }
async function loadOpenCount() { try { state.openCount = can('alarms.view') ? (await api('/api/alarms/open-count')).count : 0; } catch { /* ignore */ } renderBadge(); }
setInterval(() => { if (state.user && !document.hidden) loadStatus(); }, 30000);

on('unauth', () => { if (state.user) { state.user = null; location.hash = '#/'; location.reload(); } });

// ---------------------------------------------------------------- login
function showLogin() {
  document.title = `ورود | ${brand}`;
  render(app, html`
    <main class="login"><form class="card login-card" id="lf" autocomplete="on">
      <div class="logo"><img src="/static/icons/icon-192.png" alt="" width="76" height="76">
        <div><h1>${brand}</h1><p class="muted">سامانه هوشمند پایش ایمنی کارگاه</p></div></div>
      <div class="field"><label for="u">نام کاربری</label><input class="input ltr" id="u" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required></div>
      <div class="field"><label for="p">رمز عبور</label>
        <div class="pw"><input class="input ltr" id="p" name="password" type="password" autocomplete="current-password" required>
        <button type="button" class="iconbtn" id="eye" aria-label="نمایش رمز">${icon('eye')}</button></div></div>
      <div class="err" id="err" role="alert"></div>
      <button class="btn primary block" id="go" type="submit">ورود به داشبورد</button>
    </form></main>`);
  const f = $('#lf'), err = $('#err'), go = $('#go');
  $('#u').focus();
  $('#eye').onclick = () => { const p = $('#p'); p.type = p.type === 'password' ? 'text' : 'password'; };
  f.onsubmit = async (e) => {
    e.preventDefault(); err.textContent = ''; go.disabled = true; go.textContent = 'در حال ورود…';
    try { await api('/api/auth/login', { method: 'POST', body: { username: $('#u').value, password: $('#p').value } }); location.hash = '#/'; boot(); }
    catch (ex) { err.textContent = ex.message; go.disabled = false; go.textContent = 'ورود به داشبورد'; $('#p').select(); }
  };
}

export async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
  location.hash = '#/'; location.reload();
}

function forcePassword() {
  const m = openModal({
    title: 'تعیین رمز عبور جدید',
    body: html`<div class="alert-box warn">${icon('lock')}<span>برای امنیت حساب، لازم است رمز عبور خود را تغییر دهید.</span></div>
      <div class="field"><label>رمز فعلی</label><input class="input ltr" id="fp-cur" type="password" autocomplete="current-password"></div>
      <div class="field"><label>رمز جدید</label><input class="input ltr" id="fp-new" type="password" autocomplete="new-password"><span class="hint">حداقل ۸ کاراکتر، ترکیب حرف و عدد</span></div>
      <div class="err" id="fp-err"></div>`,
    footer: html`<button class="btn primary" id="fp-go">ذخیره رمز جدید</button>`,
  });
  $('#fp-go', m.el).onclick = async () => {
    try {
      state.user = await api('/api/auth/password', { method: 'POST', body: { current_password: $('#fp-cur', m.el).value, new_password: $('#fp-new', m.el).value } });
      m.close(); toast('رمز عبور تغییر کرد', { type: 'safe' });
    } catch (e) { $('#fp-err', m.el).textContent = e.message; }
  };
}

// ---------------------------------------------------------------- shell
const allowed = () => ROUTES.filter((r) => !r.perm || can(r.perm));

function buildShell() {
  const nav = allowed().filter((r) => !r.hidden);
  const initial = (state.user.full_name || state.user.username).trim()[0]?.toUpperCase() || '؟';
  render(app, html`
    <div class="shell">
      <aside class="side" aria-label="منوی اصلی">
        <div class="brand"><img src="/static/icons/icon-192.png" alt="" width="40" height="40"><div><b>${brand}</b><small>پایش ایمنی PPE</small></div></div>
        <nav class="nav">${nav.map((r) => html`<a href="#${r.path}" data-r="${r.id}" title="${r.title}">${icon(r.icon, 'lg')}<span class="t">${r.title}</span>${r.badge ? html`<span class="count" data-badge hidden></span>` : ''}</a>`)}</nav>
        <div class="side-foot"><div class="status-card" id="sys"></div></div>
      </aside>
      <div class="main">
        <header class="top">
          <h1 id="ptitle"></h1><span class="spacer"></span>
          <button class="iconbtn" id="b-install" title="نصب برنامه" hidden>${icon('download-cloud')}</button>
          <button class="iconbtn ${soundOn() ? 'on' : ''}" id="b-sound" title="صدای آلارم" aria-pressed="${soundOn()}">${icon(soundOn() ? 'volume-2' : 'volume-x')}</button>
          <button class="iconbtn" id="b-theme" title="تغییر پوسته">${icon('sun')}</button>
          <a class="userchip" href="#/profile" title="حساب من"><span class="avatar">${initial}</span><div><b>${state.user.full_name || state.user.username}</b><small>${state.user.role_label}</small></div></a>
        </header>
        <div class="conn-banner" id="conn" hidden>ارتباط زنده با سرور قطع شده است؛ در حال تلاش مجدد…</div>
        <main class="page" id="page" tabindex="-1"></main>
      </div>
      <nav class="bottom-nav" aria-label="منوی موبایل">
        ${nav.slice(0, 3).map((r) => html`<a href="#${r.path}" data-r="${r.id}">${icon(r.icon, 'lg')}<span>${r.title.split(' ')[0]}</span>${r.badge ? html`<span class="count" data-badge hidden></span>` : ''}</a>`)}
        <a href="#" id="b-more">${icon('menu', 'lg')}<span>بیشتر</span></a>
      </nav>
    </div>`);
  renderStatus(); renderBadge();
  $('#b-sound').onclick = (e) => {
    const b = e.currentTarget, v = !soundOn(); setSound(v);
    b.classList.toggle('on', v); b.setAttribute('aria-pressed', v); render(b, icon(v ? 'volume-2' : 'volume-x'));
    toast(v ? 'صدای آلارم فعال شد' : 'صدای آلارم خاموش شد', { ttl: 1800 });
  };
  const th = $('#b-theme'); const paintTheme = () => render(th, icon(document.documentElement.dataset.theme === 'light' ? 'moon' : 'sun'));
  paintTheme();
  th.onclick = () => {
    const t = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = t; localStorage.setItem('sc-theme', t);
    $('meta[name=theme-color]').content = t === 'light' ? '#f3f5fa' : '#0b1020'; paintTheme(); emit('theme');
  };
  const ib = $('#b-install'); ib.hidden = !canInstall(); ib.onclick = install; on('installable', () => { ib.hidden = false; });
  $('#b-more').onclick = (e) => {
    e.preventDefault();
    const rest = allowed().slice(3);
    const m = openModal({ title: 'منو', body: html`<div class="stack">${rest.map((r) => html`<a class="btn block" href="#${r.path}" data-close>${icon(r.icon)} ${r.title}</a>`)}
      <button class="btn danger block" id="m-out">${icon('log-out')} خروج از حساب</button></div>` });
    $('#m-out', m.el).onclick = logout;
  };
}

function renderStatus() {
  const el = $('#sys'); if (!el) return;
  const s = state.status, d = s?.detector;
  if (!d) { render(el, html`<div class="row"><span class="dot"></span> وضعیت نامشخص</div>`); return; }
  const map = { ppe: ['on', 'مدل PPE فعال'], person_only: ['warn', 'مدل PPE بارگذاری نشده'], demo: ['info', 'حالت نمایشی (دمو)'], none: ['off', 'مدل بارگذاری نشده'] };
  let [cls, txt] = map[d.mode] || map.none;
  if (d.state === 'loading') [cls, txt] = ['', 'در حال بارگذاری مدل…'];
  if (d.state === 'error') [cls, txt] = ['off', 'خطا در بارگذاری مدل'];
  render(el, html`<div class="row"><span class="dot ${cls === 'on' ? 'on' : cls === 'off' ? 'off' : ''}" style="${cls === 'warn' ? 'background:var(--warn)' : cls === 'info' ? 'background:var(--info)' : ''}"></span><b>${txt}</b></div>
    <div class="muted" style="margin-top:6px">دوربین آنلاین: <span class="num">${fa(s.cameras_online)}</span> از <span class="num">${fa(s.cameras_total)}</span></div>`);
}
function renderBadge() {
  $$('[data-badge]').forEach((b) => { b.hidden = !state.openCount; b.textContent = state.openCount > 99 ? '+۹۹' : fa(state.openCount); });
  const base = document.title.replace(/^\(\S+\)\s*/, '');
  document.title = state.openCount ? `(${fa(state.openCount)}) ${base}` : base;
}

// ---------------------------------------------------------------- router
async function route() {
  if (!state.user) return;
  const path = (location.hash.replace(/^#/, '') || '/').split('?')[0];
  const r = ROUTES.find((x) => x.path === path) || ROUTES[0];
  const page = $('#page');
  if (r.perm && !can(r.perm)) { render(page, html`<div class="empty">${icon('lock')}<p>شما به این بخش دسترسی ندارید.</p></div>`); return; }
  const token = ++routeToken;
  try { cleanup?.(); } catch { /* ignore */ } cleanup = null;
  $$('.nav a, .bottom-nav a[data-r]').forEach((a) => { const on_ = a.dataset.r === r.id; a.classList.toggle('active', on_); on_ ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'); });
  $('#ptitle').textContent = r.title;
  document.title = `${r.title} | ${brand}`; renderBadge();
  render(page, html`<div class="grid cols-4">${[1, 2, 3, 4].map(() => html`<div class="skeleton" style="height:84px"></div>`)}</div>`);
  try {
    const mod = await import(`./pages/${r.id}.js`);
    if (token !== routeToken) return;
    page.innerHTML = '';
    cleanup = (await mod.mount(page, { brand })) || null;
    if (token !== routeToken) { cleanup?.(); cleanup = null; }
    window.scrollTo(0, 0);
  } catch (e) {
    if (token !== routeToken) return;
    console.error(e);
    render(page, html`<div class="empty">${icon('triangle-alert')}<p>بارگذاری این بخش با خطا مواجه شد.</p><button class="btn" onclick="location.reload()">بارگذاری مجدد</button></div>`);
  }
}

// ---------------------------------------------------------------- websocket
let ws, retry = 0;
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => { retry = 0; state.ws = true; $('#conn') && ($('#conn').hidden = true); };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (m.t === 'alarm') onAlarm(m.alarm);
    if (m.t === 'cam') { const c = state.cams.find((x) => x.id === m.cam); if (c) c.online = m.online; loadStatus(); }
    emit(`ws:${m.t}`, m);
  };
  ws.onclose = () => {
    state.ws = false; if (!state.user) return;
    const b = $('#conn'); if (b) b.hidden = false;
    setTimeout(connectWS, Math.min(1000 * 2 ** retry++, 15000));
  };
  ws.onerror = () => ws.close();
}

function onAlarm(a) {
  state.openCount += 1; renderBadge();
  const title = `${kindLabel(a.kind)} — ${a.camera}`;
  toast(html`<b>${a.severity === 'high' ? '🚨 ' : '⚠️ '}${kindLabel(a.kind)}</b><br><small class="muted">${a.camera}</small>`,
    { type: a.severity === 'high' ? 'danger' : 'info', img: a.has_image ? `/api/alarms/${a.id}/image?thumb=true` : null, ttl: 8000, onClick: () => openAlarm(a.id) });
  beep(a.severity === 'high'); notifyDesktop('هشدار ایمنی', title);
  emit('alarm:new', a);
}
on('alarm:handled', loadOpenCount);

boot();
