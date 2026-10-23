(() => {
    // ISO dates may contain only a known year or month. Unknown dates stay last.
    document.querySelectorAll(".video-grid, .travel-grid").forEach((collection) => {
        const cards = [...collection.children].filter((card) =>
            card.matches(".video-card, .travel-card"),
        );
        cards.sort((first, second) => {
            const firstDate = first.dataset.startDate || "";
            const secondDate = second.dataset.startDate || "";
            return secondDate.localeCompare(firstDate);
        });
        cards.forEach((card) => collection.appendChild(card));
    });
})();
