(function () {
  const state = { loaded: false };

  function template() {
    return `<div class="feishu-admin-grid">
      <section class="panel">
        <div class="panel-hd">
          <div><div class="panel-title">机器人 Webhook</div><div class="muted" style="font-size:12px;margin-top:4px;">使用飞书群机器人提供的 webhook 地址。</div></div>
          <span class="badge gray" id="feishuStatusBadge">未配置</span>
        </div>
        <div class="feishu-admin-form">
          <div class="feishu-toggle-row">
            <div>
              <div style="font-weight:700;">启用定时推送</div>
              <div class="muted" style="font-size:12px;">到达间隔后自动推送热点板块雷达</div>
            </div>
            <input id="feishuEnabled" type="checkbox">
          </div>
          <div class="feishu-field">
            <label>飞书 Webhook URL</label>
            <input class="inp" id="feishuWebhookUrl" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/...">
          </div>
          <div class="feishu-field">
            <label>推送间隔（分钟，最小 15）</label>
            <input class="inp" id="feishuIntervalMinutes" type="number" min="15" step="15" value="120">
          </div>
          <div class="feishu-toggle-row">
            <div>
              <div style="font-weight:700;">包含股票观察池</div>
              <div class="muted" style="font-size:12px;">推送热点板块、主题依据和观察股票，附行情涨跌幅</div>
            </div>
            <input id="feishuPushStocks" type="checkbox" checked>
          </div>
          <div class="feishu-actions">
            <button class="btn btn-gold" id="feishuSaveBtn" type="button">保存配置</button>
            <button class="btn btn-outline" id="feishuTestBtn" type="button">测试推送</button>
          </div>
          <div class="feishu-status" id="feishuAdminStatus">正在读取配置...</div>
        </div>
      </section>
      <aside class="feishu-side-card">
        <h4>推送内容</h4>
        <p>每次推送前会先按热点追踪配置刷新平台数据，再从最近 2 小时热搜中提取重点新闻，由 AI 识别热度板块，并结合 TuShare 股票基础库生成观察池。</p>
        <div class="admin-divider"></div>
        <h4>合规边界</h4>
        <p>飞书消息会明确标注“弱关联，不代表投资建议”，用于直播选题和盘前准备，不作为买卖依据。</p>
        <div class="admin-divider"></div>
        <div class="muted" style="font-size:12px;" id="feishuLastMeta">暂无推送记录</div>
      </aside>
    </div>`;
  }

  function formValue() {
    return {
      enabled: Boolean(document.getElementById("feishuEnabled")?.checked),
      webhookUrl: document.getElementById("feishuWebhookUrl")?.value?.trim() || "",
      intervalMinutes: Number(document.getElementById("feishuIntervalMinutes")?.value || 120),
      pushRelatedStocks: Boolean(document.getElementById("feishuPushStocks")?.checked),
    };
  }

  function render(settings = {}) {
    document.getElementById("feishuEnabled").checked = !!settings.enabled;
    document.getElementById("feishuWebhookUrl").value = settings.webhookUrl || "";
    document.getElementById("feishuIntervalMinutes").value = settings.intervalMinutes || 120;
    document.getElementById("feishuPushStocks").checked = settings.pushRelatedStocks !== false;
    const badge = document.getElementById("feishuStatusBadge");
    if (badge) {
      badge.textContent = settings.configured ? (settings.schedulerEnabled ? "已启用" : "已配置·未启用") : "未配置";
      badge.className = `badge ${settings.configured ? "green" : "gray"}`;
    }
    const meta = document.getElementById("feishuLastMeta");
    if (meta) {
      const last = settings.lastPushedAt ? new Date(settings.lastPushedAt).toLocaleString("zh-CN") : "暂无";
      meta.textContent = `最近推送：${last}${settings.lastStatus ? ` · ${settings.lastStatus}` : ""}${settings.webhookPreview ? ` · ${settings.webhookPreview}` : ""}`;
    }
  }

  async function load() {
    const mount = document.getElementById("feishuAdminMount");
    if (!mount) return;
    if (!state.loaded) {
      mount.innerHTML = template();
      document.getElementById("feishuSaveBtn")?.addEventListener("click", save);
      document.getElementById("feishuTestBtn")?.addEventListener("click", test);
      state.loaded = true;
    }
    const status = document.getElementById("feishuAdminStatus");
    try {
      if (status) status.textContent = "正在读取飞书配置...";
      const res = await fetch("/api/admin/feishu", { credentials: "include" });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.error || payload.detail || "配置读取失败");
      render(payload.settings || {});
      if (status) status.textContent = "配置已加载。";
    } catch (error) {
      if (status) status.textContent = error.message;
    }
  }

  async function save() {
    const status = document.getElementById("feishuAdminStatus");
    try {
      if (status) status.textContent = "正在保存飞书配置...";
      const res = await fetch("/api/admin/feishu", {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: formValue() }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.error || payload.detail || "保存失败");
      render(payload.settings || {});
      if (status) status.textContent = "飞书配置已保存。";
      window.showToast?.("飞书配置已保存");
    } catch (error) {
      if (status) status.textContent = error.message;
      window.showToast?.(error.message);
    }
  }

  async function test() {
    const status = document.getElementById("feishuAdminStatus");
    try {
      await save();
      if (status) status.textContent = "正在刷新热搜并发送测试推送...";
      const res = await fetch("/api/admin/feishu/test", {
        method: "POST",
        credentials: "include",
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.error || payload.detail || "推送失败");
      if (status) status.textContent = payload.message || "测试推送成功。";
      window.showToast?.("飞书测试推送成功");
      await load();
    } catch (error) {
      if (status) status.textContent = error.message;
      window.showToast?.(error.message);
    }
  }

  window.FinVueFeishuAdmin = { load };
})();
