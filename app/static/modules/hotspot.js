// ══ 热点追踪相关函数 ══

const PLATFORM_META = {
  zhihu: { name: '知乎', icon: '📘' },
  bilibili: { name: 'B站', icon: '📺' },
  toutiao: { name: '头条', icon: '📰' },
  weibo: { name: '微博', icon: '🔥' },
  baidu: { name: '百度', icon: '🔍' },
  douyin: { name: '抖音', icon: '🎵' },
  cls: { name: '财联社', icon: '💰' },
  wallstreetcn: { name: '华尔街见闻', icon: '📈' },
  ifeng: { name: '凤凰网', icon: '📰' },
  pengpai: { name: '澎湃新闻', icon: '🌊' },
  tieba: { name: '贴吧热议', icon: '💬' }
};
let hotspotState = { platforms: [], settings: null, filter: '', keyword: '', latestSummary: '' };

async function loadHotspotMain() {
  try {
    const [statsRes, platformsRes, settingsRes, hotspotsRes] = await Promise.all([
      fetch('/api/hotspot/stats', { credentials: 'include' }),
      fetch('/api/hotspot/platforms', { credentials: 'include' }),
      fetch('/api/hotspot/settings', { credentials: 'include' }),
      fetch(`/api/hotspot/current${hotspotState.filter ? '?platform='+encodeURIComponent(hotspotState.filter) : ''}`, { credentials: 'include' })
    ]);
    
    const stats = statsRes.ok ? (await statsRes.json()).stats || {} : {};
    document.getElementById('hotspotTotalCount').textContent = fmt(stats.active || 0);
    
    const platforms = platformsRes.ok ? (await platformsRes.json()).platforms || [] : [];
    hotspotState.platforms = platforms;
    hotspotState.settings = settingsRes.ok ? (await settingsRes.json()).settings || null : null;
    const enabledIds = new Set((hotspotState.settings?.enabledPlatforms || platforms.map(p => p.id)).filter(Boolean));
    const visiblePlatforms = platforms.filter(p => enabledIds.has(p.id));
    document.getElementById('hotspotPlatformBtns').innerHTML = 
      '<button class="tag active" data-platform="" onclick="filterHotspotPlatform(\'\')">全部</button>' +
      visiblePlatforms.map(p => `<button class="tag" data-platform="${p.id}" onclick="filterHotspotPlatform('${p.id}')">${(PLATFORM_META[p.id]||{}).icon||'🔥'} ${(PLATFORM_META[p.id]||{}).name||p.name}</button>`).join('');
    
    const hotspots = hotspotsRes.ok ? await hotspotsRes.json() : { byPlatform: {}, items: [] };
    const configuredByPlatform = Object.fromEntries(
      Object.entries(hotspots.byPlatform || {}).filter(([platformId]) => enabledIds.has(platformId))
    );
    const configuredCount = Object.values(configuredByPlatform).reduce((sum, items) => sum + items.length, 0);
    document.getElementById('hotspotTotalCount').textContent = fmt(configuredCount || stats.active || 0);
    renderHotspotGridMain(configuredByPlatform);
    
    const latest = (hotspots.items||[]).reduce((m,i) => Math.max(m, new Date(i.lastSeenAt||0).getTime()), 0) || Date.now();
    document.getElementById('hotspotUpdateTime').textContent = formatTimeShort(new Date(latest));
    loadCachedHotspotSummary();
  } catch(e) { console.log('热搜加载失败', e); }
}

function renderHotspotGridMain(byPlatform) {
  if (!Object.keys(byPlatform).length) {
    document.getElementById('hotspotGridMain').innerHTML = '<div style="grid-column:span 3;text-align:center;padding:30px;color:var(--text1);">暂无数据，点击刷新获取</div>';
    return;
  }
  let html = '';
  for (const [pid, items] of Object.entries(byPlatform)) {
    const meta = PLATFORM_META[pid] || hotspotState.platforms.find(p=>p.id===pid) || { name: pid, icon: '🔥' };
    html += `<div class="hotspot-platform-card">
      <div class="hotspot-card-header"><div class="hotspot-card-title">${meta.icon} ${meta.name}</div><div class="hotspot-card-count">${items.length}条</div></div>
      <div class="hotspot-card-body">${items.slice(0,15).map(i => {
        const r = i.rank||0, rc = r===1?'r1':r===2?'r2':r===3?'r3':'';
        return `<div class="hotspot-item-main"><div class="hotspot-item-row">
          <div class="hotspot-item-rank ${rc}">#${r||'--'}</div>
          <div class="hotspot-item-content">
            ${i.url ? `<a class="hotspot-item-title" href="${i.url}" target="_blank">${i.title}<span class="arrow">↗</span></a>` : `<span class="hotspot-item-title">${i.title}</span>`}
            <div class="hotspot-item-meta">${i.hotValue ? `<span class="hotspot-item-hot">${i.hotValue}</span> · ` : ''}${formatTimeShort(new Date(i.lastSeenAt))}</div>
            <div class="hotspot-actions">
              <button class="hotspot-action-btn" onclick="analyzeHotspotMain('${i.id}', '${i.title.replace(/'/g, "\\'")}')">🤖 分析</button>
            </div>
          </div>
        </div></div>`;
      }).join('')}</div></div>`;
  }
  document.getElementById('hotspotGridMain').innerHTML = html;
}

