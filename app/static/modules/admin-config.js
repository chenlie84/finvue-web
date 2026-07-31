// FinVue admin API route pool and config-bundle import/export.
// Kept as a classic script so legacy inline handlers can keep using global function names.

function getAiProviders() {
  return Array.isArray(state.globalSettings?.aiProviders) ? state.globalSettings.aiProviders : [];
}

function normalizeAiProviderDraft(item = {}, index = 0) {
  return {
    id: String(item.id || `provider-${Date.now()}-${index}`),
    label: String(item.label || `路由 ${index + 1}`),
    baseUrl: String(item.baseUrl || "https://ark.cn-beijing.volces.com/api/v3/responses"),
    apiKey: String(item.apiKey || ""),
    model: String(item.model || ""),
    enabled: item.enabled !== false,
    priority: Number.isFinite(Number(item.priority)) ? Number(item.priority) : index + 1,
    apiFormat: String(item.apiFormat || "finvue"),
    apiKeyPlacement: String(item.apiKeyPlacement || "header"),
    useProxy: item.useProxy === undefined ? true : Boolean(item.useProxy)
  };
}

function renderAiRouteSummary() {
  if (!els.aiRouteSummary) return;
  const providers = getAiProviders().map(normalizeAiProviderDraft).filter((item) => item.enabled);
  if (!providers.length) {
    els.aiRouteSummary.textContent = "后台还没有可用 AI 路由。请去管理后台至少启用一条 API Key 和模型。";
    return;
  }
  els.aiRouteSummary.textContent = providers
    .sort((a, b) => a.priority - b.priority)
    .map((item, index) => `${index === 0 ? "主路由" : `备用 ${index}`}：${item.label} / ${item.model}`)
    .join("；");

  // 同时更新直播分析页的模型选择下拉框
  const liveModelSelect = document.getElementById("live-model-select");
  if (liveModelSelect) {
    const sortedProviders = providers.sort((a, b) => (a.priority || 0) - (b.priority || 0));
    liveModelSelect.innerHTML = '<option value="">使用默认路由池</option>';
    sortedProviders.forEach(p => {
      const label = p.label || p.model || "未知模型";
      liveModelSelect.innerHTML += `<option value="${p.id}">${escapeHtml(label)} (${escapeHtml(p.model)})</option>`;
    });
  }
}

function renderAdminAiProviders() {
  if (!els.adminAiProviders) return;
  const providers = getAiProviders().map(normalizeAiProviderDraft);
  if (!providers.length) {
    els.adminAiProviders.innerHTML = `<div class="muted">暂无 AI 路由，点击右下角新增。</div>`;
    renderAiRouteSummary();
    return;
  }
  els.adminAiProviders.innerHTML = providers.map((item, index) => `
    <div class="panel" style="margin:0;padding:12px 14px;background:var(--bg1);">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px;">
        <div style="font-size:13px;font-weight:600;">路由 ${index + 1}</div>
        <div style="display:flex;gap:8px;align-items:center;">
          <label class="muted" style="font-size:12px;display:flex;gap:6px;align-items:center;">
            <input type="checkbox" data-ai-provider-enabled="${item.id}" ${item.enabled ? "checked" : ""}/>
            启用
          </label>
          <button class="btn btn-outline" data-ai-provider-remove="${item.id}" style="font-size:11px;padding:4px 10px;">删除</button>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 120px;gap:10px;margin-bottom:10px;">
        <input class="inp" data-ai-provider-label="${item.id}" value="${escapeHtml(item.label)}" placeholder="路由名称，例如 火山主路由">
        <input class="inp" data-ai-provider-priority="${item.id}" type="number" min="1" value="${escapeHtml(String(item.priority))}" placeholder="优先级">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <input class="inp" data-ai-provider-model="${item.id}" value="${escapeHtml(item.model)}" placeholder="模型名">
        <input class="inp" data-ai-provider-key="${item.id}" type="password" value="${escapeHtml(item.apiKey)}" placeholder="API Key">
      </div>
      <input class="inp" data-ai-provider-base="${item.id}" value="${escapeHtml(item.baseUrl)}" placeholder="上游地址" style="margin-bottom:10px;">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">
        <select class="sel" data-ai-provider-format="${item.id}">
          <option value="finvue" ${item.apiFormat !== "openai" && item.apiFormat !== "anthropic" ? "selected" : ""}>FinVue 格式</option>
          <option value="openai" ${item.apiFormat === "openai" ? "selected" : ""}>OpenAI 兼容（自动补 /chat/completions）</option>
          <option value="anthropic" ${item.apiFormat === "anthropic" ? "selected" : ""}>Anthropic (/v1/messages)</option>
        </select>
        <select class="sel" data-ai-provider-key-placement="${item.id}">
          <option value="header" ${item.apiKeyPlacement !== "body" ? "selected" : ""}>Key 放 Header</option>
          <option value="body" ${item.apiKeyPlacement === "body" ? "selected" : ""}>Key 放 Body(api_key)</option>
        </select>
        <label class="muted" style="font-size:12px;display:flex;gap:8px;align-items:center;border:1px solid var(--border);border-radius:var(--r);padding:0 12px;">
          <input type="checkbox" data-ai-provider-proxy="${item.id}" ${item.useProxy ? "checked" : ""}/>
          外部接口走代理
        </label>
      </div>
      <div style="display:flex;justify-content:flex-end;margin-top:10px;">
        <button class="btn btn-outline" data-ai-provider-test="${item.id}" style="font-size:12px;padding:6px 14px;">测试连接</button>
        <span class="muted" data-ai-provider-test-result="${item.id}" style="font-size:12px;margin-left:10px;display:none;align-items:center;"></span>
      </div>
    </div>
  `).join("");
  renderAiRouteSummary();
}

