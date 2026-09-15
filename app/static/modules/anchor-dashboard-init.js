(function () {
  function mount() {
    const homeTitle = document.querySelector("#sec-home .page-title");
    if (homeTitle) homeTitle.textContent = "工作台概览";
    const portraitTitle = document.querySelector("#sec-portrait .page-title");
    if (portraitTitle) portraitTitle.textContent = "主播画像";
  }

  function boot() {
    mount();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();