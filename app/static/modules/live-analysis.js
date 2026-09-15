// FinVue live analysis request, streaming status, and report rendering helpers.
(function () {
function sanitizeProgressInsightMarkdown(markdown) {
  const text = String(markdown || "").trim();
  if (!text) return "";
  const normalized = text.replace(/\r/g, "");
  const firstMeaningfulLine = normalized
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line && line.length >= 8);
  if (!firstMeaningfulLine) return normalized;
  const firstIndex = normalized.indexOf(firstMeaningfulLine);
  const secondIndex = normalized.indexOf(firstMeaningfulLine, firstIndex + firstMeaningfulLine.length);
  if (secondIndex > 0) {
    const suffix = normalized.slice(secondIndex, secondIndex + 240);
    if (/已经改善|仍待优化|下次训练建议|总体判断/.test(suffix)) {
      return normalized.slice(0, secondIndex).trim();
    }
  }
  return normalized;
}

function renderLiveReport(markdown) {
  const now = new Date().toLocaleString("zh-CN");
  const title = getCurrentReportTitle();
  const modelLabel = state.lastAiMeta?.providerLabel
    ? `${state.lastAiMeta.providerLabel} / ${state.lastAiMeta.model}`
    : (state.lastAiMeta?.model || "后台路由");

  // 直接渲染报告，不依赖 buildReportShellHtml，避免 CSS 层级冲突
  // 用 markdownToReportHtml 生成内容，再用 DOM 强制修复宽度
  const bodyHtml = markdownToReportHtml(stripLeadingDuplicateReportTitle(markdown));

  els.liveResult.innerHTML = `
    <div style="width:100%;max-width:100%;box-sizing:border-box;padding:0;">
      <div style="width:100%;box-sizing:border-box;border-bottom:1px solid var(--color-border);padding-bottom:12px;margin-bottom:14px;">
        <h1 style="margin:0 0 8px;padding:0 0 0 10px;border-left:3px solid var(--color-accent);color:var(--color-text-0);font-size:18px;line-height:1.4;font-weight:600;box-sizing:border-box;">
          ${escapeInlineHtml(title)}
        </h1>
        <div style="display:flex;gap:8px;flex-wrap:wrap;box-sizing:border-box;">
          <span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border:1px solid var(--color-border-strong);border-radius:6px;font-size:12px;color:var(--color-text-2);box-sizing:border-box;">生成时间 ${now}</span>
          <span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border:1px solid var(--color-border-strong);border-radius:6px;font-size:12px;color:var(--color-text-2);box-sizing:border-box;">模型 ${modelLabel}</span>
        </div>
      </div>
      <div id="liveReportBodyContent">${bodyHtml}</div>
    </div>
  `;

  // 强制修复所有子元素的 width，防止 AI 返回的 HTML 带固定宽度
  forceFullWidthOnChildren(els.liveResult);

  // 把报告 shadow host 初始化为 shadow DOM,实现无滚动条、主题跟随
  els.liveResult.querySelectorAll(".ai-html-report-shadow").forEach(attachReportShadow);

  updateEvaluationTags(markdown);
}

// 递归强制将所有表格和容器元素设为 width:100%
function forceFullWidthOnChildren(container) {
  if (!container) return;
  const targets = container.querySelectorAll("table, div, section, article");
  targets.forEach(function(el) {
    el.style.width = "100%";
    el.style.maxWidth = "100%";
    el.style.boxSizing = "border-box";
  });
}

let runProgressStartedAt = 0;
let runProgressEstimateSec = 45;

function updateLiveAnalysisNavBadge(status = state.liveAnalysisNavStatus) {
  state.liveAnalysisNavStatus = status || "";
  if (!els.liveAnalysisNavBadge) return;
  els.liveAnalysisNavBadge.classList.remove("running", "done", "error");
  if (!status) {
    els.liveAnalysisNavBadge.textContent = "";
    els.liveAnalysisNavBadge.style.display = "none";
    return;
  }
  const labelMap = { running: "进行中", done: "已完成", error: "失败" };
  els.liveAnalysisNavBadge.textContent = labelMap[status] || "";
  els.liveAnalysisNavBadge.classList.add(status);
  els.liveAnalysisNavBadge.style.display = "inline-flex";
}

function setRunProgress(percent, label, note) {
  const safePercent = Math.max(0, Math.min(100, percent));
  els.runProgressCard.classList.add("active");
  els.runProgressFill.style.width = `${safePercent}%`;
  if (label) els.runProgressLabel.textContent = label;
  if (note) els.runProgressNote.textContent = note;
  const elapsedSec = runProgressStartedAt ? Math.max(0, Math.round((Date.now() - runProgressStartedAt) / 1000)) : 0;
  if (safePercent >= 100) {
    els.runProgressEta.textContent = "即将完成";
    return;
  }
  const remaining = Math.max(3, runProgressEstimateSec - elapsedSec);
  els.runProgressEta.textContent = `预计剩余 ${remaining}s`;
}

function estimateRunSeconds() {
  const transcript = mergeTextInputs(state.fileData.ts, els.tsText.value);
  const resume = (els.rsText.value.trim() || state.fileData.rs || "");
  const totalChars = transcript.length + resume.length;
  return Math.max(25, Math.min(180, 28 + Math.round(totalChars / 260)));
}

function showLiveResultGenerating() {
  els.liveResultWrap.classList.add("visible", "generating");
  els.liveResultShell.classList.add("generating");
  els.liveResult.innerHTML = '<div style="color:var(--color-text-2);font-size:13px;padding:20px 0;">正在生成报告内容，请稍候…</div>';
  els.evalTagRow.style.display = "none";
  els.evalTagRow.innerHTML = "";
}

function showLiveResultReady() {
  els.liveResultWrap.classList.add("visible");
  els.liveResultWrap.classList.remove("generating");
  els.liveResultShell.classList.remove("generating");
}

function startRunProgress() {
  runProgressStartedAt = Date.now();
  runProgressEstimateSec = estimateRunSeconds();
  updateLiveAnalysisNavBadge("running");
  setRunProgress(6, "正在整理输入内容", "检查逐字稿、热点和提示词结构。");
  showLiveResultGenerating();
}

function finishRunProgress(success = true, message = "") {
  updateLiveAnalysisNavBadge(success ? "done" : "error");
  setRunProgress(100, success ? "分析完成" : "分析中断", message || (success ? "报告已生成，可继续查看和复制。" : "本次分析未完成，请检查提示后重试。"));
  setTimeout(() => {
    els.runProgressCard.classList.remove("active");
    els.runProgressFill.style.width = "0%";
  }, 1400);
}

function resetBatchRunResults() {
  // 简化：批量队列已下线，保留入口避免外部旧引用报错
  state.batchRunResults = [];
  state.currentBatchResultId = "";
}

function renderBatchRunResults() {
  // 简化：批量结果列表已下线
  return;
}

function openBatchRunResult(resultId) {
  const safeId = decodeURIComponent(String(resultId || ""));
  const item = (Array.isArray(state.batchRunResults) ? state.batchRunResults : []).find((entry) => entry.id === safeId) || null;
  if (!item) return;
  state.currentBatchResultId = safeId;
  renderBatchRunResults();
  if (item.status === "success") {
    state.lastMarkdown = item.markdown || "";
    renderLiveReport(item.markdown || "未获得分析结果");
  } else {
    renderLiveReport([
      "## 生成失败",
      "",
      `当前文件：${item.fileName || item.label || "未命名文件"}`,
      "",
      `错误信息：${item.errorMessage || "生成失败"}`
    ].join("\n"));
  }
  showLiveResultReady();
}

function pushBatchRunResult(result) {
  const list = Array.isArray(state.batchRunResults) ? state.batchRunResults.slice() : [];
  list.push(result);
  state.batchRunResults = list;
  state.currentBatchResultId = result.id;
  renderBatchRunResults();
}

async function runLiveStream(payload) {
  const response = await apiFetch("/api/generate-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new Error(errorPayload.error || "生成失败");
  }
  if (!response.body) {
    throw new Error("当前浏览器不支持流式读取");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let markdown = "";
  let sawChunk = false;
  let aiMeta = null;

  const updateStreamProgress = (chars) => {
    const elapsedSec = Math.max(1, Math.round((Date.now() - runProgressStartedAt) / 1000));
    const speed = Math.max(1, Math.round(chars / elapsedSec));
    const charProgress = Math.min(0.72, Math.log10(chars + 10) / 5);
    const timeProgress = Math.min(0.2, elapsedSec / Math.max(25, runProgressEstimateSec * 1.4));
    const percent = Math.min(94, 22 + Math.round((charProgress + timeProgress) * 100));
    setRunProgress(percent, "正在生成分析报告", `已生成 ${chars} 字，当前约 ${speed} 字/秒`);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let event;
      try {
        event = JSON.parse(trimmed);
      } catch {
        continue;
      }
      if (event.type === "status") {
        if (event.stage === "connecting") {
          setRunProgress(12, "正在连接模型", event.message || "模型服务连接中");
        } else if (event.stage === "accepted") {
          setRunProgress(18, "模型已受理请求", event.message || "正在等待首段内容返回");
        } else if (event.stage === "streaming") {
          setRunProgress(20, "模型已开始输出", event.message || "正在逐步生成报告正文");
          showLiveResultGenerating();
        }
        continue;
      }
      if (event.aiMeta) {
        aiMeta = event.aiMeta;
        state.lastAiMeta = aiMeta;
      }
      if (event.type === "chunk") {
        sawChunk = true;
        markdown += event.delta || "";
        state.lastMarkdown = markdown;
        updateStreamProgress(markdown.length);
        continue;
      }
      if (event.type === "done") {
        const finalMarkdown = event.markdown || markdown;
        state.lastMarkdown = finalMarkdown;
        state.lastAiMeta = event.aiMeta || aiMeta || null;
        renderLiveReport(finalMarkdown || "未获得分析结果");
        showLiveResultReady();
        return finalMarkdown;
      }
      if (event.type === "error") {
        const providerPart = event.providerLabel ? `路由：${event.providerLabel}${event.model ? ` / ${event.model}` : ""}` : "";
        throw new Error([event.error || "流式生成失败", providerPart, event.hint || ""].filter(Boolean).join("｜"));
      }
    }
  }

  if (sawChunk) {
    renderLiveReport(markdown || "未获得分析结果");
    showLiveResultReady();
    return markdown;
  }
  throw new Error("模型未返回有效内容");
}

async function runLiveOnce(payload) {
  const response = await apiFetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const attempts = Array.isArray(result.attempts) ? result.attempts : [];
    const attemptSummary = attempts.length
      ? `已尝试：${attempts.map((item) => `${item.providerLabel}/${item.model}：${item.error}`).join("；")}`
      : "";
    throw new Error([result.error || result.detail || result.message || "生成失败", attemptSummary].filter(Boolean).join("｜"));
  }
  const markdown = result.markdown || "";
  state.lastAiMeta = result.aiMeta || null;
  state.lastMarkdown = markdown;
  renderLiveReport(markdown || "未获得分析结果");
  showLiveResultReady();
  return markdown;
}

