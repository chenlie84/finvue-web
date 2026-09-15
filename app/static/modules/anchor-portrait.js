(function () {
  const state = {
    payload: null,
    selectedName: "",
    keyword: "",
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

  function levelLabel(status) {
    if (status === "green") return "绿区";
    if (status === "red") return "红区";
    return "黄区";
  }

  function safe(v, fallback = "—") {
    return v === null || v === undefined || v === "" ? fallback : v;
  }

  function renderPortrait(payload) {
    state.payload = payload;
    const section = document.getElementById("sec-portrait");
    if (!section) return;
    ensureDefaultRange();
    const anchors = payload.anchors || [];
    const api = window.AnchorDashboardApi;
    const refreshStats = payload.refresh_stats || {};
    if (!state.selectedName && anchors[0]) state.selectedName = anchors[0].account;
    const selected = anchors.find((item) => item.account === state.selectedName) || anchors[0];
    if (selected) state.selectedName = selected.account;
    const filtered = anchors.filter((anchor) => {
      const haystack = `${anchor.account || ""} ${anchor.action || ""} ${anchor.quadrant || ""}`.toLowerCase();
      return haystack.includes(state.keyword.toLowerCase());
    });

    const acuAvg = anchors.length ? anchors.reduce((sum, item) => sum + Number(item.acu || 0), 0) / anchors.length : 0;
    const retentionAvg = anchors.length ? anchors.reduce((sum, item) => sum + Number(item.retention || 0), 0) / anchors.length : 0;
    const followAvg = anchors.length ? anchors.reduce((sum, item) => sum + Number(item.follow_rate || 0), 0) / anchors.length : 0;

    section.innerHTML = `
      <div class="page-title">主播画像</div>
      <div class="page-sub">接入 anchor_dashboard 的主要主播周会数据，聚合主播状态、动作建议和 ROI 评估。</div>
      <div class="anchor-profile-shell">
        <div class="anchor-dashboard-section">
          <div class="anchor-dashboard-head">
            <div>
              <h3>画像监控</h3>
              <div class="anchor-dashboard-note">按日期区间切换主播大盘与 ROI 参考数据</div>
            </div>
            <button class="btn" id="anchorPortraitRefreshBtn">刷新画像</button>
          </div>
          <div class="anchor-toolbar">
            <label class="anchor-field">
              <span>开始日期</span>
              <input id="anchorPortraitStartDate" class="inp" type="date" value="${state.start}">
            </label>
            <label class="anchor-field">
              <span>结束日期</span>
              <input id="anchorPortraitEndDate" class="inp" type="date" value="${state.end}">
            </label>
            <div class="anchor-toolbar-note">当前区间：${state.start} 至 ${state.end}</div>
            <div class="anchor-toolbar-note">全局最新抓取：${safe(refreshStats.latest_live_time, safe(refreshStats.latest_live_date, "—"))}</div>
          </div>
        </div>
        <div class="anchor-kpi-grid">
          <div class="anchor-kpi-card"><div class="anchor-kpi-label">主要主播数</div><div class="anchor-kpi-value gold">${anchors.length}</div><div class="anchor-kpi-sub">当前 anchor_dashboard 主体名单</div></div>
          <div class="anchor-kpi-card"><div class="anchor-kpi-label">平均 ACU</div><div class="anchor-kpi-value blue">${acuAvg.toFixed(1)}</div><div class="anchor-kpi-sub">月均在线人数</div></div>
          <div class="anchor-kpi-card"><div class="anchor-kpi-label">平均停留</div><div class="anchor-kpi-value green">${retentionAvg.toFixed(2)}</div><div class="anchor-kpi-sub">分钟</div></div>
          <div class="anchor-kpi-card"><div class="anchor-kpi-label">平均转粉率</div><div class="anchor-kpi-value gold">${api.formatPercent(followAvg, 2)}</div><div class="anchor-kpi-sub">最新抓取日期 ${safe(refreshStats.latest_live_date, "—")}</div></div>
        </div>
        <div class="anchor-profile-layout">
          <div class="anchor-profile-list">
            <div class="anchor-dashboard-head" style="padding:18px 18px 0;">
              <h3>主播列表</h3>
              <span class="anchor-dashboard-note">${filtered.length} / ${anchors.length}</span>
            </div>
            <div style="padding:12px 18px 0;">
              <input id="anchorPortraitSearch" class="inp" placeholder="搜索主播、动作、象限…" value="${state.keyword}">
            </div>
            <div class="anchor-profile-list-body">
              ${filtered.map((anchor) => `
                <button class="anchor-profile-card ${anchor.account === state.selectedName ? "active" : ""}" data-anchor-select="${anchor.account}">
                  <div class="anchor-profile-title-row">
                    <div>
                      <div class="anchor-profile-title">${anchor.account}</div>
                      <div class="anchor-meta">${anchor.action || "未设置动作"} · ${anchor.quadrant || "未分象限"} · 最新统计 ${safe(anchor.week_start, refreshStats.latest_live_date || "—")}</div>
                    </div>
                    <span class="anchor-status-pill ${anchor.status || "yellow"}">${levelLabel(anchor.status)}</span>
                  </div>
                  <div class="anchor-profile-summary">系统动作：${anchor.system_action || "待判断"}；当前粉丝 ${api.formatCompactNumber(anchor.current_fans)}</div>
                  <div class="anchor-profile-tags">
                    <span class="anchor-pill">ACU ${Number(anchor.acu || 0).toFixed(1)}</span>
                    <span class="anchor-pill">停留 ${Number(anchor.retention || 0).toFixed(2)}</span>
                    <span class="anchor-pill">转粉 ${api.formatPercent(anchor.follow_rate, 2)}</span>
                  </div>
                </button>
              `).join("") || `<div class="anchor-profile-card"><div class="anchor-meta">没有匹配到主播</div></div>`}
            </div>
          </div>
          <div class="anchor-profile-detail">
            ${selected ? `
              <div class="anchor-profile-hero">
                <div class="anchor-dashboard-head">
                  <div>
                    <h3>${selected.account}</h3>
                    <div class="anchor-dashboard-note">${selected.action || "未设置动作"} · ${selected.system_action || "待判断"} · ${selected.quadrant || "未分象限"}</div>
                  </div>
                  <span class="anchor-status-pill ${selected.status || "yellow"}">${levelLabel(selected.status)}</span>
                </div>
                <div class="anchor-hero-metrics">
                  <div class="anchor-hero-metric"><span>在岗月数</span><strong>${safe(selected.tenure_month, 0)} 个月</strong></div>
                  <div class="anchor-hero-metric"><span>最新统计日期</span><strong>${safe(selected.week_start, refreshStats.latest_live_date || "—")}</strong></div>
                  <div class="anchor-hero-metric"><span>月均 ACU</span><strong>${Number(selected.acu || 0).toFixed(1)}</strong></div>
                  <div class="anchor-hero-metric"><span>停留</span><strong>${Number(selected.retention || 0).toFixed(2)} min</strong></div>
                  <div class="anchor-hero-metric"><span>转粉率</span><strong>${api.formatPercent(selected.follow_rate, 2)}</strong></div>
                  <div class="anchor-hero-metric"><span>当前粉丝</span><strong>${api.formatCompactNumber(selected.current_fans)}</strong></div>
                  <div class="anchor-hero-metric"><span>月收入</span><strong>${safe(selected.monthly_income, 0)} 万</strong></div>
                </div>
              </div>
              <div class="anchor-dashboard-two-col">
                <div class="anchor-dashboard-section">
                  <div class="anchor-dashboard-head"><h3>主播状态与阈值</h3><span class="anchor-dashboard-note">系统状态 ${selected.system_status || "未判断"}</span></div>
                  <div class="anchor-pill-row">
                    ${Object.entries(selected.states || {}).map(([key, value]) => `<span class="anchor-pill">${key} · ${value}</span>`).join("") || `<span class="anchor-pill">暂无阈值状态</span>`}
                  </div>
                  <div class="anchor-profile-summary">通过率：${safe(selected.pass_ratio, "—")}；人工改判：${selected.manual_override_applied ? "已应用" : "无"}。</div>
                </div>
                <div class="anchor-dashboard-section">
                  <div class="anchor-dashboard-head"><h3>异常与观察</h3><span class="anchor-dashboard-note">${(selected.anomalies || []).length} 条</span></div>
                  <div class="anchor-risk-list">
                    ${(selected.anomalies || []).length ? selected.anomalies.map((item) => `<div class="anchor-risk-row"><div class="anchor-meta">${item.title || "异常提醒"}</div><div class="anchor-dashboard-note">${item.detail || ""}</div></div>`).join("") : `<div class="anchor-risk-row"><div class="anchor-meta">当前没有异常提醒</div></div>`}
                  </div>
                </div>
              </div>
              <div id="anchorRoiMount"></div>
            ` : `
              <div class="anchor-dashboard-section"><div class="anchor-meta">当前没有主播数据</div></div>
            `}
          </div>
        </div>
      </div>
    `;

    section.querySelector("#anchorPortraitSearch")?.addEventListener("input", (event) => {
      state.keyword = event.target.value || "";
      renderPortrait(state.payload);
    });
    section.querySelector("#anchorPortraitStartDate")?.addEventListener("change", (event) => {
      state.start = event.target.value || state.start;
    });
    section.querySelector("#anchorPortraitEndDate")?.addEventListener("change", (event) => {
      state.end = event.target.value || state.end;
    });
    section.querySelector("#anchorPortraitRefreshBtn")?.addEventListener("click", async () => {
      if (state.start && state.end && state.start > state.end) {
        window.showToast?.("开始日期不能晚于结束日期");
        return;
      }
      await ensureRendered(true);
    });
    section.querySelectorAll("[data-anchor-select]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedName = button.dataset.anchorSelect || "";
        renderPortrait(state.payload);
      });
    });
    if (selected) {
      window.AnchorRoiCalculator?.render(section.querySelector("#anchorRoiMount"), selected, {
        periodText: `${state.start} 至 ${state.end}`
      });
    }
  }

  async function ensureRendered(force = false) {
    try {
      ensureDefaultRange();
      const payload = await window.AnchorDashboardApi.fetchWeekly({
        force,
        start: state.start,
        end: state.end
      });
      renderPortrait(payload);
    } catch (error) {
      const section = document.getElementById("sec-portrait");
      if (section) {
        section.innerHTML = `<div class="page-title">主播画像</div><div class="page-sub">主播画像数据加载失败</div><div class="panel"><div class="muted">${error.message}</div></div>`;
      }
      window.showToast?.(error.message || "主播画像加载失败");
    }
  }

  window.AnchorPortraitPage = {
    ensureRendered
  };
})();
