(() => {
    const viewer = document.querySelector(".photo-viewer");
    if (!viewer || typeof viewer.showModal !== "function") return;

    const photos = [...document.querySelectorAll("[data-photo]")].sort(
        (first, second) => Number(first.dataset.order) - Number(second.dataset.order),
    );
    const image = document.getElementById("viewer-image");
    const caption = document.getElementById("viewer-caption");
    const position = document.getElementById("viewer-position");
    const original = document.getElementById("viewer-original");
    let active = 0;
    let opener;

    function display(index) {
        active = (index + photos.length) % photos.length;
        const photo = photos[active];
        image.src = photo.href;
        image.alt = photo.querySelector("img").alt;
        caption.textContent = photo.dataset.caption;
        position.textContent = `${String(active + 1).padStart(2, "0")} / ${String(photos.length).padStart(2, "0")}`;
        original.href = photo.href;
    }

    photos.forEach((photo, index) => {
        photo.addEventListener("click", (event) => {
            if (
                event.button !== 0 ||
                event.ctrlKey ||
                event.metaKey ||
                event.shiftKey ||
                event.altKey
            )
                return;
            event.preventDefault();
            opener = photo;
            display(index);
            viewer.showModal();
            document.body.classList.add("photo-viewer-open");
        });
    });

    viewer.querySelector("[data-close]").addEventListener("click", () => viewer.close());
    viewer.querySelector("[data-previous]").addEventListener("click", () => display(active - 1));
    viewer.querySelector("[data-next]").addEventListener("click", () => display(active + 1));
    viewer.addEventListener("keydown", (event) => {
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            display(active + (event.key === "ArrowLeft" ? -1 : 1));
        }
    });
    viewer.addEventListener("click", (event) => {
        if (event.target !== viewer) return;
        const bounds = viewer.getBoundingClientRect();
        if (
            event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom
        )
            viewer.close();
    });
    viewer.addEventListener("close", () => {
        document.body.classList.remove("photo-viewer-open");
        if (opener) opener.focus({ preventScroll: true });
    });
})();
