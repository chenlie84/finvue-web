(function () {
  function mount() {
    const homeNavBtn = Array.from(document.querySelectorAll("#pg-dashboard .sidebar .nav-item")).find((item) => item.textContent.includes("工作台总览") || item.textContent.includes("工作台概览"));
    if (homeNavBtn) homeNavBtn.innerHTML = `<span class="ni">◈</span> 工作台概览`;
    const navBtn = Array.from(document.querySelectorAll("#pg-dashboard .sidebar .nav-item")).find((item) => item.textContent.includes("投顾画像") || item.textContent.includes("主播画像"));
    if (navBtn) navBtn.innerHTML = `<span class="ni">◎</span> 主播画像`;
    const homeTitle = document.querySelector("#sec-home .page-title");
    if (homeTitle) homeTitle.textContent = "工作台概览";
    const portraitTitle = document.querySelector("#sec-portrait .page-title");
    if (portraitTitle) portraitTitle.textContent = "主播画像";
  }

  function installShowSecHook() {
    if (window.__anchorDashboardShowSecPatched || typeof window.showSec !== "function") return;
    const original = window.showSec;
    window.showSec = function patchedShowSec(id, btn) {
      original.call(this, id, btn);
      if (id === "home") {
        window.AnchorDashboardOverview?.ensureRendered();
      } else if (id === "portrait") {
        window.AnchorPortraitPage?.ensureRendered();
      }
    };
    window.__anchorDashboardShowSecPatched = true;
  }

  function boot() {
    mount();
    installShowSecHook();
    window.AnchorDashboardOverview?.ensureRendered();
    window.AnchorPortraitPage?.ensureRendered();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
