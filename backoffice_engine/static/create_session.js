document.addEventListener('DOMContentLoaded', () => {

  document.getElementById('btn-select-all')?.addEventListener('click', () => {
    document.querySelectorAll('.file-list input[type="checkbox"]')
      .forEach(cb => cb.checked = true);
  });

  document.getElementById('btn-deselect-all')?.addEventListener('click', () => {
    document.querySelectorAll('.file-list input[type="checkbox"]')
      .forEach(cb => cb.checked = false);
  });

  const stypeBtns       = document.querySelectorAll('.stype-btn');
  const sessionTypeInput = document.getElementById('session-type-input');
  const fileSection     = document.getElementById('file-selection-section');
  const submitBtn      = document.getElementById('submit-btn');

  stypeBtns.forEach(btn => {
   btn.addEventListener('click', () => {
    stypeBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const type = btn.getAttribute('data-type');
    sessionTypeInput.value = type;
    if (type === 'general_chat') {
      fileSection.style.display  = 'none';
      submitBtn.disabled         = false;
    } else {
      fileSection.style.display  = '';
      // re-evaluate: disable submit only if no files exist
      const hasFiles = fileSection.querySelector('.file-list input');
      submitBtn.disabled = !hasFiles;
    }
  });
});
});