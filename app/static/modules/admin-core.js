// FinVue admin shell, dashboard summary, and user-permission management.
// Legacy inline handlers still call these names, so this classic script keeps them global.

function getLatestAdminTimestamp() {
  const candidates = [
    ...state.anchorProfiles.map((item) => item.updatedAt || item.createdAt),
    ...state.transcriptEntries.map((item) => item.updatedAt || item.analyzedAt || item.createdAt),
    ...state.complianceEntries.map((item) => item.updatedAt || item.createdAt),
    ...state.caseEntries.map((item) => item.updatedAt || item.createdAt)
  ].filter(Boolean);
  if (!candidates.length) return "";
  return candidates.sort().slice(-1)[0];
}

function updateAdminDashboardSummary() {
  if (!els.adminUserCount) return;
  const userCount = state.adminUsers.length;
  const adminCount = state.adminUsers.filter((item) => item.role === "admin").length;
  const profilesCount = state.anchorProfiles.length;
  const transcriptCount = state.transcriptEntries.length;
  const complianceCount = state.complianceEntries.length;
  const caseCount = state.caseEntries.length;
  const highRiskCount = state.complianceEntries.filter((item) => {
    const level = String(item.level || "").toLowerCase();
    return level === "red" || level === "gray";
  }).length;
  const roleCount = Object.keys(getRoleDefinitions()).length;
  const taskCount = Object.keys(getTaskDefinitions()).length;
  const latestSync = getLatestAdminTimestamp();
  const latestProfile = [...state.anchorProfiles].sort((a, b) => String(b.updatedAt || b.createdAt || "").localeCompare(String(a.updatedAt || a.createdAt || "")))[0];
  const latestTranscript = [...state.transcriptEntries].sort((a, b) => String(b.analyzedAt || b.updatedAt || b.createdAt || "").localeCompare(String(a.analyzedAt || a.updatedAt || a.createdAt || "")))[0];
  const latestCompliance = [...state.complianceEntries].sort((a, b) => String(b.updatedAt || b.createdAt || "").localeCompare(String(a.updatedAt || a.createdAt || "")))[0];
  const latestCase = [...state.caseEntries].sort((a, b) => String(b.updatedAt || b.createdAt || "").localeCompare(String(a.updatedAt || a.createdAt || "")))[0];
  const providers = getAiProviders().map(normalizeAiProviderDraft);
  const enabledProviders = providers.filter((item) => item.enabled);
  // 安全设置每个元素（避免 null 报错）
  if (els.adminUserCount) els.adminUserCount.textContent = String(userCount);
  if (els.adminPromptCount) els.adminPromptCount.textContent = `${roleCount}/${taskCount}`;
  if (els.adminAssetCount) els.adminAssetCount.textContent = String(profilesCount + transcriptCount + complianceCount + caseCount);
  if (els.adminRiskCount) els.adminRiskCount.textContent = String(highRiskCount);
  if (els.adminProfilesCount) els.adminProfilesCount.textContent = String(profilesCount);
  if (els.adminTranscriptsCount) els.adminTranscriptsCount.textContent = String(transcriptCount);
  if (els.adminComplianceCount) els.adminComplianceCount.textContent = String(complianceCount);
  if (els.adminCaseCount) els.adminCaseCount.textContent = String(caseCount);
  if (els.adminAdminCount) els.adminAdminCount.textContent = String(adminCount);
  if (els.adminLatestSync) els.adminLatestSync.textContent = latestSync ? formatDateTime(latestSync) : "--";
  if (els.adminHotCount) els.adminHotCount.textContent = String(state.hotArr.length);
  if (els.adminReportFormatSummary) els.adminReportFormatSummary.textContent = els.reportFormat?.value?.trim() || "未设置";
  if (els.adminRiskSummary) els.adminRiskSummary.textContent = highRiskCount
    ? `当前共有 ${highRiskCount} 条灰区或红区话术沉淀，优先复查最近新增条目。`
    : "当前没有灰区或红区话术堆积。";
  if (els.adminAssetSummary) els.adminAssetSummary.textContent = `人物档案 ${profilesCount} 条，逐字稿 ${transcriptCount} 条，合规 ${complianceCount} 条，案例 ${caseCount} 条。`;
  if (els.adminPromptSummary) els.adminPromptSummary.textContent = `当前共维护 ${roleCount} 个角色项、${taskCount} 个任务项；热点 ${state.hotArr.length} 条。`;
  if (els.adminConfigSummary) els.adminConfigSummary.textContent = `已配置 ${providers.length} 条 AI 路由，其中启用 ${enabledProviders.length} 条；角色项 ${roleCount} 个，任务项 ${taskCount} 个，热点 ${state.hotArr.length} 条。保存后会同步影响当前工作台分析。`;
  if (els.adminProfileActivity) els.adminProfileActivity.textContent = latestProfile
    ? `${latestProfile.name || "未命名人物"} 最近一次快照时间：${formatDateTime(latestProfile.updatedAt || latestProfile.createdAt)}。`
    : "暂无人物档案更新。";
  if (els.adminTranscriptActivity) els.adminTranscriptActivity.textContent = latestTranscript
    ? `${latestTranscript.anchorName || "未命名逐字稿"} 最近沉淀于 ${formatDateTime(latestTranscript.analyzedAt || latestTranscript.updatedAt || latestTranscript.createdAt)}。`
    : "暂无逐字稿沉淀。";
  if (els.adminKnowledgeActivity) els.adminKnowledgeActivity.textContent = latestCompliance || latestCase
    ? `最近知识沉淀：${latestCompliance ? `合规 ${formatDateTime(latestCompliance.updatedAt || latestCompliance.createdAt)}` : ""}${latestCompliance && latestCase ? " / " : ""}${latestCase ? `案例 ${formatDateTime(latestCase.updatedAt || latestCase.createdAt)}` : ""}。`
    : "暂无合规或案例更新。";
  if (els.adminPageSub) els.adminPageSub.textContent = latestSync
    ? `系统运行状态 · 最后同步 ${formatDateTime(latestSync)}`
    : "系统运行状态 · 暂无本地沉淀数据";
  const adminRoleStats = document.getElementById("adminRoleStats");
  const adminRoleMatrix = document.getElementById("adminRoleMatrix");
  const adminLogsList = document.getElementById("adminLogsList");
  const adminApiOverview = document.getElementById("adminApiOverview");
  const adminApiHealthSummary = document.getElementById("adminApiHealthSummary");
  const adminBackupSummary = document.getElementById("adminBackupSummary");
  const adminMonitorRoutes = document.getElementById("adminMonitorRoutes");
  const adminMonitorAssets = document.getElementById("adminMonitorAssets");
  const adminMonitorRisks = document.getElementById("adminMonitorRisks");
  const adminMonitorSummary = document.getElementById("adminMonitorSummary");
  if (adminRoleStats) {
    adminRoleStats.innerHTML = `
      <div class="admin-role-card"><h4>管理员</h4><p>当前 ${adminCount} 个管理员账号，可管理用户、系统设置、API 路由和知识资产。</p></div>
      <div class="admin-role-card"><h4>普通用户</h4><p>当前 ${Math.max(userCount - adminCount, 0)} 个普通账号，主要执行直播分析、查看资料和沉淀库内容。</p></div>
    `;
  }
  if (adminRoleMatrix) {
    adminRoleMatrix.innerHTML = `
      <div class="admin-role-card"><h4>角色项</h4><p>当前维护 ${roleCount} 个角色项，角色侧重由工作台高级设置控制。</p></div>
      <div class="admin-role-card"><h4>任务项</h4><p>当前维护 ${taskCount} 个任务项，主播评价体系与新人面试分析会走不同任务链路。</p></div>
      <div class="admin-role-card"><h4>全局权限边界</h4><p>管理员负责后台与路由池；普通用户专注分析、资料库、逐字稿库、合规库和案例库。</p></div>
    `;
  }
  if (adminLogsList) {
    const events = buildAdminRecentEvents().slice(0, 10);
    adminLogsList.innerHTML = events.length
      ? events.map((item) => `
        <div class="admin-log-item">
          <div class="admin-log-meta"><span>${escapeHtml(item.module)}</span><span>${escapeHtml(item.timeLabel)}</span></div>
          <div class="admin-log-title">${escapeHtml(item.title)}</div>
          <div class="admin-log-desc">${escapeHtml(item.description)}</div>
        </div>
      `).join("")
      : `<div class="admin-log-item"><div class="admin-log-title">暂无操作记录</div><div class="admin-log-desc">当前本地还没有足够的沉淀记录用于生成后台日志时间线。</div></div>`;
  }
  if (adminApiOverview) {
    adminApiOverview.innerHTML = providers.length
      ? providers
        .sort((a, b) => a.priority - b.priority)
        .map((item) => `
          <div class="admin-role-card">
            <h4>${escapeHtml(item.label)}</h4>
            <p>模型：${escapeHtml(item.model || "未设置")}<br>优先级：${escapeHtml(String(item.priority))}<br>状态：${item.enabled ? "启用中" : "已停用"}</p>
          </div>
        `).join("")
      : `<div class="admin-note">后台还没有配置可用 AI 路由。请在下方至少新增一条有效的 API Key 与模型。</div>`;
  }
  if (adminApiHealthSummary) {
    adminApiHealthSummary.textContent = providers.length
      ? `当前共配置 ${providers.length} 条 AI 路由，启用 ${enabledProviders.length} 条。主路由失败时会自动切到备用路由，批量任务建议至少保留 2 条可用路由。`
      : "后台还没有可用 AI 路由。请先在这里配置，再回工作台执行分析。";
  }
  if (adminBackupSummary) {
    adminBackupSummary.textContent = latestSync
      ? `最近一次服务端沉淀发生在 ${formatDateTime(latestSync)}。建议在大规模修改提示词或批量分析前备份数据库。`
      : "当前暂无本地沉淀，备份策略以预防性备份为主。";
  }
  if (adminMonitorRoutes) adminMonitorRoutes.textContent = String(enabledProviders.length);
  if (adminMonitorAssets) adminMonitorAssets.textContent = String(profilesCount + transcriptCount + complianceCount + caseCount);
  if (adminMonitorRisks) adminMonitorRisks.textContent = String(highRiskCount);
  if (adminMonitorSummary) {
    adminMonitorSummary.innerHTML = `
      <div class="admin-log-item">
        <div class="admin-log-title">本地服务状态正常</div>
        <div class="admin-log-desc">当前后台基于服务端模式运行，管理侧数据来自 MySQL 与对象存储。</div>
      </div>
      <div class="admin-log-item">
        <div class="admin-log-title">AI 路由池摘要</div>
        <div class="admin-log-desc">${escapeHtml(providers.length ? `共 ${providers.length} 条路由，启用 ${enabledProviders.length} 条；主路由和备用路由均由后台统一管理。` : "尚未配置 AI 路由。")}</div>
      </div>
      <div class="admin-log-item">
        <div class="admin-log-title">知识资产沉淀</div>
        <div class="admin-log-desc">${escapeHtml(`人物 ${profilesCount} 条，逐字稿 ${transcriptCount} 条，合规 ${complianceCount} 条，案例 ${caseCount} 条。`)}</div>
      </div>
    `;
  }
  renderAiRouteSummary();
}

