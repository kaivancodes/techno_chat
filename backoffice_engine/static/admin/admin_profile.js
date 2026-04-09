document.addEventListener('DOMContentLoaded', () => {

  const usernameInput = document.getElementById('username-input');
  const usernameHint  = document.getElementById('username-hint');
  const reqFields = document.querySelectorAll('.req-field');
  const saveBtn = document.getElementById('btn-save-profile');

  const validPattern  = /^[a-zA-Z][a-zA-Z0-9._]{0,29}$/;
  let isUsernameValid = false;

  function validateSaveState() {
    let allFilled = true;
    reqFields.forEach(f => {
      if (!f.value || f.value.trim() === '') allFilled = false;
    });
    
    if (usernameInput.value.trim() !== '' && !isUsernameValid) {
        allFilled = false;
    }

    if (allFilled) {
      saveBtn.removeAttribute('disabled');
    } else {
      saveBtn.setAttribute('disabled', 'true');
    }
  }

  reqFields.forEach(f => {
      f.addEventListener('input', validateSaveState);
      f.addEventListener('change', validateSaveState);
  });

  if (usernameInput && usernameHint) {
    usernameInput.addEventListener('input', () => {
      const val = usernameInput.value.trim();

      if (val === '') {
        usernameHint.textContent  = 'Must start with a letter. Only letters, numbers, _ or . allowed. Max 30 chars.';
        usernameHint.style.color  = 'var(--t3)';
        isUsernameValid = false;
        validateSaveState();
        return;
      }

      if (!val[0].match(/[a-zA-Z]/)) {
        usernameHint.textContent = '✗ Must start with a letter.';
        usernameHint.style.color = 'var(--danger)';
        isUsernameValid = false;
        validateSaveState();
        return;
      }

      if (val.length > 30) {
        usernameHint.textContent = '✗ Maximum 30 characters.';
        usernameHint.style.color = 'var(--danger)';
        isUsernameValid = false;
        validateSaveState();
        return;
      }

      if (!validPattern.test(val)) {
        usernameHint.textContent = '✗ Only letters, numbers, underscores (_) or dots (.) allowed.';
        usernameHint.style.color = 'var(--danger)';
        isUsernameValid = false;
        validateSaveState();
        return;
      }

      usernameHint.textContent = '✓ Username looks good.';
      usernameHint.style.color = '#4ade80';
      isUsernameValid = true;
      validateSaveState();
    });
  }

  // Initial trigger
  if (usernameInput) {
      // simulate an event to trigger validation flag correctly on load
      const event = new Event('input');
      usernameInput.dispatchEvent(event);
  }

});
