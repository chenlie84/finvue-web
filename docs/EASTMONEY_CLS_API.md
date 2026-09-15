# 东方财富 & 财联社 接口说明文档

> 本文档梳理 FinVue-Web 仓库内对**东方财富（EastMoney）**和**财联社（CLS）**两个数据源的所有 HTTP 接口调用点，包括端点地址、请求参数、返回字段、调用代码位置和降级策略。

---

## 1. 总览

| 数据源 | 用途 | 调用方式 | 鉴权 | 主调用方 |
| --- | --- | --- | --- | --- |
| 东方财富 | 行情快照、板块 K 线、龙虎榜、成分股 | HTTPS GET 公共接口 | 无（需 Referer） | `scripts/generate_daily_market_review.py` |
| 财联社 | 实时财经电报、热搜（仅作为引用/榜单） | 间接通过 newsnow 聚合 API | 无 | `services/hotspot_fetcher.py` |

> **说明**：FinVue 自身**不直接调用财联社官方接口**。财联社数据在仓库内出现两次：① 热搜聚合 API（`newsnow.busiyi.world`）将 `cls` 作为平台 ID 返回热门电报标题；② 行情复盘日报读取 `cls_news_*.csv` 历史文件作为"专业财经新闻证据"补充。前者实为 newsnow，后者是离线落盘数据。

---

## 2. 东方财富（EastMoney）

东方财富接口由 `scripts/generate_daily_market_review.py` 在 TuShare 板块日线、龙虎榜不可用时降级调用，**无任何鉴权**但需设置正确 `Referer` 头，否则会被反爬拦截。

### 2.1 基础地址常量

文件：`scripts/generate_daily_market_review.py` L37–L43

```python
EASTMONEY_CLIST     = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE     = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_DATACENTER= "https://datacenter-web.eastmoney.com/api/data/v1/get"

HEADERS = {
    "Referer":    "https://quote.eastmoney.com/",
    "User-Agent": "Mozilla/5.0",
}
```

### 2.2 `clist/get` — 板块/股票列表

代码位置：`eastmoney_clist(fs, pz=500)` L365–L379

| 项目 | 说明 |
| --- | --- |
| Method | `GET` |
| URL | `https://push2.eastmoney.com/api/qt/clist/get` |
| Headers | `Referer: https://quote.eastmoney.com/`, `User-Agent: Mozilla/5.0` |
| 超时 | 主 5s，备用 7s（环境变量 `DAILY_MARKET_REVIEW_EASTMONEY_TIMEOUT_SECONDS` / `DAILY_MARKET_REVIEW_EASTMONEY_FALLBACK_TIMEOUT_SECONDS`） |

请求参数（Query String）：

| 参数 | 含义 | 取值 |
| --- | --- | --- |
| `pn` | 页码 | 1 |
| `pz` | 单页条数 | 默认 500（成分股场景用 600） |
| `po` | 排序方向 | 1 降序 |
| `np` | 翻页协议 | 1 |
| `fltt` | 字段类型 | 2 |
| `invt` | 数值精度 | 2 |
| `fid` | 排序字段 | `f3`（涨跌幅） |
| `fs` | 过滤条件 | 见下表 |
| `fields` | 返回字段集合 | `f12,f14,f2,f3,f4,f5,f6,f20,f62,f128,f136,f140,f141,f152` |

`fs` 过滤条件编码（东方财富内部代号）：

| 场景 | `fs` 取值 | 含义 |
| --- | --- | --- |
| 概念板块 | `m:90+t:3` | 行情中心概念板块 |
| 行业板块 | `m:90+t:2` | 行情中心行业板块 |
| 板块成分股 | `b:{board_code}` | 例如 `b:BK0890` |

返回字段说明（`f` 前缀）：

| 字段 | 含义 |
| --- | --- |
| f12 | 代码（6 位） |
| f14 | 名称 |
| f2  | 最新价 |
| f3  | 涨跌幅（%） |
| f4  | 涨跌额 |
| f5  | 成交量（手） |
| f6  | 成交额（元） |
| f20 | 总市值 |
| f62 | 主力净流入 |
| f128 | 板块成分股数 |
| f136 | 板块涨跌幅 |
| f140 | 板块领涨股代码 |
| f141 | 板块领涨股涨幅 |
| f152 | 板块换手率 |

代码调用上下文：

