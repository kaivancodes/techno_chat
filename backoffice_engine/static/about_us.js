document.addEventListener('DOMContentLoaded', () => {

  const els = document.querySelectorAll(
    '.stack-item, .flow-step, .purpose-card, .privacy-banner, .tech-logo-item'
  );

  els.forEach((el, i) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(14px)';
    el.style.transition = `opacity 0.38s ease ${i * 0.05}s, transform 0.38s ease ${i * 0.05}s`;
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.10 });

  els.forEach((el) => observer.observe(el));

});