function getConfiguredHotspotPlatformIds() {
  const configured = hotspotState.settings?.enabledPlatforms || [];
  if (configured.length) return configured;
  return hotspotState.platforms.map(p => p.id).filter(Boolean);
}

function openHotspotConfigPage() {
  document.getElementById('hotspotMainContent').style.display = 'none';
  document.getElementById('hotspotConfigPage').style.display = 'block';
  loadHotspotConfig();
}

function closeHotspotConfigPage() {
  document.getElementById('hotspotConfigPage').style.display = 'none';
  document.getElementById('hotspotMainContent').style.display = 'block';
}

function renderHotspotConfigForm() {
  const settings = hotspotState.settings || {};
  const enabled = new Set(settings.enabledPlatforms || hotspotState.platforms.map(p => p.id));
  document.getElementById('hotspotPlatformConfigGrid').innerHTML = hotspotState.platforms.map(p => {
    const meta = PLATFORM_META[p.id] || { name: p.name, icon: p.icon || '🔥' };
    return `
      <label class="hotspot-platform-option">
        <input type="checkbox" class="hotspot-platform-config-check" value="${escapeHtmlAttr(p.id)}" ${enabled.has(p.id) ? 'checked' : ''}>
        <div class="hotspot-platform-option-main">
          <div class="hotspot-platform-option-name">${escapeHtml(meta.icon)} ${escapeHtml(meta.name || p.name)}</div>
          <div class="hotspot-platform-option-meta">${escapeHtml(p.category || 'news')}</div>
        </div>
      </label>
    `;
  }).join('');
  const minutes = Number(settings.fetchIntervalMinutes || 60);
  document.getElementById('hotspotIntervalHoursInput').value = Math.max(0.25, minutes / 60);
  document.getElementById('hotspotRetentionDaysInput').value = Number(settings.retentionDays || 30);
  document.getElementById('hotspotAutoAnalyzeInput').checked = !!settings.autoAnalyze;
}

async function loadHotspotConfig() {
  try {
    const [platformsRes, settingsRes] = await Promise.all([
      fetch('/api/hotspot/platforms', { credentials: 'include' }),
      fetch('/api/hotspot/settings', { credentials: 'include' })
    ]);
    if (!platformsRes.ok || !settingsRes.ok) throw new Error('配置加载失败');
    hotspotState.platforms = (await platformsRes.json()).platforms || [];
    hotspotState.settings = (await settingsRes.json()).settings || {};
    renderHotspotConfigForm();
  } catch(e) {
    showToast('配置加载失败: '+e.message);
  }
}

function toggleAllHotspotPlatforms(checked) {
  document.querySelectorAll('.hotspot-platform-config-check').forEach(input => { input.checked = checked; });
}

