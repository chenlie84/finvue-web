// FinVue report export center: report list, preview, and selected-record downloads.
// Legacy inline handlers call these names directly, so this classic script keeps them global.

function getReportTypeDisplayName(type) {
  if (type === "currentLive") return "当前工作区报告";
  if (type === "anchorProgress") return "主播提升复盘";
  if (type === "anchorCompare") return "主播对比分析";
  return REPORT_TYPE_META[type]?.title || type || "未命名报告";
}

function getExportRecordTimestamp(record) {
  return record?.createdAt || record?.analyzedAt || record?.timestamp || "";
}

function getExportRecordSortValue(record) {
  return String(getExportRecordTimestamp(record) || "");
}

function collectExportRecords() {
  const records = [];
  if (state.lastMarkdown && els.liveResult?.innerHTML?.trim()) {
    records.push({
      key: "current-live-report",
      sourceType: "currentLive",
      title: getCurrentReportTitle(),
      subtitle: extractSnapshotConclusion(state.lastMarkdown),
      markdown: state.lastMarkdown,
      aiMeta: state.lastAiMeta || null,
      createdAt: new Date().toISOString(),
      htmlGetter: () => getReportExportHtml()
    });
  }
  (Array.isArray(state.anchorProfiles) ? state.anchorProfiles : []).forEach((profile) => {
    (Array.isArray(profile.snapshots) ? profile.snapshots : []).forEach((snapshot) => {
      if (!snapshot?.markdown) return;
      const key = `snapshot::${profile.id}::${snapshot.analyzedAt || ""}::${snapshot.reportType || ""}`;
      records.push({
        key,
        sourceType: snapshot.reportType || "snapshot",
        title: `${profile.anchorName || "未命名主播"} · ${getReportTypeDisplayName(snapshot.reportType)}`,
        subtitle: extractSnapshotConclusion(snapshot.markdown),
        markdown: snapshot.markdown,
        aiMeta: snapshot.aiMeta || null,
        createdAt: snapshot.analyzedAt || profile.updatedAt || profile.createdAt || "",
        profileId: profile.id,
        snapshotKey: `${snapshot.analyzedAt || ""}-${snapshot.reportType || ""}`,
        htmlGetter: () => getAnchorSnapshotExportHtml(profile, snapshot)
      });
    });
    const progressSummary = buildAnchorProgressSummary(profile);
    const progressInsightKey = progressSummary ? getAnchorProgressInsightKey(profile, progressSummary) : "";
    const progressInsight = progressInsightKey ? state.currentAnchorProgressInsights?.[progressInsightKey] : null;
    if (progressInsight?.markdown) {
      records.push({
        key: `progress::${profile.id}::${progressInsight.createdAt || ""}`,
        sourceType: "anchorProgress",
        title: `${profile.anchorName || "未命名主播"} · 主播提升复盘`,
        subtitle: extractSnapshotConclusion(progressInsight.markdown),
        markdown: progressInsight.markdown,
        aiMeta: progressInsight.aiMeta || null,
        createdAt: progressInsight.createdAt || "",
        profileId: profile.id,
        htmlGetter: () => {
          const currentProfileId = state.currentAnchorProfileId;
          state.currentAnchorProfileId = profile.id;
          const html = getCurrentAnchorProgressInsightExportHtml();
          state.currentAnchorProfileId = currentProfileId;
          return html;
        }
      });
    }
  });
  if (state.currentAnchorCompareResult?.markdown) {
    const compareProfiles = getComparedAnchorProfiles();
    const compareTitle = compareProfiles.length === 2
      ? `${compareProfiles[0].anchorName} vs ${compareProfiles[1].anchorName} · 对比分析`
      : "主播对比分析";
    records.push({
      key: `compare::${state.currentAnchorCompareResult.createdAt || ""}`,
      sourceType: "anchorCompare",
      title: compareTitle,
      subtitle: extractSnapshotConclusion(state.currentAnchorCompareResult.markdown),
      markdown: state.currentAnchorCompareResult.markdown,
      aiMeta: state.currentAnchorCompareResult.aiMeta || null,
      createdAt: state.currentAnchorCompareResult.createdAt || "",
      htmlGetter: () => {
        return buildReportExportDocument(compareTitle, state.currentAnchorCompareResult.markdown, {
          title: compareTitle,
          timestamp: new Date(state.currentAnchorCompareResult.createdAt || Date.now()).toLocaleString("zh-CN"),
          model: state.currentAnchorCompareResult.aiMeta?.providerLabel
            ? `${state.currentAnchorCompareResult.aiMeta.providerLabel} / ${state.currentAnchorCompareResult.aiMeta.model}`
            : (state.currentAnchorCompareResult.aiMeta?.model || "后台路由"),
          badges: ["主播对比分析", `生成时间 ${new Date(state.currentAnchorCompareResult.createdAt || Date.now()).toLocaleString("zh-CN")}`]
        });
      }
    });
  }
  return records.sort((a, b) => getExportRecordSortValue(b).localeCompare(getExportRecordSortValue(a)));
}