function downloadAdminConfigUrl(url) {
  const link = document.createElement("a");
  link.href = url;
  link.download = "";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

async function importAiConfigFile(file) {
  if (!file) return;
  try {
    if (!isAdmin()) throw new Error("需要管理员权限");
    if (els.adminStatus) els.adminStatus.textContent = "正在导入 AI 配置文件...";
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/admin/ai-config/import", {
      method: "POST",
      credentials: "include",
      body: form
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || payload.error || "AI 配置文件导入失败");
    state.globalSettings = payload.settings || state.globalSettings || {};
    state.globalSettings.aiProviders = (Array.isArray(state.globalSettings.aiProviders) ? state.globalSettings.aiProviders : []).map(normalizeAiProviderDraft);
    renderAdminAiProviders();
    updateAdminDashboardSummary();
    if (els.adminStatus) els.adminStatus.textContent = payload.message || "AI 配置已导入";
    const imported = payload.imported || {};
    showToast(`AI 配置已导入：${imported.providerCount || 0} 条路由，${imported.enabledCount || 0} 条启用`);
  } catch (error) {
    if (els.adminStatus) els.adminStatus.textContent = error.message;
    showToast(error.message);
  } finally {
    const input = document.getElementById("aiConfigFileInput");
    if (input) input.value = "";
  }
}

async function importConfigBundleFile(file) {
  if (!file) return;
  const status = document.getElementById("configBundleStatus");
  try {
    if (!isAdmin()) throw new Error("需要管理员权限");
    if (status) status.textContent = `正在导入总配置文件：${file.name}...`;
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/admin/config/import", {
      method: "POST",
      credentials: "include",
      body: form
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || payload.error || "总配置文件导入失败");
    state.globalSettings = payload.settings || state.globalSettings || {};
    state.globalSettings.aiProviders = (Array.isArray(state.globalSettings.aiProviders) ? state.globalSettings.aiProviders : []).map(normalizeAiProviderDraft);
    renderAdminAiProviders();
    updateAdminDashboardSummary();
    window.FinVueMarketAdmin?.load?.();
    window.FinVueFeishuAdmin?.load?.();
    const imported = payload.imported || {};
    const parts = [];
    if (imported.tushare) parts.push(`TuShare：${imported.tushare.indexCount || 0} 个指数 / ${imported.tushare.stockCount || 0} 只股票`);
    if (imported.feishu) parts.push(`飞书：${imported.feishu.hasWebhook ? "Webhook 已配置" : "未含 Webhook"}`);
    if (imported.ai) parts.push(`AI：${imported.ai.providerCount || 0} 条路由 / ${imported.ai.enabledCount || 0} 条启用`);
    if (imported.dailyReview) parts.push(`复盘定时：${imported.dailyReview.schedulerEnabled ? "已启用" : "未启用"} / ${imported.dailyReview.dailyRunTime || "--"}`);
    if (status) status.textContent = `${payload.message || "总配置已导入"}。${parts.join("；") || "未返回导入摘要"}`;
    showToast("FinVue 总配置已导入");
  } catch (error) {
    if (status) status.textContent = error.message;
    showToast(error.message);
  } finally {
    const input = document.getElementById("configBundleFileInput");
    if (input) input.value = "";
  }
}

function collectAiProvidersFromUi() {
  const providers = getAiProviders().map(normalizeAiProviderDraft);
  return providers.map((item, index) => ({
    id: item.id,
    label: String(document.querySelector(`[data-ai-provider-label="${CSS.escape(item.id)}"]`)?.value || item.label).trim() || `路由 ${index + 1}`,
    baseUrl: String(document.querySelector(`[data-ai-provider-base="${CSS.escape(item.id)}"]`)?.value || item.baseUrl).trim() || "https://ark.cn-beijing.volces.com/api/v3/responses",
    apiKey: String(document.querySelector(`[data-ai-provider-key="${CSS.escape(item.id)}"]`)?.value || item.apiKey).trim(),
    model: String(document.querySelector(`[data-ai-provider-model="${CSS.escape(item.id)}"]`)?.value || item.model).trim(),
    enabled: Boolean(document.querySelector(`[data-ai-provider-enabled="${CSS.escape(item.id)}"]`)?.checked),
    priority: Number(document.querySelector(`[data-ai-provider-priority="${CSS.escape(item.id)}"]`)?.value || item.priority || index + 1),
    apiFormat: String(document.querySelector(`[data-ai-provider-format="${CSS.escape(item.id)}"]`)?.value || item.apiFormat || "finvue"),
    apiKeyPlacement: String(document.querySelector(`[data-ai-provider-key-placement="${CSS.escape(item.id)}"]`)?.value || item.apiKeyPlacement || "header"),
    useProxy: Boolean(document.querySelector(`[data-ai-provider-proxy="${CSS.escape(item.id)}"]`)?.checked)
  }));
}