async function refreshLiveAiRoutes() {
  const localProviders = typeof getAiProviders === "function"
    ? getAiProviders().map(normalizeAiProviderDraft).filter((item) => item.enabled)
    : (Array.isArray(state.globalSettings?.aiProviders) ? state.globalSettings.aiProviders.filter((item) => item?.enabled !== false) : []);
  if (localProviders.length) return localProviders;
  const response = await apiFetch("/api/settings");
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || payload.detail || "读取 AI 路由配置失败");
  state.globalSettings = payload.settings || state.globalSettings || {};
  if (typeof renderAiRouteSummary === "function") renderAiRouteSummary();
  const providers = typeof getAiProviders === "function"
    ? getAiProviders().map(normalizeAiProviderDraft).filter((item) => item.enabled)
    : (Array.isArray(state.globalSettings.aiProviders) ? state.globalSettings.aiProviders.filter((item) => item?.enabled !== false) : []);
  if (!providers.length) {
    throw new Error("当前账号未读取到启用的 AI 路由。请确认已在管理员账号保存配置，并退出后重新登录。");
  }
  return providers;
}

function shouldFallbackToNonStream(error) {
  const message = String(error?.message || "");
  return [
    "模型长时间未开始输出",
    "模型长时间未继续返回内容",
    "当前浏览器不支持流式读取",
    "模型未返回有效内容"
  ].some((keyword) => message.includes(keyword));
}