- L537：`fetch_boards_for_date` 降级逻辑中调用 `eastmoney_clist(fs, pz=limit_each_type)` 拉取概念/行业板块列表。
- L589：`board_constituents` 调用 `eastmoney_clist(f"b:{board_code}", pz=600)` 拉取板块成分股。

### 2.3 `stock/kline/get` — 板块/股票 K 线

代码位置：`board_kline_on_date(code, trade_date)` L382–L411

| 项目 | 说明 |
| --- | --- |
| Method | `GET` |
| URL | `https://push2his.eastmoney.com/api/qt/stock/kline/get` |
| secid 规则 | `90.{board_code}`（板块以 `90.` 前缀） |

请求参数：

| 参数 | 含义 | 取值 |
| --- | --- | --- |
| `secid` | 板块/股票 ID | 板块 `90.{BK代码}` |
| `fields1` | 头部信息字段 | `f1,f2,f3,f4,f5,f6` |
| `fields2` | K 线字段 | `f51..f61`（日期、开盘、收盘、最高、最低、成交量、成交额、振幅、涨跌幅、涨跌额、换手率） |
| `klt` | K 线周期 | `101`（日线） |
| `fqt` | 复权方式 | `1`（前复权） |
| `beg` / `end` | 起止日期 | 形如 `20260623`（yyyyMMdd） |

返回结构（节选自代码解析）：

```python
{
    "board_code": "BK0890",
    "board_name": "MLCC",
    "date":      "2026-06-23",
    "open":      ..., "close": ..., "high": ..., "low": ...,
    "volume":    ..., "amount": ...,
    "amplitude": ..., "pct_chg": ..., "change": ...,
    "turnover":  ...,
}
```

代码调用上下文：

- `fetch_board_kline_rows`（L462–L511）：用 `ThreadPoolExecutor`（默认 16 线程，env `DAILY_MARKET_REVIEW_BOARD_FETCH_WORKERS`）并发拉取所有候选板块指定交易日的 K 线。`source` 字段会写为 `"东方财富降级源"` 或 `"东方财富种子板块降级源"`。
- 板块降级流程：先 `eastmoney_clist` 拿种子板块，再并发抓 K 线；若都失败，最后用 `SEED_BOARDS`（15 个预置板块，如 MLCC、被动元件、钨、玻纤、碳化硅等）再次单点抓取。

### 2.4 `datacenter-web/data/v1/get` — 龙虎榜数据中心

代码位置：`eastmoney_lhb(trade_date)` L703–L773

| 项目 | 说明 |
| --- | --- |
| Method | `GET` |
| URL | `https://datacenter-web.eastmoney.com/api/data/v1/get` |
| reportName | `RPT_DAILYBILLBOARD_DETAILS` |
| 翻页 | 自动按 `result.pages` 翻页（最多 100 页） |
| 单页条数 | 默认 500（env `DAILY_MARKET_REVIEW_EASTMONEY_LHB_PAGE_SIZE`） |

请求参数：

| 参数 | 取值 |
| --- | --- |
| `sortColumns` | `TRADE_DATE,SECURITY_CODE` |
| `sortTypes` | `-1,1`（日期降序，代码升序） |
| `pageSize` | 500 |
| `pageNumber` | 1..N |
| `reportName` | `RPT_DAILYBILLBOARD_DETAILS` |
| `columns` | 见下表 |
| `filter` | `(TRADE_DATE='{iso_trade_date}')`，日期为 `yyyy-MM-dd` 形式（`iso_date` 函数转换） |

请求 `columns` 列表：

```
SECURITY_CODE, SECUCODE, SECURITY_NAME_ABBR, TRADE_DATE, EXPLAIN,
CLOSE_PRICE, CHANGE_RATE, BILLBOARD_NET_AMT, BILLBOARD_BUY_AMT,
BILLBOARD_SELL_AMT, BILLBOARD_DEAL_AMT, ACCUM_AMOUNT, DEAL_NET_RATIO,
TURNOVERRATE, FREE_MARKET_CAP
```

输出标准化（写入 `pd.DataFrame` 的列）：

