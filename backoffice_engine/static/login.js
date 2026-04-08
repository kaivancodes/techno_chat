document.addEventListener('DOMContentLoaded', () => {

  const pwInput  = document.getElementById('password');
  const pwToggle = document.getElementById('pw-toggle');
  const eyeOpen  = document.getElementById('eye-open');
  const eyeShut  = document.getElementById('eye-shut');

  if (pwToggle) {
    pwToggle.addEventListener('click', () => {
      const isHidden = pwInput.type === 'password';
      pwInput.type       = isHidden ? 'text'     : 'password';
      eyeOpen.style.display = isHidden ? 'none'  : 'block';
      eyeShut.style.display = isHidden ? 'block' : 'none';
    });
  }

  const form    = document.getElementById('login-form');
  const btnSign = document.getElementById('btn-signin');

  if (form) {
    form.addEventListener('submit', () => {
      btnSign.disabled = true;
      btnSign.classList.add('loading');
    });
  }

});