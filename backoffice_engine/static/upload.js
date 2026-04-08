document.addEventListener('DOMContentLoaded', () => {

  const toggleBtn      = document.getElementById('btn-upload-toggle');
  const zone           = document.getElementById('upload-zone');
  const uploadBox      = document.getElementById('upload-box');
  const fileInput      = document.getElementById('file-input');
  const uploadLabel    = document.getElementById('upload-label');
  const uploadForm     = document.getElementById('upload-form');
  const uploadProgress = document.getElementById('upload-progress');
  const uploadAnalysis = document.getElementById('upload-analysis-copy');
  const uploadProgressCopy = document.getElementById('upload-progress-copy');

  const analyzerCopy = {
    pdf: 'PDF upload: extracting page text, tables, structure, and image-backed content.',
    txt: 'TXT upload: indexing the full text with line-aware retrieval and stats.',
    md: 'Markdown upload: preserving sections, headings, and glossary-style definitions.',
    pptx: 'PPTX upload: analyzing each slide, text block, table, and presentation structure.',
    doc: 'DOCX upload: analyzing paragraphs, headings, tables, and embedded media.',
    docx: 'DOCX upload: analyzing paragraphs, headings, tables, and embedded media.',
    csv: 'CSV upload: indexing rows with column-aware statistical analysis.',
    xls: 'Excel upload: indexing sheet-by-sheet data with row and column statistics.',
    xlsx: 'Excel upload: indexing sheet-by-sheet data with row and column statistics.',
    png: 'Image upload: extracting visual content and searchable descriptions.',
    jpg: 'Image upload: extracting visual content and searchable descriptions.',
    jpeg: 'Image upload: extracting visual content and searchable descriptions.',
    webp: 'Image upload: extracting visual content and searchable descriptions.',
    svg: 'Image upload: extracting visual content and searchable descriptions.'
  };

  if (!toggleBtn) return;

  /* Toggle upload zone */
  toggleBtn.addEventListener('click', () => {
    zone.classList.toggle('active');
  });

  /* Drag & drop */
  uploadBox.addEventListener('dragover', e => {
    e.preventDefault();
    uploadBox.classList.add('dragover');
  });

  uploadBox.addEventListener('dragleave', () => {
    uploadBox.classList.remove('dragover');
  });

  uploadBox.addEventListener('drop', e => {
    e.preventDefault();
    uploadBox.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      submitFile();
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) submitFile();
  });

  function submitFile() {
    const fileName = fileInput.files[0].name || '';
    const ext = fileName.includes('.') ? fileName.split('.').pop().toLowerCase() : '';
    const analysisText = analyzerCopy[ext] || 'Uploading file with the matching analyzer and retrieval pipeline.';
    uploadLabel.textContent = fileInput.files[0].name;
    if (uploadAnalysis) uploadAnalysis.textContent = analysisText;
    if (uploadProgressCopy) uploadProgressCopy.textContent = analysisText;
    uploadBox.style.display = 'none';
    uploadProgress.classList.add('active');
    uploadForm.submit();
  }

});
