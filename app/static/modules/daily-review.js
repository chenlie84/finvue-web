(function () {
  const state = { loaded: false, reports: [], selected: null, data: null, sectorId: "", chart: null };

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const num = (value, digits = 2) => value == null || Number.isNaN(Number(value)) ? "--" : Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
  const pct = (value) => value == null ? "--" : `${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(2)}%`;
  const tone = (value) => Number(value || 0) > 0 ? "up" : Number(value || 0) < 0 ? "down" : "flat";

  async function requestJson(url, options = {}) {
    const response = await (window.apiFetch || fetch)(url, { credentials: "include", ...options });
    const data = await response.json();
    if (!response.ok || data.ok === false) {
      const detail = data.detail && typeof data.detail === "object" ? data.detail : {};
      const error = new Error(detail.message || data.error || data.detail || "请求失败");
      error.diagnostics = detail.diagnostics || data.diagnostics || null;
      throw error;
    }
    return data;
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function setStatus(text, kind = "") {
    const el = $("dailyReviewStatus");
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = kind;
  }

  function statusWithDiagnostics(prefix, error) {
    const el = $("dailyReviewStatus");
    if (!el) return;
    const message = error?.message || String(error || "请求失败");
    const diagnostics = error?.diagnostics || null;
    if (!diagnostics) {
      setStatus(`${prefix}${message}`, "error");
      return;
    }
    const rows = [
      ["阶段", diagnostics.stage],
      ["交易日", diagnostics.tradeDate],
      ["耗时", diagnostics.elapsedSeconds ? `${diagnostics.elapsedSeconds} 秒` : ""],
      ["超时阈值", diagnostics.timeoutSeconds ? `${diagnostics.timeoutSeconds} 秒` : ""],
      ["返回码", diagnostics.returncode],
      ["脚本", diagnostics.script],
      ["脚本存在", diagnostics.scriptExists === false ? "否" : diagnostics.scriptExists === true ? "是" : ""],
      ["工作目录", diagnostics.cwd],
      ["输出目录", diagnostics.outputDir],
      ["输出目录存在", diagnostics.outputDirExists === false ? "否" : diagnostics.outputDirExists === true ? "是" : ""],
      ["命令", diagnostics.command],
    ].filter(([, value]) => value !== undefined && value !== null && value !== "");
    const recent = (diagnostics.recentOutputFiles || []).map((item) => `${item.name} (${item.size} bytes, ${item.updatedAt})`).join("\n");
    el.innerHTML = `
      <div class="daily-review-error-main">${esc(prefix)}${esc(message)}</div>
      <details class="daily-review-diagnostics" open>
        <summary>诊断详情</summary>
        <dl>${rows.map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>
        ${diagnostics.stderrTail ? `<h4>stderr 尾部</h4><pre>${esc(diagnostics.stderrTail)}</pre>` : ""}
        ${diagnostics.stdoutTail ? `<h4>stdout 尾部</h4><pre>${esc(diagnostics.stdoutTail)}</pre>` : ""}
        ${recent ? `<h4>最近输出文件</h4><pre>${esc(recent)}</pre>` : ""}
        ${(diagnostics.suggestions || []).length ? `<h4>排查建议</h4><ul>${diagnostics.suggestions.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : ""}
      </details>`;
    el.dataset.tone = "error";
  }

  function renderHistory() {
    const list = $("dailyReviewList");
    if ($("dailyReviewCount")) $("dailyReviewCount").textContent = `${state.reports.length} 份`;
    if (!list) return;
    list.innerHTML = state.reports.length ? state.reports.map((item) => `
      <button class="daily-review-date-chip${state.selected?.filename === item.filename ? " active" : ""}" type="button" data-review-file="${esc(item.filename)}">
        ${esc((item.tradeDate || "").replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3"))}
        ${item.dataAvailable ? "" : '<span title="需要重新生成原生数据">旧</span>'}
      </button>`).join("") : '<span class="muted">暂无复盘</span>';
    list.querySelectorAll("[data-review-file]").forEach((button) => button.addEventListener("click", () => selectReport(button.dataset.reviewFile)));
  }

  function renderScheduler(payload = {}) {
    const settings = payload.settings || {};
    const stateInfo = payload.state || {};
    const enabledInput = $("dailyReviewSchedulerEnabled");
    const timeInput = $("dailyReviewSchedulerTime");
    const retryInput = $("dailyReviewSchedulerRetry");
    const weekdayInput = $("dailyReviewSchedulerWeekdayOnly");
    if (enabledInput) enabledInput.checked = !!settings.enabled;
    if (timeInput) timeInput.value = settings.dailyRunTime || "17:40";
    if (retryInput) retryInput.value = settings.retryMinutes || 30;
    if (weekdayInput) weekdayInput.checked = settings.weekdayOnly !== false;
    const meta = $("dailyReviewSchedulerMeta");
    if (meta) {
      const token = payload.tokenConfigured ? "TuShare 已配置" : "TuShare Token 未配置";
      const status = stateInfo.status ? `最近状态：${stateInfo.status}${stateInfo.message ? ` · ${stateInfo.message}` : ""}` : "暂无运行记录";
      meta.textContent = `${payload.enabled ? "已启用" : "未启用"} · 北京时间 ${settings.dailyRunTime || "--"} · ${token} · ${status}`;
    }
  }

  function collectSchedulerSettings() {
    return {
      enabled: Boolean($("dailyReviewSchedulerEnabled")?.checked),
      dailyRunTime: $("dailyReviewSchedulerTime")?.value || "17:40",
      retryMinutes: Number($("dailyReviewSchedulerRetry")?.value || 30),
      weekdayOnly: $("dailyReviewSchedulerWeekdayOnly")?.checked !== false
    };
  }

  async function loadScheduler() {
    try {
      renderScheduler(await requestJson("/api/daily-review/scheduler"));
    } catch (_) {}
  }

  async function saveScheduler() {
    const button = $("dailyReviewSchedulerSaveBtn");
    try {
      if (button) button.disabled = true;
      const payload = await requestJson("/api/daily-review/scheduler", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: collectSchedulerSettings() })
      });
      renderScheduler(payload);
      window.showToast?.("行情复盘定时任务已保存");
    } catch (error) {
      window.showToast?.(`定时任务保存失败：${error.message}`);
    } finally {
      if (button) button.disabled = false;
    }
  }

  function metric(label, value, detail, kind = "") {
    return `<div class="daily-review-metric"><div class="daily-review-metric-label">${esc(label)}</div><div class="daily-review-metric-value ${kind}">${esc(value)}</div><div class="daily-review-metric-detail">${esc(detail)}</div></div>`;
  }

  function renderStock(stock) {
    return `<article class="daily-review-stock">
      <div class="daily-review-stock-head">
        <div><strong>${esc(stock.name)}</strong><span>${esc(stock.code)}</span></div>
        <b class="${tone(stock.pctChange)}">${pct(stock.pctChange)}</b>
      </div>
      <div class="daily-review-stock-tags"><span class="role ${stock.role === "龙头" ? "leader" : stock.role === "弹性" ? "elastic" : stock.role === "景气" ? "prosperity" : ""}">${esc(stock.role || "跟踪")}</span><span>${esc(stock.industry || "未分类")}</span></div>
      <dl><div><dt>成交额</dt><dd>${num(stock.amount)} 亿</dd></div><div><dt>换手</dt><dd>${num(stock.turnoverRate)}%</dd></div><div><dt>市值</dt><dd>${num(stock.marketValue)} 亿</dd></div></dl>
      <div class="daily-review-stock-scores"><span>行情景气 <b>${num(stock.prosperityScore, 1)}</b></span><span>弹性 <b>${num(stock.elasticityScore, 1)}</b></span></div>
      <p>${esc(stock.reason || "等待归因")}</p>
      <div class="daily-review-stock-risk">反证：${esc(stock.risk || "关注板块退潮与资金承接")}</div>
    </article>`;
  }

  function renderSectorDetail() {
    const mount = $("dailyReviewSectorDetail");
    if (!mount || !state.data) return;
    const sectors = state.data.sectors || [];
    const sector = sectors.find((item) => item.id === state.sectorId) || sectors[0];
    if (!sector) { mount.innerHTML = ""; return; }
    state.sectorId = sector.id;
    const analysis = sector.analysis || {};
    const stocks = sector.stocks || [];
    const evidence = Array.isArray(analysis.driverEvidence) ? analysis.driverEvidence : [];
    mount.innerHTML = `
      <div class="daily-review-sector-tabs">${sectors.map((item) => `<button type="button" data-sector-id="${esc(item.id)}" class="${item.id === sector.id ? "active" : ""}"><span>${esc(item.name)}</span><b class="${tone(item.pctChange)}">${pct(item.pctChange)}</b></button>`).join("")}</div>
      <section class="daily-review-sector-head">
        <div><span class="daily-review-eyebrow">当前主线</span><h2>${esc(sector.name)}</h2><p>${esc(analysis.summary || "等待 AI 归因")}</p></div>
        <div class="daily-review-sector-score"><b class="${tone(sector.pctChange)}">${pct(sector.pctChange)}</b><span>${sector.subsectors?.length || 0} 个细分赛道</span></div>
      </section>
      <div class="daily-review-analysis-grid">
        <article><span>产业链传导</span><p>${esc(analysis.chainLogic)}</p></article>
        <article><span>上涨驱动</span><p>${esc(analysis.riseReason)}</p></article>
        <article class="risk"><span>下跌与退潮风险</span><p>${esc(analysis.fallRisk)}</p></article>
        <article><span>次日验证</span><p>${esc(analysis.outlook)}</p></article>
      </div>
      ${evidence.length ? `<section class="daily-review-driver-evidence"><div class="daily-review-section-head"><div><span class="daily-review-eyebrow">Evidence chain</span><h3>上涨驱动证据链</h3></div><span>事实 → 传导 → 验证</span></div><div>${evidence.map((item) => `<article><b>${esc(item.type || "待核验")}</b><strong>${esc(item.fact)}</strong><p>${esc(item.transmission)}</p><small>验证：${esc(item.validation)}</small>${item.sourceUrl ? `<a href="${esc(item.sourceUrl)}" target="_blank" rel="noopener noreferrer">来源：${esc(item.sourceTitle || "产业新闻")}</a>` : ""}</article>`).join("")}</div></section>` : ""}
      <section class="daily-review-section">
        <div class="daily-review-section-head"><div><span class="daily-review-eyebrow">Industry chain</span><h3>细分赛道强度</h3></div><span>涨跌与成分股宽度</span></div>
        <div class="daily-review-subsector-table">
          <div class="head"><span>细分赛道</span><span>涨跌幅</span><span>代表标的</span><span>上涨 / 下跌</span><span>核心驱动</span></div>
          ${(sector.subsectors || []).map((sub) => `<div class="row"><span><strong>${esc(sub.name)}</strong><small>${esc(sub.chainStage || sub.type)} · ${esc(sub.source)}</small></span><b class="${tone(sub.pctChange)}">${pct(sub.pctChange)}</b><span>${esc((sub.stocks || []).slice(0, 6).map((s) => s.name).join("、") || "--")}</span><span class="breadth"><i style="--up:${Math.max(1, sub.upCount || 0)};--down:${Math.max(1, sub.downCount || 0)}"></i>${sub.upCount || 0} / ${sub.downCount || 0}</span><span>${esc(sub.reason)}</span></div>`).join("")}
        </div>
      </section>
      <section class="daily-review-section">
        <div class="daily-review-section-head"><div><span class="daily-review-eyebrow">Leaders & beta</span><h3>龙头与弹性标的</h3></div><span>AI 归因基于当日行情与公开消息</span></div>
        <div class="daily-review-stock-grid">${stocks.map(renderStock).join("")}</div>
      </section>`;
    mount.querySelectorAll("[data-sector-id]").forEach((button) => button.addEventListener("click", () => { state.sectorId = button.dataset.sectorId; renderSectorDetail(); }));
  }

  function renderChart() {
    const chartEl = $("dailyReviewSankey");
    if (!chartEl || !state.data || typeof window.echarts === "undefined") return;
    state.chart?.dispose();
    state.chart = window.echarts.init(chartEl);
    const raw = state.data.sankey || { nodes: [], links: [] };
    const colors = { sector: "#E5B84A", subsector: "#4A90D9", stock: "#2DBD85" };
    const nodes = (raw.nodes || []).map((node) => ({ ...node, itemStyle: { color: colors[node.kind] || "#9B7FE8" } }));
    chartEl.style.height = `${Math.min(560, Math.max(320, nodes.length * 7))}px`;
    state.chart.resize();
    state.chart.setOption({
      backgroundColor: "transparent",
      tooltip: { trigger: "item", backgroundColor: "#11131A", borderColor: "#2E3347", textStyle: { color: "#EAE6DD" }, formatter: (item) => item.dataType === "node" ? `${esc(item.data.displayName || item.name)}${item.data.code ? `<br/>${esc(item.data.code)} · ${esc(item.data.role)}` : ""}<br/>涨跌：${pct(item.data.pctChange)}` : `${esc(item.data.source)} → ${esc(item.data.target)}` },
      series: [{ type: "sankey", left: 10, right: 116, top: 10, bottom: 10, nodeWidth: 8, nodeGap: 8, draggable: false, nodeAlign: "justify", emphasis: { focus: "adjacency" }, data: nodes, links: raw.links || [], lineStyle: { color: "gradient", opacity: 0.22, curveness: 0.48 }, label: { color: "#8B918C", fontSize: 10, distance: 5, formatter: ({ data }) => data.displayName || String(data.name || "").split("｜").slice(1).join("｜") || data.name }, levels: [{ depth: 0, itemStyle: { borderWidth: 0 } }, { depth: 1, itemStyle: { borderWidth: 0 } }, { depth: 2, itemStyle: { borderWidth: 0 }, label: { position: "right", width: 104, overflow: "truncate" } }] }],
    });
    state.chart.on("click", (params) => {
      if (params.dataType !== "node" || !String(params.name).startsWith("板块｜")) return;
      const name = String(params.name).replace("板块｜", "");
      const sector = (state.data.sectors || []).find((item) => item.name === name);
      if (sector) { state.sectorId = sector.id; renderSectorDetail(); }
    });
  }

  function renderNative() {
    const mount = $("dailyReviewNative");
    if (!mount || !state.data) return;
    const report = state.data;
    const o = report.overview || {};
    mount.innerHTML = `
      <section class="daily-review-summary">
        <div><span class="daily-review-eyebrow">${esc(report.tradeDate?.replace(/(\d{4})(\d{2})(\d{2})/, "$1.$2.$3"))} · ${esc(report.source)}</span><h1>A 股产业链行情复盘</h1><p>${esc(report.marketConclusion || "从强势板块出发，观察产业链扩散与龙头承接。")}</p></div>
        <div class="daily-review-ai-state ${report.ai?.status || "pending"}"><i></i><span>${esc(report.ai?.message || "规则归因")}</span><small>${esc(report.ai?.provider || "")}</small></div>
      </section>
      <div class="daily-review-metrics">
        ${metric("上涨 / 下跌", `${num(o.advance, 0)} / ${num(o.decline, 0)}`, `涨跌比 ${num(o.advanceDeclineRatio)}`, o.advance >= o.decline ? "up" : "down")}
        ${metric("成交额", `${num(o.amountYi)} 亿`, "全市场成交额")}
        ${metric("涨停 / 跌停", `${num(o.limitUp, 0)} / ${num(o.limitDown, 0)}`, "近似统计", o.limitUp > o.limitDown ? "up" : "down")}
        ${metric("市场状态", o.sentiment || "--", "由市场宽度判断", o.sentiment === "活跃" ? "up" : o.sentiment === "退潮" ? "down" : "")}
        ${metric("强势主线", `${report.sectors?.length || 0} 条`, "板块产业链聚合")}
        ${metric("龙虎榜标的", `${num(o.lhbCount, 0)} 只`, "机构与股通验证")}
      </div>
      <section class="daily-review-flow-section">
        <div class="daily-review-section-head"><div><span class="daily-review-eyebrow">Capital flow map</span><h3>板块 → 细分赛道 → 龙头 / 弹性标的</h3></div><div class="daily-review-legend"><span class="sector">板块</span><span class="track">细分赛道</span><span class="stock">标的</span></div></div>
        <div id="dailyReviewSankey" class="daily-review-sankey"></div>
      </section>
      <div id="dailyReviewSectorDetail"></div>
      <section class="daily-review-section daily-review-news">
        <div class="daily-review-section-head"><div><span class="daily-review-eyebrow">Evidence</span><h3>当日产业新闻线索</h3></div><span>用于验证，不替代公告与财报</span></div>
        <div>${(report.news || []).length ? report.news.map((item, index) => { const body = `<b>${String(index + 1).padStart(2, "0")}</b><span>${esc(item.title)}<small>${esc(item.platform || "产业新闻")}${item.relevance ? ` · 关联 ${num(item.relevance, 0)}` : ""}</small></span><time>${esc(item.publishedAt || "")}</time>`; return item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${body}</a>` : `<div class="daily-review-news-item">${body}</div>`; }).join("") : '<div class="daily-review-empty">当日暂无匹配的产业新闻。</div>'}</div>
      </section>`;
    renderChart();
    renderSectorDetail();
  }

  async function selectReport(filename) {
    state.selected = state.reports.find((item) => item.filename === filename) || null;
    state.data = null;
    renderHistory();
    if (!state.selected?.dataAvailable || !state.selected?.dataUrl) {
      $("dailyReviewNative").innerHTML = '<div class="daily-review-empty"><strong>这是一份旧版 HTML 报告</strong><br>请按该交易日重新生成，即可获得原生产业链页面与 AI 涨跌归因。</div>';
      setStatus("旧版报告没有结构化数据，请重新生成", "warn");
      return;
    }
    setStatus(`正在加载 ${state.selected.tradeDate} 结构化复盘...`);
    try {
      const payload = await requestJson(state.selected.dataUrl);
      state.data = payload.report;
      state.sectorId = state.data?.sectors?.[0]?.id || "";
      const dateInput = $("dailyReviewDateInput");
      if (dateInput && state.data?.tradeDate) dateInput.value = state.data.tradeDate.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3");
      renderNative();
      setStatus(`已加载 ${state.data.tradeDate} · ${state.data.source}`, "ok");
    } catch (error) {
      statusWithDiagnostics("复盘加载失败：", error);
    }
  }

  async function load(force = false) {
    if (state.loaded && !force) return;
    setStatus("正在读取行情复盘...");
    try {
      loadScheduler();
      const data = await requestJson("/api/daily-review/reports");
      state.reports = Array.isArray(data.reports) ? data.reports : [];
      state.loaded = true;
      const target = data.latest || state.reports[0] || null;
      renderHistory();
      if (target) await selectReport(target.filename);
      else setStatus("暂无复盘，请生成最新交易日数据");
    } catch (error) { statusWithDiagnostics("行情复盘加载失败：", error); }
  }

  async function generate() {
    const value = String($("dailyReviewDateInput")?.value || "").replaceAll("-", "");
    const button = $("dailyReviewGenerateBtn");
    if (button) button.disabled = true;
    setStatus(value ? `正在生成 ${value} 复盘并进行 AI 归因...` : "正在生成最新交易日复盘并进行 AI 归因...");
    try {
      let data = await requestJson("/api/daily-review/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ date: value }) });
      if (data.jobId) {
        setStatus(data.message || "复盘生成已启动，正在等待后台任务...");
        data = await waitForGenerationJob(data.jobId);
      }
      state.reports = data.reports || [];
      state.loaded = true;
      renderHistory();
      if (data.latest) await selectReport(data.latest.filename);
      setStatus(data.aiWarning ? `复盘已生成；${data.aiWarning}` : "复盘与 AI 涨跌归因已生成", data.aiWarning ? "warn" : "ok");
      window.showToast?.("行情复盘已生成");
    } catch (error) { statusWithDiagnostics("生成失败：", error); window.showToast?.(`生成失败：${error.message}`); }
    finally { if (button) button.disabled = false; }
  }

  async function waitForGenerationJob(jobId) {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await sleep(3000);
      const payload = await requestJson(`/api/daily-review/jobs/${encodeURIComponent(jobId)}`);
      const job = payload.job || {};
      if (job.status === "completed") return job.result || {};
      if (job.status === "failed") {
        const error = new Error(job.error || job.message || "后台生成失败");
        error.diagnostics = job.diagnostics || null;
        throw error;
      }
      const waited = Math.round(((attempt + 1) * 3) / 60 * 10) / 10;
      setStatus(`${job.message || "后台生成中"} · 已等待 ${waited} 分钟`);
      if (attempt % 4 === 3) {
        try {
          const data = await requestJson("/api/daily-review/reports");
          state.reports = Array.isArray(data.reports) ? data.reports : [];
          renderHistory();
        } catch (_) {}
      }
    }
    throw new Error("后台生成仍在进行，请稍后刷新列表查看输出结果");
  }

  function bind() {
    $("dailyReviewRefreshBtn")?.addEventListener("click", () => load(true));
    $("dailyReviewGenerateBtn")?.addEventListener("click", generate);
    $("dailyReviewSchedulerSaveBtn")?.addEventListener("click", saveScheduler);
    window.addEventListener("resize", () => state.chart?.resize());
  }
  document.addEventListener("DOMContentLoaded", bind);
  window.FinVueDailyReview = { load, generate };
})();
