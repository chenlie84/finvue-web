(function () {
  const state = {
    loaded: false,
    reports: [],
    selected: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatDateTime(value) {
    if (!value) return "未知时间";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", { hour12: false });
  }

  function formatSize(bytes) {
    const value = Number(bytes || 0);
    if (!value) return "0 KB";
    if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
    return `${Math.max(1, Math.round(value / 1024))} KB`;
  }

  async function requestJson(url, options = {}) {
    const fetcher = window.apiFetch || fetch;
    const response = await fetcher(url, { credentials: "include", ...options });
    const data = await response.json();
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || data.detail || "请求失败");
    }
    return data;
  }

  function setStatus(text, tone = "") {
    const el = $("dailyReviewStatus");
    if (!el) return;
    el.textContent = text;
    el.style.color = tone === "error" ? "var(--red)" : tone === "ok" ? "var(--green)" : "var(--text1)";
  }

  function renderList() {
    const list = $("dailyReviewList");
    const count = $("dailyReviewCount");
    if (count) count.textContent = `${state.reports.length} 份`;
    if (!list) return;
    if (!state.reports.length) {
      list.innerHTML = '<div class="daily-review-empty">还没有生成行情复盘报告。</div>';
      return;
    }
    list.innerHTML = state.reports.map((item) => {
      const active = state.selected?.filename === item.filename ? " active" : "";
      return `
        <button class="daily-review-card${active}" type="button" data-review-file="${escapeHtml(item.filename)}">
          <div class="daily-review-card-title">${escapeHtml(item.title || item.filename)}</div>
          <div class="daily-review-card-meta">
            <span>${escapeHtml(item.tradeDate || "未知日期")}</span>
            <span>${escapeHtml(formatSize(item.size))}</span>
            <span>${escapeHtml(formatDateTime(item.updatedAt))}</span>
          </div>
        </button>
      `;
    }).join("");
    list.querySelectorAll("[data-review-file]").forEach((button) => {
      button.addEventListener("click", () => selectReport(button.dataset.reviewFile || ""));
    });
  }

  function renderViewer() {
    const title = $("dailyReviewViewerTitle");
    const frame = $("dailyReviewFrame");
    const openBtn = $("dailyReviewOpenBtn");
    if (!frame || !title || !openBtn) return;
    if (!state.selected) {
      title.textContent = "未选择报告";
      frame.removeAttribute("src");
      frame.style.display = "none";
      openBtn.disabled = true;
      return;
    }
    title.textContent = state.selected.title || state.selected.filename;
    frame.style.display = "block";
    frame.src = state.selected.viewUrl;
    openBtn.disabled = false;
  }

  function selectReport(filename) {
    const found = state.reports.find((item) => item.filename === filename) || null;
    state.selected = found;
    renderList();
    renderViewer();
  }

  async function load(force = false) {
    if (state.loaded && !force) return;
    setStatus("正在读取每日行情复盘...");
    try {
      const data = await requestJson("/api/daily-review/reports");
      state.reports = Array.isArray(data.reports) ? data.reports : [];
      state.selected = data.latest || state.reports[0] || null;
      state.loaded = true;
      renderList();
      renderViewer();
      setStatus(state.selected ? `已加载最新复盘：${state.selected.tradeDate || state.selected.filename}` : "暂无行情复盘报告", state.selected ? "ok" : "");
    } catch (error) {
      setStatus(`行情复盘加载失败：${error.message}`, "error");
    }
  }

  async function generate() {
    const dateInput = $("dailyReviewDateInput");
    const dateValue = String(dateInput?.value || "").replaceAll("-", "");
    const button = $("dailyReviewGenerateBtn");
    if (button) button.disabled = true;
    setStatus(dateValue ? `正在生成 ${dateValue} 行情复盘...` : "正在生成最新交易日行情复盘...");
    try {
      const data = await requestJson("/api/daily-review/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: dateValue }),
      });
      state.reports = Array.isArray(data.reports) ? data.reports : [];
      state.selected = data.latest || state.reports[0] || null;
      state.loaded = true;
      renderList();
      renderViewer();
      setStatus(data.message || "行情复盘已生成", "ok");
      window.showToast?.("行情复盘已生成");
    } catch (error) {
      setStatus(`生成失败：${error.message}`, "error");
      window.showToast?.(`生成失败：${error.message}`);
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function uploadSelectedFile(file) {
    if (!file) return;
    const dateInput = $("dailyReviewDateInput");
    const dateValue = String(dateInput?.value || "").replaceAll("-", "");
    const button = $("dailyReviewUploadBtn");
    if (button) button.disabled = true;
    setStatus(`正在上传 ${file.name} 到云端...`);
    try {
      const form = new FormData();
      form.append("file", file);
      if (dateValue) form.append("date", dateValue);
      const data = await requestJson("/api/daily-review/upload", {
        method: "POST",
        body: form,
      });
      state.reports = Array.isArray(data.reports) ? data.reports : [];
      state.selected = data.report || data.latest || state.reports[0] || null;
      state.loaded = true;
      renderList();
      renderViewer();
      setStatus(data.message || "行情复盘已上传到云端", "ok");
      window.showToast?.("行情复盘已上传");
    } catch (error) {
      setStatus(`上传失败：${error.message}`, "error");
      window.showToast?.(`上传失败：${error.message}`);
    } finally {
      if (button) button.disabled = false;
      const input = $("dailyReviewUploadInput");
      if (input) input.value = "";
    }
  }

  function openSelected() {
    if (!state.selected?.viewUrl) return;
    window.open(state.selected.viewUrl, "_blank", "noopener,noreferrer");
  }

  function bind() {
    $("dailyReviewRefreshBtn")?.addEventListener("click", () => load(true));
    $("dailyReviewUploadBtn")?.addEventListener("click", () => $("dailyReviewUploadInput")?.click());
    $("dailyReviewUploadInput")?.addEventListener("change", (event) => uploadSelectedFile(event.target?.files?.[0]));
    $("dailyReviewGenerateBtn")?.addEventListener("click", generate);
    $("dailyReviewOpenBtn")?.addEventListener("click", openSelected);
  }

  document.addEventListener("DOMContentLoaded", bind);
  window.FinVueDailyReview = { load, generate, openSelected };
})();