function addAiProviderDraft() {
  // 确保 state.globalSettings 已初始化
  if (!state.globalSettings) {
    state.globalSettings = {};
  }
  // 先收集当前 UI 中的修改，避免丢失用户编辑的内容
  state.globalSettings.aiProviders = collectAiProvidersFromUi();
  const next = getAiProviders().map(normalizeAiProviderDraft);
  next.push(normalizeAiProviderDraft({}, next.length));
  state.globalSettings.aiProviders = next;
  renderAdminAiProviders();
  updateAdminDashboardSummary();
}

function removeAiProviderDraft(providerId) {
  // 先收集当前 UI 中的修改，避免丢失用户编辑的内容
  state.globalSettings.aiProviders = collectAiProvidersFromUi();
  state.globalSettings.aiProviders = getAiProviders()
    .map(normalizeAiProviderDraft)
    .filter((item) => item.id !== providerId);
  renderAdminAiProviders();
  updateAdminDashboardSummary();
}

function bindAdminConfigEvents() {
  els.addAiProviderBtn?.addEventListener("click", addAiProviderDraft);
  document.getElementById("aiConfigImportBtn")?.addEventListener("click", () => document.getElementById("aiConfigFileInput")?.click());
  document.getElementById("aiConfigExportBtn")?.addEventListener("click", () => downloadAdminConfigUrl("/api/admin/ai-config/export"));
  document.getElementById("aiConfigTemplateBtn")?.addEventListener("click", () => downloadAdminConfigUrl("/api/admin/ai-config/template"));
  document.getElementById("aiConfigFileInput")?.addEventListener("change", (event) => importAiConfigFile(event.target.files?.[0]));
  document.getElementById("configBundleImportBtn")?.addEventListener("click", () => document.getElementById("configBundleFileInput")?.click());
  document.getElementById("configBundleExportBtn")?.addEventListener("click", () => downloadAdminConfigUrl("/api/admin/config/export"));
  document.getElementById("configBundleTemplateBtn")?.addEventListener("click", () => downloadAdminConfigUrl("/api/admin/config/template"));
  document.getElementById("configBundleFileInput")?.addEventListener("change", (event) => importConfigBundleFile(event.target.files?.[0]));
  els.adminAiProviders?.addEventListener("click", async (event) => {
    // 删除按钮
    const removeBtn = event.target.closest("[data-ai-provider-remove]");
    if (removeBtn) {
      removeAiProviderDraft(removeBtn.dataset.aiProviderRemove || "");
      return;
    }
    // 测试连接按钮
    const testBtn = event.target.closest("[data-ai-provider-test]");
    if (testBtn) {
      const providerId = testBtn.dataset.aiProviderTest;
      const resultSpan = document.querySelector(`[data-ai-provider-test-result="${providerId}"]`);
      const btn = testBtn;

      if (resultSpan) {
        resultSpan.style.display = "flex";
        resultSpan.textContent = "测试中...";
        resultSpan.style.color = "#f59e0b";
      }
      btn.disabled = true;

      try {
        // 收集当前路由配置
        const providers = collectAiProvidersFromUi();
        const provider = providers.find(p => p.id === providerId);
        if (!provider) throw new Error("未找到路由配置");

        // 调用测试接口
        const response = await fetch("/api/test-ai-provider", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(provider)
        });
        const result = await response.json();

        if (result.success) {
          resultSpan.textContent = "✓ " + (result.message || "连接成功");
          resultSpan.style.color = "#10b981";
        } else {
          resultSpan.textContent = "✗ " + (result.error || "连接失败");
          resultSpan.style.color = "#ef4444";
        }
      } catch (exc) {
        resultSpan.textContent = "✗ " + (exc.message || "连接失败");
        resultSpan.style.color = "#ef4444";
      } finally {
        btn.disabled = false;
      }
    }
  });
  els.adminAiProviders?.addEventListener("input", () => {
    renderAiRouteSummary();
    updateAdminDashboardSummary();
  });
  els.adminAiProviders?.addEventListener("change", () => {
    renderAiRouteSummary();
    updateAdminDashboardSummary();
  });
}

bindAdminConfigEvents();
