import { $, $$, ago, api, can, emit, fa, fa1, html, icon, kindLabel, on, openAlarm, render, sevBadge, state, ftime } from '../ui.js';

export async function mount(root) {
  const cams = state.cams.filter((c) => c.enabled);
  let sel = Number(sessionStorage.getItem('sc-cam')) || cams[0]?.id;
  if (!cams.some((c) => c.id === sel)) sel = cams[0]?.id;
  const live = {}; // cam id -> {online, counts, persons, fps}
  cams.forEach((c) => { live[c.id] = { online: c.online, counts: c.counts, persons: [], fps: c.fps }; });
  let compliance = null, feed = [];
  const offs = [];
  let visible = true;

  if (!cams.length) {
    render(root, html`<div class="card"><div class="empty">${icon('camera')}<p>هیچ دوربین فعالی تعریف نشده است.</p>
      ${can('cameras.manage') ? html`<a class="btn primary" href="#/cameras">${icon('plus')} افزودن دوربین</a>` : ''}</div></div>`);
    return;
  }

  render(root, html`
    <div class="stack">
      <div id="warn"></div>
      <div class="grid cols-4">
        <div class="card kpi"><div class="ico">${icon('users-round', 'lg')}</div><div><div class="val num" id="k-total">۰</div><div class="lab">افراد در صحنه</div></div></div>
        <div class="card kpi safe"><div class="ico">${icon('shield-check', 'lg')}</div><div><div class="val num" id="k-safe">۰</div><div class="lab">ایمن</div></div></div>
        <div class="card kpi danger" id="k-bad-card"><div class="ico">${icon('shield-alert', 'lg')}</div><div><div class="val num" id="k-bad">۰</div><div class="lab">متخلف (کامل یا ناقص)</div></div></div>
        <div class="card kpi"><div class="ring" id="ring"><svg viewBox="0 0 54 54"><circle class="bg" cx="27" cy="27" r="22"/><circle class="fg" cx="27" cy="27" r="22"/></svg></div>
          <div><div class="val num" id="k-comp">—</div><div class="lab">انطباق ایمنی امروز</div></div></div>
      </div>
      <div class="live-grid">
        <section class="card" aria-label="تصویر زنده">
          <div class="card-h"><h2>${icon('radio')} تصویر زنده</h2>
            <div class="tabs sp" id="camtabs" role="tablist">${cams.map((c) => html`<button class="tab ${c.id === sel ? 'active' : ''}" role="tab" data-cam="${c.id}"><span class="dot" data-d="${c.id}"></span> ${c.name}</button>`)}</div></div>
          <div class="video-wrap" id="vw">
            <img class="feed" id="feed" alt="تصویر زنده دوربین" decoding="async">
            <div class="video-ov"><span class="pill" id="p-live"><span class="dot live"></span> زنده</span><span class="pill num" id="p-fps"></span><button class="pill sp" id="fs" style="pointer-events:auto;border:0;cursor:pointer;color:#fff" aria-label="تمام‌صفحه">${icon('maximize')}</button></div>
            <div class="video-off" id="voff" hidden>${icon('wifi-off', 'xl')}<b>دوربین آفلاین است</b><span>اتصال دوربین یا منبع تصویر را بررسی کنید؛ سیستم به‌صورت خودکار دوباره تلاش می‌کند.</span></div>
          </div>
          <div class="legend"><span><i style="background:var(--safe)"></i>ایمن</span><span><i style="background:var(--warn)"></i>ناقص (یک مورد)</span><span><i style="background:var(--danger)"></i>ناایمن</span><span><i style="background:var(--muted)"></i>نامشخص</span>
            <span class="muted sp">H: کلاه ایمنی · V: لباس کار</span></div>
        </section>
        <div class="stack">
          <section class="card"><div class="card-h"><h2>${icon('scan-eye')} افراد شناسایی‌شده</h2><span class="badge sp num" id="pc">۰</span></div><div class="people" id="people"></div></section>
          <section class="card"><div class="card-h"><h2>${icon('siren')} آخرین آلارم‌ها</h2>${can('alarms.view') ? html`<a class="btn sm ghost sp" href="#/alarms">همه</a>` : ''}</div><div class="feed-list" id="feed-list"></div></section>
        </div>
      </div>
    </div>`);

  const feedEl = $('#feed', root), voff = $('#voff', root);
  let retryT;
  function startFeed() {
    clearTimeout(retryT);
    if (!visible) return;
    feedEl.src = `/api/stream/${sel}?t=${Date.now()}`;
  }
  feedEl.onerror = () => { retryT = setTimeout(startFeed, 2500); };
  function stopFeed() { clearTimeout(retryT); feedEl.removeAttribute('src'); }
  const vis = () => { visible = !document.hidden; visible ? startFeed() : stopFeed(); };
  document.addEventListener('visibilitychange', vis);

  function paintWarn() {
    const d = state.status?.detector;
    const el = $('#warn', root);
    if (!d) return;
    if (d.mode === 'person_only') render(el, html`<div class="alert-box warn">${icon('triangle-alert')}<div><b>مدل تشخیص PPE بارگذاری نشده است.</b> فقط افراد شمارش می‌شوند و وضعیت کلاه/لباس «نامشخص» است. فایل مدل را در <span class="ltr">models/ppe.pt</span> قرار دهید (راهنما: training/README.md).</div></div>`);
    else if (d.mode === 'demo') render(el, html`<div class="alert-box info">${icon('info')}<div>سیستم در <b>حالت نمایشی</b> کار می‌کند؛ تصویر و تشخیص شبیه‌سازی‌شده است.</div></div>`);
    else if (d.state === 'error') render(el, html`<div class="alert-box danger">${icon('circle-x')}<div>بارگذاری مدل ناموفق بود: <span class="ltr">${d.error}</span></div></div>`);
    else el.innerHTML = '';
  }

  function paintCam() {
    const l = live[sel] || {};
    $$('[data-d]', root).forEach((d) => { const on_ = live[d.dataset.d]?.online; d.className = `dot ${on_ ? 'on' : 'off'}`; });
    voff.hidden = !!l.online;
    $('#p-live', root).hidden = !l.online;
    $('#p-fps', root).textContent = l.online && l.fps ? `${fa1(l.fps)} fps` : '';
    paintPeople(l.persons || []);
  }
  function paintKpi() {
    const t = { total: 0, safe: 0, bad: 0 };
    Object.values(live).forEach((l) => { if (l.online && l.counts) { t.total += l.counts.total; t.safe += l.counts.safe; t.bad += l.counts.partial + l.counts.unsafe; } });
    $('#k-total', root).textContent = fa(t.total); $('#k-safe', root).textContent = fa(t.safe); $('#k-bad', root).textContent = fa(t.bad);
    $('#k-bad-card', root).classList.toggle('hot', t.bad > 0);
    const k = $('#k-comp', root), ring = $('#ring', root);
    const c = compliance;
    k.textContent = c == null ? '—' : `${fa1(c)}٪`;
    ring.style.setProperty('--p', c ?? 0);
    ring.className = `ring ${c == null ? '' : c >= 90 ? '' : c >= 70 ? 'warn' : 'bad'}`;
  }
  const ST = { safe: 'ایمن', partial: 'ناقص', unsafe: 'ناایمن', unknown: 'نامشخص' };
  const ppe = (v, l) => html`<span class="ppe ${v === true ? 'ok' : v === false ? 'no' : ''}">${icon(v === true ? 'check' : v === false ? 'x' : 'info')} ${l}</span>`;
  function paintPeople(ps) {
    $('#pc', root).textContent = fa(ps.length);
    const el = $('#people', root);
    if (!ps.length) { render(el, html`<div class="empty" style="padding:22px">${icon('users-round')}<p>فردی در تصویر نیست</p></div>`); return; }
    render(el, ps.slice().sort((a, b) => b.vsec - a.vsec).map((p) => html`
      <div class="person ${p.status}"><b class="num">#${fa(p.id)}</b>${ppe(p.helmet, 'کلاه')}${ppe(p.vest, 'لباس')}
        <span class="sp badge ${p.status === 'safe' ? 'safe' : p.status === 'partial' ? 'warn' : p.status === 'unsafe' ? 'danger' : ''}">${ST[p.status]}${p.vsec > 0 ? html` · <span class="num">${fa(Math.round(p.vsec))}ث</span>` : ''}</span></div>`));
  }
  function paintFeed() {
    const el = $('#feed-list', root);
    if (!feed.length) { render(el, html`<div class="empty" style="padding:22px">${icon('shield-check')}<p>آلارمی ثبت نشده است</p></div>`); return; }
    render(el, feed.map((a) => html`<button class="alarm-item" data-a="${a.id}">
      ${a.has_image ? html`<img src="/api/alarms/${a.id}/image?thumb=true" loading="lazy" alt="" width="74" height="48">` : html`<span class="thumb"></span>`}
      <div class="grow"><b>${kindLabel(a.kind)}</b><small>${a.camera} · <span class="num">${ftime(a.created_at)}</span> · ${ago(a.created_at)}</small></div>
      ${a.status === 'new' ? sevBadge(a.severity) : ''}</button>`));
  }

  async function loadCompliance() { try { compliance = (await api('/api/stats?days=1&tz_offset=' + new Date().getTimezoneOffset())).summary.compliance; paintKpi(); } catch { /* ignore */ } }
  async function loadFeed() {
    if (!can('alarms.view')) { $('#feed-list', root).closest('section').hidden = true; return; }
    try { feed = (await api('/api/alarms?page_size=8')).items; paintFeed(); } catch { /* ignore */ }
  }

  root.addEventListener('click', (e) => {
    const t = e.target.closest('[data-cam]');
    if (t) { sel = Number(t.dataset.cam); sessionStorage.setItem('sc-cam', sel); $$('.tab', root).forEach((x) => x.classList.toggle('active', x === t)); startFeed(); paintCam(); return; }
    const a = e.target.closest('[data-a]');
    if (a) openAlarm(Number(a.dataset.a), () => { loadFeed(); emit('alarm:handled'); });
    if (e.target.closest('#fs')) { const w = $('#vw', root); document.fullscreenElement ? document.exitFullscreen() : w.requestFullscreen?.(); }
  });

  offs.push(on('ws:hello', (m) => { Object.entries(m.cams).forEach(([id, v]) => { live[id] = { ...live[id], ...v }; }); paintKpi(); paintCam(); }));
  offs.push(on('ws:live', (m) => { live[m.cam] = { online: m.online, counts: m.counts, persons: m.persons, fps: m.fps }; paintKpi(); if (m.cam === sel) paintCam(); }));
  offs.push(on('ws:cam', (m) => { live[m.cam] = { ...(live[m.cam] || {}), online: m.online }; paintCam(); paintKpi(); }));
  offs.push(on('alarm:new', (a) => { feed.unshift(a); feed = feed.slice(0, 8); paintFeed(); $('#feed-list', root).firstElementChild?.classList.add('new-flash'); loadCompliance(); }));
  const poll = setInterval(() => { paintFeed(); loadCompliance(); paintWarn(); }, 30000);

  paintWarn(); paintCam(); paintKpi(); paintPeople(live[sel]?.persons || []); paintFeed();
  startFeed(); loadFeed(); loadCompliance();

  return () => { offs.forEach((o) => o()); clearInterval(poll); clearTimeout(retryT); document.removeEventListener('visibilitychange', vis); stopFeed(); };
}
