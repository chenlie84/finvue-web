/* ═══════════════════════════════════════════════════════════════════════════
   FinVue UI Core v2 — 公共交互工具
   - countUp       : 数字滚入(KPI 入场)
   - bindCountUps  : 自动扫描 data-count-to
   - toast         : 轻提示
   - emptyState    : 空状态 DOM
   - spinner       : 加载态 DOM
   - injectStagger : 自动给列表加 stagger
   - confirm       : 二次确认弹窗
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  /* ── count-up ─────────────────────────────────────────────────────── */
  function countUp(el, target, duration) {
    if (!el) return;
    if (el.dataset.counted === "1") return;
    el.dataset.counted = "1";
    var dur = duration || 800;
    var startTime = performance.now();
    var start = 0;
    var fmt;
    try { fmt = new Intl.NumberFormat("zh-CN"); } catch (e) { fmt = null; }
    function render(v) {
      if (fmt) el.textContent = fmt.format(Math.round(v));
      else el.textContent = String(Math.round(v));
    }
    function tick(now) {
      var t = Math.min((now - startTime) / dur, 1);
      var eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      render(start + (target - start) * eased);
      if (t < 1) requestAnimationFrame(tick);
      else render(target);
    }
    render(start);
    requestAnimationFrame(tick);
  }

  function bindCountUps(root) {
    var scope = root || document;
    var nodes = scope.querySelectorAll("[data-count-to]");
    if (!("IntersectionObserver" in window)) {
      nodes.forEach(function (el) { countUp(el, Number(el.dataset.countTo || 0), 0); });
      return;
    }
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          countUp(e.target, Number(e.target.dataset.countTo || 0));
          obs.unobserve(e.target);
        }
      });
    }, { threshold: 0.3, rootMargin: "0px 0px -40px 0px" });
    nodes.forEach(function (el) { obs.observe(el); });
  }

  /* ── toast ────────────────────────────────────────────────────────── */
  var _toastEl = null;
  var _toastT = null;
  function ensureToast() {
    if (_toastEl) return _toastEl;
    var el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.className = "toast";
      document.body.appendChild(el);
    }
    _toastEl = el;
    return el;
  }
  function toast(msg, type, timeout) {
    var el = ensureToast();
    el.textContent = msg || "";
    el.className = "toast show" + (type ? " toast-" + type : "");
    clearTimeout(_toastT);
    _toastT = setTimeout(function () { el.className = "toast"; }, timeout || 2200);
  }
  // 兼容旧 API
  function showToast(msg) { toast(msg); }

  /* ── empty-state ──────────────────────────────────────────────────── */
  function emptyState(opts) {
    opts = opts || {};
    var wrap = document.createElement("div");
    wrap.className = "empty-state";
    var icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = opts.icon || "◌";
    var title = document.createElement("div");
    title.className = "empty-title";
    title.textContent = opts.title || "暂无数据";
    wrap.appendChild(icon);
    wrap.appendChild(title);
    if (opts.desc) {
      var desc = document.createElement("div");
      desc.className = "empty-desc";
      desc.textContent = opts.desc;
      wrap.appendChild(desc);
    }
    if (opts.action) {
      var btn = document.createElement("button");
      btn.className = "btn btn-outline btn-sm";
      btn.textContent = opts.action;
      if (opts.onAction) btn.addEventListener("click", opts.onAction);
      wrap.appendChild(btn);
    }
    return wrap;
  }

  /* ── spinner ──────────────────────────────────────────────────────── */
  function spinner(size) {
    var el = document.createElement("span");
    el.className = "finvue-spinner";
    if (size) el.style.width = el.style.height = size + "px";
    return el;
  }

  /* ── inject-stagger ───────────────────────────────────────────────── */
  function injectStagger(root) {
    var scope = root || document;
    var sels = ".stagger, [data-stagger]";
    if (scope.querySelectorAll(sels).length === 0 && scope.matches && scope.matches(sels)) {
      scope.classList.add("stagger");
    }
    var nodes = scope.querySelectorAll(sels);
    nodes.forEach(function (n) { n.classList.add("stagger"); });
  }

  /* ── confirm ──────────────────────────────────────────────────────── */
  function confirm(opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      var bd = document.createElement("div");
      bd.className = "modal-backdrop";
      var panel = document.createElement("div");
      panel.className = "modal-panel";
      panel.style.maxWidth = "420px";
      panel.innerHTML =
        '<div class="panel-hd"><div class="panel-title">' + (opts.title || "确认操作") + '</div></div>' +
        '<div style="padding:6px 0 14px;color:var(--color-text-1);font-size:13px;line-height:1.65;">' +
          (opts.message || "") +
        '</div>' +
        '<div class="flex-end gap-sm">' +
          '<button class="btn btn-outline" data-act="cancel">取消</button>' +
          '<button class="btn btn-gold" data-act="ok">' + (opts.okText || "确定") + '</button>' +
        '</div>';
      bd.appendChild(panel);
      document.body.appendChild(bd);
      function close(ok) {
        document.body.removeChild(bd);
        resolve(ok);
      }
      bd.addEventListener("click", function (e) {
        var a = e.target.closest("[data-act]");
        if (!a) {
          if (e.target === bd) close(false);
          return;
        }
        close(a.dataset.act === "ok");
      });
    });
  }

  /* ── fmt helpers ──────────────────────────────────────────────────── */
  function fmtNum(n) {
    var v = Number(n || 0);
    try { return new Intl.NumberFormat("zh-CN").format(v); } catch (e) { return String(v); }
  }
  function escHtml(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  /* ── exports ──────────────────────────────────────────────────────── */
  window.FinVueUI = {
    countUp: countUp,
    bindCountUps: bindCountUps,
    toast: toast,
    showToast: showToast,
    emptyState: emptyState,
    spinner: spinner,
    injectStagger: injectStagger,
    confirm: confirm,
    fmtNum: fmtNum,
    escHtml: escHtml
  };
  // 兼容 IIFE 模块直接调用 showToast(...) / toast(...)
  window.showToast = showToast;
  window.toast = toast;
})();
