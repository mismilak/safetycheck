import { $, api, confirmDialog, fa1, html, icon, on, openModal, render, state, toast } from '../ui.js';

const TYPES = [['0', 'وب‌کم لپ‌تاپ / USB (شماره ۰)'], ['rtsp', 'دوربین IP (RTSP)'], ['file', 'فایل ویدیو (تست)'], ['demo', 'شبیه‌ساز نمایشی (دمو)']];

export async function mount(root) {
  const offs = [];
  async function load() {
    try { state.cams = await api('/api/cameras'); } catch (e) { toast(e.message, { type: 'danger' }); }
    paint();
  }
  function paint() {
    render(root, html`
      <div class="stack">
        <div class="row"><p class="muted grow">دوربین‌های متصل به سیستم؛ هر دوربین قوانین خودش (کلاه / لباس کار) را دارد.</p><button class="btn primary" id="add">${icon('plus')} دوربین جدید</button></div>
        <div class="grid cols-3">${state.cams.map((c) => html`
          <div class="card cam-card">
            <div class="row"><span class="dot ${c.enabled ? (c.online ? 'on' : 'off') : ''}"></span><b class="grow">${c.name}</b>
              <span class="badge ${c.enabled ? (c.online ? 'safe' : 'danger') : ''}">${c.enabled ? (c.online ? 'آنلاین' : 'آفلاین') : 'غیرفعال'}</span></div>
            <div class="muted">${c.location || '—'}</div>
            <div class="src ltr">${c.source}</div>
            <div class="row wrap"><span class="ppe ${c.require_helmet ? 'ok' : ''}">${icon(c.require_helmet ? 'check' : 'x')} کلاه ایمنی</span><span class="ppe ${c.require_vest ? 'ok' : ''}">${icon(c.require_vest ? 'check' : 'x')} لباس کار</span>
              ${c.online && c.fps ? html`<span class="badge info num sp">${fa1(c.fps)} fps</span>` : ''}</div>
            <div class="row"><button class="btn sm" data-edit="${c.id}">${icon('pencil')} ویرایش</button><button class="btn sm danger sp" data-del="${c.id}">${icon('trash-2')}</button></div>
          </div>`)}</div>
      </div>`);
  }

  function form(c = {}) {
    const src = c.source || '0';
    const type = /^\d+$/.test(src) ? '0' : src === 'demo' ? 'demo' : /^rtsps?:|^https?:|^rtmp:/i.test(src) ? 'rtsp' : 'file';
    const m = openModal({
      title: c.id ? 'ویرایش دوربین' : 'دوربین جدید',
      body: html`<div class="form-grid">
        <div class="field"><label for="c-name">نام دوربین</label><input class="input" id="c-name" maxlength="128" value="${c.name || ''}" placeholder="مثلاً درب ورودی کارگاه"></div>
        <div class="field"><label for="c-loc">محل نصب</label><input class="input" id="c-loc" maxlength="128" value="${c.location || ''}"></div>
        <div class="field"><label for="c-type">نوع منبع</label><select class="select" id="c-type">${TYPES.map(([v, l]) => html`<option value="${v}" ${v === type ? 'selected' : ''}>${l}</option>`)}</select></div>
        <div class="field"><label for="c-src">آدرس / شماره منبع</label><input class="input ltr" id="c-src" value="${src}" spellcheck="false" autocapitalize="none"><span class="hint" id="c-hint"></span></div>
        <label class="switch"><input type="checkbox" id="c-h" ${c.require_helmet !== false ? 'checked' : ''}><span class="track"></span>الزام کلاه ایمنی</label>
        <label class="switch"><input type="checkbox" id="c-v" ${c.require_vest !== false ? 'checked' : ''}><span class="track"></span>الزام لباس کار / جلیقه</label>
        <label class="switch full"><input type="checkbox" id="c-en" ${c.enabled !== false ? 'checked' : ''}><span class="track"></span>دوربین فعال باشد</label>
        <div class="err full" id="c-err"></div></div>`,
      footer: html`<button class="btn primary" id="c-save">${icon('save')} ذخیره</button><button class="btn" id="c-test">${icon('wifi')} تست اتصال</button>`,
    });
    const hints = { 0: 'برای وب‌کم داخلی لپ‌تاپ عدد ۰ و برای دوربین USB دوم عدد ۱', rtsp: 'نمونه: rtsp://user:pass@192.168.1.20:554/stream1', file: 'مسیر فایل روی سرور، مثل videos/site.mp4', demo: 'بدون نیاز به دوربین؛ صحنه شبیه‌سازی‌شده' };
    const t = $('#c-type', m.el), s = $('#c-src', m.el), h = $('#c-hint', m.el);
    const sync = (fromUser) => { h.textContent = hints[t.value]; if (fromUser) { if (t.value === 'demo') s.value = 'demo'; else if (t.value === '0') s.value = '0'; else if (t.value === 'rtsp' && !/^\w+:/.test(s.value)) s.value = 'rtsp://'; else if (t.value === 'file' && /^(\d+|demo)$/.test(s.value)) s.value = ''; } s.readOnly = t.value === 'demo'; };
    t.onchange = () => sync(true); sync(false);
    const body = () => ({ name: $('#c-name', m.el).value, location: $('#c-loc', m.el).value, source: s.value, enabled: $('#c-en', m.el).checked, require_helmet: $('#c-h', m.el).checked, require_vest: $('#c-v', m.el).checked });
    $('#c-test', m.el).onclick = async (e) => {
      const b = e.currentTarget; b.disabled = true; $('#c-err', m.el).style.color = 'var(--muted)'; $('#c-err', m.el).textContent = 'در حال تست اتصال…';
      try { const r = await api('/api/cameras/test', { method: 'POST', body: { source: s.value } }); $('#c-err', m.el).style.color = r.ok ? 'var(--safe)' : 'var(--danger)'; $('#c-err', m.el).textContent = r.message; }
      catch (er) { $('#c-err', m.el).style.color = 'var(--danger)'; $('#c-err', m.el).textContent = er.message; }
      b.disabled = false;
    };
    $('#c-save', m.el).onclick = async () => {
      try { await api(c.id ? `/api/cameras/${c.id}` : '/api/cameras', { method: c.id ? 'PUT' : 'POST', body: body() }); m.close(); toast('ذخیره شد', { type: 'safe', ttl: 2000 }); setTimeout(load, 800); }
      catch (er) { $('#c-err', m.el).style.color = 'var(--danger)'; $('#c-err', m.el).textContent = er.message; }
    };
  }

  root.addEventListener('click', async (e) => {
    if (e.target.closest('#add')) return form();
    const ed = e.target.closest('[data-edit]'), del = e.target.closest('[data-del]');
    if (ed) form(state.cams.find((c) => c.id === Number(ed.dataset.edit)));
    if (del) {
      const c = state.cams.find((x) => x.id === Number(del.dataset.del));
      if (await confirmDialog(`دوربین «${c.name}» و تمام آلارم‌های آن حذف شود؟`, { danger: true, okText: 'حذف' })) {
        try { await api(`/api/cameras/${c.id}`, { method: 'DELETE' }); toast('حذف شد', { type: 'safe', ttl: 2000 }); load(); } catch (er) { toast(er.message, { type: 'danger' }); }
      }
    }
  });
  offs.push(on('ws:cam', () => setTimeout(load, 300)));
  const poll = setInterval(load, 15000);
  await load();
  return () => { offs.forEach((o) => o()); clearInterval(poll); };
}
