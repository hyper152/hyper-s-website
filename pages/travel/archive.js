(() => {
    const cards = [...document.querySelectorAll('.travel-card')];
    const search = document.querySelector('#travel-search');
    const count = document.querySelector('#travel-count');
    const result = document.querySelector('#travel-result');
    const empty = document.querySelector('#travel-empty');
    let selectedYear = 'all';
    let selectedCategory = 'all';
    function update() {
        const query = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        cards.forEach(card => {
            const matches = (selectedYear === 'all' || card.dataset.year === selectedYear)
                && (selectedCategory === 'all' || card.dataset.category === selectedCategory)
                && card.dataset.search.toLocaleLowerCase().includes(query);
            card.hidden = !matches;
            if (matches) visible += 1;
        });
        count.textContent = visible;
        result.textContent = `${visible} 段旅程${visible === cards.length ? '，按时间倒序' : ` / 共 ${cards.length} 段`}`;
        empty.hidden = visible > 0;
        document.querySelectorAll('[data-year-filter]').forEach(button => button.setAttribute('aria-pressed', button.dataset.yearFilter === selectedYear));
        document.querySelectorAll('[data-category-filter]').forEach(button => button.setAttribute('aria-pressed', button.dataset.categoryFilter === selectedCategory));
    }
    document.querySelectorAll('[data-year-filter]').forEach(button => button.addEventListener('click', () => { selectedYear = button.dataset.yearFilter; update(); }));
    document.querySelectorAll('[data-category-filter]').forEach(button => button.addEventListener('click', () => { selectedCategory = button.dataset.categoryFilter; update(); }));
    search.addEventListener('input', update);
    document.querySelector('#travel-reset').addEventListener('click', () => { selectedYear = 'all'; selectedCategory = 'all'; search.value = ''; update(); search.focus(); });
    update();
})();