async function saveHotspotConfig() {
  const btn = document.getElementById('hotspotConfigSaveBtn');
  const note = document.getElementById('hotspotConfigNote');
  const enabledPlatforms = [...document.querySelectorAll('.hotspot-platform-config-check:checked')].map(input => input.value);
  if (!enabledPlatforms.length) {
    showToast('至少选择一个平台');
    return;
  }
  const intervalHours = Math.max(0.25, Number(document.getElementById('hotspotIntervalHoursInput').value || 1));
  const retentionDays = Math.max(1, Math.round(Number(document.getElementById('hotspotRetentionDaysInput').value || 30)));
  btn.disabled = true;
  btn.textContent = '保存中...';
  try {
    const res = await fetch('/api/hotspot/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        enabledPlatforms,
        trackedKeywords: hotspotState.settings?.trackedKeywords || [],
        fetchIntervalMinutes: Math.round(intervalHours * 60),
        retentionDays,
        autoAnalyze: document.getElementById('hotspotAutoAnalyzeInput').checked
      })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || '保存失败');
    hotspotState.settings = {
      ...(hotspotState.settings || {}),
      enabledPlatforms,
      fetchIntervalMinutes: Math.round(intervalHours * 60),
      retentionDays,
      autoAnalyze: document.getElementById('hotspotAutoAnalyzeInput').checked
    };
    note.textContent = `已保存：${enabledPlatforms.length} 个平台，每 ${intervalHours} 小时自动刷新。`;
    showToast('热搜配置已保存');
    await loadHotspotMain();
    closeHotspotConfigPage();
  } catch(e) {
    showToast('保存失败: '+e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '保存配置';
  }
}

