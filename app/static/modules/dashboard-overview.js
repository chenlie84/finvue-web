(function () {
  const state = {
    start: "",
    end: ""
  };

  function formatDateInput(date) {
    const d = new Date(date);
    if (Number.isNaN(d.getTime())) return "";
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function ensureDefaultRange() {
    if (state.start && state.end) return;
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 6);
    state.start = formatDateInput(start);
    state.end = formatDateInput(end);
  }

  function cardMetric(label, value, sub, accentClass = "") {
    return `
      <div class="anchor-kpi-card">
        <div class="anchor-kpi-label">${label}</div>
        <div class="anchor-kpi-value ${accentClass}">${value}</div>
        <div class="anchor-kpi-sub">${sub}</div>
      </div>
    `;
  }

  function weeklyCard(label, value, unit, change) {
    const api = window.AnchorDashboardApi;
    const signed = api.formatSignedPercent(change);
    const tone = Number(change) > 0 ? "green" : Number(change) < 0 ? "red" : "";
    return `
      <div class="anchor-pill">
        <span>${label}</span>
        <strong>${value}${unit === "rate" ? "" : unit || ""}</strong>
        <span class="${tone}">${signed}</span>
      </div>
    `;
  }

  function renderHome(payload) {
    const api = window.AnchorDashboardApi;
    const section = document.getElementById("sec-home");
    if (!section) return;
    ensureDefaultRange();

    const summary = payload.summary || {};
    const cards = (payload.weekly_meeting_overview || {}).summary_cards || [];
    const anchors = (payload.anchors || []).slice().sort((a, b) => Number(b.acu || 0) - Number(a.acu || 0));
    const anomalies = payload.anomaly_list || [];
    const cultivatePool = payload.cultivate_pool || [];
    const actionRecords = (payload.action_records || []).slice(0, 6);
    const acuCard = cards.find((item) => String(item.label || "").includes("ACU"));
    const retentionCard = cards.find((item) => String(item.label || "").includes("停留"));
    const followCard = cards.find((item) => String(item.label || "").includes("转粉"));

    section.innerHTML = `
      <div class="page-title">工作台概览</div>
      <div class="page-sub">主播大盘实时快照 · 最近更新时间 ${api.formatDateTime(payload.updated_at)}</div>
      <div class="anchor-dashboard-grid">
        <div class="anchor-dashboard-section">
          <div class="anchor-dashboard-head">
            <div>
              <h3>大盘监控</h3>
              <div class="anchor-dashboard-note">选择日期区间后重拉 anchor_dashboard 周会与主播数据</div>
            </div>
            <button class="btn" id="dashboardDateRefreshBtn">刷新数据</button>
          </div>
          <div class="anchor-toolbar">
            <label class="anchor-field">
              <span>开始日期</span>
              <input id="dashboardStartDate" class="inp" type="date" value="${state.start}">
            </label>
            <label class="anchor-field">
              <span>结束日期</span>
              <input id="dashboardEndDate" class="inp" type="date" value="${state.end}">
            </label>
            <div class="anchor-toolbar-note">当前区间：${state.start} 至 ${state.end}</div>
          </div>
        </div>
        <div class="anchor-kpi-grid">
          ${cardMetric("在库主播", summary.total_anchors ?? "—", `红 ${summary.red ?? 0} / 黄 ${summary.yellow ?? 0} / 绿 ${summary.green ?? 0}`, "gold")}
          ${cardMetric("区间 ACU 均值", acuCard ? api.formatCompactNumber(acuCard.value) : "—", acuCard ? api.formatSignedPercent(acuCard.change) : "暂无数据", "blue")}
          ${cardMetric("区间停留均值", retentionCard ? `${Number(retentionCard.value || 0).toFixed(1)} min` : "—", retentionCard ? api.formatSignedPercent(retentionCard.change) : "暂无数据", "green")}
          ${cardMetric("区间转粉率", followCard ? api.formatPercent(followCard.value, 2) : "—", followCard ? api.formatSignedPercent(followCard.change) : "暂无数据", "gold")}
        </div>
        <div class="anchor-dashboard-two-col">
          <div class="anchor-dashboard-section">
            <div class="anchor-dashboard-head">
              <h3>主要主播表现</h3>
              <span class="anchor-dashboard-note">来自 anchor_dashboard 周会数据</span>
            </div>
            <div class="anchor-summary-list">
              ${anchors.slice(0, 6).map((anchor) => `
                <div class="anchor-summary-row">
                  <div>
                    <div class="anchor-name">${anchor.account || "未命名主播"}</div>
                    <div class="anchor-meta">${anchor.action || "未设置动作"} · ${anchor.quadrant || "未分象限"} · 在岗 ${anchor.tenure_month || 0} 个月</div>
                    <div class="anchor-pill-row">
                      <span class="anchor-status-pill ${anchor.status || "yellow"}">${anchor.status === "green" ? "绿区" : anchor.status === "red" ? "红区" : "黄区"}</span>
                      <span class="anchor-pill">系统动作 ${anchor.system_action || "待判断"}</span>
                      <span class="anchor-pill">人工动作 ${anchor.action || "待判断"}</span>
                    </div>
                  </div>
                  <div class="anchor-stat">
                    <div class="anchor-stat-label">ACU</div>
                    <div class="anchor-stat-value gold">${Number(anchor.acu || 0).toFixed(1)}</div>
                  </div>
                  <div class="anchor-stat">
                    <div class="anchor-stat-label">停留</div>
                    <div class="anchor-stat-value blue">${Number(anchor.retention || 0).toFixed(2)}</div>
                  </div>
                  <div class="anchor-stat">
                    <div class="anchor-stat-label">转粉率</div>
                    <div class="anchor-stat-value green">${api.formatPercent(anchor.follow_rate, 2)}</div>
                  </div>
                </div>
              `).join("")}
            </div>
          </div>
          <div class="anchor-dashboard-grid">
            <div class="anchor-dashboard-section">
              <div class="anchor-dashboard-head">
                <h3>周会摘要</h3>
                <span class="anchor-dashboard-note">核心指标变动</span>
              </div>
              <div class="anchor-pill-row">
                ${cards.slice(0, 6).map((item) => weeklyCard(item.label, item.unit === "rate" ? api.formatPercent(item.value, 2) : api.formatCompactNumber(item.value, 1), item.unit, item.change)).join("")}
              </div>
            </div>
            <div class="anchor-dashboard-section">
              <div class="anchor-dashboard-head">
                <h3>异常提醒</h3>
                <span class="anchor-dashboard-note">${anomalies.length} 条待关注</span>
              </div>
              <div class="anchor-risk-list">
                ${anomalies.length ? anomalies.slice(0, 5).map((item) => `
                  <div class="anchor-risk-row">
                    <div class="anchor-name">${item.account || "未命名主播"}</div>
                    <div class="anchor-meta">${item.title || "异常提醒"}</div>
                    <div class="anchor-dashboard-note">${item.detail || ""}</div>
                  </div>
                `).join("") : `<div class="anchor-risk-row"><div class="anchor-meta">当前没有异常提醒</div></div>`}
              </div>
            </div>
            <div class="anchor-dashboard-section">
              <div class="anchor-dashboard-head">
                <h3>重点培养池</h3>
                <span class="anchor-dashboard-note">${cultivatePool.length} 位主播</span>
              </div>
              <div class="anchor-queue-list">
                ${cultivatePool.length ? cultivatePool.slice(0, 5).map((item) => `
                  <div class="anchor-queue-row">
                    <div class="anchor-name">${item.account}</div>
                    <div class="anchor-meta">${item.reason || "无备注"}</div>
                  </div>
                `).join("") : `<div class="anchor-queue-row"><div class="anchor-meta">当前没有培养池数据</div></div>`}
              </div>
            </div>
            <div class="anchor-dashboard-section">
              <div class="anchor-dashboard-head">
                <h3>最近动作记录</h3>
                <span class="anchor-dashboard-note">运营干预</span>
              </div>
              <div class="anchor-queue-list">
                ${actionRecords.length ? actionRecords.map((item) => `
                  <div class="anchor-queue-row">
                    <div class="anchor-name">${item.account || "未命名主播"}</div>
                    <div class="anchor-meta">${item.action || item.decision || "已记录动作"}</div>
                  </div>
                `).join("") : `<div class="anchor-queue-row"><div class="anchor-meta">暂无动作记录</div></div>`}
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    section.querySelector("#dashboardStartDate")?.addEventListener("change", (event) => {
      state.start = event.target.value || state.start;
    });
    section.querySelector("#dashboardEndDate")?.addEventListener("change", (event) => {
      state.end = event.target.value || state.end;
    });
    section.querySelector("#dashboardDateRefreshBtn")?.addEventListener("click", async () => {
      if (state.start && state.end && state.start > state.end) {
        window.showToast?.("开始日期不能晚于结束日期");
        return;
      }
      await ensureRendered(true);
    });
  }

  async function ensureRendered(force = false) {
    try {
      ensureDefaultRange();
      const payload = await window.AnchorDashboardApi.fetchWeekly({
        force,
        start: state.start,
        end: state.end
      });
      renderHome(payload);
    } catch (error) {
      const section = document.getElementById("sec-home");
      if (section) {
        section.innerHTML = `
          <div class="page-title">工作台概览</div>
          <div class="page-sub">主播大盘数据加载失败</div>
          <div class="panel"><div class="muted">${error.message}</div></div>
        `;
      }
      window.showToast?.(error.message || "工作台概览加载失败");
    }
  }

  window.AnchorDashboardOverview = {
    ensureRendered
  };
})();
