import { $, api, ago, can, confirmDialog, dayRange, debounce, emit, fa, fdt, html, icon, kindLabel, on, openAlarm, render, sevBadge, state, statusBadge, toast } from '../ui.js';

export async function mount(root) {
  const q = { status: '', kind: '', severity: '', camera_id: '', range: '7', page: 1 };
  const saved = JSON.parse(sessionStorage.getItem('sc-alarm-filters') || 'null');
  if (saved) Object.assign(q, saved, { page: 1 });
  const PS = 15;
  let total = 0;

  const opt = (v, l, cur) => html`<option value="${v}" ${String(cur) === String(v) ? 'selected' : ''}>${l}</option>`;
  render(root, html`
    <div class="card">
      <div class="filters" id="flt">
        <div class="field"><label for="f-status">وضعیت</label><select class="select" id="f-status" data-k="status">${opt('', 'همه', q.status)}${opt('new', 'جدید', q.status)}${opt('ack', 'رسیدگی شد', q.status)}${opt('false_positive', 'هشدار کاذب', q.status)}</select></div>
        <div class="field"><label for="f-kind">نوع تخلف</label><select class="select" id="f-kind" data-k="kind">${opt('', 'همه', q.kind)}${opt('no_helmet', 'بدون کلاه', q.kind)}${opt('no_vest', 'بدون لباس کار', q.kind)}${opt('no_both', 'بدون کلاه و لباس', q.kind)}</select></div>
        <div class="field"><label for="f-sev">شدت</label><select class="select" id="f-sev" data-k="severity">${opt('', 'همه', q.severity)}${opt('high', 'بالا', q.severity)}${opt('medium', 'متوسط', q.severity)}</select></div>
        <div class="field"><label for="f-cam">دوربین</label><select class="select" id="f-cam" data-k="camera_id">${opt('', 'همه', q.camera_id)}${state.cams.map((c) => opt(c.id, c.name, q.camera_id))}</select></div>
        <div class="field"><label for="f-range">بازه زمانی</label><select class="select" id="f-range" data-k="range">${opt('1', 'امروز', q.range)}${opt('7', '۷ روز اخیر', q.range)}${opt('30', '۳۰ روز اخیر', q.range)}${opt('0', 'همه', q.range)}</select></div>
        <div class="row sp" style="gap:8px">
          <button class="btn" id="refresh" title="بازخوانی">${icon('refresh-cw')}</button>
          ${can('alarms.handle') ? html`<button class="btn primary" id="ackall">${icon('check-check')} رسیدگی به همه جدیدها</button>` : ''}
        </div>
      </div>
      <div class="tbl-wrap"><table class="table cards"><thead><tr><th></th><th>تخلف</th><th>دوربین</th><th>زمان</th><th>شدت</th><th>وضعیت</th></tr></thead><tbody id="rows"></tbody></table></div>
      <div id="empty"></div>
      <div class="pager" id="pager"></div>
    </div>`);

  const rows = $('#rows', root);
  async function load() {
    sessionStorage.setItem('sc-alarm-filters', JSON.stringify(q));
    const p = new URLSearchParams({ page: q.page, page_size: PS });
    ['status', 'kind', 'severity', 'camera_id'].forEach((k) => q[k] && p.set(k, q[k]));
    if (Number(q.range)) { const r = dayRange(Number(q.range)); p.set('frm', r.frm); p.set('to', r.to); }
    try {
      const d = await api(`/api/alarms?${p}`);
      total = d.total;
      render(rows, d.items.map((a) => html`<tr class="click" data-id="${a.id}" tabindex="0">
        <td data-l="">${a.has_image ? html`<img class="thumb" loading="lazy" decoding="async" width="74" height="48" alt="" src="/api/alarms/${a.id}/image?thumb=true">` : html`<span class="thumb" style="display:inline-block"></span>`}</td>
        <td data-l="تخلف"><b>${kindLabel(a.kind)}</b></td>
        <td data-l="دوربین">${a.camera}</td>
        <td data-l="زمان" class="num">${fdt(a.created_at)}<br><small class="muted">${ago(a.created_at)}</small></td>
        <td data-l="شدت">${sevBadge(a.severity)}</td>
        <td data-l="وضعیت">${statusBadge(a.status)}</td></tr>`));
      $('#empty', root).innerHTML = d.items.length ? '' : `<div class="empty"><svg class="i"><use href="/static/icons/sprite.svg#i-shield-check"/></svg><p>آلارمی با این فیلترها یافت نشد</p></div>`;
      const pages = Math.max(1, Math.ceil(total / PS));
      render($('#pager', root), html`<button class="btn sm" id="prev" ${q.page <= 1 ? 'disabled' : ''} aria-label="صفحه قبل">${icon('chevron-right')}</button>
        <span class="num">صفحه ${fa(q.page)} از ${fa(pages)} — ${fa(total)} مورد</span>
        <button class="btn sm" id="next" ${q.page >= pages ? 'disabled' : ''} aria-label="صفحه بعد">${icon('chevron-left')}</button>`);
    } catch (e) { toast(e.message, { type: 'danger' }); }
  }

  root.addEventListener('change', (e) => { const k = e.target.dataset.k; if (k) { q[k] = e.target.value; q.page = 1; load(); } });
  root.addEventListener('click', async (e) => {
    if (e.target.closest('#prev')) { q.page--; load(); return; }
    if (e.target.closest('#next')) { q.page++; load(); return; }
    if (e.target.closest('#refresh')) { load(); return; }
    if (e.target.closest('#ackall')) {
      if (await confirmDialog('همه آلارم‌های جدید «رسیدگی شد» ثبت شوند؟', { okText: 'تأیید' })) {
        try { const r = await api('/api/alarms/ack-all', { method: 'POST' }); toast(`${fa(r.count)} آلارم رسیدگی شد`, { type: 'safe' }); emit('alarm:handled'); load(); } catch (er) { toast(er.message, { type: 'danger' }); }
      }
      return;
    }
    const tr = e.target.closest('tr[data-id]');
    if (tr) openAlarm(Number(tr.dataset.id), () => { emit('alarm:handled'); load(); });
  });
  root.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const tr = e.target.closest('tr[data-id]'); if (tr) tr.click(); } });

  const reload = debounce(() => { if (q.page === 1) load(); }, 600);
  const off = on('alarm:new', reload);
  load();
  return off;
}
