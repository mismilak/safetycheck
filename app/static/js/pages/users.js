import { $, api, can, confirmDialog, fa, fdt, html, icon, openModal, render, state, toast } from '../ui.js';

const PERMS = [
  ['مشاهده پایش زنده، آلارم‌ها و آمار', [1, 1, 1, 1]],
  ['رسیدگی به آلارم‌ها / ثبت هشدار کاذب', [0, 1, 1, 1]],
  ['دریافت گزارش (Excel / CSV / چاپ)', [0, 0, 1, 1]],
  ['مدیریت دوربین‌ها', [0, 0, 1, 1]],
  ['مشاهده تنظیمات سیستم', [0, 0, 1, 1]],
  ['تغییر تنظیمات و اعلان‌ها', [0, 0, 0, 1]],
  ['حذف آلارم‌ها', [0, 0, 0, 1]],
  ['مدیریت کاربران و مشاهده لاگ ممیزی', [0, 0, 0, 1]],
];
const ROLE_COLS = ['بیننده', 'اپراتور', 'مدیر ایمنی', 'مدیر سیستم'];

export async function mount(root) {
  let users = [], roles = [], tab = 'users';
  const ACT = { login: 'ورود', login_failed: 'ورود ناموفق', password_change: 'تغییر رمز', user_create: 'ایجاد کاربر', user_update: 'ویرایش کاربر', user_delete: 'حذف کاربر', camera_create: 'افزودن دوربین', camera_update: 'ویرایش دوربین', camera_delete: 'حذف دوربین', settings_update: 'تغییر تنظیمات', alarm_update: 'رسیدگی آلارم', alarm_ack_all: 'رسیدگی گروهی', alarm_delete: 'حذف آلارم', report_export: 'خروجی گزارش' };

  async function load() {
    try { [users, roles] = await Promise.all([api('/api/users'), api('/api/roles')]); } catch (e) { toast(e.message, { type: 'danger' }); }
    paint();
  }
  async function paint() {
    const body = tab === 'users' ? usersView() : tab === 'roles' ? rolesView() : await auditView();
    render(root, html`<div class="stack">
      <div class="row wrap"><div class="tabs"><button class="tab ${tab === 'users' ? 'active' : ''}" data-t="users">کاربران</button><button class="tab ${tab === 'roles' ? 'active' : ''}" data-t="roles">سطوح دسترسی</button><button class="tab ${tab === 'audit' ? 'active' : ''}" data-t="audit">لاگ ممیزی</button></div>
        ${tab === 'users' ? html`<button class="btn primary sp" id="add">${icon('plus')} کاربر جدید</button>` : ''}</div>${body}</div>`);
  }
  const usersView = () => html`<section class="card"><div class="tbl-wrap"><table class="table cards"><thead><tr><th>کاربر</th><th>نقش</th><th>وضعیت</th><th>آخرین ورود</th><th></th></tr></thead><tbody>
    ${users.map((u) => html`<tr><td data-l="کاربر"><b>${u.full_name || u.username}</b><br><small class="muted ltr">${u.username}</small></td>
      <td data-l="نقش"><span class="badge info">${u.role_label}</span></td>
      <td data-l="وضعیت"><span class="badge ${u.is_active ? 'safe' : ''}">${u.is_active ? 'فعال' : 'غیرفعال'}</span></td>
      <td data-l="آخرین ورود" class="num">${u.last_login ? fdt(u.last_login) : '—'}</td>
      <td data-l=""><div class="row"><button class="btn sm" data-edit="${u.id}">${icon('pencil')} ویرایش</button>${u.id !== state.user.id ? html`<button class="btn sm danger" data-del="${u.id}" aria-label="حذف">${icon('trash-2')}</button>` : ''}</div></td></tr>`)}</tbody></table></div></section>`;
  const rolesView = () => html`<section class="card"><div class="card-h"><h2>${icon('key-round')} ماتریس سطوح دسترسی</h2></div><div class="tbl-wrap"><table class="table perm-table"><thead><tr><th>قابلیت</th>${ROLE_COLS.map((r) => html`<th>${r}</th>`)}</tr></thead><tbody>
    ${PERMS.map(([l, v]) => html`<tr><td>${l}</td>${v.map((x) => html`<td>${x ? html`<span style="color:var(--safe)">${icon('circle-check')}</span>` : html`<span class="muted">—</span>`}</td>`)}</tr>`)}</tbody></table></div></section>`;
  async function auditView() {
    let rows = []; try { rows = await api('/api/audit?limit=150'); } catch { /* ignore */ }
    return html`<section class="card"><div class="tbl-wrap"><table class="table cards"><thead><tr><th>زمان</th><th>کاربر</th><th>عملیات</th><th>جزئیات</th><th>IP</th></tr></thead><tbody>
      ${rows.map((a) => html`<tr><td data-l="زمان" class="num">${fdt(a.ts)}</td><td data-l="کاربر" class="ltr">${a.username}</td><td data-l="عملیات"><span class="badge ${a.action === 'login_failed' ? 'danger' : ''}">${ACT[a.action] || a.action}</span></td><td data-l="جزئیات"><small>${a.detail}</small></td><td data-l="IP" class="ltr muted">${a.ip}</td></tr>`)}</tbody></table></div></section>`;
  }

  function form(u) {
    const m = openModal({
      title: u ? `ویرایش ${u.username}` : 'کاربر جدید',
      body: html`<div class="form-grid">
        <div class="field"><label for="u-un">نام کاربری</label><input class="input ltr" id="u-un" value="${u?.username || ''}" ${u ? 'disabled' : ''} autocapitalize="none" spellcheck="false"><span class="hint">حروف انگلیسی، عدد و . _ -</span></div>
        <div class="field"><label for="u-fn">نام و نام خانوادگی</label><input class="input" id="u-fn" value="${u?.full_name || ''}" maxlength="128"></div>
        <div class="field"><label for="u-role">نقش</label><select class="select" id="u-role">${roles.map((r) => html`<option value="${r.id}" ${(u?.role || 'viewer') === r.id ? 'selected' : ''}>${r.label}</option>`)}</select></div>
        <div class="field"><label for="u-pw">${u ? 'رمز جدید (اختیاری)' : 'رمز عبور'}</label><input class="input ltr" id="u-pw" type="password" autocomplete="new-password"><span class="hint">حداقل ۸ کاراکتر، ترکیب حرف و عدد. کاربر در اولین ورود باید رمز را تغییر دهد.</span></div>
        ${u ? html`<label class="switch full"><input type="checkbox" id="u-act" ${u.is_active ? 'checked' : ''} ${u.id === state.user.id ? 'disabled' : ''}><span class="track"></span>حساب فعال باشد</label>` : ''}
        <div class="err full" id="u-err"></div></div>`,
      footer: html`<button class="btn primary" id="u-save">${icon('save')} ذخیره</button>`,
    });
    $('#u-save', m.el).onclick = async () => {
      const role = $('#u-role', m.el).value, full_name = $('#u-fn', m.el).value, password = $('#u-pw', m.el).value;
      try {
        if (u) await api(`/api/users/${u.id}`, { method: 'PATCH', body: { role, full_name, password: password || undefined, is_active: $('#u-act', m.el).checked } });
        else await api('/api/users', { method: 'POST', body: { username: $('#u-un', m.el).value, role, full_name, password } });
        m.close(); toast('ذخیره شد', { type: 'safe', ttl: 2000 }); load();
      } catch (e) { $('#u-err', m.el).textContent = e.message; }
    };
  }

  root.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-t]'); if (t) { tab = t.dataset.t; paint(); return; }
    if (e.target.closest('#add')) return form();
    const ed = e.target.closest('[data-edit]'), del = e.target.closest('[data-del]');
    if (ed) form(users.find((x) => x.id === Number(ed.dataset.edit)));
    if (del) {
      const u = users.find((x) => x.id === Number(del.dataset.del));
      if (await confirmDialog(`کاربر «${u.username}» حذف شود؟`, { danger: true, okText: 'حذف' })) {
        try { await api(`/api/users/${u.id}`, { method: 'DELETE' }); toast('حذف شد', { type: 'safe', ttl: 2000 }); load(); } catch (er) { toast(er.message, { type: 'danger' }); }
      }
    }
  });
  await load();
}
