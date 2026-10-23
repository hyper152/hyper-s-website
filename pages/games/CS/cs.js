(() => {
    const photos = [...document.querySelectorAll('.cs-zoom img')];
    const viewer = document.querySelector('#cs-viewer');
    const image = viewer.querySelector('img');
    const caption = viewer.querySelector('p');
    const count = document.querySelector('#cs-counter');
    const previous = document.querySelector('#cs-prev');
    const next = document.querySelector('#cs-next');
    let index = 0;
    function show(selected) {
        if (selected < 0 || selected >= photos.length) return;
        index = selected;
        image.src = photos[index].currentSrc || photos[index].src;
        image.alt = caption.textContent = photos[index].alt;
        count.textContent = `${index + 1} / ${photos.length}`;
        previous.disabled = index === 0;
        next.disabled = index === photos.length - 1;
    }
    document.querySelectorAll('.cs-zoom').forEach((button, selected) => button.addEventListener('click', () => { show(selected); viewer.showModal(); }));
    document.querySelector('#cs-close').addEventListener('click', () => viewer.close());
    previous.addEventListener('click', () => show(index - 1));
    next.addEventListener('click', () => show(index + 1));
    viewer.addEventListener('keydown', event => {
        if (event.key === 'ArrowLeft') { event.preventDefault(); show(index - 1); }
        if (event.key === 'ArrowRight') { event.preventDefault(); show(index + 1); }
    });
    viewer.addEventListener('click', event => {
        if (event.target !== viewer) return;
        const rect = viewer.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) viewer.close();
    });
})();