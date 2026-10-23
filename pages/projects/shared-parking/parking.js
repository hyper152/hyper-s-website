(() => {
  'use strict';
  const dialog = document.getElementById('parking-lightbox');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  const image = dialog.querySelector('img');
  const caption = dialog.querySelector('p');
  document.querySelectorAll('[data-parking-image]').forEach(link => {
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      const figure = link.closest('figure');
      const original = figure.querySelector('img');
      image.src = link.href;
      image.alt = original.alt;
      caption.textContent = figure.querySelector('figcaption strong').textContent;
      dialog.showModal();
      document.documentElement.classList.add('parking-modal-open');
    });
  });
  dialog.querySelector('button').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    const bounds = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
  });
  dialog.addEventListener('close', () => {
    document.documentElement.classList.remove('parking-modal-open');
    image.removeAttribute('src');
  });
})();