function buildAdminRecentEvents() {
  return [
    ...state.anchorProfiles.map((item) => ({
      at: item.updatedAt || item.createdAt || "",
      module: "人物资料",
      title: `${item.name || "未命名人物"} 更新快照`,
      description: `人物档案已沉淀，最近更新时间 ${formatDateTime(item.updatedAt || item.createdAt)}。`
    })),
    ...state.transcriptEntries.map((item) => ({
      at: item.analyzedAt || item.updatedAt || item.createdAt || "",
      module: "逐字稿库",
      title: `${item.anchorName || item.fileName || "未命名逐字稿"} 入库`,
      description: `逐字稿与章节结构已沉淀，共 ${Array.isArray(item.chapters) ? item.chapters.length : 0} 个章节。`
    })),
    ...state.complianceEntries.map((item) => ({
      at: item.updatedAt || item.createdAt || "",
      module: "合规库",
      title: `${item.anchorName || "未命名来源"} 新增合规条目`,
      description: `${normalizeComplianceLevelLabel(item.level)} · ${item.phrase || "未命名话术"}`
    })),
    ...state.caseEntries.map((item) => ({
      at: item.updatedAt || item.createdAt || "",
      module: "案例库",
      title: `${item.title || "未命名案例"} 已沉淀`,
      description: `${item.category || "案例"} · ${item.sourceAnchor || "未知来源"}`
    }))
  ]
    .filter((item) => item.at)
    .sort((a, b) => String(b.at).localeCompare(String(a.at)))
    .map((item) => ({
      ...item,
      timeLabel: formatDateTime(item.at)
    }));
}

