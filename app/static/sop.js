    const STORE_KEY = "anchor_onboarding_sop_v2";
    const DRAFT_KEY = "anchor_onboarding_sop_draft_v2";
    const DIRTY_KEY = "anchor_onboarding_sop_dirty_v2";  // 未保存的 textarea 脏值（Task 14 用）
    const API_BASE = "/api/sop";
    const MAX_DAYS = 28;
    const TODAY = () => new Date().toISOString().slice(0, 10);

    const weeklyPlan = [
      {
        id: 1,
        code: "P1",
        title: "第 1 周 · 熟悉与定位",
        cycle: "建议 4-5 天",
        intro: "先完成破冰、老师画像和基础认知搭建。未达标就继续停留在第 1 周循环。",
        actions: [
          {
            title: "破冰与熟悉",
            desc: "带老师熟悉职场、工作环境、团队节奏，以聊天为主建立信任感。",
            substeps: [
              "带老师熟悉职场、工作环境、吃饭节奏",
              "了解爱好"
            ]
          },
          {
            title: "老师画像梳理",
            desc: "确认擅长点、不擅长点、知识体系、表达风格和内容优势。",
            substeps: [
              { title: "擅长的点", mode: "options", children: ["趋势交易", "市场热点", "情绪", "技术+基本面", "波段操作"] },
              { title: "不擅长的点", mode: "options", children: ["消息面", "细分板块"] },
              { title: "知识体系", children: ["知识体系已梳理"] },
              { title: "语言风格", mode: "options", children: ["专业严谨", "段子手", "通俗易懂", "幽默风趣", "稳健长期投资", "娓娓道来", "逻辑严谨", "故事感"] }
            ]
          },
          {
            title: "试讲观察",
            desc: "安排短内容练习，记录播感、表达差异、镜头状态。",
            substeps: [
              "练习几分钟内容",
              "听其中的不同点",
              "记录播感、表达差异、镜头状态"
            ]
          },
          {
            title: "账号与资质准备",
            desc: "推进资质资料、平台准备、多平台节奏与挂靠动作。",
            substeps: [
              { title: "抖音 11000 粉丝路径确认", children: ["短视频先做 1000 粉并打上标签", "买 10000 粉并确保抖音可挂黄V投资顾问资质"] },
              "联系佳丽完成约牛资质挂靠",
              { title: "多平台准备", children: ["视频号", "快手", "小红书"] }
            ]
          },
          {
            title: "合规底线确认",
            desc: "开播前把投顾合规红线、平台规则和公司要求讲清楚。",
            substeps: [
              { title: "学习合规知识", children: ["学习投顾合规基础知识", "学习平台直播规则", "学习公司内部合规要求"] },
              { title: "参加合规培训", children: ["完成合规培训学习", "完成合规培训确认"] },
              { title: "符合持牌机构和公司合规", children: ["不能推荐个股", "不能预测点位和使用确定性话术", "开播前风险提示话术统一", "禁止引流话术：快速入群", "禁止引流话术：专享内部资料", "禁止炫耀个人收益", "主播不主动私信"] }
            ]
          },
          {
            title: "人性挖掘与直播观念",
            desc: "把老师定位、价值观、性格和直播认知先打牢。",
            substeps: [
              { title: "定位", children: ["之前的经历", "做主播的信念是什么"] },
              { title: "价值观", children: ["帮助更多的人避坑", "传递自我价值，提升用户认知"] },
              { title: "性格", mode: "options", children: ["理性", "感性", "话多", "话少", "共情能力", "说服力"] },
              { title: "树立正确直播观念", children: ["流量不要看太重，重心在内容上", "坚持每天至少1场，以内容为核心", "第一周正式直播可先 30-40 分钟"] }
            ]
          },
          {
            title: "对标直播账号挖掘",
            desc: "从高在线直播间里拆内容和风格，给老师找明确参考系。",
            substeps: [
              "查看万人 / 千人在线直播间",
              { title: "拆解维度", children: ["内容", "情绪", "话术", "风格", "场景", "可同时拆多个直播间"] }
            ]
          }
        ]
      },
      {
        id: 2,
        code: "P2",
        title: "第 2 周 · 练播与大纲",
        cycle: "建议 5-7 天",
        intro: "核心是把内容讲顺、镜头感练出来，并形成可复用的大纲结构。未达标则继续循环第 2 周。",
        actions: [
          {
            title: "内部练播留档",
            desc: "对镜头练播并录制，反复看播感、节奏、语气和互动感。",
            substeps: [
              { title: "自然舒适", children: ["站着播 or 坐着播"] },
              { title: "互动感", children: ["距离", "肢体"] },
              { title: "分享感", children: ["站在用户角度表达，让用户听得懂"] },
              { title: "情绪", children: ["W型起承转合，有轻有重", "上涨行情表达", "下跌行情表达", "震荡行情表达"] }
            ]
          },
          {
            title: "直播主题确定",
            desc: "围绕真实观点、爆点和反差感，锁定近期练播主题。",
            substeps: [
              { title: "反差、冲突、打破预期", children: ["例如：一根K线背后的故事", "例如：近期一段K线的故事"] }
            ]
          },
          {
            title: "直播框架输出",
            desc: "按照爆点、原因、影响、策略、总结五段式整理内容。",
            substeps: [
              { title: "步骤", children: ["今日爆点", "K线背后的原因，为什么这么走", "给用户造成什么影响", "今天 / 明天怎么办，需要看哪些信号", "5分钟总结：爆点 + 大盘 + 板块 + 明天看什么信号"] }
            ]
          },
          {
            title: "复盘只改一个点",
            desc: "每次练播后只盯一个问题优化，避免一次改太多。",
            substeps: [
              "练习后查漏补缺",
              "每次只改一个点",
              "盘中和盘后至少各练 1 场"
            ]
          },
          {
            title: "实名认证与资质过审",
            desc: "第二周最后一天把账号和资质全部收口。",
            substeps: [
              "4个平台账号完成实名认证",
              "检查直播资质是否过审",
              "没过审及时重新提交"
            ]
          }
        ]
      },
      {
        id: 3,
        code: "P3",
        title: "第 3 周 · 场景与联调",
        cycle: "建议 5-7 天",
        intro: "重点是把直播间搭起来、设备跑顺、平台打通。未达标则继续循环第 3 周。",
        actions: [
          {
            title: "场景确定",
            desc: "确认办公室、居家或会议模式，保证镜头感和专业感一致。",
            substeps: [
              { title: "专业办公室", children: ["已确定专业办公室场景"] },
              { title: "简约居家", children: ["已确定简约居家场景"] },
              { title: "会议模式", children: ["待搭建：共享屏幕 + 人物摄像头"] },
              { title: "主播服装、声音", children: ["服装休闲为主，声音清楚"] }
            ]
          },
          {
            title: "固定时间设定",
            desc: "明确日常开播时间，建立当天问题当天复盘机制。",
            substeps: [
              { title: "固定时间开播，做直播预约数据", children: ["建立当天问题当天复盘机制", "例如每周一到周五下午 5:00 开播"] },
              { title: "根据市场热点以及散户恐慌情绪适时加播", children: ["当天大A暴跌", "当天大A暴涨", "消息面影响巨大"] }
            ]
          },
          {
            title: "设备全链路检查",
            desc: "手机、相机、电脑、OBS、直播伴侣、麦克风、灯光全部联调。",
            substeps: [
              { title: "手机", children: ["抖音直播伴侣"] },
              { title: "相机", children: ["采集卡"] },
              { title: "电脑", children: ["OBS", "抖音直播伴侣", "微信-视频号直播伴侣", "写批注软件"] },
              { title: "麦克风", children: ["保证所有绿灯亮起，链接正常"] },
              { title: "灯光", children: ["一个直播间 3 盏灯"] },
              { title: "电视屏", children: ["可写可画"] }
            ]
          },
          {
            title: "贴片与执业信息",
            desc: "风险提示、主播执业信息和直播间展示内容准备完成。",
            substeps: [
              { title: "风险提示", children: ["行情观点及分析结果仅供参考，不构成投资意见"] },
              "主播执业信息贴片制作完成"
            ]
          },
          {
            title: "平台联调与练播",
            desc: "最后一轮实操验证，确保进入正式开播状态。",
            substeps: [
              "继续练播",
              "确保所有平台可以开播"
            ]
          }
        ]
      },
      {
        id: 4,
        code: "P4",
        title: "第 4 周 · 正式开播",
        cycle: "建议 7-10 天",
        intro: "目标是稳定开播节奏。若表现仍未达标，可继续停留在第 4 周，但会触发 4 周周期预警。",
        actions: [
          {
            title: "正式开播与排班",
            desc: "先保证稳定开播，再根据状态逐步加场。",
            substeps: [
              "1天1场固定时间开播",
              "根据主播状态和直播效果决定是否增加场次"
            ]
          },
          {
            title: "直播效果复盘",
            desc: "把正式开播后的状态、效果和后续迭代点持续记录下来。",
            substeps: [
              "记录内容表现",
              "记录用户反馈",
              "记录状态问题",
              "记录下一次优化点"
            ]
          }
        ]
      }
    ];

    const initialState = {
      anchors: {},
      logs: []
    };

    const pages = Array.from(document.querySelectorAll(".page"));
    const navItems = Array.from(document.querySelectorAll(".nav-item"));
    const operatorNameEl = document.getElementById("operatorName");
    const anchorNameEl = document.getElementById("anchorName");
    const noteTextEl = document.getElementById("noteText");
    const saveTextEl = document.getElementById("saveText");
    const autoDateBoxEl = document.getElementById("autoDateBox");
    const anchorStateBoxEl = document.getElementById("anchorStateBox");
    const trainingWarnEl = document.getElementById("trainingWarn");
    const phaseListEl = document.getElementById("phaseList");
    const overviewGridEl = document.getElementById("overviewGrid");
    const summaryGridEl = document.getElementById("summaryGrid");
    const planGridEl = document.getElementById("planGrid");
    const summaryKeywordEl = document.getElementById("summaryKeyword");
    const summaryStatusEl = document.getElementById("summaryStatus");
    const summaryOperatorEl = document.getElementById("summaryOperator");
    const weekSwitcherEl = document.getElementById("weekSwitcher");
    const sidebarCountEl = document.getElementById("sidebarCount");
    const operatorSuggestionsEl = document.getElementById("operatorSuggestions");
    const anchorSuggestionsEl = document.getElementById("anchorSuggestions");
    const operatorQuickPicksEl = document.getElementById("operatorQuickPicks");
    const anchorQuickPicksEl = document.getElementById("anchorQuickPicks");
    const panelAlertEl = document.getElementById("panelAlert");
    const saveBtnEl = document.getElementById("saveBtn");

    let db = { anchors: {} };  // 运行时内存态，由服务端拉取初始化
    let pendingStepFeedback = null;
    let expandedSummaryAnchor = null;
    let collapsedWorkflowSteps = {};
    let collapsedWorkflowWeeks = {};
    let selectedWorkflowWeek = null;
    let customOptions = [];
    let stepNoteSaveTimers = {};

    function loadJson(key, fallback) {
      try {
        const raw = JSON.parse(localStorage.getItem(key));
        return raw || fallback;
      } catch {
        return fallback;
      }
    }

    function getDirty() {
      return loadJson(DIRTY_KEY, {});
    }

    function setDirty(key, value) {
      const dirty = getDirty();
      dirty[key] = value;
      localStorage.setItem(DIRTY_KEY, JSON.stringify(dirty));
    }

    function clearDirtyKeys(keys) {
      const dirty = getDirty();
      keys.forEach((k) => delete dirty[k]);
      localStorage.setItem(DIRTY_KEY, JSON.stringify(dirty));
    }

    function dirtyKeyFor(anchorName, week, actionIndex, subIndex = -1, childIndex = -1) {
      return `${anchorName}|${week}|${actionIndex}|${subIndex}|${childIndex}`;
    }

    const MAIN_NOTE_DIRTY_SUFFIX = "|__main_note__";

    function saveDb() {
      // no-op: 主数据源已改为服务端，这里保留空函数避免旧调用点报错。
      // 后续 Task 会改写各调用点直接调 API。
    }

    async function initFromServer() {
      try {
        const resp = await fetch(`${API_BASE}/anchors`);
        if (resp.status === 403) {
          // 用户没有 sop 权限，静默处理
          console.log("用户没有 SOP 权限");
          document.body.innerHTML = '<div style="padding:40px;text-align:center;color:#999;"><h3>权限不足</h3><p>您没有访问"带新SOP"功能的权限，请联系管理员授权。</p></div>';
          return;
        }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const { anchors } = await resp.json();
        db.anchors = {};
        for (const a of anchors) {
          db.anchors[a.anchorName] = hydrateAnchorFromServer(a);
        }
      } catch (err) {
        console.error("加载主播数据失败：", err);
        // 不再弹出 alert，改为在页面上显示错误
        document.body.innerHTML = `<div style="padding:40px;text-align:center;color:#999;"><h3>加载失败</h3><p>${err.message || '请检查网络或刷新页面'}</p></div>`;
      }
    }

    /**
     * 把服务端返回的扁平 progress 数组转成前端嵌套结构。
     */
    function hydrateAnchorFromServer(serverAnchor) {
      const anchor = {
        anchorName: serverAnchor.anchorName,
        operatorName: serverAnchor.operatorName,
        startDate: serverAnchor.startDate,
        lastSavedDate: serverAnchor.lastSavedDate,
        currentWeek: serverAnchor.currentWeek,
        status: serverAnchor.status,
        note: serverAnchor.note || "",
        currentBlocker: serverAnchor.currentBlocker || "未填写备注",
        warning: serverAnchor.warning,
        weekActions: buildEmptyWeekActions(),
        weekNotes: buildEmptyWeekNotes(),
        weekSubActions: buildEmptyWeekSubActions(),
        weekSubNotes: buildEmptyWeekSubNotes(),
        weekSubChildActions: buildEmptyWeekSubChildActions(),
        weekSubChildNotes: buildEmptyWeekSubChildNotes(),
        weekCompletedAt: {},
      };

      // 覆盖 progress
      for (const p of serverAnchor.progress || []) {
        if (p.subIndex === -1 && p.childIndex === -1) {
          // action 层
          anchor.weekActions[p.week][p.actionIndex] = p.checked;
          anchor.weekNotes[p.week][p.actionIndex] = p.note || "";
        } else if (p.childIndex === -1) {
          // substep 层
          anchor.weekSubActions[p.week][p.actionIndex][p.subIndex] = p.checked;
          anchor.weekSubNotes[p.week][p.actionIndex][p.subIndex] = p.note || "";
        } else {
          // child 层
          anchor.weekSubChildActions[p.week][p.actionIndex][p.subIndex][p.childIndex] = p.checked;
          anchor.weekSubChildNotes[p.week][p.actionIndex][p.subIndex][p.childIndex] = p.note || "";
        }
      }

      // weekCompletions
      for (const [week, iso] of Object.entries(serverAnchor.weekCompletions || {})) {
        anchor.weekCompletedAt[week] = iso;
      }

      return anchor;
    }

    function saveDraft() {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        operatorName: operatorNameEl.value.trim(),
        anchorName: anchorNameEl.value.trim(),
        note: noteTextEl.value,
        actions: getCurrentDraftActions()
      }));
    }

    function loadDraft() {
      const draft = loadJson(DRAFT_KEY, null);
      if (!draft) return;
      operatorNameEl.value = draft.operatorName || "";
      anchorNameEl.value = draft.anchorName || "";
      noteTextEl.value = draft.note || "";
    }

    function syncFormFromExistingAnchor() {
      const anchor = getAnchorRecord(anchorNameEl.value);
      if (!anchor) return;
      operatorNameEl.value = operatorNameEl.value.trim() || anchor.operatorName || "";
      noteTextEl.value = anchor.note || "";
    }

    function showPage(pageName) {
      pages.forEach((page) => page.classList.toggle("active", page.id === `page-${pageName}`));
      navItems.forEach((item) => item.classList.toggle("active", item.dataset.page === pageName));
    }

    navItems.forEach((item) => item.addEventListener("click", () => showPage(item.dataset.page)));

    function normalizeAnchorName(name) {
      return (name || "").trim();
    }

    function getAnchorRecord(name) {
      return db.anchors[normalizeAnchorName(name)] || null;
    }

    function ensureAnchorRecord() {
      const anchorName = normalizeAnchorName(anchorNameEl.value);
      const operatorName = operatorNameEl.value.trim();
      if (!anchorName || !operatorName) return null;

      if (!db.anchors[anchorName]) {
        db.anchors[anchorName] = {
          anchorName,
          operatorName,
          startDate: TODAY(),
          lastSavedDate: null,
          currentWeek: 1,
          status: "进行中",
          note: "",
          weekActions: buildEmptyWeekActions(),
          weekNotes: buildEmptyWeekNotes(),
          weekSubActions: buildEmptyWeekSubActions(),
          weekSubNotes: buildEmptyWeekSubNotes(),
          weekSubChildActions: buildEmptyWeekSubChildActions(),
          weekSubChildNotes: buildEmptyWeekSubChildNotes(),
          weekCompletedAt: {},
          currentBlocker: "未填写备注",
          warning: false
        };
      }

      db.anchors[anchorName].operatorName = operatorName;
      db.anchors[anchorName].weekNotes = db.anchors[anchorName].weekNotes || buildEmptyWeekNotes();
      db.anchors[anchorName].weekSubActions = db.anchors[anchorName].weekSubActions || buildEmptyWeekSubActions();
      db.anchors[anchorName].weekSubNotes = db.anchors[anchorName].weekSubNotes || buildEmptyWeekSubNotes();
      db.anchors[anchorName].weekSubChildActions = db.anchors[anchorName].weekSubChildActions || buildEmptyWeekSubChildActions();
      db.anchors[anchorName].weekSubChildNotes = db.anchors[anchorName].weekSubChildNotes || buildEmptyWeekSubChildNotes();
      return db.anchors[anchorName];
    }

    function buildEmptyWeekActions() {
      const weekActions = {};
      weeklyPlan.forEach((week) => {
        weekActions[week.id] = week.actions.map(() => false);
      });
      return weekActions;
    }

    function buildEmptyWeekNotes() {
      const weekNotes = {};
      weeklyPlan.forEach((week) => {
        weekNotes[week.id] = week.actions.map(() => "");
      });
      return weekNotes;
    }

    function buildEmptyWeekSubActions() {
      const weekSubActions = {};
      weeklyPlan.forEach((week) => {
        weekSubActions[week.id] = week.actions.map((action) => (action.substeps || []).map(() => false));
      });
      return weekSubActions;
    }

    function buildEmptyWeekSubNotes() {
      const weekSubNotes = {};
      weeklyPlan.forEach((week) => {
        weekSubNotes[week.id] = week.actions.map((action) => (action.substeps || []).map(() => ""));
      });
      return weekSubNotes;
    }

    function buildEmptyWeekSubChildActions() {
      const weekSubChildActions = {};
      weeklyPlan.forEach((week) => {
        weekSubChildActions[week.id] = week.actions.map((action) =>
          (action.substeps || []).map((substep) =>
            getSubstepChildren(substep).map(() => false)
          )
        );
      });
      return weekSubChildActions;
    }

    function buildEmptyWeekSubChildNotes() {
      const weekSubChildNotes = {};
      weeklyPlan.forEach((week) => {
        weekSubChildNotes[week.id] = week.actions.map((action) =>
          (action.substeps || []).map((substep) =>
            getSubstepChildren(substep).map(() => "")
          )
        );
      });
      return weekSubChildNotes;
    }

    function getSubstepTitle(substep) {
      return typeof substep === "string" ? substep : substep.title;
    }

    function getSubstepChildren(substep) {
      return typeof substep === "string" ? [] : (substep.children || []);
    }

    function isSubstepOptionGroup(substep) {
      return typeof substep === "object" && substep.mode === "options";
    }

    function isCustomOptionGroup(substep) {
      return isSubstepOptionGroup(substep);
    }

    function appendCustomOptionToPlan(option) {
      const week = weeklyPlan.find((item) => item.id === option.week);
      const substep = week?.actions?.[option.actionIndex]?.substeps?.[option.subIndex];
      if (!isCustomOptionGroup(substep)) return false;
      if (substep.children.includes(option.label)) return false;
      substep.children.push(option.label);
      return true;
    }

    function extendAnchorChildStateForOption(option) {
      Object.values(db.anchors).forEach((anchor) => {
        const childChecks = anchor.weekSubChildActions?.[option.week]?.[option.actionIndex]?.[option.subIndex];
        const childNotes = anchor.weekSubChildNotes?.[option.week]?.[option.actionIndex]?.[option.subIndex];
        if (childChecks && childChecks.length < getSubstepChildren(weeklyPlan[option.week - 1].actions[option.actionIndex].substeps[option.subIndex]).length) {
          childChecks.push(false);
        }
        if (childNotes && childNotes.length < getSubstepChildren(weeklyPlan[option.week - 1].actions[option.actionIndex].substeps[option.subIndex]).length) {
          childNotes.push("");
        }
      });
    }

    async function initCustomOptions() {
      try {
        const resp = await fetch(`${API_BASE}/options`);
        if (resp.status === 403) {
          // 用户没有 sop 权限，静默处理（initFromServer 会处理页面显示）
          console.log("用户没有 SOP 权限 (options)");
          return;
        }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const { options } = await resp.json();
        customOptions = options || [];
        customOptions.forEach(appendCustomOptionToPlan);
      } catch (err) {
        console.error("加载人工选项失败：", err);
        // 不再弹出 alert，静默处理
      }
    }

    async function addCustomOption({ week, actionIndex, subIndex, label }) {
      const cleaned = label.trim();
      if (!cleaned) return;
      const resp = await fetch(`${API_BASE}/options`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ week, actionIndex, subIndex, label: cleaned }),
      });
      if (!resp.ok) throw new Error(`新增选项失败：${resp.status}`);
      const option = await resp.json();
      customOptions = customOptions.filter((item) => item.id !== option.id).concat(option);
      appendCustomOptionToPlan(option);
      extendAnchorChildStateForOption(option);
    }

    function isSubstepComplete(substep, checked, childChecks) {
      const children = getSubstepChildren(substep);
      if (!children.length) return checked;
      if (isSubstepOptionGroup(substep)) {
        return (childChecks || []).some(Boolean);
      }
      return checked;
    }

    function getDaysInTraining(anchor) {
      if (!anchor?.startDate) return 0;
      const start = new Date(anchor.startDate + "T00:00:00");
      const now = new Date(TODAY() + "T00:00:00");
      return Math.max(1, Math.floor((now - start) / 86400000) + 1);
    }

    function getCurrentWeekPlan(anchor) {
      const weekId = anchor?.currentWeek || 1;
      return weeklyPlan.find((week) => week.id === weekId) || weeklyPlan[0];
    }

    function getCurrentDraftActions() {
      return Array.from(phaseListEl.querySelectorAll('input[type="checkbox"]:checked')).map((input) => ({
        week: Number(input.dataset.week),
        index: Number(input.dataset.index)
      }));
    }

    function renderWeekSwitcher(anchor, visibleWeekId, currentWeekId) {
      if (!weekSwitcherEl) return;
      weekSwitcherEl.innerHTML = `
        <div class="week-switcher-head">
          <div>
            <div class="tag">Week Selector</div>
            <h3>选择本次要处理的周计划</h3>
          </div>
          <span>${anchor ? `当前停留：第 ${currentWeekId} 周` : "先选择主播"}</span>
        </div>
        <div class="week-tabs">
          ${weeklyPlan.map((week) => {
            const stats = getWeekProgressStats(anchor, week);
            const pct = stats.total ? Math.round((stats.done / stats.total) * 100) : 0;
            const status = getWeekStatus(anchor, week.id);
            const isSelected = week.id === visibleWeekId;
            const isCurrent = week.id === currentWeekId;
            return `
              <button
                type="button"
                class="week-tab ${isSelected ? "active" : ""} ${isCurrent ? "current" : ""}"
                data-select-week="${week.id}"
              >
                <span class="week-tab-code">${week.code}</span>
                <strong>${week.title.replace("第 ", "").replace(" 周 · ", " · ")}</strong>
                <small>${status.label} · ${stats.done}/${stats.total}</small>
                <em><i style="--pct:${pct}%"></i></em>
              </button>
            `;
          }).join("")}
        </div>
      `;

      weekSwitcherEl.querySelectorAll("[data-select-week]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedWorkflowWeek = Number(button.dataset.selectWeek);
          renderWorkflow();
          renderPlan();
        });
      });
    }

    function renderWorkflow() {
      const anchor = getAnchorRecord(anchorNameEl.value);
      const currentWeekId = anchor?.currentWeek || 1;
      const visibleWeekId = selectedWorkflowWeek || currentWeekId;
      const today = TODAY();
      autoDateBoxEl.textContent = `保存日期：${today}`;

      renderWeekSwitcher(anchor, visibleWeekId, currentWeekId);

      phaseListEl.innerHTML = weeklyPlan.filter((week) => week.id === visibleWeekId).map((week) => {
        const weekStatus = getWeekStatus(anchor, week.id);
        const checks = anchor?.weekActions?.[week.id] || week.actions.map(() => false);
        const notes = anchor?.weekNotes?.[week.id] || week.actions.map(() => "");
        const subChecks = anchor?.weekSubActions?.[week.id] || week.actions.map((action) => (action.substeps || []).map(() => false));
        const subChildChecks = anchor?.weekSubChildActions?.[week.id] || week.actions.map((action) => (action.substeps || []).map((substep) => getSubstepChildren(substep).map(() => false)));
        const progressStats = getWeekProgressStats(anchor, week);
        const progressPct = progressStats.total ? Math.round((progressStats.done / progressStats.total) * 100) : 0;
        const phaseClass = week.id === currentWeekId ? "current" : (week.id < currentWeekId || (anchor?.status === "已完成" && week.id === 4) ? "done" : "wait");
        const canCollapseWeek = false;
        const isWeekCollapsed = false;
        return `
          <section class="phase ${phaseClass}">
            <div class="phase-head">
              <div class="phase-left">
                <div class="phase-code">${week.code}</div>
                <div>
                  <h3>${week.title}</h3>
                  <p>${week.intro}</p>
                </div>
              </div>
              <div class="phase-meta">
                <span>${week.cycle}</span>
                <span>${progressStats.done}/${progressStats.total}</span>
                <div class="phase-progress" title="完成度 ${progressPct}%"><span style="--pct:${progressPct}%"></span></div>
                <span class="phase-status ${weekStatus.className}">${weekStatus.label}</span>
                ${canCollapseWeek ? `
                  <button
                    type="button"
                    class="phase-toggle"
                    data-toggle-week="${week.id}"
                    aria-expanded="${isWeekCollapsed ? "false" : "true"}"
                  >${isWeekCollapsed ? "展开本周" : "收起本周"}</button>
                ` : ""}
              </div>
            </div>
            <div ${isWeekCollapsed ? 'style="display:none;"' : ""}>
              ${week.actions.map((action, index) => {
                const checked = checks[index];
                const anchorExists = !!anchor;
                const disabled = !anchorExists || week.id !== currentWeekId;
                const noteValue = notes[index] || "";
                const currentSubChecks = subChecks[index] || [];
                const currentSubChildChecks = subChildChecks[index] || [];
                const hasSubsteps = (action.substeps || []).length > 0;
                const isCollapsed = !!collapsedWorkflowSteps[`${week.id}-${index}`];
                return `
                  <div class="step ${checked ? "done" : ""} ${disabled ? "disabled" : ""}" data-step-key="${week.id}-${index}">
                    <input
                      type="checkbox"
                      data-week="${week.id}"
                      data-index="${index}"
                      ${checked ? "checked" : ""}
                      ${disabled ? "disabled" : ""}
                    >
                    <div class="step-main">
                      <div class="step-head">
                        <div class="step-title">${action.title}</div>
                        ${hasSubsteps ? `
                          <button
                            type="button"
                            class="step-toggle"
                            data-toggle-step="${week.id}-${index}"
                            aria-expanded="${isCollapsed ? "false" : "true"}"
                          >${isCollapsed ? "展开细项" : "收起细项"}</button>
                        ` : ""}
                      </div>
                      <div class="step-desc">${action.desc}</div>
                      <textarea
                        class="step-note"
                        data-week-note="${week.id}"
                        data-note-index="${index}"
                        placeholder="填写这个动作对应的备注：例如当前卡点、人设方向、反馈结论"
                        ${disabled ? "disabled" : ""}
                      >${escapeHtml(noteValue)}</textarea>
                      ${hasSubsteps && !isCollapsed ? `
                        <div class="substep-list">
                          ${action.substeps.map((substep, subIndex) => `
                            <div class="substep-item">
                              <div class="substep-top">
                                ${isSubstepOptionGroup(substep) ? "" : `
                                  <input
                                    type="checkbox"
                                    data-sub-week="${week.id}"
                                    data-sub-action="${index}"
                                    data-sub-index="${subIndex}"
                                    ${currentSubChecks[subIndex] ? "checked" : ""}
                                    ${disabled ? "disabled" : ""}
                                  >
                                `}
                                <div class="substep-title">${escapeHtml(getSubstepTitle(substep))}</div>
                                ${isSubstepOptionGroup(substep) ? `
                                  <div class="substep-state">${((currentSubChildChecks[subIndex] || []).filter(Boolean).length) ? `已选 ${(currentSubChildChecks[subIndex] || []).filter(Boolean).length} 项` : "未选择"}</div>
                                ` : ""}
                              </div>
                              ${getSubstepChildren(substep).length ? `
                                <div class="subsubstep-list">
                                  ${getSubstepChildren(substep).map((child, childIndex) => `
                                    <div class="subsubstep-item">
                                      <div class="subsubstep-top">
                                        <input
                                          type="checkbox"
                                          data-child-week="${week.id}"
                                          data-child-action="${index}"
                                          data-child-sub="${subIndex}"
                                          data-child-index="${childIndex}"
                                          ${(currentSubChildChecks[subIndex] || [])[childIndex] ? "checked" : ""}
                                          ${disabled ? "disabled" : ""}
                                        >
                                        <div class="subsubstep-title">${escapeHtml(child)}</div>
                                      </div>
                                    </div>
                                  `).join("")}
                                </div>
                              ` : ""}
                              ${isCustomOptionGroup(substep) ? `
                                <div class="custom-option-adder">
                                  <input
                                    type="text"
                                    data-custom-option-input="${week.id}-${index}-${subIndex}"
                                    placeholder="手动添加${escapeHtml(getSubstepTitle(substep))}"
                                    ${anchorExists && week.id !== currentWeekId ? "disabled" : ""}
                                  >
                                  <button
                                    type="button"
                                    class="custom-option-btn"
                                    data-add-custom-option="${week.id}-${index}-${subIndex}"
                                    ${anchorExists && week.id !== currentWeekId ? "disabled" : ""}
                                  >添加</button>
                                </div>
                              ` : ""}
                            </div>
                          `).join("")}
                        </div>
                      ` : ""}
                    </div>
                  </div>
                `;
              }).join("")}
            </div>
          </section>
        `;
      }).join("");

      phaseListEl.querySelectorAll('[data-toggle-week]').forEach((button) => {
        button.addEventListener("click", () => {
          const weekId = Number(button.dataset.toggleWeek);
          collapsedWorkflowWeeks[weekId] = !(collapsedWorkflowWeeks[weekId] !== false);
          renderWorkflow();
        });
      });

      phaseListEl.querySelectorAll('[data-toggle-step]').forEach((button) => {
        button.addEventListener("click", () => {
          const key = button.dataset.toggleStep;
          collapsedWorkflowSteps[key] = !collapsedWorkflowSteps[key];
          renderWorkflow();
        });
      });

      phaseListEl.querySelectorAll("[data-add-custom-option]").forEach((button) => {
        button.addEventListener("click", async () => {
          const [week, actionIndex, subIndex] = button.dataset.addCustomOption.split("-").map(Number);
          const input = phaseListEl.querySelector(`[data-custom-option-input="${button.dataset.addCustomOption}"]`);
          const label = input?.value.trim() || "";
          if (!label) {
            input?.focus();
            return;
          }
          button.disabled = true;
          try {
            await addCustomOption({ week, actionIndex, subIndex, label });
            const substepTitle = getSubstepTitle(weeklyPlan.find((item) => item.id === week)?.actions?.[actionIndex]?.substeps?.[subIndex]);
            if (input) input.value = "";
            renderWorkflow();
            renderSummary();
            renderPlan();
            flashStatus(`已添加${substepTitle || "选项"}：${label}`);
          } catch (err) {
            alert(err.message);
          } finally {
            button.disabled = false;
          }
        });
      });

      phaseListEl.querySelectorAll("[data-custom-option-input]").forEach((input) => {
        input.addEventListener("keydown", (event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          phaseListEl.querySelector(`[data-add-custom-option="${input.dataset.customOptionInput}"]`)?.click();
        });
      });

      phaseListEl.querySelectorAll('input[data-week][data-index]').forEach((input) => {
        input.addEventListener("change", async () => {
          const anchorName = normalizeAnchorName(anchorNameEl.value);
          const liveAnchor = getAnchorRecord(anchorName);
          if (!liveAnchor) {
            input.checked = !input.checked;
            panelAlertEl.className = "panel-alert warn show";
            panelAlertEl.textContent = "请先点 '保存全部动作' 创建主播，再勾选。";
            return;
          }
          const week = Number(input.dataset.week);
          const index = Number(input.dataset.index);
          const prev = liveAnchor.weekActions[week][index];
          pendingStepFeedback = `${week}-${index}`;
          liveAnchor.weekActions[week][index] = input.checked;
          liveAnchor.note = noteTextEl.value.trim();
          liveAnchor.lastSavedDate = TODAY();
          updateAnchorDerivedFields(liveAnchor);
          try {
            await putProgressChecked({
              anchorName,
              week,
              actionIndex: index,
              checked: input.checked,
              note: liveAnchor.weekNotes[week]?.[index] || "",
            });
          } catch (err) {
            liveAnchor.weekActions[week][index] = prev;
            input.checked = prev;
            alert(err.message);
            return;
          }
          saveDraft();
          renderWorkflow();
          renderPlan();
          renderOverview();
          renderSummary();
          renderQuickPicks();
          flashStatus(`已自动保存：${liveAnchor.anchorName} ｜ ${TODAY()} ｜ 第 ${liveAnchor.currentWeek} 周`);
        });
      });

      phaseListEl.querySelectorAll(".step-note").forEach((textarea) => {
        textarea.addEventListener("input", () => {
          const anchor = getAnchorRecord(anchorNameEl.value);
          if (!anchor) return;
          const week = Number(textarea.dataset.weekNote);
          const index = Number(textarea.dataset.noteIndex);
          anchor.weekNotes[week][index] = textarea.value;
          setDirty(
            dirtyKeyFor(anchor.anchorName, week, index),
            textarea.value,
          );
          scheduleStepNoteSave(textarea);
        });

        textarea.addEventListener("blur", () => {
          saveStepNote(textarea);
        });
      });

      phaseListEl.querySelectorAll('[data-sub-week]').forEach((input) => {
        input.addEventListener("change", async () => {
          const anchorName = normalizeAnchorName(anchorNameEl.value);
          const liveAnchor = getAnchorRecord(anchorName);
          if (!liveAnchor) {
            input.checked = !input.checked;
            panelAlertEl.className = "panel-alert warn show";
            panelAlertEl.textContent = "请先点 '保存全部动作' 创建主播，再勾选。";
            return;
          }
          const week = Number(input.dataset.subWeek);
          const actionIndex = Number(input.dataset.subAction);
          const subIndex = Number(input.dataset.subIndex);
          const prev = liveAnchor.weekSubActions[week][actionIndex][subIndex];
          liveAnchor.weekSubActions[week][actionIndex][subIndex] = input.checked;
          liveAnchor.lastSavedDate = TODAY();
          updateAnchorDerivedFields(liveAnchor);
          try {
            await putProgressChecked({
              anchorName, week, actionIndex, subIndex, checked: input.checked,
            });
          } catch (err) {
            liveAnchor.weekSubActions[week][actionIndex][subIndex] = prev;
            input.checked = prev;
            alert(err.message);
            return;
          }
          saveDraft();
          renderWorkflow();
          renderOverview();
          renderSummary();
          flashStatus(`已保存细项动作：${liveAnchor.anchorName} ｜ ${TODAY()}`);
        });
      });

      phaseListEl.querySelectorAll('[data-child-week]').forEach((input) => {
        input.addEventListener("change", async () => {
          const anchorName = normalizeAnchorName(anchorNameEl.value);
          const liveAnchor = getAnchorRecord(anchorName);
          if (!liveAnchor) {
            input.checked = !input.checked;
            panelAlertEl.className = "panel-alert warn show";
            panelAlertEl.textContent = "请先点 '保存全部动作' 创建主播，再勾选。";
            return;
          }
          const week = Number(input.dataset.childWeek);
          const actionIndex = Number(input.dataset.childAction);
          const subIndex = Number(input.dataset.childSub);
          const childIndex = Number(input.dataset.childIndex);
          const prev = liveAnchor.weekSubChildActions[week][actionIndex][subIndex][childIndex];
          liveAnchor.weekSubChildActions[week][actionIndex][subIndex][childIndex] = input.checked;
          liveAnchor.lastSavedDate = TODAY();
          updateAnchorDerivedFields(liveAnchor);
          try {
            await putProgressChecked({
              anchorName, week, actionIndex, subIndex, childIndex, checked: input.checked,
            });
          } catch (err) {
            liveAnchor.weekSubChildActions[week][actionIndex][subIndex][childIndex] = prev;
            input.checked = prev;
            alert(err.message);
            return;
          }
          saveDraft();
          renderWorkflow();
          renderOverview();
          renderSummary();
          flashStatus(`已保存三级细项：${liveAnchor.anchorName} ｜ ${TODAY()}`);
        });
      });

      renderAnchorState(anchor);
      renderWarning(anchor);
      renderPanelAlert(anchor);

      if (pendingStepFeedback) {
        const nextStepEl = phaseListEl.querySelector(`[data-step-key="${pendingStepFeedback}"]`);
        triggerStepFeedback(nextStepEl);
        pendingStepFeedback = null;
      }
    }

    function getWeekStatus(anchor, weekId) {
      if (!anchor) {
        if (weekId === 1) return { label: "当前周", className: "current" };
        return { label: "待开始", className: "wait" };
      }

      const overdue = getDaysInTraining(anchor) > MAX_DAYS && anchor.status !== "已完成";
      if (weekId < anchor.currentWeek) return { label: "已达标", className: "done" };
      if (weekId === anchor.currentWeek) {
        if (overdue) return { label: "已超期", className: "overdue" };
        return { label: "当前周", className: "current" };
      }
      return { label: "待开始", className: "wait" };
    }

    function updateAnchorDerivedFields(anchor) {
      const currentWeek = getCurrentWeekPlan(anchor);
      const checks = anchor.weekActions[anchor.currentWeek] || [];
      let blocker = "大项已勾完，可按培训效果进入下一周";

      for (let actionIndex = 0; actionIndex < currentWeek.actions.length; actionIndex += 1) {
        const action = currentWeek.actions[actionIndex];
        if (!checks[actionIndex]) {
          blocker = action.title;
          break;
        }
      }

      anchor.currentBlocker = blocker;
      anchor.warning = getDaysInTraining(anchor) > MAX_DAYS && anchor.status !== "已完成";
    }

    function renderAnchorState(anchor) {
      if (!anchor) {
        anchorStateBoxEl.innerHTML = `
          <div>当前周次：<strong>第 1 周</strong></div>
          <div>培训天数：<strong>0 天</strong></div>
          <div>当前卡点：<strong>待输入主播名字</strong></div>
        `;
        return;
      }

      updateAnchorDerivedFields(anchor);
      anchorStateBoxEl.innerHTML = `
        <div>当前周次：<strong>第 ${anchor.currentWeek} 周</strong></div>
        <div>培训天数：<strong>${getDaysInTraining(anchor)} 天</strong></div>
        <div>当前卡点：<strong>${escapeHtml(anchor.currentBlocker)}</strong></div>
      `;
    }

    function renderPanelAlert(anchor) {
      if (!anchor) {
        panelAlertEl.className = "panel-alert info show";
        panelAlertEl.textContent = "先选择主播，再按当前周勾选动作。";
        return;
      }

      const currentWeek = getCurrentWeekPlan(anchor);
      const checks = anchor.weekActions[anchor.currentWeek] || [];
      const remainingParentCount = checks.filter((item) => !item).length;

      if (remainingParentCount > 0) {
        panelAlertEl.className = "panel-alert warn show";
        panelAlertEl.textContent = `本周大项还没做完，还差 ${remainingParentCount} 项。先完成大项再推进。`;
        return;
      }

      panelAlertEl.className = "panel-alert info show";
      panelAlertEl.textContent = "当前周大项已勾完，细项可继续补充，也可以直接进入下一周。";
    }

    function triggerStepFeedback(stepEl) {
      if (!stepEl) return;
      stepEl.classList.remove("flash", "check-pop");
      void stepEl.offsetWidth;
      stepEl.classList.add("flash", "check-pop");
      window.setTimeout(() => {
        stepEl.classList.remove("flash", "check-pop");
      }, 760);
    }

    function flashStatus(text) {
      saveTextEl.textContent = text;
      saveTextEl.classList.remove("pop");
      void saveTextEl.offsetWidth;
      saveTextEl.classList.add("pop");
      window.setTimeout(() => {
        saveTextEl.classList.remove("pop");
      }, 360);
    }

    function triggerButtonFeedback(buttonEl) {
      if (!buttonEl) return;
      buttonEl.classList.remove("feedback");
      void buttonEl.offsetWidth;
      buttonEl.classList.add("feedback");
      window.setTimeout(() => {
        buttonEl.classList.remove("feedback");
      }, 580);
    }

    function renderWarning(anchor) {
      if (!anchor) {
        trainingWarnEl.className = "warn-banner";
        trainingWarnEl.textContent = "先输入主播姓名后，系统会显示该主播当前进度与是否超出 4 周标准周期。";
        return;
      }

      const days = getDaysInTraining(anchor);
      if (anchor.warning) {
        trainingWarnEl.className = "warn-banner";
        trainingWarnEl.innerHTML = `时间预警：<strong>${anchor.anchorName}</strong> 已培训 <strong>${days} 天</strong>，超过标准 4 周。当前仍停留在 <strong>第 ${anchor.currentWeek} 周</strong>，请尽快处理卡点：<strong>${escapeHtml(anchor.currentBlocker)}</strong>。`;
      } else {
        trainingWarnEl.className = "info-banner";
        trainingWarnEl.innerHTML = `当前主播：<strong>${anchor.anchorName}</strong> ｜ 培训 <strong>${days} 天</strong> ｜ 当前在 <strong>第 ${anchor.currentWeek} 周</strong>。若本周未达标，动作会继续循环，不会自动推进。`;
      }
    }

    function getStepNoteContext(textarea) {
      const anchor = getAnchorRecord(anchorNameEl.value);
      if (!anchor) return null;
      const week = Number(textarea.dataset.weekNote);
      const actionIndex = Number(textarea.dataset.noteIndex);
      return {
        anchor,
        anchorName: anchor.anchorName,
        week,
        actionIndex,
        dirtyKey: dirtyKeyFor(anchor.anchorName, week, actionIndex),
      };
    }

    function scheduleStepNoteSave(textarea) {
      const ctx = getStepNoteContext(textarea);
      if (!ctx) return;
      window.clearTimeout(stepNoteSaveTimers[ctx.dirtyKey]);
      stepNoteSaveTimers[ctx.dirtyKey] = window.setTimeout(() => {
        saveStepNote(textarea);
      }, 700);
    }

    async function saveStepNote(textarea) {
      const ctx = getStepNoteContext(textarea);
      if (!ctx) return;
      window.clearTimeout(stepNoteSaveTimers[ctx.dirtyKey]);

      const note = textarea.value;
      ctx.anchor.weekNotes[ctx.week][ctx.actionIndex] = note;
      try {
        await putProgressChecked({
          anchorName: ctx.anchorName,
          week: ctx.week,
          actionIndex: ctx.actionIndex,
          note,
        });
        clearDirtyKeys([ctx.dirtyKey]);
        ctx.anchor.lastSavedDate = TODAY();
        renderSummary();
        flashStatus(`已自动保存备注：${ctx.anchorName} ｜ ${TODAY()}`);
      } catch (err) {
        console.error("保存动作备注失败：", err);
        panelAlertEl.className = "panel-alert warn show";
        panelAlertEl.textContent = "备注自动保存失败，请稍后重试或点击保存全部动作。";
      }
    }

    async function putProgressChecked({ anchorName, week, actionIndex, subIndex = -1, childIndex = -1, checked, note }) {
      const body = { week, actionIndex, subIndex, childIndex };
      if (checked !== undefined) body.checked = checked;
      if (note !== undefined) body.note = note;
      const resp = await fetch(
        `${API_BASE}/anchors/${encodeURIComponent(anchorName)}/progress`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (!resp.ok) {
        throw new Error(`PUT /progress 失败：${resp.status}`);
      }
    }

    async function saveProgress() {
      const anchorName = normalizeAnchorName(anchorNameEl.value);
      const operatorName = operatorNameEl.value.trim();

      if (!anchorName || !operatorName) {
        alert("请先填写运营名和主播名。");
        return;
      }

      saveBtnEl.disabled = true;
      try {
        // 1) UPSERT 主播元数据（首次即创建）
        const anchorResp = await fetch(`${API_BASE}/anchors/${encodeURIComponent(anchorName)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            operatorName,
            note: noteTextEl.value,
            currentBlocker: (db.anchors[anchorName]?.currentBlocker) || null,
          }),
        });
        if (!anchorResp.ok) throw new Error(`PUT anchor 失败：${anchorResp.status}`);
        const fullAnchor = await anchorResp.json();
        db.anchors[anchorName] = hydrateAnchorFromServer(fullAnchor);

        // 2) 扫描脏值，批量 PUT /progress
        const dirty = getDirty();
        const flushedKeys = [];
        for (const [key, value] of Object.entries(dirty)) {
          if (!key.startsWith(anchorName + "|")) continue;
          if (key.endsWith(MAIN_NOTE_DIRTY_SUFFIX)) {
            flushedKeys.push(key);  // 主播级 note 已随第 1 步写入
            continue;
          }
          const parts = key.split("|");
          // parts = [anchorName, week, actionIndex, subIndex, childIndex]
          const body = {
            week: Number(parts[1]),
            actionIndex: Number(parts[2]),
            subIndex: Number(parts[3]),
            childIndex: Number(parts[4]),
            note: value,
          };
          const resp = await fetch(
            `${API_BASE}/anchors/${encodeURIComponent(anchorName)}/progress`,
            {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            },
          );
          if (!resp.ok) {
            console.error(`PUT /progress 失败 ${key}`, resp.status);
            continue;  // 保留脏值，下次再试
          }
          flushedKeys.push(key);
        }
        clearDirtyKeys(flushedKeys);

        saveTextEl.textContent = `已保存（${TODAY()}）`;
        panelAlertEl.className = "panel-alert success show";
        panelAlertEl.textContent = "保存成功。";
        renderWorkflow();
        renderPlan();
        renderOverview();
        renderSummary();
        renderQuickPicks();
      } catch (err) {
        console.error(err);
        alert(`保存失败：${err.message}`);
      } finally {
        saveBtnEl.disabled = false;
      }
    }

    async function advanceWeek() {
      const anchorName = normalizeAnchorName(anchorNameEl.value);
      if (!anchorName || !getAnchorRecord(anchorName)) {
        alert("请先保存主播。");
        return;
      }
      if (!confirm(`确认标记 ${anchorName} 本周达标并进入下一周？`)) return;

      try {
        const resp = await fetch(
          `${API_BASE}/anchors/${encodeURIComponent(anchorName)}/advance`,
          { method: "POST" },
        );
        if (!resp.ok) throw new Error(`POST /advance 失败：${resp.status}`);
        const fullAnchor = await resp.json();
        db.anchors[anchorName] = hydrateAnchorFromServer(fullAnchor);
        renderOverview();
        renderWorkflow();
        renderPlan();
        renderSummary();
      } catch (err) {
        alert(err.message);
      }
    }

    function renderOverview() {
      const anchors = Object.values(db.anchors);
      const active = anchors.filter((anchor) => anchor.status !== "已完成");
      const warning = anchors.filter((anchor) => anchor.warning).length;
      const completed = anchors.filter((anchor) => anchor.status === "已完成").length;
      const averageDays = anchors.length
        ? Math.round(anchors.reduce((sum, anchor) => sum + getDaysInTraining(anchor), 0) / anchors.length)
        : 0;

      overviewGridEl.innerHTML = [
        { label: "在训主播", value: active.length, desc: "当前仍在推进的主播", className: "active" },
        { label: "超期预警", value: warning, desc: "超过 28 天仍未完成", className: "warning" },
        { label: "已完成", value: completed, desc: "已完成四周标准计划", className: "done" },
        { label: "平均天数", value: averageDays, desc: "主播平均培训周期", className: "days" }
      ].map((item) => `
        <div class="overview-card ${item.className}">
          <div class="label">${item.label}</div>
          <div class="value">${item.value}</div>
          <div class="desc">${item.desc}</div>
        </div>
      `).join("");

      sidebarCountEl.textContent = `${anchors.length} 个主播在跟进`;
    }

    function renderQuickPicks() {
      const anchors = Object.values(db.anchors);
      const operatorNames = Array.from(new Set(anchors.map((item) => item.operatorName).filter(Boolean))).slice(0, 6);
      const anchorNames = anchors
        .sort((a, b) => new Date(b.lastSavedDate || "1970-01-01") - new Date(a.lastSavedDate || "1970-01-01"))
        .map((item) => item.anchorName)
        .filter(Boolean)
        .slice(0, 6);

      operatorSuggestionsEl.innerHTML = operatorNames.map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");
      anchorSuggestionsEl.innerHTML = anchorNames.map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");

      operatorQuickPicksEl.innerHTML = operatorNames.map((name) => `<button class="quick-chip" type="button" data-operator="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("");
      anchorQuickPicksEl.innerHTML = anchorNames.map((name) => `<button class="quick-chip" type="button" data-anchor="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("");

      operatorQuickPicksEl.querySelectorAll("[data-operator]").forEach((button) => {
        button.addEventListener("click", () => {
          operatorNameEl.value = button.dataset.operator;
          saveDraft();
          flashStatus(`已选择运营：${button.dataset.operator}`);
        });
      });

      anchorQuickPicksEl.querySelectorAll("[data-anchor]").forEach((button) => {
        button.addEventListener("click", () => {
          anchorNameEl.value = button.dataset.anchor;
          selectedWorkflowWeek = null;
          syncFormFromExistingAnchor();
          saveDraft();
          renderWorkflow();
          renderPlan();
          flashStatus(`已选择主播：${button.dataset.anchor}`);
        });
      });
    }

    function renderAnchorWeeksDetail(anchor) {
      return weeklyPlan.map((week) => {
        const actions = anchor.weekActions?.[week.id] || week.actions.map(() => false);
        const notes = anchor.weekNotes?.[week.id] || week.actions.map(() => "");
        const subActions = anchor.weekSubActions?.[week.id] || week.actions.map((action) => (action.substeps || []).map(() => false));
        const subNotes = anchor.weekSubNotes?.[week.id] || week.actions.map((action) => (action.substeps || []).map(() => ""));
        const subChildActions = anchor.weekSubChildActions?.[week.id] || week.actions.map((action) => (action.substeps || []).map((substep) => getSubstepChildren(substep).map(() => false)));
        const subChildNotes = anchor.weekSubChildNotes?.[week.id] || week.actions.map((action) => (action.substeps || []).map((substep) => getSubstepChildren(substep).map(() => "")));
        const completedCount = actions.filter(Boolean).length;

        return `
          <section class="summary-week">
            <div class="summary-week-head">
              <h4>${week.title}</h4>
              <span>${completedCount}/${week.actions.length}</span>
            </div>
            <div class="summary-action-list">
              ${week.actions.map((action, index) => `
                <div class="summary-action-item">
                  <div class="summary-action-top">
                    <div class="summary-action-title">${index + 1}. ${escapeHtml(action.title)}</div>
                    <span class="summary-action-state ${actions[index] ? "done" : "todo"}">${actions[index] ? "已完成" : "未完成"}</span>
                  </div>
                  <div class="summary-action-desc">${escapeHtml(action.desc)}</div>
                  <div class="summary-action-note">${escapeHtml(notes[index] || "暂无备注")}</div>
                  ${(action.substeps || []).length ? `
                    <div class="substep-list">
                      ${action.substeps.map((substep, subIndex) => `
                        <div class="substep-item">
                          <div class="summary-action-top">
                            <div class="summary-action-title">${index + 1}.${subIndex + 1} ${escapeHtml(getSubstepTitle(substep))}</div>
                            <span class="summary-action-state ${(subActions[index] || [])[subIndex] ? "done" : "todo"}">${(subActions[index] || [])[subIndex] ? "已完成" : "未完成"}</span>
                          </div>
                          ${getSubstepChildren(substep).length ? `
                            <div class="subsubstep-list">
                              ${getSubstepChildren(substep).map((child, childIndex) => `
                                <div class="subsubstep-item">
                                  <div class="summary-action-top">
                                    <div class="summary-action-title">${index + 1}.${subIndex + 1}.${childIndex + 1} ${escapeHtml(child)}</div>
                                    <span class="summary-action-state ${(((subChildActions[index] || [])[subIndex] || [])[childIndex]) ? "done" : "todo"}">${(((subChildActions[index] || [])[subIndex] || [])[childIndex]) ? "已完成" : "未完成"}</span>
                                  </div>
                                </div>
                              `).join("")}
                            </div>
                          ` : ""}
                        </div>
                      `).join("")}
                    </div>
                  ` : ""}
                </div>
              `).join("")}
            </div>
          </section>
        `;
      }).join("");
    }

    function filterSummaryAnchors() {
      const keyword = summaryKeywordEl.value.trim().toLowerCase();
      const statusKeyword = summaryStatusEl.value.trim().toLowerCase();
      const operatorKeyword = summaryOperatorEl.value.trim().toLowerCase();

      return Object.values(db.anchors).filter((anchor) => {
        const trainingState = anchor.warning ? "已超期" : `第 ${anchor.currentWeek} 周`;
        const keywordMatched = !keyword || [
          anchor.anchorName,
          anchor.operatorName,
          anchor.currentBlocker,
          anchor.note
        ].some((text) => String(text || "").toLowerCase().includes(keyword));
        const statusMatched = !statusKeyword || trainingState.toLowerCase().includes(statusKeyword);
        const operatorMatched = !operatorKeyword || String(anchor.operatorName || "").toLowerCase().includes(operatorKeyword);
        return keywordMatched && statusMatched && operatorMatched;
      });
    }

    function getWeekProgressStats(anchor, week) {
      const actionChecks = anchor?.weekActions?.[week.id] || week.actions.map(() => false);
      const subChecks = anchor?.weekSubActions?.[week.id] || week.actions.map((action) => (action.substeps || []).map(() => false));
      const childChecks = anchor?.weekSubChildActions?.[week.id] || week.actions.map((action) => (action.substeps || []).map((substep) => getSubstepChildren(substep).map(() => false)));
      const actionDone = actionChecks.filter(Boolean).length;
      const subDone = subChecks.reduce((sum, items) => sum + items.filter(Boolean).length, 0);
      const childDone = childChecks.reduce((sum, actionItems) => (
        sum + actionItems.reduce((childSum, childItems) => childSum + childItems.filter(Boolean).length, 0)
      ), 0);
      const total = week.actions.length
        + week.actions.reduce((sum, action) => sum + (action.substeps || []).length, 0)
        + week.actions.reduce((sum, action) => sum + (action.substeps || []).reduce((childSum, substep) => childSum + getSubstepChildren(substep).length, 0), 0);

      return {
        done: actionDone + subDone + childDone,
        total
      };
    }

    function renderAnchorTimeline(anchor) {
      return `
        <div class="summary-timeline">
          ${weeklyPlan.map((week) => {
            const stats = getWeekProgressStats(anchor, week);
            const isCurrent = week.id === anchor.currentWeek;
            const isDone = week.id < anchor.currentWeek || (anchor.status === "已完成" && week.id === 4);
            const isFuture = week.id > anchor.currentWeek;
            const statusClass = isCurrent ? (anchor.warning ? "overdue" : "current") : (isDone ? "done" : "todo");
            const statusText = isCurrent ? (anchor.warning ? "超期" : "进行中") : (isDone ? "已达标" : "待开始");
            const hint = isCurrent
              ? `已完成 ${stats.done}/${stats.total}${stats.done < stats.total ? `，当前卡点：${escapeHtml(anchor.currentBlocker)}` : "，可推进下一周"}`
              : (isDone ? `这一周已通过，完成 ${stats.done}/${stats.total}` : `还没开始，标准动作 ${stats.total} 项`);
            return `
              <div class="timeline-week ${statusClass}">
                <div class="timeline-top">
                  <span class="timeline-code">${week.code}</span>
                  <span class="timeline-state">${statusText}</span>
                </div>
                <div class="timeline-title">${escapeHtml(week.title.replace("第 ", "").replace(" 周 · ", " · "))}</div>
                <div class="timeline-metric">${stats.done}/${stats.total}</div>
                <div class="timeline-hint">${hint}</div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    }

    function renderSummary() {
      const anchors = filterSummaryAnchors();
      if (!anchors.length) {
        summaryGridEl.innerHTML = '<div class="empty">当前没有匹配的主播汇总数据。</div>';
        return;
      }

      summaryGridEl.innerHTML = anchors
        .sort((a, b) => {
          if (a.warning !== b.warning) return a.warning ? -1 : 1;
          return new Date(b.lastSavedDate || "1970-01-01") - new Date(a.lastSavedDate || "1970-01-01");
        })
        .map((anchor) => `
          <article class="summary-card ${anchor.status === "已完成" ? "done" : ""} ${expandedSummaryAnchor === anchor.anchorName ? "expanded" : ""}" data-summary-anchor="${escapeHtml(anchor.anchorName)}">
            <div class="summary-top">
              <div>
                <div class="summary-title">${escapeHtml(anchor.anchorName)}</div>
                <div class="summary-subtitle">运营：${escapeHtml(anchor.operatorName)} ｜ 最近填报：${escapeHtml(anchor.lastSavedDate || "未保存")}</div>
              </div>
              <div class="summary-meta">
                <span class="meta-pill">${anchor.warning ? "已超期" : `第 ${anchor.currentWeek} 周`}</span>
                <span class="meta-pill">${anchor.status}</span>
                <button
                  type="button"
                  class="summary-delete-btn"
                  data-delete-anchor="${escapeHtml(anchor.anchorName)}"
                  aria-label="删除 ${escapeHtml(anchor.anchorName)}"
                >删除</button>
              </div>
            </div>
            ${
              (() => {
                const week = weeklyPlan.find((item) => item.id === anchor.currentWeek) || weeklyPlan[0];
                const stats = getWeekProgressStats(anchor, week);
                const pct = stats.total ? Math.round((stats.done / stats.total) * 100) : 0;
                return `<div class="summary-progress" title="当前周完成度 ${pct}%"><span style="--pct:${pct}%"></span></div>`;
              })()
            }
            <div class="summary-body">
              <div class="summary-cell">
                <span class="mini">当前周次</span>
                <strong>第 ${anchor.currentWeek} 周</strong>
              </div>
              <div class="summary-cell">
                <span class="mini">培训天数</span>
                <strong>${getDaysInTraining(anchor)} 天</strong>
              </div>
              <div class="summary-cell">
                <span class="mini">当前卡点</span>
                <strong>${escapeHtml(anchor.currentBlocker)}</strong>
              </div>
              <div class="summary-cell">
                <span class="mini">当前周完成</span>
                <strong>${
                  (() => {
                    const week = weeklyPlan.find((item) => item.id === anchor.currentWeek);
                    const actionDone = (anchor.weekActions[anchor.currentWeek] || []).filter(Boolean).length;
                    const subDone = (anchor.weekSubActions?.[anchor.currentWeek] || []).reduce((sum, items) => sum + items.filter(Boolean).length, 0);
                    const childDone = (anchor.weekSubChildActions?.[anchor.currentWeek] || []).reduce((sum, actionItems) => (
                      sum + actionItems.reduce((childSum, childItems) => childSum + childItems.filter(Boolean).length, 0)
                    ), 0);
                    const total = week.actions.length
                      + week.actions.reduce((sum, action) => sum + (action.substeps || []).length, 0)
                      + week.actions.reduce((sum, action) => sum + (action.substeps || []).reduce((childSum, substep) => childSum + getSubstepChildren(substep).length, 0), 0);
                    return `${actionDone + subDone + childDone}/${total}`;
                  })()
                }</strong>
              </div>
            </div>
            ${renderAnchorTimeline(anchor)}
            <div class="summary-note">${escapeHtml(anchor.note || "暂无备注")}</div>
            <div class="summary-expand-tip">${expandedSummaryAnchor === anchor.anchorName ? "再次点击可收起" : "点击查看这个老师每一周的所有动作"}</div>
            ${expandedSummaryAnchor === anchor.anchorName ? `
              <div class="summary-detail">
                ${renderAnchorWeeksDetail(anchor)}
              </div>
            ` : ""}
          </article>
        `).join("");

      summaryGridEl.querySelectorAll("[data-summary-anchor]").forEach((card) => {
        card.addEventListener("click", () => {
          const anchorName = card.dataset.summaryAnchor;
          expandedSummaryAnchor = expandedSummaryAnchor === anchorName ? null : anchorName;
          renderSummary();
        });
      });

      summaryGridEl.querySelectorAll("[data-delete-anchor]").forEach((button) => {
        button.addEventListener("click", async (event) => {
          event.stopPropagation();
          const anchorName = button.dataset.deleteAnchor;
          if (!confirm(`确认删除主播「${anchorName}」？删除后该主播的所有进度记录也会一起删除。`)) return;

          button.disabled = true;
          try {
            const resp = await fetch(`${API_BASE}/anchors/${encodeURIComponent(anchorName)}`, {
              method: "DELETE",
            });
            if (!resp.ok) throw new Error(`删除失败：${resp.status}`);

            delete db.anchors[anchorName];
            if (expandedSummaryAnchor === anchorName) expandedSummaryAnchor = null;
            if (normalizeAnchorName(anchorNameEl.value) === anchorName) {
              anchorNameEl.value = "";
              noteTextEl.value = "";
            }
            renderOverview();
            renderWorkflow();
            renderSummary();
            renderQuickPicks();
            flashStatus(`已删除主播：${anchorName}`);
          } catch (err) {
            alert(err.message);
          } finally {
            button.disabled = false;
          }
        });
      });
    }

    function renderPlan() {
      const anchor = getAnchorRecord(anchorNameEl.value);
      const currentWeekId = anchor?.currentWeek || 1;

      planGridEl.innerHTML = weeklyPlan.map((week) => {
        const status = getWeekStatus(anchor, week.id);
        const stats = getWeekProgressStats(anchor, week);
        const pct = stats.total ? Math.round((stats.done / stats.total) * 100) : 0;
        const checks = anchor?.weekActions?.[week.id] || week.actions.map(() => false);
        const notes = anchor?.weekNotes?.[week.id] || week.actions.map(() => "");
        const cardClass = week.id === currentWeekId ? "current" : (week.id < currentWeekId || (anchor?.status === "已完成" && week.id === 4) ? "done" : "wait");

        return `
          <section class="plan-card plan-exec-card ${cardClass}">
            <div class="plan-card-head">
              <div>
                <div class="plan-card-code">${week.code}</div>
                <h3>${week.title}</h3>
                <p>${week.intro}</p>
              </div>
              <div class="plan-card-status">
                <span class="phase-status ${status.className}">${status.label}</span>
                <strong>${stats.done}/${stats.total}</strong>
                <div class="phase-progress" title="完成度 ${pct}%"><span style="--pct:${pct}%"></span></div>
              </div>
            </div>
            <div class="plan-action-list">
              ${week.actions.map((action, index) => {
                const checked = !!checks[index];
                const noteValue = notes[index] || "";
                const children = (action.substeps || []).map((substep) => {
                  const title = getSubstepTitle(substep);
                  const childLabels = getSubstepChildren(substep);
                  if (childLabels.length) {
                    return `${title}：${childLabels.slice(0, 4).join(" / ")}${childLabels.length > 4 ? " ..." : ""}`;
                  }
                  return title;
                });

                return `
                  <div class="plan-action-row ${checked ? "done" : ""}" data-plan-step-key="${week.id}-${index}">
                    <label class="plan-check">
                      <input
                        type="checkbox"
                        data-plan-week="${week.id}"
                        data-plan-index="${index}"
                        ${checked ? "checked" : ""}
                        ${anchor ? "" : "disabled"}
                      >
                      <span></span>
                    </label>
                    <div class="plan-action-copy">
                      <div class="plan-action-title">${index + 1}. ${escapeHtml(action.title)}</div>
                      <p>${escapeHtml(action.desc)}</p>
                      ${children.length ? `
                        <div class="plan-subitem-strip">
                          ${children.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
                        </div>
                      ` : ""}
                    </div>
                    <textarea
                      class="step-note plan-action-note"
                      data-week-note="${week.id}"
                      data-note-index="${index}"
                      placeholder="运营记录：执行情况、卡点、反馈结论..."
                      ${anchor ? "" : "disabled"}
                    >${escapeHtml(noteValue)}</textarea>
                  </div>
                `;
              }).join("")}
            </div>
          </section>
        `;
      }).join("");

      bindPlanMapInteractions();
    }

    function bindPlanMapInteractions() {
      planGridEl.querySelectorAll("[data-plan-week][data-plan-index]").forEach((input) => {
        input.addEventListener("change", async () => {
          const anchorName = normalizeAnchorName(anchorNameEl.value);
          const liveAnchor = getAnchorRecord(anchorName);
          if (!liveAnchor) {
            input.checked = !input.checked;
            panelAlertEl.className = "panel-alert warn show";
            panelAlertEl.textContent = "请先填写运营和主播，并点击“保存主播”。";
            return;
          }

          const week = Number(input.dataset.planWeek);
          const index = Number(input.dataset.planIndex);
          const prev = liveAnchor.weekActions[week][index];
          liveAnchor.weekActions[week][index] = input.checked;
          liveAnchor.note = noteTextEl.value.trim();
          liveAnchor.lastSavedDate = TODAY();
          updateAnchorDerivedFields(liveAnchor);

          try {
            await putProgressChecked({
              anchorName,
              week,
              actionIndex: index,
              checked: input.checked,
              note: liveAnchor.weekNotes[week]?.[index] || "",
            });
          } catch (err) {
            liveAnchor.weekActions[week][index] = prev;
            input.checked = prev;
            alert(err.message);
            return;
          }

          saveDraft();
          renderPlan();
          renderWorkflow();
          renderOverview();
          renderSummary();
          renderQuickPicks();
          flashStatus(`已保存：${liveAnchor.anchorName} ｜ ${weeklyPlan.find((item) => item.id === week)?.title || `第 ${week} 周`} ｜ 第 ${index + 1} 项`);
        });
      });

      planGridEl.querySelectorAll(".plan-action-note").forEach((textarea) => {
        textarea.addEventListener("input", () => {
          const anchor = getAnchorRecord(anchorNameEl.value);
          if (!anchor) return;
          const week = Number(textarea.dataset.weekNote);
          const index = Number(textarea.dataset.noteIndex);
          anchor.weekNotes[week][index] = textarea.value;
          setDirty(dirtyKeyFor(anchor.anchorName, week, index), textarea.value);
          scheduleStepNoteSave(textarea);
        });

        textarea.addEventListener("blur", () => {
          saveStepNote(textarea);
        });
      });
    }

    function exportCsv() {
      const anchors = Object.values(db.anchors);
      const rows = [
        ["记录类型", "主播名字", "运营名字", "开始日期", "最近填报", "当前周次", "培训天数", "状态", "是否超期", "当前卡点", "总备注", "已完成路径汇总", "最后完成项", "步骤周次", "步骤序号", "步骤名称", "步骤说明", "是否完成", "步骤备注"]
      ];

      anchors.forEach((anchor) => {
        const completedPaths = [];
        const completedDetails = [];

        weeklyPlan.forEach((week) => {
          const weekActions = anchor.weekActions?.[week.id] || week.actions.map(() => false);
          const weekNotes = anchor.weekNotes?.[week.id] || week.actions.map(() => "");
          const weekSubActions = anchor.weekSubActions?.[week.id] || week.actions.map((action) => (action.substeps || []).map(() => false));
          const weekSubNotes = anchor.weekSubNotes?.[week.id] || week.actions.map((action) => (action.substeps || []).map(() => ""));
          const weekSubChildActions = anchor.weekSubChildActions?.[week.id] || week.actions.map((action) => (action.substeps || []).map((substep) => getSubstepChildren(substep).map(() => false)));
          const weekSubChildNotes = anchor.weekSubChildNotes?.[week.id] || week.actions.map((action) => (action.substeps || []).map((substep) => getSubstepChildren(substep).map(() => "")));

          week.actions.forEach((action, index) => {
            if (weekActions[index]) {
              const path = `${week.title} / ${index + 1}. ${action.title}`;
              completedPaths.push(path);
              completedDetails.push({
                weekLabel: week.title,
                stepCode: `${index + 1}`,
                stepName: action.title,
                stepDesc: action.desc,
                note: weekNotes[index] || ""
              });
            }

            (action.substeps || []).forEach((substep, subIndex) => {
              if ((weekSubActions[index] || [])[subIndex]) {
                const path = `${week.title} / ${index + 1}.${subIndex + 1} ${action.title} / ${getSubstepTitle(substep)}`;
                completedPaths.push(path);
                completedDetails.push({
                  weekLabel: week.title,
                  stepCode: `${index + 1}.${subIndex + 1}`,
                  stepName: `${action.title} / ${getSubstepTitle(substep)}`,
                  stepDesc: "",
                  note: (weekSubNotes[index] || [])[subIndex] || ""
                });
              }

              getSubstepChildren(substep).forEach((child, childIndex) => {
                if ((((weekSubChildActions[index] || [])[subIndex] || [])[childIndex])) {
                  const path = `${week.title} / ${index + 1}.${subIndex + 1}.${childIndex + 1} ${action.title} / ${getSubstepTitle(substep)} / ${child}`;
                  completedPaths.push(path);
                  completedDetails.push({
                    weekLabel: week.title,
                    stepCode: `${index + 1}.${subIndex + 1}.${childIndex + 1}`,
                    stepName: `${action.title} / ${getSubstepTitle(substep)} / ${child}`,
                    stepDesc: "",
                    note: (((weekSubChildNotes[index] || [])[subIndex] || [])[childIndex]) || ""
                  });
                }
              });
            });
          });
        });

        rows.push([
          "汇总",
          anchor.anchorName,
          anchor.operatorName,
          anchor.startDate,
          anchor.lastSavedDate || "",
          `第 ${anchor.currentWeek} 周`,
          `${getDaysInTraining(anchor)}`,
          anchor.status,
          anchor.warning ? "是" : "否",
          anchor.currentBlocker,
          anchor.note || "",
          completedPaths.join("；"),
          completedPaths[completedPaths.length - 1] || "",
          "",
          "",
          "",
          "",
          "",
          ""
        ]);

        completedDetails.forEach((detail) => {
          rows.push([
            "明细",
            anchor.anchorName,
            anchor.operatorName,
            anchor.startDate,
            anchor.lastSavedDate || "",
            `第 ${anchor.currentWeek} 周`,
            `${getDaysInTraining(anchor)}`,
            anchor.status,
            anchor.warning ? "是" : "否",
            anchor.currentBlocker,
            anchor.note || "",
            "",
            "",
            detail.weekLabel,
            detail.stepCode,
            detail.stepName,
            detail.stepDesc,
            "已完成",
            detail.note
          ]);
        });
      });

      const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
      const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `主播带新汇总-${TODAY()}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      flashStatus("CSV 已导出。");
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function bindLiveFields() {
      [operatorNameEl, anchorNameEl].forEach((el) => {
        el.addEventListener("input", () => {
          const anchor = getAnchorRecord(anchorNameEl.value);
          if (anchor) {
            anchor.operatorName = operatorNameEl.value.trim() || anchor.operatorName;
            updateAnchorDerivedFields(anchor);
            saveDb();
          }
          if (el === anchorNameEl) syncFormFromExistingAnchor();
          if (el === anchorNameEl) selectedWorkflowWeek = null;
          saveDraft();
          renderWorkflow();
          renderPlan();
          renderOverview();
          renderSummary();
          renderQuickPicks();
        });
      });

      noteTextEl.addEventListener("input", () => {
        const name = normalizeAnchorName(anchorNameEl.value);
        if (!name) return;
        const anchor = getAnchorRecord(name);
        if (!anchor) return;
        anchor.note = noteTextEl.value;
        setDirty(name + MAIN_NOTE_DIRTY_SUFFIX, noteTextEl.value);
      });

      [summaryKeywordEl, summaryStatusEl, summaryOperatorEl].forEach((el) => {
        el.addEventListener("input", renderSummary);
      });

      document.getElementById("clearSummaryFilterBtn").addEventListener("click", () => {
        summaryKeywordEl.value = "";
        summaryStatusEl.value = "";
        summaryOperatorEl.value = "";
        renderSummary();
      });

      document.getElementById("saveBtn").addEventListener("click", saveProgress);
      document.getElementById("advanceBtn").addEventListener("click", advanceWeek);
      document.getElementById("exportBtn").addEventListener("click", exportCsv);
    }

    window.addEventListener("DOMContentLoaded", async () => {
      await initCustomOptions();
      await initFromServer();
      loadDraft();
      renderWorkflow();
      renderOverview();
      renderSummary();
      renderPlan();
      renderQuickPicks();
      bindLiveFields();
    });