function buildLivePrompt() {
  // 单一提示词模式：用户在 taskPrompt 中编辑完整提示词
  const mainPrompt = normalizeLiveAnalysisPrompt(els.taskPrompt.value.trim());
  const transcript = mergeTextInputs(state.fileData.ts, els.tsText.value);
  const hotTopics = state.hotArr.length ? state.hotArr.join("、") : "";
  const reportType = getSelectedReportType();
  const resume = reportType === "newbieInterview" ? (els.rsText.value.trim() || state.fileData.rs || "") : "";
  const reportMeta = REPORT_TYPE_META[reportType] || REPORT_TYPE_META.anchorEvaluation;
  const transcriptLabel = reportType === "newbieInterview" ? "【面试逐字稿】" : "【逐字稿】";
  const resumeLabel = reportType === "newbieInterview" ? "【候选人简历】" : "【主播简历】";
  const transcriptNotes = els.transcriptNotes?.value.trim() || "";
  const evaluationNotes = els.evaluationNotes?.value.trim() || "";
  const metricsRawText = els.metricsRawText.value.trim();

  const htmlFormatGuard = [
    "【输出格式约束】",
    "如果上面的提示词要求输出 HTML，请输出可直接渲染的 HTML 报告；可以包含 <style>，但不要包含 <script>。",
    "HTML 报告要使用深色主题或自带完整配色，不能只输出解释文字。",
    "不要把 HTML 放进 ```html 代码块里；直接输出 HTML 内容即可。",
    "如果上面的提示词没有要求 HTML，则输出 Markdown。"
  ].join("\n");

  return [
    "请严格根据以下唯一提示生成结果，只输出一份最终完整报告，不要重复输出。",
    mainPrompt ? `【分析提示词】\n${mainPrompt}` : "",
    htmlFormatGuard,
    hotTopics ? `【外部热点】\n${hotTopics}` : "",
    reportType === "anchorEvaluation" && evaluationNotes ? `【补充背景说明】\n${evaluationNotes}` : "",
    reportType === "anchorEvaluation" && metricsRawText ? `【直播数据原始摘要】\n${metricsRawText}` : "",
    resume ? `${resumeLabel}\n${resume}` : "",
    `${transcriptLabel}\n${transcript}`,
    transcriptNotes ? `【补充备注】\n${transcriptNotes}` : "",
    "再次强调：最终只允许输出一份完整报告。"
  ].filter(Boolean).join("\n\n");
}

