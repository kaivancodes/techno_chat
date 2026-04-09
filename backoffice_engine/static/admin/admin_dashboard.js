document.addEventListener('DOMContentLoaded', () => {

  // --- Bulk Checkbox and Delete Button Logic ---
  const selectAllCb = document.getElementById('selectAll');
  const rowCbs = document.querySelectorAll('.row-cb');
  const btnDelete = document.getElementById('btn-delete-selected');

  function updateDeleteButtonState() {
    if (!btnDelete) return;
    const anyChecked = Array.from(rowCbs).some(cb => cb.checked);
    if (anyChecked) {
      btnDelete.removeAttribute('disabled');
    } else {
      btnDelete.setAttribute('disabled', 'true');
    }
  }

  if (selectAllCb) {
    selectAllCb.addEventListener('change', (e) => {
      const isChecked = e.target.checked;
      rowCbs.forEach(cb => {
        cb.checked = isChecked;
      });
      updateDeleteButtonState();
    });
  }

  rowCbs.forEach(cb => {
    cb.addEventListener('change', () => {
      if (!cb.checked && selectAllCb) {
        selectAllCb.checked = false;
      } else if (selectAllCb) {
        // if all are now checked, check selectAll
        const allChecked = Array.from(rowCbs).every(c => c.checked);
        selectAllCb.checked = allChecked;
      }
      updateDeleteButtonState();
    });
  });

  // --- Modal Logic ---
  const btnNewContrib = document.getElementById('btn-new-contributor');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const modalOverlay  = document.getElementById('contributor-modal');

  if (btnNewContrib && modalOverlay) {
    btnNewContrib.addEventListener('click', () => {
      modalOverlay.classList.add('active');
    });
  }

  if (btnCloseModal && modalOverlay) {
    btnCloseModal.addEventListener('click', () => {
      modalOverlay.classList.remove('active');
    });
  }

  // Close when clicking outside modal box
  if (modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) {
        modalOverlay.classList.remove('active');
      }
    });
  }

});