function showAdminSec(id, btn) {
  if (!isAdmin() && id !== "api") {
    showToast("当前账号只能访问 API 管理");
    id = "api";
    btn = null;
  }
  document.querySelectorAll("#pg-admin .asec").forEach((sec) => sec.classList.remove("active"));
  document.getElementById("asec-" + id)?.classList.add("active");
  const navItems = document.querySelectorAll("#pg-admin .sidebar .nav-item");
  navItems.forEach((item) => item.classList.remove("active"));
  if (btn) {
    btn.classList.add("active");
  } else {
    const target = Array.from(navItems).find((item) => item.getAttribute("onclick")?.includes(`'${id}'`));
    target?.classList.add("active");
  }
  if (id === "operation-import") loadOperationImportLogs();
  if (id === "updates") renderAdminReleaseHistory();
  if (id === "logs") loadActionLogs();
  if (id === "remote-db") loadRemoteDbSettings();
  if (id === "tushare") window.FinVueMarketAdmin?.load?.();
  if (id === "feishu") window.FinVueFeishuAdmin?.load?.();
}

function canAccessAdmin() {
  return isAdmin() || hasDashboardPermission("admin-api");
}

function applyAdminPermissions() {
  const adminOnlySections = new Set(["console", "users", "roles", "settings", "logs", "remote-db", "tushare", "backup", "monitor"]);
  document.querySelectorAll("#pg-admin .sidebar .nav-item").forEach((item) => {
    const onclick = item.getAttribute("onclick") || "";
    const match = onclick.match(/showAdminSec\('([^']+)'/);
    const section = match?.[1] || "";
    item.style.display = !isAdmin() && adminOnlySections.has(section) ? "none" : "";
  });
  document.querySelectorAll("#pg-admin .s-section").forEach((item) => {
    item.style.display = isAdmin() ? "" : "none";
  });
}

