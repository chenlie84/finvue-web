(function () {
  const state = { loaded: false, adminLoaded: false, stockUniverse: [], stockQuery: "", stockIndustry: "" };

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
  const inlineMd = (value) => html(value)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  function markdownToHtml(markdown) {
    const lines = String(markdown || "").split(/\r?\n/);
    let out = "";
    let listOpen = false;
    const closeList = () => {
      if (listOpen) {
        out += "</ul>";
        listOpen = false;
      }
    };
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) {
        closeList();
        continue;
      }
      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        closeList();
        out += `<h${heading[1].length}>${inlineMd(heading[2])}</h${heading[1].length}>`;
        continue;
      }
      const bullet = line.match(/^[-*]\s+(.+)$/) || line.match(/^\d+[.)]\s+(.+)$/);
      if (bullet) {
        if (!listOpen) {
          out += "<ul>";
          listOpen = true;
        }
        out += `<li>${inlineMd(bullet[1])}</li>`;
        continue;
      }
      closeList();
      out += `<p>${inlineMd(line)}</p>`;
    }
    closeList();
    return out || "暂无分析结果";
  }

  function renderStatus(settings, snapshot) {
    const badge = document.getElementById("marketSourceBadge");
    const status = document.getElementById("marketStatus");
    const hasData = Boolean((snapshot?.indexes || []).length || (snapshot?.stocks || []).length);
    const hasToken = Boolean(settings?.configured || settings?.hasToken || hasData);
    if (badge) {
      badge.textContent = hasToken ? (settings?.schedulerEnabled ? "TuShare已配置" : "TuShare已配置·定时关闭") : "TuShare未配置";
      badge.className = `badge ${hasToken ? "green" : "gray"}`;
    }
    if (status) {
      const counts = snapshot?.summary ? `指数 ${snapshot.summary.indexCount || 0} / 股票 ${snapshot.summary.stockCount || 0}` : "暂无数据";
      status.textContent = hasToken || hasData
        ? `数据源：TuShare · ${counts} · 更新时间 ${timeText(snapshot?.updatedAt)}${settings?.schedulerEnabled ? "" : " · 后台定时未启用"}`
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

  async function generateAttribution() {
    const btn = document.getElementById("marketAttributionBtn");
    const content = document.getElementById("marketAttributionContent");
    const meta = document.getElementById("marketAttributionMeta");
    try {
      if (btn) btn.disabled = true;
      if (content) content.innerHTML = '<span class="spinner"></span> 正在结合行情与热点追踪生成归因...';
      const res = await fetch("/api/market/ai-attribution", { method: "POST", credentials: "include" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || payload.detail || "归因生成失败");
      if (content) content.innerHTML = markdownToHtml(payload.analysis || "");
      if (meta) {
        const generated = payload.generatedAt ? new Date(payload.generatedAt).toLocaleString("zh-CN") : new Date().toLocaleString("zh-CN");
        meta.textContent = `生成于 ${generated} · 命中 ${payload.matchedTargets?.length || 0} 个标的/主题 · 覆盖 ${payload.hotspotCount || 0} 条热点`;
      }
      window.showToast?.("AI 消息面归因已生成");
    } catch (error) {
      if (content) content.textContent = error.message;
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
            <label><span class="lbl">股票代码（由下方股票库选择，也可手动补充）</span><textarea class="textarea" id="tushareStockCodes" rows="6"></textarea></label>
          </div>
          <div class="market-stock-picker">
            <div class="market-stock-toolbar">
              <input class="inp" id="tushareStockSearch" placeholder="搜索代码 / 名称 / 行业 / 板块" style="min-width:220px;flex:1;">
              <select class="sel" id="tushareIndustryFilter" style="width:180px;"><option value="">全部板块</option></select>
              <button class="btn btn-outline" id="tushareLoadStocksBtn" type="button">读取股票库</button>
              <button class="btn btn-outline" id="tushareRefreshStocksBtn" type="button">从TuShare刷新</button>
            </div>
            <div class="market-selected-stocks" id="tushareSelectedStocks">尚未选择股票</div>
            <div class="market-stock-list" id="tushareStockList">点击“读取股票库”后可按中文名、代码或板块搜索选择。</div>
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

  function selectedStockCodes() {
    return String(document.getElementById("tushareStockCodes")?.value || "")
      .replace(/\n/g, ",")
      .split(",")
      .map((code) => code.trim().toUpperCase())
      .filter(Boolean)
      .filter((code, index, arr) => arr.indexOf(code) === index);
  }

  function setSelectedStockCodes(codes) {
    const target = document.getElementById("tushareStockCodes");
    if (target) target.value = (codes || []).filter(Boolean).join("\n");
    renderSelectedStocks();
    renderStockList();
  }

  function renderIndustryOptions() {
    const select = document.getElementById("tushareIndustryFilter");
    if (!select) return;
    const current = select.value;
    const industries = [...new Set(state.stockUniverse.map((item) => item.industry || "未分类"))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    select.innerHTML = `<option value="">全部板块</option>${industries.map((item) => `<option value="${html(item)}">${html(item)}</option>`).join("")}`;
    select.value = industries.includes(current) ? current : "";
  }

  function renderSelectedStocks() {
    const wrap = document.getElementById("tushareSelectedStocks");
    if (!wrap) return;
    const codes = selectedStockCodes();
    if (!codes.length) {
      wrap.textContent = "尚未选择股票";
      return;
    }
    const map = Object.fromEntries(state.stockUniverse.map((item) => [item.code, item]));
    wrap.innerHTML = codes.map((code) => {
      const item = map[code] || { code, name: code, industry: "手动添加" };
      return `<button class="market-stock-chip" type="button" data-remove-stock="${html(code)}">
        <span>${html(item.name || code)}</span><span>${html(code)}</span><small>${html(item.industry || "未分类")}</small>
      </button>`;
    }).join("");
  }

  function renderStockList() {
    const list = document.getElementById("tushareStockList");
    if (!list) return;
    if (!state.stockUniverse.length) {
      list.textContent = "暂无股票基础库。点击“从TuShare刷新”后会缓存所有A股代码、中文名和板块。";
      renderIndustryOptions();
      renderSelectedStocks();
      return;
    }
    const selected = new Set(selectedStockCodes());
    const query = state.stockQuery.trim().toLowerCase();
    const industry = state.stockIndustry;
    const rows = state.stockUniverse
      .filter((item) => !industry || item.industry === industry)
      .filter((item) => {
        if (!query) return true;
        return [item.code, item.symbol, item.name, item.industry, item.market, item.area]
          .some((value) => String(value || "").toLowerCase().includes(query));
      })
      .slice(0, 120);
    list.innerHTML = rows.length ? rows.map((item) => {
      const checked = selected.has(item.code);
      return `<button class="market-stock-row ${checked ? "selected" : ""}" type="button" data-stock-code="${html(item.code)}">
        <span class="market-stock-check">${checked ? "✓" : "+"}</span>
        <span><b>${html(item.name || item.code)}</b><small>${html(item.code)} · ${html(item.market || item.exchange || "--")}</small></span>
        <span>${html(item.industry || "未分类")}</span>
        <span>${html(item.area || "--")}</span>
      </button>`;
    }).join("") : "没有匹配的股票。";
    renderIndustryOptions();
    renderSelectedStocks();
  }

  function toggleStock(code) {
    const codes = selectedStockCodes();
    if (codes.includes(code)) {
      setSelectedStockCodes(codes.filter((item) => item !== code));
    } else {
      setSelectedStockCodes([...codes, code]);
    }
  }

  async function loadStockUniverse(forceRefresh = false) {
    const status = document.getElementById("tushareAdminStatus");
    try {
      if (status) status.textContent = forceRefresh ? "正在从 TuShare 刷新股票基础库..." : "正在读取股票基础库缓存...";
      const res = await fetch(forceRefresh ? "/api/admin/tushare/stocks/refresh" : "/api/admin/tushare/stocks", {
        method: forceRefresh ? "POST" : "GET",
        credentials: "include"
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || payload.detail || "股票基础库读取失败");
      state.stockUniverse = Array.isArray(payload.universe?.items) ? payload.universe.items : [];
      renderStockList();
      if (status) status.textContent = state.stockUniverse.length
        ? `股票基础库已加载：${state.stockUniverse.length} 只，更新时间 ${timeText(payload.universe?.updatedAt)}。`
        : "暂无股票基础库缓存，请点击从TuShare刷新。";
    } catch (error) {
      if (status) status.textContent = error.message;
      window.showToast?.(error.message);
    }
  }

  function renderAdmin(settings) {
    document.getElementById("tushareEnabled").checked = !!settings.enabled;
    document.getElementById("tushareToken").value = settings.token || "";
    document.getElementById("tushareInterval").value = settings.intervalMinutes || 60;
    document.getElementById("tushareIndexCodes").value = (settings.indexCodes || []).join("\n");
    document.getElementById("tushareStockCodes").value = (settings.stockCodes || []).join("\n");
    const badge = document.getElementById("tushareAdminBadge");
    if (badge) {
      badge.textContent = settings.configured ? (settings.schedulerEnabled ? "已配置" : "已配置·定时关闭") : "未配置";
      badge.className = `badge ${settings.configured ? "green" : "gray"}`;
    }
    renderSelectedStocks();
  }

  async function loadAdmin() {
    const mount = document.getElementById("tushareAdminMount");
    if (!mount) return;
    if (!state.adminLoaded) {
      mount.innerHTML = adminTemplate();
      document.getElementById("tushareSaveBtn")?.addEventListener("click", saveAdmin);
      document.getElementById("tushareTestBtn")?.addEventListener("click", testAdmin);
      document.getElementById("tushareLoadStocksBtn")?.addEventListener("click", () => loadStockUniverse(false));
      document.getElementById("tushareRefreshStocksBtn")?.addEventListener("click", () => loadStockUniverse(true));
      document.getElementById("tushareStockSearch")?.addEventListener("input", (event) => {
        state.stockQuery = event.target.value || "";
        renderStockList();
      });
      document.getElementById("tushareIndustryFilter")?.addEventListener("change", (event) => {
        state.stockIndustry = event.target.value || "";
        renderStockList();
      });
      document.getElementById("tushareStockList")?.addEventListener("click", (event) => {
        const row = event.target.closest("[data-stock-code]");
        if (row?.dataset?.stockCode) toggleStock(row.dataset.stockCode);
      });
      document.getElementById("tushareSelectedStocks")?.addEventListener("click", (event) => {
        const chip = event.target.closest("[data-remove-stock]");
        if (chip?.dataset?.removeStock) toggleStock(chip.dataset.removeStock);
      });
      document.getElementById("tushareStockCodes")?.addEventListener("input", () => {
        renderSelectedStocks();
        renderStockList();
      });
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
      if (!state.stockUniverse.length) loadStockUniverse(false);
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

  window.FinVueMarket = { load: loadMarket, refresh: refreshMarket, generateAttribution };
  window.FinVueMarketAdmin = { load: loadAdmin };
  window.addEventListener("load", () => {
    document.getElementById("marketRefreshBtn")?.addEventListener("click", refreshMarket);
    document.getElementById("marketAttributionBtn")?.addEventListener("click", generateAttribution);
  });
})();
