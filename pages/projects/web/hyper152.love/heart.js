(() => {
    const toggles = [...document.querySelectorAll(".love-toggle")];
    const reset = document.getElementById("love-reset");

    function updateReset() {
        reset.hidden = !toggles.some((toggle) => toggle.checked);
    }

    if (new URLSearchParams(location.search).get("heart") === "1") {
        toggles.forEach((toggle) => {
            toggle.checked = true;
        });
    }
    toggles.forEach((toggle) => toggle.addEventListener("change", updateReset));
    reset.addEventListener("click", () => {
        toggles.forEach((toggle) => {
            toggle.checked = false;
        });
        updateReset();
        toggles[0].focus({ preventScroll: true });
    });
    updateReset();
})();
