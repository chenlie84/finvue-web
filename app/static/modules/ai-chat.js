// FinVue AI chat and quick assistant drawer.
// This file intentionally exposes legacy global functions because app/index.html still uses inline handlers.
// ══════════════ AI 对话功能 ══════════════
let currentChatSession = null;
let currentPromptContent = "";
let currentKnowledgeId = null;
let currentAiModel = "";

async function initAiChat() {
  // 加载提示词模板
  try {
    const promptsRes = await fetch("/api/ai-chat/prompts", { credentials: "include" });
    const prompts = await promptsRes.json();
    const select = document.getElementById("ai-prompt-select");
    select.innerHTML = '<option value="">选择提示词模板...</option>';
    prompts.forEach(p => {
      select.innerHTML += `<option value="${p.id}" data-content="${escapeHtml(p.content || '')}">${escapeHtml(p.name)}</option>`;
    });
  } catch(e) { console.error("加载提示词失败", e); }

  // 加载 AI 提供商（模型）列表
  try {
    const settingsRes = await fetch("/api/settings", { credentials: "include" });
    const settings = await settingsRes.json();
    const providers = settings.aiProviders || [];
    const modelSelect = document.getElementById("ai-model-select");
    modelSelect.innerHTML = '<option value="">使用默认模型</option>';
    providers.filter(p => p.enabled).sort((a, b) => (a.priority || 0) - (b.priority || 0)).forEach(p => {
      const label = p.label || p.model || "未知模型";
      modelSelect.innerHTML += `<option value="${p.id}">${escapeHtml(label)} (${escapeHtml(p.model)})</option>`;
    });
  } catch(e) { console.error("加载模型列表失败", e); }

  // 加载知识库
  try {
    const kbRes = await fetch("/api/ai-chat/knowledge", { credentials: "include" });
    const kbList = await kbRes.json();
    const select = document.getElementById("ai-knowledge-select");

    // 分离普通知识库和主播蒸馏库
    const normalKb = kbList.filter(k => !k.is_distill);
    const distillKb = kbList.filter(k => k.is_distill);

    let html = '<option value="">选择知识库...</option>';

    // 普通知识库
    if (normalKb.length) {
      html += '<optgroup label="上传的知识库">';
      normalKb.forEach(k => {
        html += `<option value="${k.id}">${escapeHtml(k.name)} (${k.file_type})</option>`;
      });
      html += '</optgroup>';
    }

    // 主播蒸馏库
    if (distillKb.length) {
      html += '<optgroup label="主播蒸馏库">';
      distillKb.forEach(k => {
        const badge = k.has_profile ? '[画像]' : '';
        const countBadge = k.transcript_count > 0 ? `逐字稿${k.transcript_count}` : '';
        html += `<option value="${k.id}" style="color:var(--gold);">${escapeHtml(k.name.replace('主播蒸馏：', ''))} ${badge} ${countBadge}</option>`;
      });
      html += '</optgroup>';
    }

    select.innerHTML = html;
  } catch(e) { console.error("加载知识库失败", e); }

  // 加载会话列表
  loadChatSessions();
}

async function loadChatSessions() {
  try {
    const res = await fetch("/api/ai-chat/sessions", { credentials: "include" });
    const sessions = await res.json();
    const container = document.getElementById("ai-chat-sessions");
    if (!sessions.length) {
      container.innerHTML = '<div class="muted" style="padding:12px;font-size:12px;">暂无对话历史</div>';
      return;
    }
    container.innerHTML = sessions.map(s => `
      <div class="nav-item ${currentChatSession === s.session_id ? 'active' : ''}" onclick="selectChatSession('${s.session_id}')" style="font-size:12px;padding:8px 10px;">
        ${escapeHtml(s.title || '新对话')}
      </div>
    `).join('');
  } catch(e) { console.error("加载会话失败", e); }
}

async function selectChatSession(sessionId) {
  currentChatSession = sessionId;
  loadChatSessions();
  loadChatMessages(sessionId);
}

