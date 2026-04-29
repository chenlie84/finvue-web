(function () {
  const roiStore = {
    items: null,
    saveTimers: new Map()
  };

  function currency(value) {
    return `¥${Math.round(value || 0).toLocaleString("zh-CN")}`;
  }

  function roiClass(roi) {
    if (roi >= 50) return "pos";
    if (roi >= 0) return "warn";
    return "neg";
  }

  function calcScenario(viewers, cvrPct, price, commissionPct, monthlyCost, sessionsPerYear, adspendPerSession) {
    const cvr = cvrPct / 100;
    const comm = commissionPct / 100;

    const buyersPerSession = Math.round(viewers * cvr);
    const grossPerSession = buyersPerSession * price;
    const netPerSession = grossPerSession * (1 - comm);
    const revenueYear = netPerSession * sessionsPerYear;
    const fixedCostYear = monthlyCost * 12;
    const adCostYear = adspendPerSession * sessionsPerYear;
    const totalCostYear = fixedCostYear + adCostYear;
    const profit = revenueYear - totalCostYear;
    const roi = totalCostYear > 0 ? (profit / totalCostYear) * 100 : 0;

    return {
      buyersPerSession,
      grossPerSession,
      netPerSession,
      revenueYear,
      fixedCostYear,
      adCostYear,
      totalCostYear,
      profit,
      roi
    };
  }

  function normalizeCvr(anchor) {
    const rate = Number(anchor?.follow_rate || 0) * 100;
    if (!Number.isFinite(rate) || rate <= 0) {
      return { low: 1, mid: 3, high: 5 };
    }
    const mid = Math.max(0.5, Math.min(20, Number(rate.toFixed(1))));
    return {
      low: Math.max(0.1, Number((mid * 0.5).toFixed(1))),
      mid,
      high: Math.min(20, Number((mid * 1.7).toFixed(1)))
    };
  }

  function normalizeAnchorKey(anchor) {
    return String(anchor?.account || anchor?.name || "").trim().toLowerCase();
  }

  async function loadRoiStore(force = false) {
    if (!force && roiStore.items) return roiStore.items;
    const response = await fetch("/api/anchor-roi-settings", {
      credentials: "same-origin",
      cache: "no-store"
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "读取主播 ROI 设置失败");
    }
    roiStore.items = payload.items && typeof payload.items === "object" ? payload.items : {};
    return roiStore.items;
  }

  async function persistAnchorRoiSettings(anchorKey, values) {
    const response = await fetch("/api/anchor-roi-settings", {
      method: "PUT",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        key: anchorKey,
        values
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "保存主播 ROI 设置失败");
    }
    roiStore.items = payload.items && typeof payload.items === "object" ? payload.items : roiStore.items || {};
    return roiStore.items?.[anchorKey] || values;
  }

  function readCurrentValues(container) {
    const byName = (name) => Number(container.querySelector(`[data-roi="${name}"]`)?.value || 0);
    return {
      viewers: byName("viewers"),
      price: byName("price"),
      cycle: byName("cycle"),
      commission: byName("commission"),
      cost: byName("cost"),
      adspend: byName("adspend"),
      cvrLow: byName("cvr-low"),
      cvrMid: byName("cvr-mid"),
      cvrHigh: byName("cvr-high")
    };
  }

  function applyValues(container, values) {
    if (!values) return;
    const map = {
      viewers: "viewers",
      price: "price",
      cycle: "cycle",
      commission: "commission",
      cost: "cost",
      adspend: "adspend",
      cvrLow: "cvr-low",
      cvrMid: "cvr-mid",
      cvrHigh: "cvr-high"
    };
    Object.entries(map).forEach(([key, name]) => {
      const input = container.querySelector(`[data-roi="${name}"]`);
      if (!input) return;
      const next = Number(values[key]);
      if (!Number.isFinite(next)) return;
      input.value = String(next);
    });
  }

  function updateSaveStatus(container, message, type = "") {
    const node = container.querySelector('[data-roi-panel="save-status"]');
    if (!node) return;
    node.textContent = message || "";
    node.className = `roi-save-status ${type}`.trim();
  }

  function scheduleSave(anchorKey, container) {
    if (!anchorKey) return;
    const existing = roiStore.saveTimers.get(anchorKey);
    if (existing) clearTimeout(existing);
    updateSaveStatus(container, "保存中...", "saving");
    const timer = setTimeout(async () => {
      try {
        await persistAnchorRoiSettings(anchorKey, readCurrentValues(container));
        updateSaveStatus(container, "已按当前主播保存", "saved");
      } catch (error) {
        updateSaveStatus(container, error.message || "保存失败", "error");
      } finally {
        roiStore.saveTimers.delete(anchorKey);
      }
    }, 500);
    roiStore.saveTimers.set(anchorKey, timer);
  }

  async function render(container, anchor, options = {}) {
    if (!container) return;
    const anchorKey = normalizeAnchorKey(anchor);
    const periodText = String(options.periodText || "").trim();
    const cvr = normalizeCvr(anchor);
    const defaults = {
      viewers: Math.max(100, Math.round(Number(anchor?.acu || 1000))),
      price: 1980,
      cycle: 3,
      commission: 20,
      cost: 12000,
      adspend: 5000,
      cvrLow: cvr.low,
      cvrMid: cvr.mid,
      cvrHigh: cvr.high
    };

    container.innerHTML = `
      <div class="anchor-roi-card">
        <div class="anchor-dashboard-head">
          <div>
            <h3>主播 ROI 评估</h3>
            <div class="anchor-dashboard-note">按你给的 v3 逻辑，估算主播在保守 / 基准 / 乐观三种转化率下的全年投入产出。</div>
            ${periodText ? `<div class="anchor-dashboard-note">统计区间：${periodText}</div>` : ""}
          </div>
        </div>
        <div class="roi-widget">
          <div class="roi-control-group">
            <div class="roi-section-title">主播基础数据</div>
            <div class="roi-save-status" data-roi-panel="save-status">切换主播时会自动带出该主播上次保存的 ROI 参数。</div>
            <div class="roi-slider-row">
              <span class="roi-slider-label">月均在线人数</span>
              <input type="range" min="100" max="10000" step="100" value="${defaults.viewers}" data-roi="viewers">
              <span class="roi-slider-value" data-roi-out="viewers"></span>
            </div>
            <div class="roi-slider-row">
              <span class="roi-slider-label">课程单价</span>
              <input type="range" min="500" max="9999" step="100" value="${defaults.price}" data-roi="price">
              <span class="roi-slider-value" data-roi-out="price"></span>
            </div>
            <div class="roi-slider-row">
              <span class="roi-slider-label">下粉周期（月）</span>
              <input type="range" min="1" max="6" step="1" value="${defaults.cycle}" data-roi="cycle">
              <span class="roi-slider-value" data-roi-out="cycle"></span>
            </div>
            <div class="roi-slider-row">
              <span class="roi-slider-label">平台抽成</span>
              <input type="range" min="0" max="40" step="1" value="${defaults.commission}" data-roi="commission">
              <span class="roi-slider-value" data-roi-out="commission"></span>
            </div>
          </div>
          <div class="roi-control-group">
            <div class="roi-section-title">成本构成</div>
            <div class="roi-slider-row">
              <span class="roi-slider-label">主播月固定成本</span>
              <input type="range" min="3000" max="50000" step="1000" value="${defaults.cost}" data-roi="cost">
              <span class="roi-slider-value" data-roi-out="cost"></span>
            </div>
            <div class="roi-slider-row">
              <span class="roi-slider-label">每场投流费用</span>
              <input type="range" min="0" max="50000" step="500" value="${defaults.adspend}" data-roi="adspend">
              <span class="roi-slider-value" data-roi-out="adspend"></span>
            </div>
          </div>
          <div class="roi-control-group">
            <div class="roi-section-title">转化率（三场景）</div>
            <div class="roi-cvr-grid">
              <div class="roi-cvr-col">
                <div class="roi-cvr-tag conservative">保守</div>
                <div class="roi-cvr-input-wrap"><input type="number" min="0.1" max="20" step="0.1" value="${defaults.cvrLow}" data-roi="cvr-low"><span>%</span></div>
                <div class="roi-cvr-hint">冷启动 / 新主播</div>
              </div>
              <div class="roi-cvr-col">
                <div class="roi-cvr-tag base">基准</div>
                <div class="roi-cvr-input-wrap"><input type="number" min="0.1" max="20" step="0.1" value="${defaults.cvrMid}" data-roi="cvr-mid"><span>%</span></div>
                <div class="roi-cvr-hint">行业均值</div>
              </div>
              <div class="roi-cvr-col">
                <div class="roi-cvr-tag optimistic">乐观</div>
                <div class="roi-cvr-input-wrap"><input type="number" min="0.1" max="20" step="0.1" value="${defaults.cvrHigh}" data-roi="cvr-high"><span>%</span></div>
                <div class="roi-cvr-hint">成熟主播</div>
              </div>
            </div>
          </div>
          <div class="roi-section-title">三场景预测（全年）</div>
          <div class="roi-scenario-grid" data-roi-panel="scenario-grid"></div>
          <div class="roi-section-title">基准场景损益明细</div>
          <div class="roi-pnl-table" data-roi-panel="pnl-table"></div>
          <div class="roi-verdict" data-roi-panel="verdict"></div>
        </div>
      </div>
    `;

    const controls = Array.from(container.querySelectorAll("[data-roi]"));
    const outputs = Object.fromEntries(Array.from(container.querySelectorAll("[data-roi-out]")).map((node) => [node.dataset.roiOut, node]));
    const panels = {
      scenarios: container.querySelector('[data-roi-panel="scenario-grid"]'),
      pnl: container.querySelector('[data-roi-panel="pnl-table"]'),
      verdict: container.querySelector('[data-roi-panel="verdict"]')
    };

    function readValue(name) {
      return Number(container.querySelector(`[data-roi="${name}"]`)?.value || 0);
    }

    function update() {
      const viewers = readValue("viewers");
      const price = readValue("price");
      const cycle = readValue("cycle");
      const commission = readValue("commission");
      const cost = readValue("cost");
      const adspend = readValue("adspend");
      const cvrLow = readValue("cvr-low") || 1;
      const cvrMid = readValue("cvr-mid") || 3;
      const cvrHigh = readValue("cvr-high") || 5;
      const sessionsPerYear = Math.max(1, Math.floor(12 / Math.max(1, cycle)));

      outputs.viewers.textContent = `${viewers.toLocaleString("zh-CN")} 人`;
      outputs.price.textContent = currency(price);
      outputs.cycle.textContent = `每 ${cycle} 个月`;
      outputs.commission.textContent = `${commission}%`;
      outputs.cost.textContent = currency(cost);
      outputs.adspend.textContent = adspend === 0 ? "不投流" : `${currency(adspend)} / 场`;

      const scenarios = [
        { key: "conservative", label: "保守", cvr: cvrLow, className: "conservative" },
        { key: "base", label: "基准", cvr: cvrMid, className: "base" },
        { key: "optimistic", label: "乐观", cvr: cvrHigh, className: "optimistic" }
      ].map((scenario) => ({
        ...scenario,
        ...calcScenario(viewers, scenario.cvr, price, commission, cost, sessionsPerYear, adspend)
      }));

      panels.scenarios.innerHTML = scenarios.map((scenario) => `
        <div class="roi-scenario-col">
          <div class="roi-scenario-head ${scenario.className}">${scenario.label} CVR ${scenario.cvr}%</div>
          <div class="roi-scenario-body">
            <div class="roi-s-row"><span class="roi-s-label">每场成交</span><span class="roi-s-value">${scenario.buyersPerSession} 人 × ${sessionsPerYear} 场</span></div>
            <div class="roi-s-row"><span class="roi-s-label">全年净收入</span><span class="roi-s-value">${currency(scenario.revenueYear)}</span></div>
            <div class="roi-s-row"><span class="roi-s-label">全年总成本</span><span class="roi-s-value">${currency(scenario.totalCostYear)}</span></div>
            <div class="roi-s-row"><span class="roi-s-label">净利润</span><span class="roi-s-value ${scenario.profit >= 0 ? "pos" : "neg"}">${currency(scenario.profit)}</span></div>
            <div class="roi-s-row"><span class="roi-s-label">ROI</span><span class="roi-s-roi ${roiClass(scenario.roi)}">${scenario.roi >= 0 ? "+" : ""}${Math.round(scenario.roi)}%</span></div>
          </div>
        </div>
      `).join("");

      const base = scenarios[1];
      const rows = [
        { label: "全年场次", value: `${sessionsPerYear} 场` },
        { label: `每场成交人数（CVR ${cvrMid}%）`, value: `${base.buyersPerSession} 人` },
        { label: "每场毛收入", value: currency(base.grossPerSession) },
        { label: `平台抽成（${commission}%）`, value: `- ${currency(base.grossPerSession * commission / 100)}`, className: "neg", indent: true },
        { label: "每场净收入", value: currency(base.netPerSession) },
        { label: "全年总收入", value: currency(base.revenueYear), className: "pos" },
        { label: "主播固定成本（全年）", value: `- ${currency(base.fixedCostYear)}`, className: "neg" }
      ];
      if (adspend > 0) {
        rows.push({ label: `投流费用（${sessionsPerYear} 场）`, value: `- ${currency(base.adCostYear)}`, className: "neg" });
      }
      rows.push({ label: "全年净利润", value: currency(base.profit), className: base.profit >= 0 ? "pos" : "neg" });
      panels.pnl.innerHTML = rows.map((row) => `
        <div class="roi-pnl-row">
          <span class="roi-pnl-label ${row.indent ? "roi-pnl-indent" : ""}">${row.label}</span>
          <span class="${row.className || ""}">${row.value}</span>
        </div>
      `).join("");

      let verdictText = "";
      let verdictClass = "warning";
      if (base.roi >= 100) {
        verdictText = `基准场景 ROI ${Math.round(base.roi)}%，含投流后仍有 ${currency(base.profit)} 净利润，值得持续投入。`;
        verdictClass = "success";
      } else if (base.roi >= 20) {
        verdictText = `基准场景 ROI ${Math.round(base.roi)}%，可以转正但空间不大。建议先跑 1-2 场验证实际转化率，再决定是否加大投流。`;
      } else if (base.roi >= 0) {
        verdictText = `基准场景 ROI 仅 ${Math.round(base.roi)}%，含投流后几乎不赚钱。若实际转化低于基准则亏损，投流力度建议保守。`;
      } else {
        verdictText = `基准场景 ROI ${Math.round(base.roi)}%，当前成本结构下无法覆盖支出。可尝试降低投流预算或提高课程单价，再重新评估。`;
        verdictClass = "danger";
      }
      panels.verdict.className = `roi-verdict ${verdictClass}`;
      panels.verdict.textContent = verdictText;
    }

    controls.forEach((control) => control.addEventListener("input", () => {
      update();
      scheduleSave(anchorKey, container);
    }));

    try {
      const items = await loadRoiStore();
      const saved = items?.[anchorKey];
      if (saved) {
        applyValues(container, saved);
        updateSaveStatus(container, "已带出当前主播的历史 ROI 参数", "saved");
      }
    } catch (error) {
      updateSaveStatus(container, error.message || "读取 ROI 设置失败", "error");
    }
    update();
  }

  window.AnchorRoiCalculator = {
    render
  };
})();
