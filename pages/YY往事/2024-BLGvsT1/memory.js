(() => {
    const videos = [...document.querySelectorAll("video")];
    videos.forEach((current) => {
        current.addEventListener("play", () => {
            videos.forEach((video) => {
                if (video !== current) video.pause();
            });
        });
    });
})();