function renderAdminUsers(users = state.adminUsers) {
  const keyword = String(els.adminUserSearch?.value || "").trim().toLowerCase();
  const filtered = keyword
    ? users.filter((user) => `${user.username} ${user.role}`.toLowerCase().includes(keyword))
    : users;
  els.adminUsersTable.innerHTML = "";
  if (!filtered.length) {
    els.adminUsersTable.innerHTML = `<tr><td colspan="6">暂无用户</td></tr>`;
    return;
  }
  for (const user of filtered) {
    const nextRole = user.role === "admin" ? "user" : "admin";
    const permissionSummary = summarizeUserPermissions(user);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="width:30px;height:30px;border-radius:50%;background:var(--gold-dim);color:var(--gold);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;">${escapeHtml(user.username.slice(0,1).toUpperCase())}</div>
          <div><div style="font-weight:500;">${escapeHtml(user.username)}</div><div style="font-size:11px;color:var(--text1)">${escapeHtml(user.username)}</div></div>
        </div>
      </td>
      <td><span class="badge ${user.role === "admin" ? "gold" : "blue"}">${escapeHtml(user.role)}</span></td>
      <td><span class="badge green">● 正常</span></td>
      <td class="mono muted">${escapeHtml(new Date(user.createdAt).toLocaleString("zh-CN"))}</td>
      <td class="mono muted">${escapeHtml(permissionSummary)}</td>
      <td><div style="display:flex;gap:6px;flex-wrap:wrap;"><button class="btn-sm btn-outline-sm" data-role-user="${escapeHtml(user.username)}" data-role-next="${nextRole}">设为${nextRole === "admin" ? "超级管理员" : "普通用户"}</button><button class="btn-sm btn-outline-sm" data-perm-user="${escapeHtml(user.username)}">模块授权</button><button class="btn-sm btn-outline-sm" data-delete-user="${escapeHtml(user.username)}" style="color:var(--red);border-color:rgba(224,82,82,.35);">删除</button></div></td>
    `;
    els.adminUsersTable.appendChild(tr);
  }
}

function summarizeUserPermissions(user) {
  if (user.role === "admin") return "全部模块";
  const permissions = user.permissions && typeof user.permissions === "object" ? user.permissions : {};
  const granted = Object.keys(DASHBOARD_PERMISSION_LABELS).filter((key) => Boolean(permissions[key]));
  if (!granted.length) return "未授权";
  const labels = granted.slice(0, 3).map((key) => DASHBOARD_PERMISSION_LABELS[key] || key);
  const suffix = granted.length > 3 ? ` 等${granted.length}项` : ` 共${granted.length}项`;
  return `${labels.join(" / ")}${suffix}`;
}

function renderAccessSettings(access = state.accessSettings) {
  state.accessSettings = {
    openRegistration: Boolean(access?.openRegistration),
    updatedAt: access?.updatedAt || "",
    updatedBy: access?.updatedBy || ""
  };
  if (els.openRegistrationToggle) els.openRegistrationToggle.checked = state.accessSettings.openRegistration;
  if (els.accessSettingsMeta) {
    const updated = state.accessSettings.updatedAt ? ` · ${formatDateTime(state.accessSettings.updatedAt)}` : "";
    const by = state.accessSettings.updatedBy ? ` · 操作人 ${state.accessSettings.updatedBy}` : "";
    els.accessSettingsMeta.textContent = `${state.accessSettings.openRegistration ? "当前允许用户自行注册" : "当前仅超级管理员可创建用户"}${updated}${by}`;
  }
  state.registrationEnabled = state.accessSettings.openRegistration;
  syncRegistrationUi();
}

async function loadAdminUsers() {
  try {
    const response = await apiFetch("/api/admin/users");
    const payload = await response.json();
    state.adminUsers = Array.isArray(payload.users) ? payload.users : [];
    if (payload.access) renderAccessSettings(payload.access);
    renderAdminUsers();
    updateAdminDashboardSummary();
    els.adminStatus.textContent = `已加载 ${state.adminUsers.length} 个用户`;
  } catch (error) {
    els.adminStatus.textContent = error.message;
  }
}

async function updateAccessSettings(openRegistration) {
  try {
    const response = await apiFetch("/api/admin/access", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access: { openRegistration } })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "保存失败");
    renderAccessSettings(payload.access || { openRegistration });
    showToast(openRegistration ? "已开放注册" : "已关闭开放注册");
  } catch (error) {
    renderAccessSettings(state.accessSettings);
    els.adminStatus.textContent = error.message;
    showToast(error.message);
  }
}

async function createAdminUser() {
  const username = String(els.createUserName?.value || "").trim();
  const password = String(els.createUserPassword?.value || "");
  const role = String(els.createUserRole?.value || "user");
  if (!username || password.length < 6) {
    showToast("请输入用户名和至少 6 位初始密码");
    return;
  }
  try {
    if (els.createUserBtn) els.createUserBtn.disabled = true;
    const response = await apiFetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, role })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "创建失败");
    if (els.createUserName) els.createUserName.value = "";
    if (els.createUserPassword) els.createUserPassword.value = "";
    await loadAdminUsers();
    showToast("用户已创建");
  } catch (error) {
    els.adminStatus.textContent = error.message;
    showToast(error.message);
  } finally {
    if (els.createUserBtn) els.createUserBtn.disabled = false;
  }
}

async function deleteAdminUser(username) {
  if (!username) return;
  if (!confirm(`确认删除用户「${username}」？`)) return;
  try {
    const response = await apiFetch(`/api/admin/users/${encodeURIComponent(username)}`, { method: "DELETE" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "删除失败");
    await loadAdminUsers();
    showToast("用户已删除");
  } catch (error) {
    els.adminStatus.textContent = error.message;
    showToast(error.message);
  }
}

async function updateAdminUserRole(username, role) {
  try {
    const response = await apiFetch("/api/admin/users/role", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, role })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "更新失败");
    await loadAdminUsers();
    showToast("角色已更新");
  } catch (error) {
    els.adminStatus.textContent = error.message;
    showToast(error.message);
  }
}

async function updateAdminUserPermissions(username, permissions) {
  try {
    const response = await apiFetch("/api/admin/users/permissions", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, permissions })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "更新失败");
    await loadAdminUsers();
    showToast("模块权限已更新");
  } catch (error) {
    els.adminStatus.textContent = error.message;
    showToast(error.message);
  }
}

async function editAdminUserPermissions(username) {
  const user = state.adminUsers.find((item) => item.username === username);
  if (!user) {
    showToast("未找到用户");
    return;
  }
  if (user.role === "admin") {
    showToast("管理员默认拥有全部模块权限");
    return;
  }
  state.permissionEditorUsername = username;
  renderPermissionModal(user);
  els.permissionModal?.classList.add("active");
}

function renderPermissionModal(user) {
  const current = user.permissions && typeof user.permissions === "object" ? user.permissions : {};
  els.permissionModalUser.textContent = `${user.username} 的工作台模块权限`;
  els.permissionModalGrid.innerHTML = Object.entries(DASHBOARD_PERMISSION_LABELS).map(([key, label]) => `
    <label class="perm-item">
      <input type="checkbox" data-perm-check="${escapeHtml(key)}" ${current[key] ? "checked" : ""}>
      <span>${escapeHtml(label)}</span>
    </label>
  `).join("");
}

function closePermissionModal() {
  state.permissionEditorUsername = "";
  els.permissionModal?.classList.remove("active");
}

function setPermissionModalChecks(checked) {
  els.permissionModalGrid?.querySelectorAll("[data-perm-check]").forEach((input) => {
    input.checked = checked;
  });
}

async function savePermissionModal() {
  const username = state.permissionEditorUsername;
  if (!username) return;
  const permissions = {};
  Object.keys(DASHBOARD_PERMISSION_LABELS).forEach((key) => {
    permissions[key] = Boolean(els.permissionModalGrid?.querySelector(`[data-perm-check="${key}"]`)?.checked);
  });
  await updateAdminUserPermissions(username, permissions);
  closePermissionModal();
}
