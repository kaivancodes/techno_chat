document.addEventListener('DOMContentLoaded', () => {
  const themeStorageKey = document.documentElement.dataset.themeStorageKey || 'tc_theme';
  const prefersLightQuery = window.matchMedia('(prefers-color-scheme: light)');

  /* ═══════════════════════════
     PROFILE DROPDOWN
  ═══════════════════════════ */
  const profileBtn      = document.getElementById('profile-btn');
  const profileDropdown = document.getElementById('profile-dropdown');

  if (profileBtn && profileDropdown) {

    profileBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = profileDropdown.classList.toggle('show');
      profileBtn.setAttribute('aria-expanded', String(isOpen));
    });

    document.addEventListener('click', (e) => {
      if (!profileBtn.contains(e.target) && !profileDropdown.contains(e.target)) {
        profileDropdown.classList.remove('show');
        profileBtn.setAttribute('aria-expanded', 'false');
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        profileDropdown.classList.remove('show');
        profileBtn.setAttribute('aria-expanded', 'false');
        profileBtn.focus();
      }
    });

  }

  /* ═══════════════════════════
     THEME TOGGLE
  ═══════════════════════════ */
  const themeBtns  = document.querySelectorAll('.tbtn');
  const savedTheme = localStorage.getItem(themeStorageKey) || 'dark';
  applyTheme(savedTheme);

  themeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const theme = btn.getAttribute('data-theme');
      applyTheme(theme);
      localStorage.setItem(themeStorageKey, theme);
    });
  });

  function applyTheme(theme) {
    themeBtns.forEach(b => b.classList.remove('on'));
    const active = document.querySelector(`.tbtn[data-theme="${theme}"]`);
    if (active) active.classList.add('on');

    if (theme === 'system') {
      const prefersLight = prefersLightQuery.matches;
      document.documentElement.setAttribute('data-theme', prefersLight ? 'light' : 'dark');
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }
  }

  prefersLightQuery.addEventListener('change', (e) => {
    if (localStorage.getItem(themeStorageKey) === 'system') {
      document.documentElement.setAttribute('data-theme', e.matches ? 'light' : 'dark');
    }
  });

});