function wrapExportDocument(title, reportHtml) {
  const headAssets = Array.from(document.head.querySelectorAll('style, link[rel="stylesheet"]'))
    .map((node) => node.outerHTML)
    .join("\n");
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>${escapeHtml(title || "报告导出")}</title>
${headAssets}
<style>
  html,body{height:auto !important;min-height:auto !important;overflow:visible !important;}
  body{margin:0;padding:28px 24px;background:var(--bg0);color:var(--text0);}
  .main-content{height:auto !important;min-height:auto !important;overflow:visible !important;padding:0 !important;}
  .app-body,.app-page,.sec,.panel{height:auto !important;min-height:auto !important;overflow:visible !important;}
  @page { size: A4; margin: 12mm; }
  @media print { body{padding:0 !important;background:var(--bg0);} }
</style>
</head>
<body>
  <div class="main-content" style="padding:0;">${reportHtml}</div>
</body>
</html>`;
}

function buildReportExportDocument(title, markdown, options = {}) {
  if (isHtmlReportContent(markdown)) {
    return buildStandaloneHtmlReportDocument(markdown, title || options.title || getCurrentReportTitle());
  }
  const shell = buildReportShellHtml(markdown, options);
  return wrapExportDocument(title || options.title || "报告导出", shell);
}

function openExportRecord(recordKey) {
  state.currentExportRecordKey = decodeURIComponent(String(recordKey || ""));
  renderExportCenter();
}

function getSelectedExportRecord(records = collectExportRecords()) {
  if (!records.length) return null;
  return records.find((item) => item.key === state.currentExportRecordKey) || records[0];
}

function renderExportCenter() {
  const records = collectExportRecords();
  const selected = getSelectedExportRecord(records);
  state.currentExportRecordKey = selected?.key || "";
  const snapshotCount = (Array.isArray(state.anchorProfiles) ? state.anchorProfiles : [])
    .reduce((total, item) => total + (Array.isArray(item.snapshots) ? item.snapshots.length : 0), 0);
  if (els.exportReportCount) els.exportReportCount.textContent = String(records.length);
  if (els.exportSnapshotCount) els.exportSnapshotCount.textContent = String(snapshotCount);
  if (els.exportBatchCount) els.exportBatchCount.textContent = String((Array.isArray(state.batchRunResults) ? state.batchRunResults : []).length);
  if (els.exportSelectedType) els.exportSelectedType.textContent = selected ? getReportTypeDisplayName(selected.sourceType) : "—";
  if (els.exportSelectedMeta) els.exportSelectedMeta.textContent = selected?.createdAt ? formatDateTime(selected.createdAt) : "请先从左侧列表选择";
  if (els.exportQuickMeta) els.exportQuickMeta.textContent = selected ? `${selected.title} · 已就绪` : "当前没有可导出的报告";
  if (els.exportHistoryMeta) els.exportHistoryMeta.textContent = `${records.length} 条`;
  if (els.exportQuickActions) {
    els.exportQuickActions.innerHTML = selected ? `
      <div class="muted" style="font-size:12px;line-height:1.7;">${escapeHtml(selected.title)}<br>${escapeHtml(selected.subtitle || "暂无摘要")}</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button class="btn btn-gold" onclick="exportSelectedRecord('html')">下载 HTML</button>
        <button class="btn btn-outline" onclick="exportSelectedRecord('pdf')">下载 PDF</button>
      </div>
    ` : `<div class="muted">先在直播分析页生成报告，或者从主播资料库沉淀一份历史快照，这里就会自动出现可导出条目。</div>`;
  }
  if (els.exportHistoryList) {
    els.exportHistoryList.innerHTML = records.length ? records.map((item) => {
      const isActive = item.key === state.currentExportRecordKey;
      return `
        <button class="analyst-row" style="width:100%;text-align:left;background:${isActive ? "rgba(200,146,42,0.08)" : "var(--bg1)"};border:1px solid ${isActive ? "rgba(200,146,42,0.42)" : "var(--border)"};box-shadow:${isActive ? "0 0 0 1px rgba(200,146,42,0.16) inset" : "none"};border-radius:var(--r);padding:12px 14px;cursor:pointer;color:var(--text0);" onclick="openExportRecord('${encodeURIComponent(item.key)}')">
          <div style="flex:1;min-width:0;">
            <div style="font-size:14px;font-weight:700;color:var(--text0);line-height:1.5;">${escapeHtml(item.title)}</div>
            <div style="font-size:12px;color:var(--text1);margin-top:6px;line-height:1.6;">${escapeHtml(item.subtitle || "暂无摘要")}</div>
          </div>
          <div style="text-align:right;white-space:nowrap;">
            <div style="font-size:12px;color:var(--gold);">${escapeHtml(getReportTypeDisplayName(item.sourceType))}</div>
            <div style="font-size:11px;color:var(--text2);margin-top:6px;">${escapeHtml(item.createdAt ? formatDateTime(item.createdAt) : "--")}</div>
          </div>
        </button>
      `;
    }).join("") : `<div class="muted">当前还没有可导出的报告。</div>`;
  }
  if (els.exportPreviewMeta) {
    els.exportPreviewMeta.textContent = selected
      ? `${getReportTypeDisplayName(selected.sourceType)} · ${selected.createdAt ? formatDateTime(selected.createdAt) : "未记录时间"}`
      : "未选择报告";
  }
  if (els.exportPreviewContent) {
    els.exportPreviewContent.innerHTML = selected?.markdown
      ? buildReportShellHtml(selected.markdown, {
          title: selected.title,
          timestamp: new Date(selected.createdAt || Date.now()).toLocaleString("zh-CN"),
          model: selected.aiMeta?.providerLabel
            ? `${selected.aiMeta.providerLabel} / ${selected.aiMeta.model}`
            : (selected.aiMeta?.model || "后台路由"),
          badges: [
            getReportTypeDisplayName(selected.sourceType),
            `生成时间 ${new Date(selected.createdAt || Date.now()).toLocaleString("zh-CN")}`
          ]
        })
      : `<div class="muted">当前选中项没有可预览内容。</div>`;
  }
}

function getExportRecordDocumentHtml(record) {
  if (!record) return "";
  if (typeof record.htmlGetter === "function") {
    const html = record.htmlGetter();
    if (html) return html;
  }
  if (!record.markdown) return "";
  return buildReportExportDocument(record.title, record.markdown, {
    title: record.title,
    timestamp: new Date(record.createdAt || Date.now()).toLocaleString("zh-CN"),
    model: record.aiMeta?.providerLabel
      ? `${record.aiMeta.providerLabel} / ${record.aiMeta.model}`
      : (record.aiMeta?.model || "后台路由"),
    badges: [
      getReportTypeDisplayName(record.sourceType),
      `生成时间 ${new Date(record.createdAt || Date.now()).toLocaleString("zh-CN")}`
    ]
  });
}

function getExportRecordBaseName(record) {
  const title = String(record?.title || "report")
    .replace(/[^\u4e00-\u9fa5a-zA-Z0-9_-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  const stamp = new Date(record?.createdAt || Date.now()).toISOString().replace(/[:T]/g, "-").slice(0, 16);
  return `${title || "report"}-${stamp}`;
}

async function exportSelectedRecord(kind) {
  const records = collectExportRecords();
  const selected = getSelectedExportRecord(records);
  if (!selected) {
    showToast("当前没有可导出的报告");
    return;
  }
  const html = getExportRecordDocumentHtml(selected);
  if (!html) {
    showToast("当前报告内容为空，无法导出");
    return;
  }
  const base = getExportRecordBaseName(selected);
  if (kind === "html") {
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    downloadBlob(blob, `${base}.html`);
    showToast("HTML 报告下载成功");
    return;
  }
  try {
    showToast("正在生成 PDF...");
    const response = await apiFetch("/api/export-report-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html, fileName: base })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "PDF 生成失败");
    }
    const blob = await response.blob();
    downloadBlob(blob, `${base}.pdf`);
    showToast("PDF 报告下载成功");
  } catch (error) {
    showToast(error.message || "PDF 生成失败");
  }
}
