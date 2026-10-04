import { $, $$, api, fa, fa1, fdateShort, html, icon, kindLabel, on, render, tzOffset, toast } from '../ui.js';

let chartLib;
function loadChart() {
  if (window.Chart) return Promise.resolve();
  chartLib ||= new Promise((res, rej) => {
    const s = document.createElement('script');
    s.src = '/static/vendor/chart.umd.min.js'; s.onload = res; s.onerror = () => rej(new Error('chart'));
    document.head.appendChild(s);
  });
  return chartLib;
}
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export async function mount(root) {
  let days = Number(sessionStorage.getItem('sc-stat-days')) || 7;
  let data, charts = [];
  render(root, html`
    <div class="stack">
      <div class="row wrap"><div class="tabs" id="rng" role="tablist">${[[1, 'امروز'], [7, '۷ روز'], [30, '۳۰ روز'], [90, '۹۰ روز']].map(([d, l]) => html`<button class="tab ${d === days ? 'active' : ''}" data-d="${d}">${l}</button>`)}</div></div>
      <div class="grid cols-4" id="kpis"></div>
      <div class="grid cols-2">
        <section class="card"><div class="card-h"><h2>${icon('clock')} توزیع ساعتی تخلف‌ها</h2></div><div class="card-b"><div class="chart-box"><canvas id="c-hour" role="img" aria-label="نمودار ساعتی"></canvas></div></div></section>
        <section class="card"><div class="card-h"><h2>${icon('activity')} روند روزانه و نرخ انطباق</h2></div><div class="card-b"><div class="chart-box"><canvas id="c-day" role="img" aria-label="نمودار روزانه"></canvas></div></div></section>
        <section class="card"><div class="card-h"><h2>${icon('shirt')} نوع تخلف</h2></div><div class="card-b"><div class="chart-box sm"><canvas id="c-kind" role="img" aria-label="نوع تخلف"></canvas></div></div></section>
        <section class="card"><div class="card-h"><h2>${icon('camera')} تخلف به تفکیک دوربین</h2></div><div class="card-b"><div class="bars" id="cams"></div></div></section>
      </div>
    </div>`);

  function kpis() {
    const s = data.summary, comp = s.compliance;
    render($('#kpis', root), html`
      <div class="card kpi danger"><div class="ico">${icon('bell-ring', 'lg')}</div><div><div class="val num">${fa(s.alarms)}</div><div class="lab">کل آلارم‌ها</div></div></div>
      <div class="card kpi warn"><div class="ico">${icon('siren', 'lg')}</div><div><div class="val num">${fa(s.high)}</div><div class="lab">شدت بالا</div></div></div>
      <div class="card kpi accent"><div class="ico">${icon('eye', 'lg')}</div><div><div class="val num">${fa(s.new)}</div><div class="lab">رسیدگی‌نشده</div></div></div>
      <div class="card kpi ${comp == null ? '' : comp >= 90 ? 'safe' : 'warn'}"><div class="ico">${icon('shield-check', 'lg')}</div><div><div class="val num">${comp == null ? '—' : fa1(comp) + '٪'}</div><div class="lab">میانگین انطباق ایمنی</div></div></div>`);
  }

  function draw() {
    charts.forEach((c) => c.destroy()); charts = [];
    const C = window.Chart; if (!C || !data) return;
    const text = css('--muted'), grid = css('--border'), accent = css('--accent'), danger = css('--danger'), warn = css('--warn'), safe = css('--safe'), info = css('--info');
    C.defaults.font.family = 'Vazirmatn, system-ui, sans-serif'; C.defaults.color = text; C.defaults.borderColor = grid;
    const tick = (v) => fa(v);
    const base = { responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
      plugins: { legend: { rtl: true, labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: { rtl: true, textDirection: 'rtl', callbacks: { label: (c) => ` ${c.dataset.label}: ${fa(c.parsed.y ?? c.parsed)}` } } } };
    const xy = { x: { reverse: true, grid: { display: false } }, y: { position: 'right', beginAtZero: true, ticks: { callback: tick, precision: 0 }, grid: { color: grid } } };

    charts.push(new C($('#c-hour', root), { type: 'bar',
      data: { labels: data.hourly.map((_, h) => fa(h)), datasets: [{ label: 'تعداد آلارم', data: data.hourly, backgroundColor: accent, borderRadius: 6, maxBarThickness: 22 }] },
      options: { ...base, plugins: { ...base.plugins, legend: { display: false } }, scales: xy } }));

    const dl = data.daily.map((d) => fdateShort(d.date + 'T12:00:00'));
    charts.push(new C($('#c-day', root), { data: { labels: dl, datasets: [
      { type: 'bar', label: 'آلارم', data: data.daily.map((d) => d.alarms), backgroundColor: danger + 'cc', borderRadius: 6, maxBarThickness: 26, yAxisID: 'y' },
      { type: 'line', label: 'انطباق ٪', data: data.daily.map((d) => d.compliance), borderColor: safe, backgroundColor: safe, tension: .35, pointRadius: 3, spanGaps: true, yAxisID: 'y1' }] },
      options: { ...base, interaction: { mode: 'index', intersect: false }, scales: { x: { reverse: true, grid: { display: false }, ticks: { maxTicksLimit: 10, autoSkip: true } },
        y: { position: 'right', beginAtZero: true, ticks: { callback: tick, precision: 0 }, grid: { color: grid } },
        y1: { position: 'left', min: 0, max: 100, ticks: { callback: (v) => fa(v) + '٪' }, grid: { display: false } } } } }));

    const k = data.kinds;
    charts.push(new C($('#c-kind', root), { type: 'doughnut',
      data: { labels: ['no_helmet', 'no_vest', 'no_both'].map(kindLabel), datasets: [{ data: [k.no_helmet, k.no_vest, k.no_both], backgroundColor: [warn, info, danger], borderWidth: 0, hoverOffset: 6 }] },
      options: { ...base, cutout: '66%', plugins: { ...base.plugins, legend: { position: 'bottom', rtl: true, labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: { rtl: true, callbacks: { label: (c) => ` ${c.label}: ${fa(c.parsed)}` } } } } }));

    const max = Math.max(1, ...data.cameras.map((c) => c.alarms));
    render($('#cams', root), data.cameras.length ? data.cameras.map((c) => html`<div class="bar-row"><div class="row"><span>${c.name}</span><b class="sp num">${fa(c.alarms)}</b></div><div class="bar"><i style="width:${(100 * c.alarms / max).toFixed(1)}%"></i></div></div>`)
      : html`<div class="empty">${icon('shield-check')}<p>تخلفی ثبت نشده است</p></div>`);
  }

  async function load() {
    try {
      const [d] = await Promise.all([api(`/api/stats?days=${days}&tz_offset=${tzOffset()}`), loadChart()]);
      data = d; kpis(); draw();
    } catch (e) { toast(e.message, { type: 'danger' }); }
  }
  root.addEventListener('click', (e) => {
    const t = e.target.closest('[data-d]'); if (!t) return;
    days = Number(t.dataset.d); sessionStorage.setItem('sc-stat-days', days);
    $$('.tab', root).forEach((x) => x.classList.toggle('active', x === t)); load();
  });
  const off = on('theme', draw);
  load();
  return () => { off(); charts.forEach((c) => c.destroy()); };
}
