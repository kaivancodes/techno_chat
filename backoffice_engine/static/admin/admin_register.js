// ── Eye toggles ──
function toggle(btnId, inpId, openId, shutId) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.addEventListener('click', () => {
    const inp = document.getElementById(inpId);
    const isText = inp.type === 'text';
    inp.type = isText ? 'password' : 'text';
    document.getElementById(openId).style.display = isText ? 'block' : 'none';
    document.getElementById(shutId).style.display = isText ? 'none' : 'block';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  toggle('pw-t1', 'password', 'eo1', 'es1');
  toggle('pw-t2', 'confirm_password', 'eo2', 'es2');

  // ── Live validation ──
  const pw   = document.getElementById('password');
  const cp   = document.getElementById('confirm_password');
  const btn  = document.getElementById('btn-register');
  const hint = document.getElementById('match-hint');

  const rules = {
    'r-len': p => p.length >= 8,
    'r-upr': p => /[A-Z]/.test(p),
    'r-lwr': p => /[a-z]/.test(p),
    'r-num': p => /\d/.test(p),
    'r-spc': p => /[!@#$%^&*()\-_=+\[\]{}|;:'",.<>?\/`~\\]/.test(p),
  };

  function validate() {
    if (!pw || !cp || !btn || !hint) return;
    const p = pw.value, c = cp.value;
    let allPass = true;
    for (const [id, fn] of Object.entries(rules)) {
      const el = document.getElementById(id);
      if (!el) continue;
      const ok = fn(p);
      el.classList.toggle('pass', ok);
      const ri = el.querySelector('.ri');
      if (ri) ri.textContent = ok ? '✓' : '✗';
      if (!ok) allPass = false;
    }
    const matches = c.length > 0 && p === c;
    hint.textContent = c.length === 0 ? '' : matches ? '✓ Passwords match' : '✗ Passwords do not match';
    hint.className   = 'match-hint' + (c.length === 0 ? '' : matches ? ' pass' : ' fail');
    btn.disabled = !(allPass && matches);
  }

  if (pw) pw.addEventListener('input', validate);
  if (cp) cp.addEventListener('input', validate);

  const form = document.getElementById('register-form');
  if (form && btn) {
    form.addEventListener('submit', () => {
      btn.classList.add('loading');
      btn.disabled = true;
    });
  }

  // Handle redirect if success banner is present
  const successBanner = document.getElementById('success-banner');
  if (successBanner) {
    if (form) form.style.display = 'none'; // hide form on success
    setTimeout(() => {
      window.location.href = '/admin-login/';
    }, 3000);
  }
});
