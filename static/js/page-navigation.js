(() => {
    "use strict";
    const backLink = document.querySelector('[data-page-back]');
    if (!backLink) return;

    // A real link remains usable if JavaScript is unavailable or there is no in-site history.
    backLink.addEventListener('click', (event) => {
        if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        let cameFromSite = false;
        try {
            cameFromSite = new URL(document.referrer).origin === window.location.origin;
        } catch { /* Direct visit: follow the category fallback. */ }
        if (cameFromSite && window.history.length > 1) {
            event.preventDefault();
            window.history.back();
        }
    });
})();
