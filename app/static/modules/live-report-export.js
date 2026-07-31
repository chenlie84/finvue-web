// FinVue live analysis direct export helpers: current report, anchor snapshots, and progress insight.
// Kept as a classic script so existing inline handlers and export-center.js can reuse the global functions.

function getReportExportBaseName() {
  const reportType = getSelectedReportType();
  const stamp = new Date().toISOString().replace(/[:T]/g, "-").slice(0, 16);
  return `${reportType === "newbieInterview" ? "newbie-interview-report" : "anchor-evaluation-report"}-${stamp}`;
}

function getAnchorSnapshotExportBaseName(profile, snapshot) {
  const base = String(profile?.anchorName || "anchor-report").replace(/[^\u4e00-\u9fa5a-zA-Z0-9_-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
  const stamp = new Date(snapshot?.analyzedAt || Date.now()).toISOString().replace(/[:T]/g, "-").slice(0, 16);
  return `${base || "anchor-report"}-${stamp}`;
}

function setExportButtonLoading(kind, loading) {
  const isHtml = kind === "html";
  const target = isHtml ? els.htmlExportBtn : els.pdfExportBtn;
  if (!target) return;
  target.classList.toggle("disabled", loading);
  target.textContent = loading ? (isHtml ? "HTML 导出中..." : "PDF 生成中...") : (isHtml ? "HTML" : "PDF");
}

function getReportExportHtml() {
  if (state.lastMarkdown && isHtmlReportContent(state.lastMarkdown)) {
    return buildStandaloneHtmlReportDocument(state.lastMarkdown, getCurrentReportTitle());
  }
  const sourceWrap = els.liveResultWrap.cloneNode(true);
  sourceWrap.classList.add("visible");
  sourceWrap.classList.remove("generating");
  const shell = sourceWrap.querySelector(".live-result-shell");
  if (shell) shell.classList.remove("generating");
  sourceWrap.querySelectorAll(".panel-act").forEach((node) => node.remove());
  const reportHtml = sourceWrap.innerHTML;
  if (!reportHtml.trim()) {
    return "";
  }
  const headAssets = Array.from(document.head.querySelectorAll('style, link[rel="stylesheet"]'))
    .map((node) => node.outerHTML)
    .join("\n");
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>${getCurrentReportTitle()}</title>
${headAssets}
<style>
  html,body{height:auto !important;min-height:auto !important;overflow:visible !important;}
  body{margin:0;padding:28px 24px;background:var(--bg0);color:var(--text0);}
  .main-content{height:auto !important;min-height:auto !important;overflow:visible !important;padding:0 !important;}
  .app-body,.app-page,.sec,.panel{height:auto !important;min-height:auto !important;overflow:visible !important;}
  .live-result-wrap{min-height:auto !important;opacity:1 !important;transform:none !important;pointer-events:auto !important;}
  .live-result-shell{min-height:auto !important;}
  .panel-hd{display:none !important;}
  .report-skeleton{display:none !important;}
  @page { size: A4; margin: 12mm; }
  @media print {
    body{padding:0 !important;background:var(--bg0);}
  }
</style>
</head>
<body>
  <div class="main-content" style="padding:0;">${reportHtml}</div>
</body>
</html>`;
}

function getAnchorSnapshotExportHtml(profile, snapshot) {
  if (!profile || !snapshot?.markdown) return "";
  const snapshotModelLabel = snapshot.aiMeta?.providerLabel
    ? `${snapshot.aiMeta.providerLabel} / ${snapshot.aiMeta.model}`
    : snapshot.aiMeta?.model
      ? snapshot.aiMeta.model
      : state.lastAiMeta?.providerLabel
      ? `${state.lastAiMeta.providerLabel} / ${state.lastAiMeta.model}`
      : (state.lastAiMeta?.model || "后台路由");
  const title = REPORT_TYPE_META[snapshot.reportType]?.title || snapshot.reportType || "主播分析报告";
  return buildReportExportDocument(title, snapshot.markdown, {
    title: REPORT_TYPE_META[snapshot.reportType]?.title || snapshot.reportType || "主播分析报告",
    timestamp: new Date(snapshot.analyzedAt || Date.now()).toLocaleString("zh-CN"),
    model: snapshotModelLabel,
    badges: [
      `${profile.anchorName} 历史分析`,
      `生成时间 ${new Date(snapshot.analyzedAt || Date.now()).toLocaleString("zh-CN")}`,
      `模型 ${snapshotModelLabel}`
    ]
  });
}

function exportHtmlReport() {
  if (!state.lastMarkdown || !els.liveResult.innerHTML.trim()) {
    showToast("请先在直播分析页生成报告");
    return;
  }
  setExportButtonLoading("html", true);
  const html = getReportExportHtml();
  const a = document.createElement("a");
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  a.href = URL.createObjectURL(blob);
  a.download = `${getReportExportBaseName()}.html`;
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    setExportButtonLoading("html", false);
    showToast("HTML 报告下载成功");
  }, 300);
}

async function exportPdfReport() {
  if (!state.lastMarkdown || !els.liveResult.innerHTML.trim()) {
    showToast("请先在直播分析页生成报告");
    return;
  }
  try {
    setExportButtonLoading("pdf", true);
    await window.FinVueReportExport.exportPdf(apiFetch, {
      html: getReportExportHtml(),
      fileName: getReportExportBaseName()
    });
    showToast("PDF 报告下载成功");
  } catch (error) {
    showToast(error.message);
  } finally {
    setExportButtonLoading("pdf", false);
  }
}

async function exportCurrentAnchorSnapshotReport(kind) {
  const { profile, snapshot } = getCurrentAnchorSnapshot();
  if (!profile || !snapshot?.markdown) {
    showToast("请先点击一条历史报告");
    return;
  }
  const baseName = getAnchorSnapshotExportBaseName(profile, snapshot);
  const html = getAnchorSnapshotExportHtml(profile, snapshot);
  if (kind === "html") {
    const a = document.createElement("a");
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    a.href = URL.createObjectURL(blob);
    a.download = `${baseName}.html`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 300);
    showToast("历史报告 HTML 下载成功");
    return;
  }
  try {
    showToast("正在生成历史报告 PDF...");
    const response = await apiFetch("/api/export-report-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html, fileName: baseName })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "PDF 生成失败");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${baseName}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("历史报告 PDF 下载成功");
  } catch (error) {
    showToast(error.message);
  }
}

function getCurrentAnchorProgressInsightExportHtml() {
  const profile = state.anchorProfiles.find((item) => item.id === state.currentAnchorProfileId) || null;
  if (!profile) return "";
  const progressSummary = buildAnchorProgressSummary(profile);
  if (!progressSummary) return "";
  const progressInsightKey = getAnchorProgressInsightKey(profile, progressSummary);
  const progressInsight = progressInsightKey ? state.currentAnchorProgressInsights[progressInsightKey] || null : null;
  if (!progressInsight?.markdown) return "";
  return buildReportExportDocument(`${profile.anchorName} · 提升复盘`, progressInsight.markdown, {
    title: `${profile.anchorName} · 提升复盘`,
    timestamp: new Date(progressInsight.createdAt || Date.now()).toLocaleString("zh-CN"),
    model: progressInsight.aiMeta?.providerLabel
      ? `${progressInsight.aiMeta.providerLabel} / ${progressInsight.aiMeta.model}`
      : (progressInsight.aiMeta?.model || "后台路由"),
    badges: [
      "历史优化复盘",
      `生成时间 ${new Date(progressInsight.createdAt || Date.now()).toLocaleString("zh-CN")}`
    ]
  });
}

async function exportCurrentAnchorProgressInsight(kind) {
  const html = getCurrentAnchorProgressInsightExportHtml();
  if (!html) {
    showToast("请先生成 AI 提升总结");
    return;
  }
  const profile = state.anchorProfiles.find((item) => item.id === state.currentAnchorProfileId) || null;
  const progressSummary = profile ? buildAnchorProgressSummary(profile) : null;
  const progressInsightKey = progressSummary ? getAnchorProgressInsightKey(profile, progressSummary) : "";
  const progressInsight = progressInsightKey ? state.currentAnchorProgressInsights[progressInsightKey] || null : null;
  const base = `${String(profile?.anchorName || "anchor-progress").replace(/[^\u4e00-\u9fa5a-zA-Z0-9_-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "") || "anchor-progress"}-improvement-${new Date(progressInsight?.createdAt || Date.now()).toISOString().replace(/[:T]/g, "-").slice(0, 16)}`;
  if (kind === "html") {
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    downloadBlob(blob, `${base}.html`);
    showToast("AI 提升总结 HTML 下载成功");
    return;
  }
  try {
    const response = await apiFetch("/api/export-report-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        html,
        filename: `${base}.pdf`
      })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "PDF 导出失败");
    }
    const blob = await response.blob();
    downloadBlob(blob, `${base}.pdf`);
    showToast("AI 提升总结 PDF 下载成功");
  } catch (error) {
    showToast(error.message || "PDF 导出失败");
  }
}

function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 300);
}