function buildLiveSystemPrompt() {
  return "你是一个严格执行单一提示词的报告生成助手。提示词要求 HTML 时直接输出可渲染的 HTML 报告；不要拆成多版输出，不要重复报告，不要补写第二份结果。";
}

async function executeSingleLiveRun() {
  await refreshLiveAiRoutes();
  // 获取选择的模型
  const modelSelect = document.getElementById("live-model-select");
  const selectedModelId = modelSelect?.value || null;

  const requestPayload = {
    systemPrompt: buildLiveSystemPrompt() || "你是一位专业的投顾直播内容分析专家。",
    userPrompt: buildLivePrompt(),
    model: selectedModelId
  };
  setRunProgress(18, "模型已受理请求", "当前路由为非流式生成，完成后会一次性返回报告。");
  state.lastMarkdown = await runLiveOnce(requestPayload);
  showLiveResultReady();
  await persistCurrentAnalysisBundle(state.lastMarkdown);
}

async function runLive() {
  const transcript = els.tsText.value.trim() || state.fileData.ts || "";
  const resume = els.rsText.value.trim() || state.fileData.rs || "";
  const reportType = getSelectedReportType();
  if (state.fileLoading.ts || state.fileLoading.rs) {
    showToast("文件仍在读取中，请稍等几秒再开始分析");
    return;
  }
  if (!transcript) {
    if (state.fileMeta.ts && !state.fileData.ts && !els.tsText.value.trim()) {
      showToast("你已上传逐字稿文件，但系统未提取到文本，请改用 txt/docx 或直接粘贴逐字稿");
      return;
    }
    showToast(reportType === "newbieInterview" ? "请先上传或粘贴面试逐字稿" : "请先上传或粘贴逐字稿");
    return;
  }
  if (reportType === "newbieInterview" && !resume) {
    if (state.fileMeta.rs && !state.fileData.rs && !els.rsText.value.trim()) {
      showToast("你已上传简历文件，但系统未提取到文本，请改用 txt/docx 或直接粘贴简历内容");
      return;
    }
    showToast("新人面试分析必须同时提供候选人简历");
    return;
  }
  // 简化：每次只分析当前上传的 1 份逐字稿；如需分析下一份，重新上传即可
  state.transcriptBatchQueue = [];
  try {
    els.runBtn.disabled = true;
    els.runBtn.innerHTML = '<span class="spinner"></span> 分析中…';
    state.lastAiMeta = null;
    resetBatchRunResults();
    startRunProgress();
    await executeSingleLiveRun();
    finishRunProgress(true, "报告已生成，可继续查看和复制。");
    showToast("分析完成");
  } catch (error) {
    const friendlyMessage = String(error?.message || "生成失败");
    renderLiveReport([
      "## 生成失败",
      "",
      `错误信息：${friendlyMessage}`,
      "",
      "排查建议：",
      "- 检查后端服务是否仍在运行",
      "- 确认 API Key 和模型名称可用",
      "- 如果刚修改过代码，先刷新页面后再试",
      "- 如果是长内容，先重试一次，观察是否切换到兼容模式"
    ].join("\n"));
    showLiveResultReady();
    finishRunProgress(false, friendlyMessage);
    showToast(friendlyMessage);
  } finally {
    els.runBtn.disabled = false;
    els.runBtn.innerHTML = "▶ 开始 AI 分析";
  }
}

async function copyLiveResult() {
  if (!state.lastMarkdown) {
    showToast("暂无可复制内容");
    return;
  }
  await navigator.clipboard.writeText(state.lastMarkdown);
  showToast("已复制到剪贴板");
}

  window.sanitizeProgressInsightMarkdown = sanitizeProgressInsightMarkdown;
  window.refreshLiveAiRoutes = refreshLiveAiRoutes;
  window.renderLiveReport = renderLiveReport;
  window.startRunProgress = startRunProgress;
  window.finishRunProgress = finishRunProgress;
  window.runLiveStream = runLiveStream;
  window.runLiveOnce = runLiveOnce;
  window.shouldFallbackToNonStream = shouldFallbackToNonStream;
  window.buildLivePrompt = buildLivePrompt;
  window.buildLiveSystemPrompt = buildLiveSystemPrompt;
  window.executeSingleLiveRun = executeSingleLiveRun;
  window.runLive = runLive;
  window.copyLiveResult = copyLiveResult;
})();
