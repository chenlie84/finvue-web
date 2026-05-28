(function () {
  const state = { loaded: false, anchors: [], lastResult: null };

  const $ = (id) => document.getElementById(id);
  const html = (value) => String(value ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  const fmt = (value, digits = 1) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    return num.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  };
  const cls = (value) => {
    if (value === "验证") return "green";
    if (value === "部分") return "gold";
    if (value === "未验证") return "red";
    return "gray";
  };
  const pctText = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    return `${num >= 0 ? "+" : ""}${fmt(num, 2)}%`;
  };
  const today = () => new Date().toISOString().slice(0, 10);
  const addDays = (date, days) => {
    const next = new Date(date);
    next.setDate(next.getDate() + days);
    return next.toISOString().slice(0, 10);
  };

  async function requestJson(url, options = {}) {
    const response = await fetch(url, { credentials: "include", headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || "请求失败");
    return data;
  }

  function setStatus(message) {
    const el = $("backtestStatus");
    if (el) el.textContent = message;
  }

  function setPeriod(days, chip) {
    const end = today();
    $("backtestEnd").value = end;
    $("backtestStart").value = addDays(end, -days);
    document.querySelectorAll(".backtest-chip").forEach((item) => item.classList.remove("active"));
    chip?.classList.add("active");
  }

  function renderAnchors() {
    const select = $("backtestAnchor");
    if (!select) return;
    const options = state.anchors.map((item) => `<option value="${html(item.anchorName)}">${html(item.anchorName)}${item.reportCount ? ` · ${item.reportCount}份` : ""}</option>`).join("");
    select.innerHTML = `<option value="all">全体主播</option>${options}`;
  }

  function kpi(label, value, note, accent) {
    return `<div class="backtest-kpi" style="--accent:${accent}">
      <div class="backtest-kpi-label">${html(label)}</div>
      <div class="backtest-kpi-value">${html(value)}</div>
      <div class="backtest-kpi-note">${html(note)}</div>
    </div>`;
  }

  function renderBars(summary) {
    const rows = [
      ["观点验证率", summary.validationRate || 0, "green"],
      ["行情命中率", summary.coverageRate || 0, "gold"],
      ["有效样本占比", summary.reportCount ? (summary.matchedCount || 0) / summary.reportCount * 100 : 0, "blue"],
    ];
    return `<div class="backtest-bars">${rows.map(([label, value, color]) => `
      <div>
        <div class="backtest-bar-head"><span>${html(label)}</span><span class="${color}">${fmt(value)}%</span></div>
        <div class="backtest-track"><div class="backtest-fill ${color}" style="width:${Math.max(0, Math.min(100, Number(value) || 0))}%"></div></div>
      </div>
    `).join("")}</div>`;
  }

  function renderTable(details) {
    if (!details?.length) return '<div class="backtest-empty">这个时间段还没有可回测的主播分析报告。</div>';
    return `<div class="backtest-table-wrap"><table class="backtest-table">
      <thead><tr><th>日期</th><th>主播</th><th>观点/报告</th><th>命中标的</th><th>方向</th><th>5日表现</th><th>验证</th><th>结论</th></tr></thead>
      <tbody>${details.map((item) => `<tr>
        <td class="mono muted">${html(item.date || "--")}</td>
        <td>${html(item.anchorName || "--")}</td>
        <td class="backtest-title-cell">${html(item.title || "--")}</td>
        <td class="backtest-target">${html(item.target || "--")}</td>
        <td>${html(item.direction || "--")}</td>
        <td class="${Number(item.returnPct || 0) >= 0 ? "green" : "red"}">${pctText(item.returnPct)}</td>
        <td><span class="badge ${cls(item.verdict)}">${html(item.verdict || "观察")}</span></td>
        <td class="muted">${html(item.conclusion || "--")}</td>
      </tr>`).join("")}</tbody>
    </table></div>`;
  }

  function renderResult(result) {
    state.lastResult = result;
    const summary = result.summary || {};
    const details = result.details || [];
    $("backtestKpis").innerHTML = [
      kpi("综合评分", summary.avgScore ? fmt(summary.avgScore) : "--", "按观点验证结果折算", "var(--gold)"),
      kpi("观点验证率", `${fmt(summary.validationRate || 0)}%`, `${summary.matchedCount || 0} 个有效方向样本`, "var(--green)"),
      kpi("行情命中率", `${fmt(summary.coverageRate || 0)}%`, "报告关键词命中行情标的/主题", "var(--blue)"),
      kpi("回测样本", `${summary.reportCount || 0}`, "来自主播资料库/分析报告", "var(--purple)"),
    ].join("");
    $("backtestInsight").innerHTML = renderBars(summary);
    $("backtestTable").innerHTML = renderTable(details);
    setStatus(summary.configured ? `回测完成：已结合 TuShare 历史行情与 ${summary.reportCount || 0} 份分析报告。` : "回测完成，但 TuShare token 未配置，无法拉取历史行情。");
    setTimeout(() => window.drawSpark?.("backtestChart", result.trend?.length ? result.trend : [7.2, 7.4, 7.1, 7.8], true), 60);
  }

  async function load() {
    if (state.loaded) return;
    state.loaded = true;
    const start = $("backtestStart");
    const end = $("backtestEnd");
    if (end && !end.value) end.value = today();
    if (start && !start.value) start.value = addDays(today(), -180);
    document.querySelectorAll("[data-backtest-days]").forEach((chip) => {
      chip.addEventListener("click", () => setPeriod(Number(chip.dataset.backtestDays || 30), chip));
    });
    $("backtestRunBtn")?.addEventListener("click", run);
    try {
      const data = await requestJson("/api/backtest/anchors");
      state.anchors = data.anchors || [];
      renderAnchors();
      setStatus(state.anchors.length ? "请选择主播和时间范围后开始回测。" : "主播资料库暂无分析报告，可先保存直播分析结果后再回测。");
    } catch (error) {
      setStatus(`读取主播资料失败：${error.message}`);
    }
  }

  async function run() {
    setStatus("正在回测：匹配主播报告关键词，并拉取对应历史行情...");
    const btn = $("backtestRunBtn");
    if (btn) btn.disabled = true;
    try {
      const data = await requestJson("/api/backtest/run", {
        method: "POST",
        body: JSON.stringify({
          anchorName: $("backtestAnchor")?.value || "all",
          dimension: $("backtestDimension")?.value || "综合验证",
          startDate: $("backtestStart")?.value,
          endDate: $("backtestEnd")?.value,
        }),
      });
      renderResult(data);
      window.showToast?.("历史回测完成");
    } catch (error) {
      setStatus(`回测失败：${error.message}`);
      window.showToast?.("历史回测失败");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  window.FinVueBacktest = { load, run };
})();
