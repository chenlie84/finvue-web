/* ═══════════════════════════════════════════════════════════════════════════
   FinVue Theme Controller v1 — 统一主题切换
   替换 index.html / hotspot.html / sop.html / 各页内的重复实现
   用法:
     <button data-theme-btn="dark">深</button>
     <button data-theme-btn="light">浅</button>
   加载即自动初始化(localStorage 记忆)
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var KEY = "finvue-theme";

  function apply(theme) {
    var t = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(KEY, t); } catch (e) {}
    syncButtons(t);
  }

  function syncButtons(theme) {
    var btns = document.querySelectorAll("[data-theme-btn]");
    btns.forEach(function (b) {
      var on = b.getAttribute("data-theme-btn") === theme;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function init() {
    var saved;
    try { saved = localStorage.getItem(KEY); } catch (e) {}
    if (!saved) {
      saved = (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) ? "light" : "dark";
    }
    apply(saved);
    document.querySelectorAll("[data-theme-btn]").forEach(function (b) {
      if (b._fvThemeBound) return;
      b._fvThemeBound = true;
      b.addEventListener("click", function () { apply(b.getAttribute("data-theme-btn")); });
    });
    // 跨 tab 同步
    window.addEventListener("storage", function (e) {
      if (e.key === KEY && e.newValue) apply(e.newValue);
    });
  }

  window.FinVueTheme = { apply: apply, init: init };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