| 字段 | 来源 | 含义 |
| --- | --- | --- |
| trade_date | TRADE_DATE | 交易日 |
| ts_code | SECUCODE | 带后缀的 TuShare 代码（`.SH/.SZ/.BJ`） |
| name | SECURITY_NAME_ABBR | 简称 |
| close | CLOSE_PRICE | 收盘价 |
| pct_change | CHANGE_RATE | 涨跌幅 |
| amount | BILLBOARD_DEAL_AMT | 龙虎榜成交额 |
| net_amount | BILLBOARD_NET_AMT | 龙虎榜净买额 |
| buy / sell | BILLBOARD_BUY_AMT / BILLBOARD_SELL_AMT | 买入/卖出额 |
| reason | EXPLAIN | 上榜原因 |
| source | 固定 `"东方财富龙虎榜"` | 来源标记 |

代码上下文：

- L1630–L1640：在 TuShare `top_list` 返回空时调用 `eastmoney_lhb`，并把 `lhb_source` 写为 `"东方财富龙虎榜"`；同时通过 `progress` 推送 `lhb:fallback:eastmoney:start/done/failed` 事件。
- 备注：东方财富公共接口**不直接返回营业部席位明细**，所以 `aggregate_seats` 仍依赖 TuShare `top_inst`。

### 2.5 降级与重试策略

`request_get`（L414–L432）：

1. 主请求用 `SESSION`（trust_env=False，避免被环境代理污染），超时 5s，失败 1 次重试。
2. 重试失败后切换到 `requests.get(..., proxies=None)` 直连，超时 7s。
3. 仍失败抛出 `RuntimeError`，由调用方捕获后写 `progress("...:failed", error_code="eastmoney_xxx_unavailable")`。

板块 K 线总抓取预算（env `DAILY_MARKET_REVIEW_BOARD_FETCH_SECONDS`，默认 110s）：

- 超过预算立即停止拉取，已抓到行数直接进入排序。
- 候选列表为空 → 用 `SEED_BOARDS` 兜底单点拉取，再失败则该日复盘直接报错。

---

## 3. 财联社（CLS）

### 3.1 财联社热搜（通过 newsnow 聚合 API）

仓库不直接访问 `cls.cn`。财联社热搜由 newsnow 公共聚合 API 统一对外提供，FinVue 仅作为消费方。

配置入口：`config.py` L121–L124

```python
# 设置 HOTSPOT_API_ENABLED=true 启用自动抓取
# 数据源使用 newsnow.busiyi.world（与 TrendRadar 项目一致的稳定 API）
HOTSPOT_API_ENABLED = os.environ.get("HOTSPOT_API_ENABLED", "false").lower() == "true"
HOTSPOT_API_URL     = os.environ.get("HOTSPOT_API_URL", "https://newsnow.busiyi.world/api/s")
```

| 项目 | 说明 |
| --- | --- |
| Method | `GET` |
| URL | `{HOTSPOT_API_URL}?id={platform_id}&latest` |
| 默认 URL | `https://newsnow.busiyi.world/api/s?id=cls&latest` |
| Headers | `User-Agent: Chrome/120`, `Accept-Language: zh-CN` |
| 代理 | 默认走 `http_proxy` / `HTTP_PROXY`，可通过 `HOTSPOT_NO_PROXY=1` 强制直连 |

平台 ID 映射（`services/hotspot_fetcher.py` L30–L42）：

```python
PLATFORM_ID_MAP = {
    "weibo": "weibo", "zhihu": "zhihu", "baidu": "baidu",
    "douyin": "douyin", "bilibili": "bilibili", "toutiao": "toutiao",
    "cls": "cls",                # ← 财联社
    "wallstreetcn": "wallstreetcn-hot",
    ...
}
```

响应格式兼容三种（`_fetch_via_api` L376–L454）：

1. **新格式**：`{"status": "cache", "id": "cls", "items": [{id, title, url, mobileUrl, extra}]}`
2. **旧格式**：`{"code": 200, "data": [...]}`
3. **newsnow 嵌套格式**：`{"cls": {"标题1": {"ranks": [1], "url": "...", "mobileUrl": "..."}, ...}}`

`direct fetch`（财联社本身**不**在 `DIRECT_FETCH_PLATFORMS` 中）：

- 直接爬取仅覆盖：weibo / baidu / douyin / zhihu / bilibili / toutiao。
- 财联社、华尔街见闻、凤凰、澎湃、贴吧等均走外部 newsnow API 兜底。

调用流程（`fetch_all_platforms` → `fetch_platform_hotspots` → `_fetch_via_api`）：

