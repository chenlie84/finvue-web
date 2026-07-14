(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const num = (value) => Number(value || 0).toLocaleString("zh-CN");

  let loaded = false;

  function setStatus(message, kind = "") {
    const el = $("dataCollectionStatus");
    if (!el) return;
    el.textContent = message;
    el.className = `data-collection-status ${kind}`;
  }

  function metric(label, value) {
    return `<div class="data-collection-metric"><span>${esc(label)}</span><b>${esc(value)}</b></div>`;
  }

  function fileRow(label, value) {
    return value ? `<div class="data-collection-file"><span>${esc(label)}</span><code>${esc(value)}</code></div>` : "";
  }

  function downloadButton(url) {
    return url ? `<a class="data-collection-download" href="${esc(url)}" target="_blank" rel="noopener">下载音频 m4a</a>` : "";
  }

  function commentsButton(url) {
    return url ? `<a class="data-collection-download secondary" href="${esc(url)}" target="_blank" rel="noopener">下载评论 JSON</a>` : "";
  }

  function profileButton(url) {
    return url ? `<a class="data-collection-profile-link" href="${esc(url)}" target="_blank" rel="noopener">打开主页</a>` : "";
  }

  function splitTags(value) {
    return String(value || "").split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean);
  }

  function renderResult(data) {
    const info = data.info || {};
    const author = info.author || {};
    const stats = info.statistics || {};
    const music = info.music || {};
    const video = info.video || {};
    const risk = info.risk_infos || {};
    const files = data.files || {};
    const comments = data.comments || info.comments || {};
    $("dataCollectionResult").innerHTML = `
      <div class="data-collection-profile">
        ${author.avatar ? `<img src="${esc(author.avatar)}" alt="">` : "<div></div>"}
        <div>
          <h3>${esc(author.nickname || "未知博主")}</h3>
          <p>抖音号：${esc(author.unique_id || author.short_id || "--")}</p>
        </div>
        ${profileButton(author.profile_url)}
      </div>
      <h2>${esc(info.desc || "未识别标题")}</h2>
      <div class="data-collection-tags">${(info.hashtags || []).map((item) => `<span>${esc(item)}</span>`).join("")}</div>
      <div class="data-collection-metrics">
        ${metric("点赞", num(stats.digg_count))}
        ${metric("评论", num(stats.comment_count))}
        ${metric("收藏", num(stats.collect_count))}
        ${metric("转发", num(stats.share_count))}
      </div>
      <div class="data-collection-info-grid">
        <div><span>视频 ID</span><b>${esc(info.aweme_id || "--")}</b></div>
        <div><span>尺寸</span><b>${esc(video.width || "--")} x ${esc(video.height || "--")}</b></div>
        <div><span>时长</span><b>${video.duration_ms ? Math.round(video.duration_ms / 1000) + " 秒" : "--"}</b></div>
        <div><span>音乐</span><b>${esc(music.title || "--")}</b></div>
      </div>
      ${risk.content ? `<div class="data-collection-risk">风险提示：${esc(risk.content)}</div>` : ""}
      <div class="data-collection-comment-status ${comments.ok || comments.collected ? "ok" : "warn"}">
        评论采集：${comments.ok || comments.collected ? `已保存 ${num((comments.comments || []).length || comments.count)} 条` : `未抓到明细，已保留评论数；${esc(comments.error || "接口可能需要风控参数")}`}
      </div>
      ${downloadButton(info.audio_download_url)}
      ${commentsButton(info.comments_download_url)}
      <div class="data-collection-files">
        ${fileRow("结构化信息", files.info)}
        ${fileRow("评论明细", files.comments)}
        ${fileRow("分享页 HTML", files.shareHtml)}
        ${fileRow("播放地址", files.playUrl)}
      </div>
    `;
  }

  function renderCreators(items) {
    const el = $("dataCollectionCreators");
    const count = $("dataCollectionCreatorCount");
    if (count) count.textContent = items.length ? `${items.length} 位主播` : "";
    if (!el) return;
    if (!items.length) {
      el.innerHTML = '<div class="data-collection-empty">暂无主播记录。采集视频后会自动沉淀到这里。</div>';
      return;
    }
    el.innerHTML = items.map((item) => {
      const videos = item.videos || [];
      const latest = videos[0] || {};
      const tags = (item.tags || []).join("，");
      return `
        <article class="data-collection-creator-card" data-creator-id="${esc(item.id)}">
          <div class="data-collection-creator-main">
            ${item.avatar ? `<img src="${esc(item.avatar)}" alt="">` : "<div></div>"}
            <div>
              <h4>${esc(item.nickname || "未知主播")}</h4>
              <p>抖音号：${esc(item.uniqueId || item.shortId || "--")} · 视频 ${num(item.videoCount || videos.length || 0)} 条</p>
              ${item.signature ? `<p class="data-collection-creator-sign">${esc(item.signature)}</p>` : ""}
            </div>
          </div>
          <div class="data-collection-creator-actions">
            ${profileButton(item.profileUrl)}
            ${latest.awemeId ? `<a href="/api/data-collection/douyin/${esc(latest.awemeId)}/audio" target="_blank" rel="noopener">最新音频</a>` : ""}
            ${latest.commentsDownloadUrl ? `<a href="${esc(latest.commentsDownloadUrl)}" target="_blank" rel="noopener">评论下载</a>` : ""}
          </div>
          <div class="data-collection-creator-form">
            <label>分类<input value="${esc(item.category || "")}" data-field="category" placeholder="如：宏观/短线/产业链/情绪"></label>
            <label>标签<input value="${esc(tags)}" data-field="tags" placeholder="逗号或空格分隔"></label>
            <label>备注<textarea rows="2" data-field="note" placeholder="记录风格、可靠度、适合跟踪的方向">${esc(item.note || "")}</textarea></label>
            <button class="btn btn-outline" type="button" onclick="window.FinVueDataCollection?.saveCreator?.('${esc(encodeURIComponent(item.id || ""))}')">保存标签</button>
          </div>
          ${latest.title ? `<div class="data-collection-creator-latest">最近视频：${esc(latest.title)}</div>` : ""}
        </article>
      `;
    }).join("");
  }

  function renderRecent(items) {
    const el = $("dataCollectionRecent");
    if (!el) return;
    if (!items.length) {
      el.innerHTML = '<div class="data-collection-empty">暂无采集记录。</div>';
      return;
    }
    el.innerHTML = items.map((item) => `
      <article class="data-collection-recent-item">
        <div>
          <h4>${esc(item.title || item.awemeId)}</h4>
          <p>${esc(item.author || "未知博主")} · ${esc(item.awemeId || "")}</p>
          <p>评论明细：${item.commentsCollected ? `${num(item.commentsCount)} 条` : "未抓到/未采集"}</p>
        </div>
        <div class="data-collection-recent-files">
          ${item.creatorProfileUrl ? `<a href="${esc(item.creatorProfileUrl)}" target="_blank" rel="noopener">主页</a>` : ""}
          ${item.audioDownloadUrl ? `<a href="${esc(item.audioDownloadUrl)}" target="_blank" rel="noopener">音频下载</a>` : ""}
          ${item.commentsDownloadUrl ? `<a href="${esc(item.commentsDownloadUrl)}" target="_blank" rel="noopener">评论下载</a>` : ""}
          <span>JSON</span>
        </div>
      </article>
    `).join("");
  }

  async function load() {
    try {
      const [recentRes, creatorsRes] = await Promise.all([
        fetch("/api/data-collection/recent", { credentials: "include" }),
        fetch("/api/data-collection/creators", { credentials: "include" }),
      ]);
      const recentData = await recentRes.json().catch(() => ({}));
      const creatorsData = await creatorsRes.json().catch(() => ({}));
      if (!recentRes.ok || recentData.ok === false) throw new Error(recentData.error || recentData.detail || "读取采集记录失败");
      if (!creatorsRes.ok || creatorsData.ok === false) throw new Error(creatorsData.error || creatorsData.detail || "读取主播库失败");
      $("dataCollectionRoot").textContent = recentData.root ? `保存目录：${recentData.root}` : "";
      renderCreators(creatorsData.items || []);
      renderRecent(recentData.items || []);
      loaded = true;
    } catch (error) {
      renderCreators([]);
      renderRecent([]);
      setStatus(error.message, "error");
    }
  }

  async function saveCreator(encodedId) {
    const creatorId = decodeURIComponent(encodedId || "");
    const card = document.querySelector(`.data-collection-creator-card[data-creator-id="${CSS.escape(creatorId)}"]`);
    if (!card) return;
    const category = card.querySelector('[data-field="category"]')?.value || "";
    const tags = splitTags(card.querySelector('[data-field="tags"]')?.value || "");
    const note = card.querySelector('[data-field="note"]')?.value || "";
    try {
      const res = await fetch(`/api/data-collection/creators/${encodeURIComponent(creatorId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ category, tags, note }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || data.detail || "保存失败");
      setStatus("主播标签已保存。", "ok");
      await load();
      window.showToast?.("主播标签已保存");
    } catch (error) {
      setStatus(`保存失败：${error.message}`, "error");
      window.showToast?.(`保存失败：${error.message}`);
    }
  }

  async function collect() {
    const source = $("dataCollectionSource")?.value?.trim();
    if (!source) {
      setStatus("请先粘贴抖音分享链接或视频 ID。", "error");
      return;
    }
    const btn = $("dataCollectionRunBtn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "采集中...";
    }
    setStatus("正在解析公开分享页并保存结构化信息，不会保存音频文件。", "loading");
    try {
      const res = await fetch("/api/data-collection/douyin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ source }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || data.detail || "采集失败");
      renderResult(data);
      setStatus("采集完成。已记录博主与视频信息；音频可通过按钮直接下载。", "ok");
      await load();
      window.showToast?.("数据采集完成");
    } catch (error) {
      setStatus(`采集失败：${error.message}`, "error");
      window.showToast?.(`采集失败：${error.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "开始采集";
      }
    }
  }

  window.FinVueDataCollection = {
    load: () => load(),
    collect,
    saveCreator,
    ensureLoaded: () => {
      if (!loaded) load();
    },
  };
})();
