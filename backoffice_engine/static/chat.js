document.addEventListener('DOMContentLoaded', () => {
  const chatData = document.getElementById('chat-data');
  const CHAT_SEND_URL = chatData.dataset.sendUrl;
  const SESSION_ID = chatData.dataset.sessionId;
  const PAGE_RENDER_URL = chatData.dataset.pageRenderUrl;
  const SESSION_TYPE = chatData.dataset.sessionType;

  const msgContainer = document.getElementById('chat-messages');
  const chatInput = document.getElementById('chat-input');
  const btnSend = document.getElementById('btn-send');
  const modelSelect = document.getElementById('model-select');
  const typingWrapper = document.getElementById('typing-wrapper');
  const typingModelLbl = document.getElementById('typing-model-lbl');
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const imageInput = document.getElementById('chat-image-input');
  const attachImageBtn = document.getElementById('btn-attach-image');
  const previewWrap = document.getElementById('image-preview-wrap');
  const previewImg = document.getElementById('image-preview');
  const previewName = document.getElementById('image-preview-name');
  const removeImageBtn = document.getElementById('btn-remove-image');
  const chatForm = document.getElementById('chat-form');

  let currentChatMode = SESSION_TYPE === 'general_chat' ? 'web_search' : 'rag';
  let pendingImageFile = null;

  document.querySelectorAll('.mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.mode-btn').forEach((item) => item.classList.remove('active'));
      btn.classList.add('active');
      currentChatMode = btn.getAttribute('data-mode');
      syncImageModeState();
    });
  });

  function scrollToBottom() {
    msgContainer.scrollTop = msgContainer.scrollHeight;
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function parseMessage(text) {
    const lines = String(text || '').split('\n');
    let html = '';
    let listType = null;

    function closeList() {
      if (listType) {
        html += `</${listType}>`;
        listType = null;
      }
    }

    lines.forEach((line) => {
      const trimmed = line.trim();
      const bulletMatch = trimmed.match(/^[-*]\s+(.+)/);
      const numberedMatch = trimmed.match(/^\d+\.\s+(.+)/);

      if (!trimmed) {
        closeList();
        html += '<br>';
        return;
      }

      if (bulletMatch) {
        if (listType !== 'ul') {
          closeList();
          listType = 'ul';
          html += '<ul class="msg-list">';
        }
        html += `<li>${inlineFormat(bulletMatch[1])}</li>`;
        return;
      }

      if (numberedMatch) {
        if (listType !== 'ol') {
          closeList();
          listType = 'ol';
          html += '<ol class="msg-list">';
        }
        html += `<li>${inlineFormat(numberedMatch[1])}</li>`;
        return;
      }

      closeList();
      html += `<p>${inlineFormat(trimmed)}</p>`;
    });

    closeList();
    return html || '<p></p>';
  }

  function inlineFormat(text) {
    let out = esc(text);
    out = out.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/`(.*?)`/g, '<code class="msg-code">$1</code>');
    return out;
  }

  function updateSendState() {
    btnSend.disabled = chatInput.value.trim() === '' && !pendingImageFile;
  }

  function isImageMode() {
    return currentChatMode === 'image_generation';
  }

  function syncImageModeState() {
    if (!attachImageBtn || !imageInput) return;

    if (isImageMode()) {
      attachImageBtn.classList.remove('is-disabled');
      imageInput.disabled = false;
      if (chatInput.placeholder === 'Ask anything...') {
        chatInput.placeholder = 'Describe the image you want to create or edit...';
      }
      return;
    }

    attachImageBtn.classList.add('is-disabled');
    imageInput.disabled = true;
    clearPendingImage();
    chatInput.placeholder = 'Ask anything...';
  }

  function buildLocationRef(src) {
    const orderedRange = (start, end) => {
      if (start == null || start === '') return ['', ''];
      if (end == null || end === '') return [start, start];
      return Number(start) <= Number(end) ? [start, end] : [end, start];
    };
    const ft = (src.file_type || '').toLowerCase();
    const [rowStart, rowEnd] = orderedRange(src.row_start, src.row_end);
    const [lineStart, lineEnd] = orderedRange(src.line_start, src.line_end);
    const [pageStart, pageEnd] = orderedRange(src.page_index, src.page_end);
    if (ft === 'md' && src.section_name && lineStart && lineEnd && lineStart !== lineEnd) return `\u00a7 ${esc(src.section_name)} \u00b7 Lines ${lineStart}\u2013${lineEnd}`;
    if (ft === 'md' && src.section_name) return `\u00a7 ${esc(src.section_name)}`;
    if ((ft === 'pptx' || ft === 'ppt') && src.slide_index != null) return `Slide ${src.slide_index}`;
    if ((ft === 'xlsx' || ft === 'xls') && rowStart) return `${src.sheet_name ? `${esc(src.sheet_name)} · ` : ''}${rowStart !== rowEnd ? `Rows ${rowStart}\u2013${rowEnd}` : `Row ${rowStart}`}`;
    if (ft === 'csv' && rowStart) return rowStart !== rowEnd ? `Rows ${rowStart}\u2013${rowEnd}` : `Row ${rowStart}`;
    if (ft === 'txt' && lineStart) return lineStart !== lineEnd ? `Lines ${lineStart}\u2013${lineEnd}` : `Line ${lineStart}`;
    if (pageStart && pageEnd && pageEnd !== pageStart) return `Page ${pageStart}\u2013${pageEnd}`;
    if (pageStart) return `Page ${pageStart}`;
    return '';
  }

  function canPreviewSource(src) {
    const ft = (src.file_type || '').toLowerCase();
    return !['csv', 'xlsx', 'xls'].includes(ft);
  }

  function displaySources(sources) {
    return (sources || []).filter((src) => src.kind !== 'generated_image' && src.kind !== 'uploaded_image');
  }

  function generatedImages(sources) {
    return (sources || []).filter((src) => src.kind === 'generated_image');
  }

  function buildMeta(model, sources, isGreeting, chatMode) {
    let html = `<span class="msg-model">${esc(model)}</span>`;
    if (isGreeting || !sources || !displaySources(sources).length) return html;

    if (chatMode === 'web_search') {
      displaySources(sources).forEach((src) => {
        html += ` <span class="msg-sep">|</span><span class="msg-source"><a href="${esc(src.link || '#')}" target="_blank" rel="noopener noreferrer" class="web-source-link">${esc(src.title || src.link || 'Source')}</a></span>`;
      });
      return html;
    }

    if (chatMode !== 'rag') return html;

    displaySources(sources).forEach((src) => {
      const ref = buildLocationRef(src);
      const fileLabel = esc(src.file_name || '');
      const sourceLabel = canPreviewSource(src)
        ? `<button type="button" class="rag-source-btn" data-file-id="${src.file_id || ''}" data-file-type="${src.file_type || ''}" data-page="${src.page_index || ''}" data-page-end="${src.page_end || ''}" data-slide="${src.slide_index || ''}" data-sheet="${esc(src.sheet_name || '')}" data-row-start="${src.row_start || ''}" data-line-start="${src.line_start || ''}" data-line-end="${src.line_end || ''}" data-section="${esc(src.section_name || '')}" data-fname="${fileLabel}" data-highlight="" onclick="openSourceViewer(this)">${fileLabel}</button>`
        : `<span class="rag-source-static">${fileLabel}</span>`;
      html += ` <span class="msg-sep">|</span><span class="msg-source">${sourceLabel}${ref ? ` &middot; ${ref}` : ''}</span>`;
    });
    return html;
  }

  function clearPendingImage() {
    pendingImageFile = null;
    if (imageInput) imageInput.value = '';
    previewImg.src = '';
    previewName.textContent = '';
    previewWrap.style.display = 'none';
    updateSendState();
  }

  function setPendingImage(file) {
    pendingImageFile = file;
    previewImg.src = URL.createObjectURL(file);
    previewName.textContent = file.name || 'Image';
    previewWrap.style.display = 'flex';
    updateSendState();
  }

  if (imageInput) {
    imageInput.addEventListener('change', () => {
      if (!isImageMode()) {
        clearPendingImage();
        return;
      }
      const [file] = imageInput.files || [];
      if (file) setPendingImage(file);
    });
  }

  if (removeImageBtn) {
    removeImageBtn.addEventListener('click', clearPendingImage);
  }

  document.addEventListener('paste', (event) => {
    if (!isImageMode()) return;
    const items = Array.from(event.clipboardData?.items || []);
    const imageItem = items.find((item) => item.type.startsWith('image/'));
    if (!imageItem) return;
    const file = imageItem.getAsFile();
    if (file) setPendingImage(file);
  });

  ['dragenter', 'dragover'].forEach((eventName) => {
    chatForm.addEventListener(eventName, (event) => {
      if (!isImageMode()) return;
      event.preventDefault();
      chatForm.classList.add('drag-active');
    });
  });

  ['dragleave', 'drop'].forEach((eventName) => {
    chatForm.addEventListener(eventName, (event) => {
      if (!isImageMode() && eventName !== 'dragleave') return;
      event.preventDefault();
      chatForm.classList.remove('drag-active');
    });
  });

  chatForm.addEventListener('drop', (event) => {
    if (!isImageMode()) return;
    const [file] = Array.from(event.dataTransfer?.files || []).filter((item) => item.type.startsWith('image/'));
    if (file) setPendingImage(file);
  });

  chatInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = `${Math.min(this.scrollHeight, 160)}px`;
    updateSendState();
  });

  chatInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (!btnSend.disabled) sendMessage();
    }
  });

  btnSend.addEventListener('click', () => {
    if (!btnSend.disabled) sendMessage();
  });

  async function sendMessage() {
    const query = chatInput.value.trim();
    if (!query && !pendingImageFile) return;
    if (!isImageMode() && pendingImageFile) {
      appendError('Select Create Image mode to upload an image.');
      clearPendingImage();
      return;
    }
    if (pendingImageFile && !query) {
      appendError('Please enter a prompt before sending the image.');
      return;
    }

    const formData = new FormData();
    formData.append('query', query);
    formData.append('model_name', modelSelect.value);
    formData.append('chat_mode', currentChatMode);
    if (pendingImageFile) formData.append('image', pendingImageFile);

    const userImage = pendingImageFile ? `<div class="user-image-preview"><img src="${esc(previewImg.src)}" class="answer-image" alt=""></div>` : '';

    chatInput.value = '';
    chatInput.style.height = 'auto';
    btnSend.disabled = true;

    const emptyEl = document.getElementById('chat-empty');
    if (emptyEl) emptyEl.remove();

    typingWrapper.insertAdjacentHTML('beforebegin', `
      <div class="message msg-user">
        <div class="msg-bubble-wrap">
          <div class="msg-bubble user-bubble">${esc(query).replace(/\n/g, '<br>')}</div>
          ${userImage}
        </div>
      </div>`);

    typingWrapper.style.display = 'flex';
    typingModelLbl.textContent = modelSelect.value;
    scrollToBottom();

    try {
      const response = await fetch(CHAT_SEND_URL, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: formData,
      });

      const data = await response.json();
      typingWrapper.style.display = 'none';

      if (!data.success) {
        appendError(data.error || 'Something went wrong.');
        return;
      }

      const msg = data.message;
      const imagesHtml = generatedImages(msg.sources).map((src) => `<div class="generated-image-wrap"><img src="${esc(src.image_url || src.link || '')}" class="answer-image previewable-image" alt="${esc(src.title || 'Generated image')}" data-image-url="${esc(src.image_url || src.link || '')}" data-image-title="${esc(src.title || 'Generated image')}"></div>`).join('');

      typingWrapper.insertAdjacentHTML('beforebegin', `
        <div class="message msg-ai">
          <div class="msg-bubble-wrap">
            <div class="msg-meta">${buildMeta(msg.model_used, msg.sources, msg.is_greeting, msg.chat_mode)}</div>
            <div class="msg-bubble ai-bubble">${parseMessage(msg.answer)}${imagesHtml}</div>
          </div>
        </div>`);

      const countEl = document.getElementById(`count-${SESSION_ID}`);
      if (countEl && msg.message_count !== undefined) {
        countEl.textContent = msg.message_count;
      }
      clearPendingImage();
    } catch (error) {
      typingWrapper.style.display = 'none';
      appendError(`Network error: ${error.message}`);
    }

    scrollToBottom();
    updateSendState();
  }

  function appendError(message) {
    typingWrapper.insertAdjacentHTML('beforebegin', `
      <div class="message msg-ai">
        <div class="msg-bubble-wrap">
          <div class="msg-bubble ai-bubble" style="border-color:var(--danger);color:var(--danger);">&#9888; ${esc(message)}</div>
        </div>
      </div>`);
  }

  window.openSourceViewer = function(btn) {
    const modal = document.getElementById('source-viewer-modal');
    const titleEl = document.getElementById('sv-title');
    const spinner = document.getElementById('sv-spinner');
    const imgEl = document.getElementById('sv-image');
    const textEl = document.getElementById('sv-text');
    const errEl = document.getElementById('sv-error');
    const downloadEl = document.getElementById('sv-download');
    const orderedRange = (start, end) => {
      if (!start) return ['', ''];
      if (!end) return [start, start];
      return Number(start) <= Number(end) ? [start, end] : [end, start];
    };

    const highlight = btn.dataset.highlight || '';
    let locLabel = '';
    if (btn.dataset.page) {
      const [pageStart, pageEnd] = orderedRange(btn.dataset.page, btn.dataset.pageEnd);
      locLabel = pageEnd && pageEnd !== pageStart ? `Page ${pageStart}\u2013${pageEnd}` : `Page ${pageStart}`;
    }
    else if (btn.dataset.slide) locLabel = `Slide ${btn.dataset.slide}`;
    else if (btn.dataset.sheet) locLabel = `Sheet: ${btn.dataset.sheet}`;
    else if (btn.dataset.section) locLabel = `\u00a7 ${btn.dataset.section}`;
    else if (btn.dataset.lineStart) {
      const [lineStart, lineEnd] = orderedRange(btn.dataset.lineStart, btn.dataset.lineEnd);
      locLabel = lineEnd && lineEnd !== lineStart ? `Lines ${lineStart}\u2013${lineEnd}` : `Line ${lineStart}`;
    }
    titleEl.textContent = locLabel ? `${btn.dataset.fname} · ${locLabel}` : btn.dataset.fname;

    modal.style.display = 'flex';
    spinner.style.display = 'flex';
    imgEl.style.display = 'none';
    textEl.style.display = 'none';
    errEl.style.display = 'none';
    downloadEl.hidden = true;
    downloadEl.removeAttribute('href');

    const params = new URLSearchParams({
      file_id: btn.dataset.fileId,
      file_type: btn.dataset.fileType,
      page_index: btn.dataset.page,
      slide_index: btn.dataset.slide,
      sheet_name: btn.dataset.sheet,
      row_start: btn.dataset.rowStart,
      line_start: btn.dataset.lineStart,
      line_end: btn.dataset.lineEnd,
      section_name: btn.dataset.section,
      highlight,
    });

    fetch(`${PAGE_RENDER_URL}?${params}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then((response) => response.json())
      .then((data) => {
        spinner.style.display = 'none';
        if (!data.success) {
          errEl.textContent = data.error || 'Preview unavailable.';
          errEl.style.display = 'block';
          return;
        }
        if (data.source_type === 'page') {
          imgEl.src = data.image_url;
          imgEl.style.display = 'block';
          downloadEl.href = data.image_url;
          downloadEl.download = btn.dataset.fname || 'preview';
          downloadEl.hidden = false;
        } else {
          textEl.textContent = data.content_text;
          textEl.style.display = 'block';
        }
      })
      .catch(() => {
        spinner.style.display = 'none';
        errEl.textContent = 'Network error loading preview.';
        errEl.style.display = 'block';
      });
  };

  window.openImageViewer = function(imageUrl, title) {
    const modal = document.getElementById('source-viewer-modal');
    const titleEl = document.getElementById('sv-title');
    const spinner = document.getElementById('sv-spinner');
    const imgEl = document.getElementById('sv-image');
    const textEl = document.getElementById('sv-text');
    const errEl = document.getElementById('sv-error');
    const downloadEl = document.getElementById('sv-download');

    titleEl.textContent = title || 'Generated image';
    modal.style.display = 'flex';
    spinner.style.display = 'none';
    textEl.style.display = 'none';
    errEl.style.display = 'none';
    imgEl.src = imageUrl;
    imgEl.style.display = 'block';
    downloadEl.href = imageUrl;
    downloadEl.download = (title || 'generated-image').replace(/\s+/g, '-').toLowerCase();
    downloadEl.hidden = false;
  };

  document.addEventListener('click', (event) => {
    const imageTarget = event.target.closest('.previewable-image');
    if (imageTarget) {
      window.openImageViewer(imageTarget.dataset.imageUrl || imageTarget.src, imageTarget.dataset.imageTitle || imageTarget.alt || 'Generated image');
      return;
    }
    if (event.target.closest('#sv-close') || event.target.id === 'sv-backdrop') {
      const modal = document.getElementById('source-viewer-modal');
      if (modal) modal.style.display = 'none';
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      const modal = document.getElementById('source-viewer-modal');
      if (modal) modal.style.display = 'none';
    }
  });

  updateSendState();
  syncImageModeState();
  scrollToBottom();
});
