(function () {
  const state = { loaded: false, adminLoaded: false };

  const fmt = (value, digits = 2) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    return num.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  };

  const cls = (value) => Number(value || 0) >= 0 ? "green" : "red";
  const sign = (value) => Number(value || 0) >= 0 ? "+" : "";
  const dateText = (value) => String(value || "").replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3") || "--";
  const timeText = (value) => value ? new Date(value).toLocaleString("zh-CN") : "暂无缓存";
  const html = (value) => String(value ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));

  function renderStatus(settings, snapshot) {
    const badge = document.getElementById("marketSourceBadge");
    const status = document.getElementById("marketStatus");
    if (badge) {
      badge.textContent = settings?.configured ? "TuShare已配置" : "TuShare未配置";
      badge.className = `badge ${settings?.configured ? "green" : "gray"}`;
    }
    if (status) {
      const counts = snapshot?.summary ? `指数 ${snapshot.summary.indexCount || 0} / 股票 ${snapshot.summary.stockCount || 0}` : "暂无数据";
      status.textContent = settings?.configured
        ? `数据源：TuShare · ${counts} · 更新时间 ${timeText(snapshot?.updatedAt)}`
        : "请先到后台管理 / TuShare配置 中填写 token 并保存。";
    }
  }

  function quoteCard(item) {
    return `<div class="market-quote-card">
      <div class="market-quote-name">${html(item.name)} <span class="market-code">${html(item.code)}</span></div>
      <div class="market-quote-value">${fmt(item.close)}</div>
      <div class="market-quote-meta ${cls(item.pctChange)}">
        <span>${sign(item.change)}${fmt(item.change)}</span>
        <span>${sign(item.pctChange)}${fmt(item.pctChange)}%</span>
      </div>
      <div class="market-code">交易日 ${dateText(item.tradeDate)}</div>
    </div>`;
  }

  function renderKpis(indexes) {
    const grid = document.getElementById("marketKpiGrid");
    if (!grid) return;
    const items = (indexes || []).slice(0, 4);
    grid.innerHTML = items.length ? items.map(quoteCard).join("") : '<div class="market-status" style="grid-column:1/-1;">暂无行情缓存</div>';
  }

  function renderTable(targetId, items) {
    const target = document.getElementById(targetId);
    if (!target) return;
    if (!items?.length) {
      target.innerHTML = '<div class="market-status">暂无数据，配置 token 后点击刷新行情。</div>';
      return;
    }
    target.innerHTML = `<table class="market-table">
      <thead><tr><th>名称</th><th>收盘</th><th>涨跌</th><th>涨跌幅</th><th>成交额</th><th>交易日</th></tr></thead>
      <tbody>${items.map((item) => `<tr>
        <td><div class="market-name">${html(item.name)}</div><div class="market-code">${html(item.code)}</div></td>
        <td class="market-num">${fmt(item.close)}</td>
        <td class="market-num ${cls(item.change)}">${sign(item.change)}${fmt(item.change)}</td>
        <td><span class="badge ${cls(item.pctChange)}">${sign(item.pctChange)}${fmt(item.pctChange)}%</span></td>
        <td class="market-num">${fmt(Number(item.amount || 0) / 100000, 2)}亿</td>
        <td class="market-code">${dateText(item.tradeDate)}</td>
      </tr>`).join("")}</tbody>
    </table>`;
  }

  async function loadMarket() {
    const status = document.getElementById("marketStatus");
    if (status) status.textContent = "正在读取行情...";
    try {
      const res = await fetch("/api/market/overview", { credentials: "include" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || payload.detail || "行情读取失败");
      renderStatus(payload.settings || {}, payload.snapshot || {});
      renderKpis(payload.snapshot?.indexes || []);
      renderTable("marketIndexTable", payload.snapshot?.indexes || []);
      renderTable("marketStockTable", payload.snapshot?.stocks || []);
      state.loaded = true;
    } catch (error) {
      if (status) status.textContent = error.message;
    }
  }

  async function refreshMarket() {
    const btn = document.getElementById("marketRefreshBtn");
    const status = document.getElementById("marketStatus");
    try {
      if (btn) btn.disabled = true;
      if (status) status.textContent = "正在从 TuShare 取数...";
      const res = await fetch("/api/market/refresh", { method: "POST", credentials: "include" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || payload.detail || "刷新失败");
      await loadMarket();
      window.showToast?.("行情已刷新");
    } catch (error) {
      if (status) status.textContent = error.message;
      window.showToast?.(error.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function adminTemplate() {
    return `<div class="market-admin-grid">
      <section class="panel">
        <div class="panel-hd"><div class="panel-title">连接与定时任务</div><span class="badge gray" id="tushareAdminBadge">未配置</span></div>
        <div class="market-admin-form">
          <label style="display:flex;gap:8px;align-items:center;color:var(--text1);font-size:13px;">
            <input id="tushareEnabled" type="checkbox" style="accent-color:var(--gold);"> 启用后台定时取数
          </label>
          <label><span class="lbl">TuShare Token</span><input class="inp" id="tushareToken" type="password" placeholder="保存后会以 ******** 显示" autocomplete="new-password" style="width:100%;"></label>
          <label><span class="lbl">取数间隔（分钟，最小 15）</span><input class="inp" id="tushareInterval" type="number" min="15" step="15" value="60" style="width:180px;"></label>
          <div class="market-admin-codes">
            <label><span class="lbl">指数代码（逗号或换行分隔）</span><textarea class="textarea" id="tushareIndexCodes" rows="6"></textarea></label>
            <label><span class="lbl">股票代码（逗号或换行分隔）</span><textarea class="textarea" id="tushareStockCodes" rows="6"></textarea></label>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn btn-outline" id="tushareTestBtn" type="button">测试 Token</button>
            <button class="btn btn-gold" id="tushareSaveBtn" type="button">保存配置</button>
          </div>
          <div class="result-box" id="tushareAdminStatus" style="min-height:auto;">正在读取配置...</div>
        </div>
      </section>
      <aside class="panel">
        <div class="panel-hd"><div class="panel-title">说明</div></div>
        <div class="market-note">当前接入 TuShare Pro HTTP API，默认使用 <b>index_daily</b> 和 <b>daily</b> 拉取最近交易日数据。该页面是行情缓存看板，不是秒级盘口。</div>
        <div class="market-note" style="margin-top:12px;">后台任务每分钟检查一次，只有超过配置间隔才会真正请求 TuShare，避免消耗过多接口频次。</div>
      </aside>
    </div>`;
  }

  function getAdminForm() {
    return {
      enabled: document.getElementById("tushareEnabled")?.checked,
      token: document.getElementById("tushareToken")?.value || "",
      intervalMinutes: Number(document.getElementById("tushareInterval")?.value || 60),
      indexCodes: document.getElementById("tushareIndexCodes")?.value || "",
      stockCodes: document.getElementById("tushareStockCodes")?.value || ""
    };
  }

  function renderAdmin(settings) {
    document.getElementById("tushareEnabled").checked = !!settings.enabled;
    document.getElementById("tushareToken").value = settings.token || "";
    document.getElementById("tushareInterval").value = settings.intervalMinutes || 60;
    document.getElementById("tushareIndexCodes").value = (settings.indexCodes || []).join("\n");
    document.getElementById("tushareStockCodes").value = (settings.stockCodes || []).join("\n");
    const badge = document.getElementById("tushareAdminBadge");
    if (badge) {
      badge.textContent = settings.configured ? "已配置" : "未配置";
      badge.className = `badge ${settings.configured ? "green" : "gray"}`;
    }
  }

  async function loadAdmin() {
    const mount = document.getElementById("tushareAdminMount");
    if (!mount) return;
    if (!state.adminLoaded) {
      mount.innerHTML = adminTemplate();
      document.getElementById("tushareSaveBtn")?.addEventListener("click", saveAdmin);
      document.getElementById("tushareTestBtn")?.addEventListener("click", testAdmin);
      state.adminLoaded = true;
    }
    const status = document.getElementById("tushareAdminStatus");
    try {
      if (status) status.textContent = "正在读取配置...";
      const res = await fetch("/api/admin/tushare", { credentials: "include" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || payload.detail || "配置读取失败");
      renderAdmin(payload.settings || {});
      if (status) status.textContent = "配置已加载。";
    } catch (error) {
      if (status) status.textContent = error.message;
    }
  }

  async function saveAdmin() {
    const status = document.getElementById("tushareAdminStatus");
    try {
      if (status) status.textContent = "正在保存配置...";
      const res = await fetch("/api/admin/tushare", {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: getAdminForm() })
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || payload.detail || "保存失败");
      renderAdmin(payload.settings || {});
      if (status) status.textContent = "TuShare 配置已保存。";
      window.showToast?.("TuShare 配置已保存");
    } catch (error) {
      if (status) status.textContent = error.message;
      window.showToast?.(error.message);
    }
  }

  async function testAdmin() {
    const status = document.getElementById("tushareAdminStatus");
    try {
      if (status) status.textContent = "正在测试 Token...";
      const res = await fetch("/api/admin/tushare/test", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: getAdminForm() })
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || payload.detail || "测试失败");
      if (status) status.textContent = payload.message || "连接成功。";
      window.showToast?.("TuShare 连接成功");
    } catch (error) {
      if (status) status.textContent = error.message;
      window.showToast?.(error.message);
    }
  }

  window.FinVueMarket = { load: loadMarket, refresh: refreshMarket };
  window.FinVueMarketAdmin = { load: loadAdmin };
  window.addEventListener("load", () => {
    document.getElementById("marketRefreshBtn")?.addEventListener("click", refreshMarket);
  });
})();
