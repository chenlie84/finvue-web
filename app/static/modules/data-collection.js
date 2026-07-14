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

  function renderResult(data) {
    const info = data.info || {};
    const author = info.author || {};
    const stats = info.statistics || {};
    const music = info.music || {};
    const video = info.video || {};
    const risk = info.risk_infos || {};
    const files = data.files || {};
    $("dataCollectionResult").innerHTML = `
      <div class="data-collection-profile">
        ${author.avatar ? `<img src="${esc(author.avatar)}" alt="">` : "<div></div>"}
        <div>
          <h3>${esc(author.nickname || "未知博主")}</h3>
          <p>抖音号：${esc(author.unique_id || author.short_id || "--")}</p>
        </div>
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
      ${downloadButton(info.audio_download_url)}
      <div class="data-collection-files">
        ${fileRow("结构化信息", files.info)}
        ${fileRow("分享页 HTML", files.shareHtml)}
        ${fileRow("播放地址", files.playUrl)}
      </div>
    `;
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
        </div>
        <div class="data-collection-recent-files">
          ${item.audioDownloadUrl ? `<a href="${esc(item.audioDownloadUrl)}" target="_blank" rel="noopener">音频下载</a>` : ""}
          <span>JSON</span>
        </div>
      </article>
    `).join("");
  }

  async function load() {
    try {
      const res = await fetch("/api/data-collection/recent", { credentials: "include" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || data.detail || "读取采集记录失败");
      $("dataCollectionRoot").textContent = data.root ? `保存目录：${data.root}` : "";
      renderRecent(data.items || []);
      loaded = true;
    } catch (error) {
      renderRecent([]);
      setStatus(error.message, "error");
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
    ensureLoaded: () => {
      if (!loaded) load();
    },
  };
})();