function normalizeHotspotAnalysisMarkdown(markdown) {
  let text = String(markdown || "").trim();
  const fenced = text.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)```\s*$/i);
  if (fenced?.[1]) text = fenced[1].trim();
  return text;
}

function renderHotspotAnalysis(markdown, title) {
  const cleaned = normalizeHotspotAnalysisMarkdown(markdown);
  return buildReportShellHtml(cleaned, {
    title: title ? `热点分析：${title}` : "热点分析报告",
    badges: ["AI 分析", new Date().toLocaleString("zh-CN")],
    footer: ""
  });
}

function stripHotspotMarkdownInline(text) {
  return String(text || "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function formatHotspotSummaryInline(text) {
  return escapeHtml(stripHotspotMarkdownInline(text))
    .replace(/(事件|为什么重要|可能影响的行业\/方向|可能影响的行业方向|方向|风险|合规提醒)：/g, '<strong>$1：</strong>');
}

function getHotspotSummarySection(markdown, titlePattern) {
  const text = normalizeHotspotAnalysisMarkdown(markdown);
  const headings = [...text.matchAll(/^##\s+(.+)$/gm)];
  for (let i = 0; i < headings.length; i += 1) {
    const heading = headings[i];
    if (!titlePattern.test(heading[1])) continue;
    const start = heading.index + heading[0].length;
    const end = i + 1 < headings.length ? headings[i + 1].index : text.length;
    return text.slice(start, end).trim();
  }
  return "";
}

function parseHotspotFocusItems(markdown) {
  const section = getHotspotSummarySection(markdown, /值得关注|关注的\s*5\s*条/i);
  const lines = section.split("\n");
  const items = [];
  let current = null;

  const pushCurrent = () => {
    if (current?.title) items.push(current);
    current = null;
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;
    const itemMatch = line.match(/^\d+[.、]\s+(.+)$/);
    if (itemMatch) {
      pushCurrent();
      current = { title: stripHotspotMarkdownInline(itemMatch[1]), event: "", reason: "", impact: "", extra: [] };
      continue;
    }
    if (!current) continue;
    const bullet = line.replace(/^[-*]\s+/, "");
    const clean = stripHotspotMarkdownInline(bullet);
    const value = clean.replace(/^(事件|为什么重要|可能影响的行业\/方向|可能影响的行业方向|方向)[:：]\s*/, "");
    if (/^事件[:：]/.test(clean)) current.event = value;
    else if (/^为什么重要[:：]/.test(clean)) current.reason = value;
    else if (/^(可能影响的行业\/方向|可能影响的行业方向|方向)[:：]/.test(clean)) current.impact = value;
    else current.extra.push(clean);
  }
  pushCurrent();
  return items.slice(0, 5);
}

function parseHotspotSimpleList(markdown, titlePattern, limit = 5) {
  const section = getHotspotSummarySection(markdown, titlePattern);
  const rows = section
    .split("\n")
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => line.replace(/^[-*]\s+/, "").replace(/^\d+[.、]\s+/, ""))
    .map(stripHotspotMarkdownInline)
    .filter(Boolean);
  return rows.slice(0, limit);
}

function renderHotspotSummary(markdown, metaText) {
  const cleaned = normalizeHotspotAnalysisMarkdown(markdown);
  const focusItems = parseHotspotFocusItems(cleaned);
  const topics = parseHotspotSimpleList(cleaned, /直播.*选题|可用选题/i, 5);
  const risks = parseHotspotSimpleList(cleaned, /风险|合规/i, 4);
  const noise = getHotspotSummarySection(cleaned, /噪音|忽略/i)
    .replace(/^[-*]\s+/, "")
    .replace(/^\d+[.、]\s+/, "")
    .trim();

  if (!focusItems.length && !topics.length && !risks.length) {
    return buildReportShellHtml(cleaned, {
      title: "AI 热点总览",
      badges: ["本轮热搜", metaText || new Date().toLocaleString("zh-CN")],
      footer: ""
    });
  }

  return `
    <div class="hotspot-summary-dashboard">
      <div class="hotspot-summary-hero">
        <div>
          <div class="hotspot-summary-kicker">AI 热点雷达</div>
          <h2>本轮最值得盯的 ${focusItems.length || 0} 条</h2>
          <p>${escapeHtml(metaText || "根据最新热搜生成")}</p>
        </div>
        <div class="hotspot-summary-stat">
          <span>${focusItems.length || 0}</span>
          <small>重点新闻</small>
        </div>
      </div>

      <div class="hotspot-focus-grid">
        ${focusItems.map((item, index) => `
          <article class="hotspot-focus-card ${index === 0 ? 'is-primary' : ''}">
            <div class="hotspot-focus-rank">#${index + 1}</div>
            <h3>${escapeHtml(item.title)}</h3>
            ${item.event ? `<p class="hotspot-focus-event">${formatHotspotSummaryInline(item.event)}</p>` : ""}
            ${item.reason ? `<p class="hotspot-focus-reason">${formatHotspotSummaryInline(item.reason)}</p>` : ""}
            ${item.impact ? `<div class="hotspot-impact-tags">${item.impact.split(/[、，,]/).filter(Boolean).slice(0, 5).map(tag => `<span>${escapeHtml(tag.trim())}</span>`).join("")}</div>` : ""}
          </article>
        `).join("")}
      </div>

      <div class="hotspot-summary-side-grid">
        <section class="hotspot-summary-box">
          <div class="hotspot-summary-box-title">直播可用选题</div>
          <ol>${topics.map(item => `<li>${formatHotspotSummaryInline(item)}</li>`).join("")}</ol>
        </section>
        <section class="hotspot-summary-box is-warning">
          <div class="hotspot-summary-box-title">风险与合规提醒</div>
          <ol>${risks.map(item => `<li>${formatHotspotSummaryInline(item)}</li>`).join("")}</ol>
        </section>
      </div>
      ${noise ? `<div class="hotspot-noise-strip"><strong>可忽略噪音</strong><span>${formatHotspotSummaryInline(noise)}</span></div>` : ""}
    </div>
  `;
}

function setHotspotSummaryLoading(message = "AI 正在筛选重要新闻...") {
  document.getElementById('hotspotSummaryPanel').style.display = 'block';
  document.getElementById('hotspotSummaryMeta').textContent = message;
  document.getElementById('hotspotSummaryContent').innerHTML = `
    <div style="padding:18px;color:var(--text1);font-size:13px;display:flex;align-items:center;gap:10px;">
      <span class="spinner" style="width:14px;height:14px;border-width:1px;"></span>
      <span>${message}</span>
    </div>
  `;
}

function renderHotspotSummaryPanel(analysis, meta = {}) {
  const generatedAt = meta.generatedAt ? new Date(meta.generatedAt) : new Date();
  const metaText = `生成于 ${generatedAt.toLocaleString("zh-CN")} · 覆盖 ${fmt(meta.itemCount || 0)} 条`;
  document.getElementById('hotspotSummaryPanel').style.display = 'block';
  document.getElementById('hotspotSummaryMeta').textContent = metaText;
  document.getElementById('hotspotSummaryContent').innerHTML = renderHotspotSummary(analysis, metaText);
}

function loadCachedHotspotSummary() {
  try {
    const cached = JSON.parse(localStorage.getItem('hotspotSummaryCache') || 'null');
    if (!cached?.analysis) return;
    const generatedAt = new Date(cached.generatedAt || 0).getTime();
    if (!generatedAt || Date.now() - generatedAt > 2 * 60 * 60 * 1000) return;
    hotspotState.latestSummary = cached.analysis || "";
    renderHotspotSummaryPanel(cached.analysis, cached);
  } catch(e) {}
}

function closeHotspotSummary() {
  document.getElementById('hotspotSummaryPanel').style.display = 'none';
}

async function analyzeHotspotSummaryMain(options = {}) {
  const btn = document.getElementById('hotspotSummaryBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ 总览中...';
  }
  setHotspotSummaryLoading(options.message || "AI 正在筛选本轮重要热搜...");
  try {
    const res = await fetch('/api/hotspot/analyze-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ topPerPlatform: 8 })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false || !data.analysis) {
      throw new Error(data.error || 'AI 总览生成失败');
    }
    const cache = {
      analysis: data.analysis,
      generatedAt: data.generatedAt || new Date().toISOString(),
      itemCount: data.itemCount || 0,
      platforms: data.platforms || []
    };
    localStorage.setItem('hotspotSummaryCache', JSON.stringify(cache));
    renderHotspotSummaryPanel(data.analysis, cache);
    hotspotState.latestSummary = data.analysis;
    if (!options.silent) showToast('AI 热点总览已生成');
  } catch(e) {
    document.getElementById('hotspotSummaryMeta').textContent = '总览生成失败';
    document.getElementById('hotspotSummaryContent').innerHTML = `<div style="padding:16px;color:var(--red);font-size:13px;">${escapeHtml(e.message)}</div>`;
    if (!options.silent) showToast('AI 总览失败: '+e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '✨ AI总览';
    }
  }
}

function latestHotspotSummaryText() {
  if (hotspotState.latestSummary) return hotspotState.latestSummary;
  try {
    const cached = JSON.parse(localStorage.getItem('hotspotSummaryCache') || 'null');
    return cached?.analysis || "";
  } catch(e) {
    return "";
  }
}

function quoteClass(value) {
  return Number(value || 0) >= 0 ? "green" : "red";
}

function quoteText(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "--";
  return `${num >= 0 ? "+" : ""}${num.toFixed(2)}%`;
}

function renderHotspotStocks(data) {
  const items = data.items || [];
  const themes = data.themes || [];
  const generated = data.generatedAt ? new Date(data.generatedAt).toLocaleString("zh-CN") : new Date().toLocaleString("zh-CN");
  document.getElementById('hotspotStockPanel').style.display = 'block';
  document.getElementById('hotspotStockMeta').textContent =
    `生成于 ${generated} · 扫描 ${fmt(data.universeCount || 0)} 只股票 · 命中 ${items.length} 个候选 · 覆盖 ${fmt(data.hotspotCount || 0)} 条热搜`;

  if (!items.length) {
    document.getElementById('hotspotStockContent').innerHTML = '<div class="hotspot-stock-empty">暂未从本轮热点中匹配到明确标的。可先刷新热搜或生成 AI 总览后再试。</div>';
    return;
  }

  const themeHtml = themes.length ? `
    <div class="hotspot-stock-themes">
      ${themes.slice(0, 8).map(item => `<span>${escapeHtml(item.theme)}${item.keywords?.length ? ` · ${escapeHtml(item.keywords.slice(0, 3).join("/"))}` : ""}</span>`).join("")}
    </div>` : "";

  document.getElementById('hotspotStockContent').innerHTML = `
    ${themeHtml}
    <div class="hotspot-stock-grid">
      ${items.map((item, index) => {
        const quote = item.quote || {};
        const pct = quote.pctChange;
        const hasQuote = pct !== undefined && pct !== null && pct !== "";
        return `<article class="hotspot-stock-card ${index < 3 ? "is-top" : ""}">
          <div class="hotspot-stock-card-head">
            <div>
              <div class="hotspot-stock-name">${escapeHtml(item.name)} <span>${escapeHtml(item.code)}</span></div>
              <div class="hotspot-stock-industry">${escapeHtml(item.theme || item.industry || "关联观察")}</div>
            </div>
            <div class="hotspot-stock-confidence">${fmt(item.confidence || 0)}<small>%</small></div>
          </div>
          <div class="hotspot-stock-quote">
            <span>${hasQuote ? escapeHtml(String(quote.close ?? "--")) : "未取行情"}</span>
            <strong class="${hasQuote ? quoteClass(pct) : "muted"}">${hasQuote ? quoteText(pct) : "--"}</strong>
          </div>
          <div class="hotspot-stock-reasons">
            ${(item.reasons || []).slice(0, 3).map(reason => `<span>${escapeHtml(reason)}</span>`).join("")}
          </div>
          <div class="hotspot-stock-evidence">
            ${(item.evidence || []).slice(0, 2).map(hit => `<div>来自热搜：${escapeHtml(hit.title || "")}</div>`).join("") || '<div>基于主题词与行业映射召回</div>'}
          </div>
        </article>`;
      }).join("")}
    </div>
    <div class="hotspot-stock-note">仅表示热点与行业/标的存在弱关联，不代表因果关系或投资建议。</div>
  `;
}

function setHotspotStocksLoading() {
  document.getElementById('hotspotStockPanel').style.display = 'block';
  document.getElementById('hotspotStockMeta').textContent = '正在从股票基础库中召回候选...';
  document.getElementById('hotspotStockContent').innerHTML = `
    <div class="hotspot-stock-loading">
      <span class="spinner" style="width:14px;height:14px;border-width:1px;"></span>
      <span>正在扫描股票名称、行业与主题关键词，并补充候选行情...</span>
    </div>
  `;
}

async function analyzeHotspotRelatedStocks() {
  const btn = document.getElementById('hotspotStockBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '匹配中...';
  }
  setHotspotStocksLoading();
  try {
    const res = await fetch('/api/hotspot/related-stocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ summary: latestHotspotSummaryText(), limit: 18, quoteLimit: 12 })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || data.detail || '关联标的匹配失败');
    renderHotspotStocks(data);
    showToast('热点关联标的已生成');
  } catch(e) {
    document.getElementById('hotspotStockMeta').textContent = '关联标的生成失败';
    document.getElementById('hotspotStockContent').innerHTML = `<div class="hotspot-stock-empty" style="color:var(--red);">${escapeHtml(e.message)}</div>`;
    showToast('关联标的失败: '+e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '关联标的';
    }
  }
}

function closeHotspotStocks() {
  document.getElementById('hotspotStockPanel').style.display = 'none';
}

// AI分析热搜
async function analyzeHotspotMain(itemId, title) {
  if (!itemId) {
    showToast('缺少热搜ID');
    return;
  }
  showToast('正在分析...');
  try {
    const res = await fetch('/api/hotspot/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ itemId: itemId, title: title })
    });
    if (!res.ok) throw new Error('分析失败');
    const data = await res.json();
    if (data.ok && data.analysis) {
      // 在当前页面显示分析结果
      document.getElementById('hotspotAnalysisPanel').style.display = 'block';
      document.getElementById('hotspotAnalysisContent').innerHTML = renderHotspotAnalysis(data.analysis, title);
      document.getElementById('hotspotAnalysisPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
      showToast('分析完成');
    } else {
      showToast(data.error || '分析失败');
    }
  } catch(e) {
    showToast('分析失败: '+e.message);
  }
}

function closeHotspotAnalysis() {
  document.getElementById('hotspotAnalysisPanel').style.display = 'none';
}

function formatTimeShort(d) {
  const diff = Date.now() - d.getTime();
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return Math.floor(diff/60000)+'分钟前';
  if (diff < 86400000) return Math.floor(diff/3600000)+'小时前';
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
}

function filterHotspotPlatform(p) {
  hotspotState.filter = p;
  document.querySelectorAll('#hotspotPlatformBtns .tag').forEach(b => b.classList.toggle('active', b.dataset.platform === p));
  loadHotspotMain();
}

function hotspotSearch() {
  const kw = document.getElementById('hotspotSearchInput').value.trim();
  if (kw) location.href = `/hotspot.html?keyword=${encodeURIComponent(kw)}`;
}

async function fetchHotspotsMain() {
  const btn = document.getElementById('hotspotFetchBtn');
  btn.disabled = true; btn.textContent = '⏳ 抓取中...';
  try {
    const platforms = getConfiguredHotspotPlatformIds();
    const res = await fetch('/api/hotspot/fetch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ platforms }) });
    const data = await res.json().catch(() => ({}));
    const result = data.result || {};
    if (!res.ok || data.ok === false || result.ok === false) {
      const failed = (result.failedPlatforms || []).map(p => `${p.platform}: ${p.error}`).join('；');
      throw new Error(data.error || result.error || failed || '抓取失败');
    }
    const failedCount = (result.failedPlatforms || []).length;
    showToast(`热搜已更新：${fmt(result.totalItems || 0)} 条${failedCount ? `，${failedCount}个平台失败` : ''}`);
    await loadHotspotMain();
    analyzeHotspotSummaryMain({ silent: true, message: "热搜已更新，正在生成 AI 总览..." });
  } catch(e) { showToast('抓取失败: '+e.message); }
  btn.disabled = false; btn.textContent = '📥 刷新';
}
