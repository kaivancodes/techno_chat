document.addEventListener('DOMContentLoaded', () => {

  // --- 1. Bulk Checkbox and Delete Button Logic ---
  const selectAllCb = document.getElementById('selectAll');
  const rowCbs = document.querySelectorAll('.row-cb');
  const btnDelete = document.getElementById('btn-delete-selected');

  function updateDeleteButtonState() {
    if (!btnDelete) return;
    const anyChecked = Array.from(rowCbs).some(cb => cb.checked);
    btnDelete.disabled = !anyChecked;

    if (!selectAllCb) return;
    const checkedCount = Array.from(rowCbs).filter(cb => cb.checked).length;
    selectAllCb.checked = checkedCount > 0 && checkedCount === rowCbs.length;
    selectAllCb.indeterminate = checkedCount > 0 && checkedCount < rowCbs.length;
  }

  if (selectAllCb) {
    selectAllCb.addEventListener('change', (e) => {
      const isChecked = e.target.checked;
      rowCbs.forEach(cb => cb.checked = isChecked);
      updateDeleteButtonState();
    });
  }

  rowCbs.forEach(cb => {
    cb.addEventListener('change', () => {
      if (!cb.checked && selectAllCb) selectAllCb.checked = false;
      else if (selectAllCb) {
        const allChecked = Array.from(rowCbs).every(c => c.checked);
        selectAllCb.checked = allChecked;
      }
      updateDeleteButtonState();
    });
  });

  // --- 2. Modal Controls (Show/Hide) ---
  const btnNewContrib = document.getElementById('btn-new-contributor');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const modalOverlay  = document.getElementById('contributor-modal');

  if (btnNewContrib && modalOverlay) {
    btnNewContrib.addEventListener('click', () => modalOverlay.classList.add('active'));
  }

  if (btnCloseModal && modalOverlay) {
    btnCloseModal.addEventListener('click', () => modalOverlay.classList.remove('active'));
  }

  if (modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) modalOverlay.classList.remove('active');
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalOverlay) {
      modalOverlay.classList.remove('active');
    }
  });

  // --- 3. Password Toggle Helper (Modular) ---
  function setupToggle(btnId, inpId, openId, shutId) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const inp = document.getElementById(inpId);
      if (!inp) return;
      const isText = inp.type === 'text';
      inp.type = isText ? 'password' : 'text';
      const open = document.getElementById(openId);
      const shut = document.getElementById(shutId);
      if (open) open.style.display = isText ? 'block' : 'none';
      if (shut) shut.style.display = isText ? 'none' : 'block';
    });
  }

  // Edit Toggles
  setupToggle('e-pw-toggle-contrib', 'e-password-contrib', 'e-eo-contrib', 'e-es-contrib');
  // Modal Toggles
  setupToggle('m-pw-t1', 'm-password', 'm-eo1', 'm-es1');
  setupToggle('m-pw-t2', 'm-confirm-password', 'm-eo2', 'm-es2');

  // --- 4. Live Validation (Modal - m- Prefixed) ---
  const mPw = document.getElementById('m-password');
  const mCp = document.getElementById('m-confirm-password');
  const mEmail = document.getElementById('m-email');
  const mEmailHint = document.getElementById('m-email-hint');
  const mBtnReg = document.getElementById('m-btn-register');
  const mMatchHint = document.getElementById('m-match-hint');

  const pwRules = {
    'm-r-len': p => p.length >= 8,
    'm-r-upr': p => /[A-Z]/.test(p),
    'm-r-lwr': p => /[a-z]/.test(p),
    'm-r-num': p => /\d/.test(p),
    'm-r-spc': p => /[!@#$%^&*()\-_=+\[\]{}|;:'",.<>?\/`~\\]/.test(p),
  };

  function validateModal() {
    if (!mPw || !mCp || !mBtnReg || !mEmail) return;
    const p = mPw.value, c = mCp.value, e = mEmail.value.trim().toLowerCase();
    
    // Email domain check
    const emailValid = e.endsWith('@technostacks.com');
    if (mEmailHint) {
      mEmailHint.classList.toggle('pass', emailValid);
      mEmailHint.textContent = emailValid ? '✓ Valid @technostacks.com email' : '✗ Must end with @technostacks.com';
    }

    // Password rules check
    let allRulesPass = true;
    for (const [id, fn] of Object.entries(pwRules)) {
      const el = document.getElementById(id);
      if (!el) continue;
      const ok = fn(p);
      el.classList.toggle('pass', ok);
      const ri = el.querySelector('.ri');
      if (ri) ri.textContent = ok ? '✓' : '✗';
      if (!ok) allRulesPass = false;
    }

    // Matching check
    const matches = c.length > 0 && p === c;
    if (mMatchHint) {
        mMatchHint.textContent = c.length === 0 ? '' : matches ? '✓ Passwords match' : '✗ Passwords do not match';
        mMatchHint.className = 'match-hint' + (c.length === 0 ? '' : matches ? ' pass' : ' fail');
    }

    mBtnReg.disabled = !(allRulesPass && matches && emailValid);
  }

  if (mPw) mPw.addEventListener('input', validateModal);
  if (mCp) mCp.addEventListener('input', validateModal);
  if (mEmail) mEmail.addEventListener('input', validateModal);

  updateDeleteButtonState();
  validateModal();

  // --- 5. Success Popup Redirect ---
  const successPopup = document.getElementById('contributor-success-popup');
  if (successPopup) {
    window.setTimeout(() => {
      const url = new URL(window.location.href);
      url.searchParams.set('section', 'contributors');
      url.searchParams.delete('contributor_added');
      window.location.href = url.toString();
    }, 3000);
  }

});