1. 读取 `config.HOTSPOT_API_ENABLED`，关闭时直接短路返回。
2. 使用 `ThreadPoolExecutor(max_workers=10)` 并发抓取。
3. `_assess_platform_freshness` 判定"陈旧缓存"：若前 10 条均无新标题且 `first_seen_at` 超过 6 小时，则跳过入库（避免标题时间被错标为"刚刚"）。
4. `save_hotspot_items` 写入 MySQL `finvue_hotspot_items` / `finvue_hotspot_snapshots`，并在 `appearance_count` 上做累加。

调度：

- `services/hotspot_scheduler.py` 每分钟轮询 `finvue_hotspot_settings.fetch_interval_minutes`，到期调用 `fetch_all_platforms(platforms)`。
- `main.py` L50 在启动时若 `HOTSPOT_API_ENABLED=true` 且 `ENV != "test"` 立即抓一轮。

### 3.2 财联社新闻文件（离线落盘）

行情复盘日报 `scripts/generate_daily_market_review.py` L1321–L1384 中的 `read_news(trade_date, boards)` 优先尝试读取 `STOCK_PROJECT/data/raw/news/` 下的：

```
cls_news_{trade_date}.csv
cls_news_latest.csv
```

约定列：`title, url, published_at, platform, analysis` 等（`as_of_date` 形如 `20260623`，函数会做 `replace("-", "")` 比对）。

筛选关键词（`keywords`，L1356）：

```
AI|硬件|MLCC|MPO|CPO|PCB|钨|钼|锗|有色|龙虎榜|服务器|光通信|六氟化钨
```

如文件缺失或 `title` 命中为空，回退到"行情线索"占位行（`platform="market-review"`, `source` 来自 `board.source`），并通过 `progress("news:fallback:boards", fallback_reason="cls_news_file_missing")` 上报。

### 3.3 财联社在"金融优先级"中的角色

`scripts/generate_daily_market_review.py` L1341：

```python
frame["financePriority"] = frame["platform"].isin(["cls", "wallstreetcn"]).astype(int)
```

排序时 `["relevance", "financePriority", "published_at"]` 全部降序，确保**财联社与华尔街见闻的内容**在新闻区获得更高排序。`api/market.py` L189、AI 归因接口同样把 `cls` 命名为"财联社"作为消息面"专业财经"来源。

`services/hotspot_stock_matcher.py`（L59）把 `PROFESSIONAL_PLATFORMS = {"cls", "wallstreetcn"}` 视为"专业财经平台"，在 `score` 上乘以 `12.0`（L291），是最高的加权倍率。

### 3.4 引用 & 链接

- `app/static/modules/releases.js` L927：注释"专业财经热搜仅保留财联社和华尔街见闻作为证据补充"。
- `app/static/modules/hotspot.js` / `app/hotspot.html`：`cls: { name: '财联社', icon: '■' }`。
- `sql/migrations/20260519_001_hotspot.sql` L82：在 `finvue_hotspot_platforms` 中插入 `('cls', '财联社', 'finance', '💰', 7)`（`7` 是 UI 排序权重）。
- `scripts/generate_daily_market_review.py` L109–L119 的 `SOURCE_LINKS` 中包含两条财联社原文链接：
  - `https://www.cls.cn/detail/2400185`（AI 硬件/CPO/MPO 线索）
  - `https://www.cls.cn/detail/2396144`（双星新材 MLCC 离型膜反证）

---

## 4. 调用矩阵（速查表）

| 场景 | 数据源 | 端点 | 文件:行 | 触发条件 |
| --- | --- | --- | --- | --- |
| 概念/行业板块列表 | 东方财富 | `push2.eastmoney.com/api/qt/clist/get` | `generate_daily_market_review.py:365` | TuShare `ths_daily` 为空 |
| 板块成分股 | 东方财富 | `push2.eastmoney.com/api/qt/clist/get` (`b:{code}`) | `generate_daily_market_review.py:589` | 拉成分股（500 优先 → 600 兜底） |
| 板块日 K 线 | 东方财富 | `push2his.eastmoney.com/api/qt/stock/kline/get` | `generate_daily_market_review.py:382` | 同上，预算内并发抓取 |
| 种子板块兜底 K 线 | 东方财富 | 同上 | `generate_daily_market_review.py:550` | 主流程全部失败 |
| 龙虎榜 | 东方财富 | `datacenter-web.eastmoney.com/api/data/v1/get` | `generate_daily_market_review.py:703` | TuShare `top_list` 为空 |
| 财联社热搜 | newsnow 聚合 | `{HOTSPOT_API_URL}?id=cls&latest` | `services/hotspot_fetcher.py:333` | 定时调度 + 手动刷新 |
| 财联社新闻 | 本地 csv | `STOCK_PROJECT/data/raw/news/cls_news_*.csv` | `generate_daily_market_review.py:1347` | 复盘日报生成时 |
| 行情 AI 归因 | 财联社（仅做展示名映射） | 无直调 | `api/market.py:189` | `/api/market/ai-attribution` |

