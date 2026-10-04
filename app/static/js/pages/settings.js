import { $, api, can, fa, html, icon, render, state, toast } from '../ui.js';

const fmtUp = (s) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${fa(h)} ساعت و ${fa(m)} دقیقه` : `${fa(m)} دقیقه`; };

export async function mount(root) {
  const edit = can('settings.edit');
  let s, st;
  try { [s, st] = await Promise.all([api('/api/settings'), api('/api/system/status')]); } catch (e) { toast(e.message, { type: 'danger' }); return; }
  const d = st.detector, dis = edit ? '' : 'disabled';
  const num = (k, label, hint, step = 1, min = 0, max = 9999) => html`<div class="field"><label for="s-${k}">${label}</label><input class="input num" id="s-${k}" data-k="${k}" type="number" step="${step}" min="${min}" max="${max}" value="${s[k]}" ${dis}>${hint ? html`<span class="hint">${hint}</span>` : ''}</div>`;
  const txt = (k, label, hint, ltr = true, type = 'text') => html`<div class="field"><label for="s-${k}">${label}</label><input class="input ${ltr ? 'ltr' : ''}" id="s-${k}" data-k="${k}" type="${type}" value="${s[k]}" ${dis} autocomplete="off" spellcheck="false">${hint ? html`<span class="hint">${hint}</span>` : ''}</div>`;
  const modeFa = { ppe: 'مدل PPE (کلاه و لباس)', person_only: 'فقط تشخیص فرد', demo: 'نمایشی', none: 'نامشخص' }[d.mode];

  render(root, html`
    <div class="grid cols-2" style="align-items:start">
      <div class="stack">
        ${edit ? '' : html`<div class="alert-box info">${icon('info')}<span>شما فقط اجازه مشاهده تنظیمات را دارید.</span></div>`}
        <section class="card"><div class="card-h"><h2>${icon('sliders-horizontal')} تشخیص و آلارم</h2></div><div class="card-b form-grid">
          ${num('conf_threshold', 'آستانه اطمینان تشخیص', 'بین ۰٫۱ تا ۰٫۹۵؛ بالاتر = آلارم کاذب کمتر، ولی احتمال از دست دادن بیشتر', 0.05, 0.1, 0.95)}
          ${num('violation_seconds', 'مدت تخلف تا ثبت آلارم (ثانیه)', 'فرد باید این مدت پیوسته بدون تجهیزات دیده شود', 0.5, 0.5, 60)}
          ${num('cooldown_seconds', 'فاصله آلارم تکراری برای یک فرد (ثانیه)', '', 5, 5, 3600)}
          ${num('min_person_height', 'حداقل ارتفاع فرد در تصویر', 'نسبت به ارتفاع تصویر (۰ تا ۰٫۸)؛ افراد دورتر نادیده گرفته می‌شوند', 0.02, 0, 0.8)}
          ${num('detect_fps', 'تعداد تشخیص در ثانیه', 'روی CPU ضعیف عدد کمتر انتخاب کنید', 1, 1, 30)}
          ${num('stream_quality', 'کیفیت ویدیوی زنده (۳۰ تا ۹۵)', 'برای شبکه ضعیف کمتر کنید', 5, 30, 95)}
          ${num('retention_days', 'نگهداری آلارم‌ها (روز)', '۰ = نگهداری نامحدود', 1, 0, 3650)}
          ${txt('org_name', 'نام سازمان / برند', 'در عنوان و صفحه ورود نمایش داده می‌شود', false)}
        </div></section>
        <section class="card"><div class="card-h"><h2>${icon('send')} اعلان‌ها</h2></div><div class="card-b form-grid">
          <label class="switch full"><input type="checkbox" id="s-tg" data-k="telegram_enabled" ${s.telegram_enabled ? 'checked' : ''} ${dis}><span class="track"></span>ارسال آلارم به تلگرام (همراه با عکس)</label>
          ${txt('telegram_token', 'توکن ربات تلگرام', 'از BotFather دریافت می‌شود؛ ذخیره می‌شود و دوباره نمایش داده نمی‌شود', true, 'password')}
          ${txt('telegram_chat_id', 'شناسه چت / گروه', '')}
          ${txt('webhook_url', 'آدرس Webhook', 'هر آلارم به‌صورت JSON با POST به این آدرس ارسال می‌شود (اتصال به سیستم‌های دیگر)')}
          <div class="field"><label for="s-sev">حداقل شدت برای اعلان</label><select class="select" id="s-sev" data-k="notify_min_severity" ${dis}><option value="medium" ${s.notify_min_severity === 'medium' ? 'selected' : ''}>متوسط و بالا</option><option value="high" ${s.notify_min_severity === 'high' ? 'selected' : ''}>فقط بالا</option></select></div>
        </div></section>
        ${edit ? html`<div class="row"><button class="btn primary" id="save">${icon('save')} ذخیره تنظیمات</button><span class="muted" id="msg"></span></div>` : ''}
      </div>
      <div class="stack">
        <section class="card"><div class="card-h"><h2>${icon('monitor-play')} وضعیت سیستم</h2></div><div class="card-b">
          <dl class="kv">
            <dt>نسخه</dt><dd class="ltr num">${st.version}</dd>
            <dt>زمان فعالیت</dt><dd class="num">${fmtUp(st.uptime)}</dd>
            <dt>دوربین‌های آنلاین</dt><dd class="num">${fa(st.cameras_online)} از ${fa(st.cameras_total)}</dd>
            <dt>پردازنده تشخیص</dt><dd class="ltr">${st.device}</dd>
            <dt>حالت تشخیص</dt><dd>${modeFa}</dd>
            <dt>مدل</dt><dd class="ltr">${d.model || '—'}</dd>
            <dt>توانایی تشخیص</dt><dd>${d.caps?.helmet ? html`<span class="ppe ok">${icon('check')} کلاه</span>` : html`<span class="ppe no">${icon('x')} کلاه</span>`} ${d.caps?.vest ? html`<span class="ppe ok">${icon('check')} لباس</span>` : html`<span class="ppe no">${icon('x')} لباس</span>`}</dd>
            ${d.classes?.length ? html`<dt>کلاس‌های مدل</dt><dd class="ltr" style="font-weight:400;font-size:.8rem">${d.classes.join(', ')}</dd>` : ''}
          </dl>
          ${d.mode === 'person_only' ? html`<div class="alert-box warn" style="margin-top:14px">${icon('triangle-alert')}<span>مدل PPE پیدا نشد. فایل <b class="ltr">best.pt</b> را با نام <b class="ltr">models/ppe.pt</b> ذخیره و برنامه را مجدداً اجرا کنید. برای آموزش مدل مخصوص محیط خودتان به <b class="ltr">training/README.md</b> مراجعه کنید.</span></div>` : ''}
        </div></section>
      </div>
    </div>`);

  if (!edit) return;
  $('#save', root).onclick = async (e) => {
    const body = {};
    root.querySelectorAll('[data-k]').forEach((el) => { body[el.dataset.k] = el.type === 'checkbox' ? el.checked : el.value; });
    e.currentTarget.disabled = true;
    try { await api('/api/settings', { method: 'PUT', body }); toast('تنظیمات ذخیره شد', { type: 'safe', ttl: 2500 }); $('#msg', root).textContent = ''; }
    catch (er) { toast(er.message, { type: 'danger' }); }
    e.currentTarget.disabled = false;
  };
}
