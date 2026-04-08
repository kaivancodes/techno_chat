document.addEventListener('DOMContentLoaded', () => {
// Toggle User Profile Dropdown
  const profileBtn = document.getElementById('profile-btn');
  const profileDropdown = document.getElementById('profile-dropdown');

  if (profileBtn && profileDropdown) {
      profileBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          profileDropdown.classList.toggle('show');
      });

      // Close dropdown when clicking outside
      document.addEventListener('click', (e) => {
          if (!profileBtn.contains(e.target) && !profileDropdown.contains(e.target)) {
              profileDropdown.classList.remove('show');
          }
      });
  }
  const themeBtns = document.querySelectorAll('.tbtn');
  const savedTheme = localStorage.getItem('tc_theme') || 'dark';
  applyTheme(savedTheme);

  themeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const theme = btn.getAttribute('data-theme');
      applyTheme(theme);
      localStorage.setItem('tc_theme', theme);
    });
  });

  function applyTheme(theme) {
    themeBtns.forEach(b => b.classList.remove('on'));
    const activeBtn = document.querySelector(`.tbtn[data-theme="${theme}"]`);
    if(activeBtn) activeBtn.classList.add('on');

    if (theme === 'system') {
      const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
      document.documentElement.setAttribute('data-theme', prefersLight ? 'light' : 'dark');
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }
  }

  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', e => {
    if (localStorage.getItem('tc_theme') === 'system') {
      document.documentElement.setAttribute('data-theme', e.matches ? 'light' : 'dark');
    }
  });
});