async function loadChatMessages(sessionId) {
  try {
    const res = await fetch(`/api/ai-chat/messages/${sessionId}`, { credentials: "include" });
    const messages = await res.json();
    const container = document.getElementById("ai-chat-messages");
    if (!messages.length) {
      container.innerHTML = '<div class="ai-msg ai-msg-assistant" style="max-width:80%;"><div style="font-size:12px;color:var(--text1);margin-bottom:4px;">AI 助手</div><div style="background:var(--bg2);padding:12px;border-radius:var(--r);">开始新对话吧！</div></div>';
      return;
    }
    container.innerHTML = messages.map(m => `
      <div class="ai-msg ${m.role === 'user' ? 'ai-msg-user' : 'ai-msg-assistant'}" style="max-width:80%;align-self:${m.role === 'user' ? 'flex-end' : 'flex-start'};">
        <div style="font-size:12px;color:var(--text1);margin-bottom:4px;">${m.role === 'user' ? '你' : 'AI 助手'}</div>
        <div class="${m.role === 'user' ? 'ai-msg-user-content' : 'ai-msg-assistant-content'}">${m.role === 'user' ? escapeHtml(m.content) : markdownToReportHtml(m.content)}</div>
      </div>
    `).join('');
    container.scrollTop = container.scrollHeight;
  } catch(e) { console.error("加载消息失败", e); }
}

async function sendAiChat() {
  const input = document.getElementById("ai-chat-input");
  const message = input.value.trim();
  if (!message) return;

  const btn = document.getElementById("ai-chat-send-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  const promptSelect = document.getElementById("ai-prompt-select");
  const selectedPrompt = promptSelect.options[promptSelect.selectedIndex];
  const systemPrompt = selectedPrompt?.dataset?.content || "";

  const knowledgeSelect = document.getElementById("ai-knowledge-select");
  const knowledgeId = knowledgeSelect.value || null;

  // 获取选择的模型
  const modelSelect = document.getElementById("ai-model-select");
  const selectedModelId = modelSelect.value || null;

  // 添加用户消息到界面
  const container = document.getElementById("ai-chat-messages");
  container.innerHTML += `
    <div class="ai-msg ai-msg-user" style="max-width:80%;align-self:flex-end;">
      <div style="font-size:12px;color:var(--text1);margin-bottom:4px;">你</div>
      <div class="ai-msg-user-content">${escapeHtml(message)}</div>
    </div>
  `;
  container.innerHTML += `
    <div class="ai-msg ai-msg-assistant" style="max-width:80%;">
      <div style="font-size:12px;color:var(--text1);margin-bottom:4px;">AI 助手</div>
      <div class="ai-msg-assistant-content"><span class="spinner"></span> 思考中...</div>
    </div>
  `;
  container.scrollTop = container.scrollHeight;
  input.value = "";

  try {
    const res = await fetch("/api/ai-chat/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        sessionId: currentChatSession,
        message: message,
        systemPrompt: systemPrompt,
        knowledgeBaseId: knowledgeId,
        model: selectedModelId
      })
    });
    const data = await res.json();

    if (data.sessionId && !currentChatSession) {
      currentChatSession = data.sessionId;
      loadChatSessions();
    }

    // 更新AI回复（使用 Markdown 渲染）
    const lastAssistant = container.querySelectorAll(".ai-msg-assistant");
    const lastMsg = lastAssistant[lastAssistant.length - 1];
    lastMsg.querySelector(".ai-msg-assistant-content").innerHTML = markdownToReportHtml(data.message || "无回复");
    container.scrollTop = container.scrollHeight;
  } catch(e) {
    showToast("发送失败: " + e.message);
  }

  btn.disabled = false;
  btn.innerHTML = "发送";
}

