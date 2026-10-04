import { $, api, can, fdt, html, icon, render, setSound, soundOn, state, toast } from '../ui.js';
import { canInstall, install, logout } from '../app.js';

export async function mount(root) {
  const u = state.user;
  render(root, html`
    <div class="grid cols-2" style="align-items:start">
      <section class="card"><div class="card-h"><h2>${icon('user-round')} اطلاعات حساب</h2></div><div class="card-b">
        <dl class="kv"><dt>نام</dt><dd>${u.full_name || '—'}</dd><dt>نام کاربری</dt><dd class="ltr">${u.username}</dd><dt>سطح دسترسی</dt><dd><span class="badge info">${u.role_label}</span></dd></dl>
        <div class="row wrap" style="margin-top:18px">
          <button class="btn" id="theme">${icon('sun')} تغییر پوسته</button>
          <label class="switch"><input type="checkbox" id="snd" ${soundOn() ? 'checked' : ''}><span class="track"></span>صدای آلارم</label>
          ${canInstall() ? html`<button class="btn" id="inst">${icon('download-cloud')} نصب برنامه (PWA)</button>` : ''}
          <button class="btn danger sp" id="out">${icon('log-out')} خروج</button></div>
      </div></section>
      <section class="card"><div class="card-h"><h2>${icon('key-round')} تغییر رمز عبور</h2></div><div class="card-b stack">
        <div class="field"><label for="pw0">رمز فعلی</label><input class="input ltr" id="pw0" type="password" autocomplete="current-password"></div>
        <div class="field"><label for="pw1">رمز جدید</label><input class="input ltr" id="pw1" type="password" autocomplete="new-password"><span class="hint">حداقل ۸ کاراکتر، ترکیب حرف و عدد</span></div>
        <div class="err" id="perr"></div>
        <div><button class="btn primary" id="pwgo">${icon('save')} ذخیره رمز</button></div>
      </div></section>
    </div>`);
  $('#out', root).onclick = logout;
  $('#theme', root).onclick = () => $('#b-theme').click();
  $('#snd', root).onchange = (e) => { setSound(e.target.checked); $('#b-sound').classList.toggle('on', e.target.checked); };
  const inst = $('#inst', root); if (inst) inst.onclick = async () => { await install(); inst.hidden = true; };
  $('#pwgo', root).onclick = async () => {
    try {
      state.user = await api('/api/auth/password', { method: 'POST', body: { current_password: $('#pw0', root).value, new_password: $('#pw1', root).value } });
      $('#pw0', root).value = $('#pw1', root).value = ''; $('#perr', root).textContent = ''; toast('رمز عبور تغییر کرد', { type: 'safe' });
    } catch (e) { $('#perr', root).textContent = e.message; }
  };
}
