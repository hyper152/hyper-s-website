const viewer = document.querySelector("#viewer");
document.querySelectorAll(".photo").forEach((button) =>
    button.addEventListener("click", () => {
        const image = button.querySelector("img");
        viewer.querySelector("img").src = image.src;
        viewer.querySelector("img").alt = image.alt;
        viewer.querySelector("p").textContent = image.alt;
        viewer.querySelector("a").href = button.dataset.original;
        viewer.showModal();
    }),
);
viewer.querySelector("button").addEventListener("click", () => viewer.close());
viewer.addEventListener("click", (event) => {
    if (event.target === viewer) {
        const r = viewer.getBoundingClientRect();
        if (
            event.clientX < r.left ||
            event.clientX > r.right ||
            event.clientY < r.top ||
            event.clientY > r.bottom
        )
            viewer.close();
    }
});