async function createNewChat() {
  currentChatSession = null;
  document.getElementById("ai-chat-messages").innerHTML = '<div class="ai-msg ai-msg-assistant" style="max-width:80%;"><div style="font-size:12px;color:var(--text1);margin-bottom:4px;">AI 助手</div><div style="background:var(--bg2);padding:12px;border-radius:var(--r);">你好！我是 AI 助手，有什么可以帮你的吗？</div></div>';
  loadChatSessions();
}

// 提示词相关
function loadPromptContent() {
  const select = document.getElementById("ai-prompt-select");
  const option = select.options[select.selectedIndex];
  currentPromptContent = option?.dataset?.content || "";
}

function editCurrentPrompt() {
  const select = document.getElementById("ai-prompt-select");
  if (!select.value) {
    showToast("请先选择一个提示词模板");
    return;
  }
  document.getElementById("ai-system-prompt").value = currentPromptContent;
  showAiChatSettings();
}

async function managePrompts() {
  document.getElementById("ai-prompt-modal").style.display = "flex";
  loadPromptList();
}

function closePromptModal() {
  document.getElementById("ai-prompt-modal").style.display = "none";
}

async function loadPromptList() {
  try {
    const res = await fetch("/api/ai-chat/prompts", { credentials: "include" });
    const prompts = await res.json();
    const container = document.getElementById("ai-prompt-list");
    container.innerHTML = prompts.map(p => `
      <div style="padding:12px;background:var(--bg2);border-radius:var(--r);border:1px solid var(--border);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <div style="font-weight:500;">${escapeHtml(p.name)}</div>
          <div style="display:flex;gap:6px;">
            ${!p.is_system ? `<button class="btn btn-outline-sm" onclick="deletePrompt(${p.id})" style="font-size:10px;padding:2px 6px;">删除</button>` : ''}
          </div>
        </div>
        <div style="font-size:11px;color:var(--text1);line-height:1.5;">${escapeHtml(p.description || p.content?.substring(0, 100) || '')}</div>
      </div>
    `).join('');
  } catch(e) { console.error("加载提示词列表失败", e); }
}

async function deletePrompt(id) {
  if (!confirm("确定删除此提示词模板？")) return;
  try {
    await fetch(`/api/ai-chat/prompts/${id}`, { method: "DELETE", credentials: "include" });
    showToast("删除成功");
    loadPromptList();
  } catch(e) { showToast("删除失败"); }
}

function showCreatePrompt() {
  const name = prompt("请输入模板名称：");
  if (!name) return;
  const content = prompt("请输入提示词内容：");
  if (!content) return;
  fetch("/api/ai-chat/prompts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ name: name, content: content, category: "custom" })
  }).then(r => r.json()).then(() => {
    showToast("创建成功");
    loadPromptList();
  });
}

// 知识库相关
function selectKnowledgeBase() {
  const select = document.getElementById("ai-knowledge-select");
  currentKnowledgeId = select.value || null;
}

async function manageKnowledge() {
  document.getElementById("ai-knowledge-modal").style.display = "flex";
  loadKnowledgeList();
}

function closeKnowledgeModal() {
  document.getElementById("ai-knowledge-modal").style.display = "none";
}

async function loadKnowledgeList() {
  try {
    const res = await fetch("/api/ai-chat/knowledge", { credentials: "include" });
    const list = await res.json();
    const container = document.getElementById("ai-knowledge-list");
    if (!list.length) {
      container.innerHTML = '<div class="muted" style="padding:12px;font-size:12px;">暂无知识库</div>';
      return;
    }
    container.innerHTML = list.map(k => `
      <div style="padding:12px;background:var(--bg2);border-radius:var(--r);border:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div style="font-weight:500;font-size:13px;">${escapeHtml(k.name)}</div>
          <div style="font-size:11px;color:var(--text1);">${k.file_type?.toUpperCase()} · ${k.file_size ? Math.round(k.file_size/1024) + 'KB' : ''}</div>
        </div>
        <button class="btn btn-danger-sm" onclick="deleteKnowledge(${k.id})" style="font-size:10px;padding:4px 8px;">删除</button>
      </div>
    `).join('');
  } catch(e) { console.error("加载知识库失败", e); }
}

