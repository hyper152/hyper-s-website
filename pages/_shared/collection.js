(() => {
  'use strict';
  const grids = document.querySelectorAll('[data-searchable-collection]');
  for (const grid of grids) {
    const cards = [...grid.querySelectorAll(':scope > a.video-card')];
    if (!cards.length) continue;
    const toolbar = document.createElement('div');
    toolbar.className = 'collection-toolbar';
    const label = document.createElement('label');
    label.className = 'collection-search';
    const input = document.createElement('input');
    input.type = 'search'; input.placeholder = '按标题、技术或关键词查找…';
    input.setAttribute('aria-label', '搜索当前内容集合');
    label.append(input);
    const result = document.createElement('span');
    result.className = 'collection-result'; result.setAttribute('aria-live', 'polite');
    toolbar.append(label, result); grid.before(toolbar);
    const empty = document.createElement('p'); empty.className = 'collection-empty';
    empty.textContent = '没有找到匹配内容，换个关键词试试。'; empty.hidden = true; grid.append(empty);
    const entries = cards.map(card => ({card, text:card.textContent.toLocaleLowerCase()}));
    function filter() {
      const terms = input.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      let count = 0;
      for (const {card, text} of entries) {card.hidden = !terms.every(term => text.includes(term)); if (!card.hidden) count++;}
      result.textContent = `${count} / ${cards.length} 项`; empty.hidden = count > 0;
    }
    input.addEventListener('input', filter); filter();
  }
})();
