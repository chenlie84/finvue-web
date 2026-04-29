(function () {
  const cache = {
    entries: {}
  };

  function formatPercent(value, digits = 1) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return `${(number * 100).toFixed(digits)}%`;
  }

  function formatSignedPercent(value, digits = 1) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    const prefix = number > 0 ? "+" : "";
    return `${prefix}${(number * 100).toFixed(digits)}%`;
  }

  function formatCompactNumber(value, digits = 0) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return new Intl.NumberFormat("zh-CN", {
      notation: "compact",
      maximumFractionDigits: digits
    }).format(number);
  }

  function formatDateTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    }).format(date);
  }

  async function fetchWeekly(options = {}) {
    const { force = false, start = "", end = "" } = options;
    const now = Date.now();
    const cacheKey = `${start || "-"}:${end || "-"}`;
    const cached = cache.entries[cacheKey];
    if (!force && cached && now - cached.fetchedAt < 60_000) {
      return cached.payload;
    }

    const params = new URLSearchParams();
    if (force) params.set("force", "1");
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const query = params.toString();
    const response = await fetch(`/api/anchor-dashboard/weekly${query ? `?${query}` : ""}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "读取主播大盘数据失败");
    }
    cache.entries[cacheKey] = {
      payload,
      fetchedAt: now
    };
    return payload;
  }

  window.AnchorDashboardApi = {
    fetchWeekly,
    formatPercent,
    formatSignedPercent,
    formatCompactNumber,
    formatDateTime,
    getCachedPayload() {
      const keys = Object.keys(cache.entries);
      if (!keys.length) return null;
      return cache.entries[keys[0]]?.payload || null;
    },
    clearCache() {
      cache.entries = {};
    }
  };
})();
