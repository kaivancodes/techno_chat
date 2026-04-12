document.addEventListener('DOMContentLoaded', () => {

  const usernameInput = document.getElementById('username-input');
  const usernameHint  = document.getElementById('username-hint');

  if (!usernameInput || !usernameHint) return;

  const validPattern  = /^[a-zA-Z][a-zA-Z0-9._]{0,29}$/;

  usernameInput.addEventListener('input', () => {
    const rawVal = usernameInput.value;
    const val = rawVal.trim();

    if (val === '') {
      usernameHint.textContent  = 'Must start with a letter. Spaces not allowed. Only letters, numbers, _ or . allowed. Max 30 chars.';
      usernameHint.style.color  = 'var(--t3)';
      return;
    }

    if (/\s/.test(rawVal)) {
      usernameHint.textContent = '✗ Spaces not allowed in username.';
      usernameHint.style.color = 'var(--danger)';
      return;
    }

    if (!val[0].match(/[a-zA-Z]/)) {
      usernameHint.textContent = '✗ Must start with a letter.';
      usernameHint.style.color = 'var(--danger)';
      return;
    }

    if (val.length > 30) {
      usernameHint.textContent = '✗ Maximum 30 characters.';
      usernameHint.style.color = 'var(--danger)';
      return;
    }

    if (!validPattern.test(val)) {
      usernameHint.textContent = '✗ Only letters, numbers, underscores (_) or dots (.) allowed.';
      usernameHint.style.color = 'var(--danger)';
      return;
    }

    usernameHint.textContent = '✓ Username looks good.';
    usernameHint.style.color = '#4ade80';
  });

});
