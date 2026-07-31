// FinVue shared UI helpers. Loaded before business modules.
(function () {
  let _tt;
  function showToast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(_tt);
    _tt = setTimeout(() => t.classList.remove("show"), 2200);
  }

  window.showToast = showToast;
})();
