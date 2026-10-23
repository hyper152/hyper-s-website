(() => {
    const viewer = document.querySelector('#viewer');
    if (!viewer) return;
    const photos = [...document.querySelectorAll('.photo')].filter(button => button.querySelector('img'));
    const preview = viewer.querySelector('img');
    const caption = viewer.querySelector('p');
    const original = viewer.querySelector('a');
    const close = viewer.querySelector('button');
    const previous = document.createElement('button');
    const next = document.createElement('button');
    const count = document.createElement('span');
    previous.type = next.type = 'button';
    previous.className = 'journal-viewer-prev'; next.className = 'journal-viewer-next'; count.className = 'journal-viewer-count';
    previous.setAttribute('aria-label', '上一张照片'); next.setAttribute('aria-label', '下一张照片');
    previous.textContent = '‹'; next.textContent = '›';
    count.setAttribute('aria-live', 'polite');
    viewer.append(previous, next, count);
    let selected = 0;
    let touchStart = null;
    function show(index) {
        if (index < 0 || index >= photos.length) return;
        selected = index;
        const button = photos[index];
        const image = button.querySelector('img');
        preview.src = image.currentSrc || image.src;
        preview.alt = image.alt;
        caption.textContent = image.alt;
        if (original) original.href = button.dataset.original || image.src;
        count.textContent = `${index + 1} / ${photos.length}`;
        previous.disabled = index === 0;
        next.disabled = index === photos.length - 1;
    }
    photos.forEach((button, index) => button.addEventListener('click', () => { show(index); if (!viewer.open) viewer.showModal(); }));
    close?.addEventListener('click', () => viewer.close());
    previous.addEventListener('click', () => show(selected - 1));
    next.addEventListener('click', () => show(selected + 1));
    viewer.addEventListener('keydown', event => {
        if (event.key === 'ArrowLeft') { event.preventDefault(); show(selected - 1); }
        if (event.key === 'ArrowRight') { event.preventDefault(); show(selected + 1); }
    });
    viewer.addEventListener('click', event => {
        if (event.target !== viewer) return;
        const rect = viewer.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) viewer.close();
    });
    preview.addEventListener('touchstart', event => { touchStart = event.changedTouches[0].clientX; }, { passive: true });
    preview.addEventListener('touchend', event => {
        if (touchStart === null) return;
        const distance = event.changedTouches[0].clientX - touchStart;
        if (Math.abs(distance) > 50) show(selected + (distance < 0 ? 1 : -1));
        touchStart = null;
    }, { passive: true });
})();