import { $, api, can, dayRange, fa, fdate, fdt, html, icon, kindLabel, render, sevBadge, state, statusBadge, toast, tzOffset } from '../ui.js';

const STATUS_FA = { new: 'جدید', ack: 'رسیدگی شد', false_positive: 'هشدار کاذب' };

export async function mount(root, { brand }) {
  const q = { range: '7', camera_id: '', status: '' };
  const opt = (v, l, cur) => html`<option value="${v}" ${String(cur) === String(v) ? 'selected' : ''}>${l}</option>`;
  render(root, html`
    <div class="stack">
      <section class="card no-print">
        <div class="card-h"><h2>${icon('file-spreadsheet')} گزارش آلارم‌ها</h2></div>
        <div class="filters">
          <div class="field"><label for="r-range">بازه</label><select class="select" id="r-range" data-k="range">${opt('1', 'امروز', q.range)}${opt('7', '۷ روز اخیر', q.range)}${opt('30', '۳۰ روز اخیر', q.range)}${opt('90', '۹۰ روز اخیر', q.range)}${opt('0', 'همه', q.range)}</select></div>
          <div class="field"><label for="r-cam">دوربین</label><select class="select" id="r-cam" data-k="camera_id">${opt('', 'همه', '')}${state.cams.map((c) => opt(c.id, c.name, ''))}</select></div>
          <div class="field"><label for="r-st">وضعیت</label><select class="select" id="r-st" data-k="status">${opt('', 'همه', '')}${opt('new', 'جدید', '')}${opt('ack', 'رسیدگی شد', '')}${opt('false_positive', 'هشدار کاذب', '')}</select></div>
          <div class="row sp wrap">
            <button class="btn primary" data-x="xlsx">${icon('download')} Excel</button>
            <button class="btn" data-x="csv">${icon('download')} CSV</button>
            <button class="btn" id="print">${icon('printer')} چاپ / PDF</button>
          </div>
        </div>
      </section>
      <section class="card" id="sheet">
        <div class="card-b"><div class="print-only" style="margin-bottom:12px"><h2>${brand} — گزارش تخلفات ایمنی</h2><p id="p-sub"></p></div>
          <div class="grid cols-4" id="sum"></div></div>
        <div class="tbl-wrap"><table class="table cards"><thead><tr><th>شناسه</th><th>زمان</th><th>دوربین</th><th>تخلف</th><th>شدت</th><th>وضعیت</th><th>رسیدگی‌کننده</th></tr></thead><tbody id="rows"></tbody></table></div>
        <div class="pager" id="more"></div>
      </section>
    </div>`);

  const params = (extra = {}) => {
    const p = new URLSearchParams(extra);
    if (q.camera_id) p.set('camera_id', q.camera_id);
    if (q.status) p.set('status', q.status);
    if (Number(q.range)) { const r = dayRange(Number(q.range)); p.set('frm', r.frm); p.set('to', r.to); }
    return p;
  };
  async function load() {
    try {
      const d = await api(`/api/alarms?${params({ page_size: 100 })}`);
      const items = d.items;
      const c = { high: 0, new: 0, fp: 0 };
      items.forEach((a) => { c.high += a.severity === 'high'; c.new += a.status === 'new'; c.fp += a.status === 'false_positive'; });
      render($('#sum', root), html`
        <div class="card kpi"><div><div class="val num">${fa(d.total)}</div><div class="lab">کل آلارم‌ها</div></div></div>
        <div class="card kpi danger"><div><div class="val num">${fa(c.high)}</div><div class="lab">شدت بالا${d.total > items.length ? ' (در نمایش)' : ''}</div></div></div>
        <div class="card kpi warn"><div><div class="val num">${fa(c.new)}</div><div class="lab">رسیدگی‌نشده</div></div></div>
        <div class="card kpi"><div><div class="val num">${fa(c.fp)}</div><div class="lab">هشدار کاذب</div></div></div>`);
      render($('#rows', root), items.map((a) => html`<tr><td data-l="شناسه" class="num">${fa(a.id)}</td><td data-l="زمان" class="num">${fdt(a.created_at)}</td><td data-l="دوربین">${a.camera}</td>
        <td data-l="تخلف">${kindLabel(a.kind)}</td><td data-l="شدت">${sevBadge(a.severity)}</td><td data-l="وضعیت">${statusBadge(a.status)}</td><td data-l="رسیدگی‌کننده">${a.handled_by || '—'}</td></tr>`));
      $('#more', root).textContent = d.total > items.length ? `${fa(items.length)} مورد اول از ${fa(d.total)} نمایش داده شد؛ برای دریافت همه، فایل Excel/CSV را دانلود کنید.` : (items.length ? '' : 'موردی یافت نشد');
      $('#p-sub', root).textContent = `تاریخ تهیه: ${fdate(new Date().toISOString())}`;
    } catch (e) { toast(e.message, { type: 'danger' }); }
  }
  root.addEventListener('change', (e) => { const k = e.target.dataset.k; if (k) { q[k] = e.target.value; load(); } });
  root.addEventListener('click', (e) => {
    const x = e.target.closest('[data-x]');
    if (x && can('reports.export')) { location.href = `/api/reports/alarms.${x.dataset.x}?${params({ tz_offset: tzOffset() })}`; }
    if (e.target.closest('#print')) window.print();
  });
  load();
}