async function deleteKnowledge(id) {
  if (!confirm("确定删除此知识库？")) return;
  try {
    await fetch(`/api/ai-chat/knowledge/${id}`, { method: "DELETE", credentials: "include" });
    showToast("删除成功");
    loadKnowledgeList();
  } catch(e) { showToast("删除失败"); }
}

async function uploadKnowledgeFile(input) {
  const file = input.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  showToast("上传中...");
  try {
    const res = await fetch("/api/ai-chat/knowledge", {
      method: "POST",
      credentials: "include",
      body: formData
    });
    const data = await res.json();
    if (data.id) {
      showToast("上传成功");
      loadKnowledgeList();
    } else {
      showToast("上传失败");
    }
  } catch(e) {
    showToast("上传失败: " + e.message);
  }
  input.value = "";
}

// 设置弹窗
function showAiChatSettings() {
  document.getElementById("ai-chat-settings-modal").style.display = "flex";
  document.getElementById("ai-system-prompt").value = currentPromptContent;
}

function closeAiChatSettings() {
  document.getElementById("ai-chat-settings-modal").style.display = "none";
}

function saveAiChatSettings() {
  const prompt = document.getElementById("ai-system-prompt").value;
  currentPromptContent = prompt;
  showToast("设置已保存");
  closeAiChatSettings();
}

// 侧边栏快速对话
function openAiDrawer() {
  document.getElementById("ai-sidebar-drawer").style.right = "0";
  document.getElementById("ai-sidebar-overlay").style.display = "block";
}

function closeAiDrawer() {
  document.getElementById("ai-sidebar-drawer").style.right = "-380px";
  document.getElementById("ai-sidebar-overlay").style.display = "none";
}

async function sendAiDrawerMessage() {
  const input = document.getElementById("ai-drawer-input");
  const message = input.value.trim();
  if (!message) return;

  const container = document.getElementById("ai-drawer-messages");
  container.innerHTML += `<div style="background:var(--gold-dim);padding:8px 12px;border-radius:var(--r);font-size:13px;align-self:flex-end;max-width:80%;">${escapeHtml(message)}</div>`;
  container.innerHTML += `<div id="drawer-loading" style="background:var(--bg2);padding:8px 12px;border-radius:var(--r);font-size:13px;"><span class="spinner"></span> 思考中...</div>`;
  container.scrollTop = container.scrollHeight;
  input.value = "";

  try {
    const res = await fetch("/api/ai-chat/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        messages: [{ role: "user", content: message }]
      })
    });
    const data = await res.json();
    const loading = document.getElementById("drawer-loading");
    if (loading) loading.remove();
    container.innerHTML += `<div style="background:var(--bg2);padding:8px 12px;border-radius:var(--r);font-size:13px;white-space:pre-wrap;">${escapeHtml(data.choices?.[0]?.message?.content || '无回复')}</div>`;
    container.scrollTop = container.scrollHeight;
  } catch(e) {
    const loading = document.getElementById("drawer-loading");
    if (loading) loading.remove();
    container.innerHTML += `<div style="color:var(--red);font-size:12px;">错误: ${e.message}</div>`;
  }
}

function openFullAiChat() {
  closeAiDrawer();
  showSec('ai-chat');
}

// 添加AI助手按钮到顶部导航
function addAiChatButton() {
  const topnav = document.querySelector(".topnav");
  if (!topnav) return;
  // 检查是否已存在
  if (document.getElementById("ai-chat-toggle-btn")) return;
  const btn = document.createElement("button");
  btn.id = "ai-chat-toggle-btn";
  btn.className = "btn btn-outline";
  btn.style.cssText = "font-size:12px;padding:5px 10px;";
  btn.innerHTML = "AI";
  btn.onclick = openAiDrawer;
  topnav.insertBefore(btn, topnav.lastElementChild);
}