---

## 5. 相关环境变量

| 变量 | 含义 | 默认 |
| --- | --- | --- |
| `HOTSPOT_API_ENABLED` | 是否启用热搜抓取（含财联社） | `false` |
| `HOTSPOT_API_URL` | newsnow 聚合地址 | `https://newsnow.busiyi.world/api/s` |
| `HOTSPOT_NO_PROXY=1` | 热搜请求强制直连，绕开 `http_proxy` | 未设置 |
| `DAILY_MARKET_REVIEW_EASTMONEY_TIMEOUT_SECONDS` | 东方财富主请求超时 | 5 |
| `DAILY_MARKET_REVIEW_EASTMONEY_FALLBACK_TIMEOUT_SECONDS` | 东方财富备用请求超时 | 7 |
| `DAILY_MARKET_REVIEW_EASTMONEY_LHB_PAGE_SIZE` | 龙虎榜单页条数 | 500 |
| `DAILY_MARKET_REVIEW_BOARD_FETCH_SECONDS` | 板块 K 线总预算秒 | 110 |
| `DAILY_MARKET_REVIEW_BOARD_FETCH_WORKERS` | 板块 K 线并发线程 | 16 |
| `http_proxy` / `HTTP_PROXY` | 热搜抓取代理（默认带） | — |

---

## 6. 风险与注意事项

1. **东方财富反爬**：`Referer` 必须为 `https://quote.eastmoney.com/`，否则会返回 200 但 `data.diff` 为空。脚本里所有东方财富请求都强制带该头。
2. **龙虎榜席位缺失**：东方财富 `RPT_DAILYBILLBOARD_DETAILS` 不返回营业部明细，机构 / 股通净买仍依赖 TuShare `top_inst`，否则会显示空。
3. **板块数据源优先级**：`TuShare ths_daily → 东方财富 clist+kline → SEED_BOARDS 单点抓取`，任意一层失败都靠下一层兜底，最终失败会通过 `progress("...:failed", error_code=...)` 上报。
4. **newsnow 第三方依赖**：`HOTSPOT_API_URL` 是公共聚合服务，可用性非 FinVue 可控；若该地址挂掉，财联社热搜会进入 `failedPlatforms`，但 `wallstreetcn` 走 `_fetch_wallstreetcn_direct` 直接拉取仍可工作。
5. **财联社文件来源**：`cls_news_*.csv` 需要外部 30_Quant/stock_analysis 项目提前落盘；缺失时复盘会自动降级为"行情线索"占位行，并在 `progress` 中打 `fallback_reason="cls_news_file_missing"`。
6. **代理与 trust_env**：`SESSION.trust_env = False` 避免 Python `requests` 自动读取环境代理影响东方财富调用；但热搜 `_fetch_via_api` 默认会读 `http_proxy`，需要 `HOTSPOT_NO_PROXY=1` 关闭。

---

## 7. 相关代码索引

- `scripts/generate_daily_market_review.py` — 行情复盘生成脚本（东方财富全部调用入口）
- `services/hotspot_fetcher.py` — 多平台热搜抓取与入库
- `services/hotspot_scheduler.py` — 热搜定时调度
- `services/hotspot_stock_matcher.py` — 热搜与股票匹配（含财联社加权）
- `api/market.py` — 行情与 AI 归因（财联社作为展示名）
- `api/hotspot.py` — 热搜接口（财联社作为可选平台）
- `config.py` — `HOTSPOT_API_*` 读取
- `sql/migrations/20260519_001_hotspot.sql` — `finvue_hotspot_platforms` 表
- `app/static/modules/hotspot.js` / `app/hotspot.html` — 前端平台映射 `cls → 财联社`
- `docs/` — 现有文档目录（本文件归入此目录）
