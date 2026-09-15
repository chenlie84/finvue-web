# 独立客户端使用说明

`docs/eastmoney_cls_client.py` 是从 FinVue-Web 仓库内**抽离出的自包含客户端**，可以**拷贝到任意项目**独立使用，**不依赖** FinVue 的 `db` / `config` / `main.py` / `scripts` / 任何 MySQL / 任何对象存储。

## 1. 准备

仅需两个第三方依赖：

```bash
pip install requests pandas
```

## 2. 命令行使用

文件自带 argparse 子命令（无需任何额外环境变量）：

```bash
# 概念+行业板块 K 线（带 SEED_BOARDS 兜底，并发+预算控制）
python docs/eastmoney_cls_client.py boards --date 20260623 --limit 120 --out boards.csv

# 龙虎榜
python docs/eastmoney_cls_client.py lhb --date 20260623 --out lhb.csv

# 板块成分股
python docs/eastmoney_cls_client.py constituents --code BK0890 --limit 600

# 财联社热搜（newsnow 聚合）
python docs/eastmoney_cls_client.py cls --limit 30 --out cls.csv
python docs/eastmoney_cls_client.py cls --no-proxy --base-url https://newsnow.busiyi.world/api/s
```

输出会直接 `print` 到 stdout，同时如果指定 `--out` 会落盘为 CSV。

## 3. 编程使用

```python
from eastmoney_cls_client import EastMoneyClient, CLSClient

# ---------- 东方财富 ----------
em = EastMoneyClient(
    board_fetch_seconds=60,    # 板块 K 线总预算（默认 110）
    board_fetch_workers=8,     # 并发线程
    lhb_page_size=500,         # 龙虎榜单页
    proxy="http://127.0.0.1:7890",  # 可选代理
)

# 1) 板块/股票列表
concepts = em.list_concept_boards(page_size=200)
industries = em.list_industry_boards(page_size=200)
constituents = em.list_constituents("BK0890", page_size=600)

# 2) 单个板块/个股 K 线
k = em.board_kline_on_date("BK0890", "20260623")
print(k)  # {code, name, date, open, close, pct_chg, amount, ...}

# 3) 并发拉所有候选板块 K 线（带 SEED_BOARDS 兜底）
df = em.fetch_boards_kline(
    trade_date="20260623",
    per_type_limit=120,
    progress_cb=lambda stage, fields: print(stage, fields),
)
print(df.head())

# 4) 龙虎榜
lhb = em.lhb("20260623")
print(lhb[["ts_code", "name", "pct_change", "net_amount", "reason"]].head())
```

```python
# ---------- 财联社（通过 newsnow 聚合） ----------
import os
os.environ["NEWSNOW_NO_PROXY"] = "1"  # 强制直连

cls = CLSClient()  # 默认 https://newsnow.busiyi.world/api/s
hot = cls.fetch(limit=30)
for item in hot:
    print(f"{item['rank']:>3}. {item['title']}  {item['url']}")
```

## 4. 暴露的 API 一览

| 类/函数 | 方法 | 用途 |
| --- | --- | --- |
| `EastMoneyClient` | `clist(fs, page_size)` | 拉板块/股票列表，原始 `f12/f14/...` 字段 |
| | `list_concept_boards(page_size)` | 概念板块列表 |
| | `list_industry_boards(page_size)` | 行业板块列表 |
| | `list_constituents(board_code, page_size)` | 板块成分股 |
| | `kline(code, trade_date, secid_prefix)` | 任意标的日 K 线 |
| | `board_kline_on_date(board_code, trade_date)` | 板块日 K 线便捷方法 |
| | `fetch_boards_kline(trade_date, ...)` | 并发拉概念+行业板块 K 线，含 SEED_BOARDS 兜底 |
| | `lhb(trade_date)` | 龙虎榜汇总（无营业部明细） |
| `CLSClient` | `fetch(latest=True, limit=50)` | 财联社热搜列表（已适配 newsnow 三种返回格式） |
| `SEED_BOARDS` | — | 15 个兜底板块常量（与原脚本一致） |
| `iso_date()` / `ymd()` | — | 日期格式工具 |

## 5. 环境变量

| 变量 | 含义 | 默认 |
| --- | --- | --- |
| `EASTMONEY_TIMEOUT_SECONDS` | 东方财富主请求超时 | 5 |
| `EASTMONEY_FALLBACK_TIMEOUT_SECONDS` | 备用直连超时 | 7 |
| `BOARD_FETCH_SECONDS` | 板块 K 线总预算 | 110 |
| `BOARD_FETCH_WORKERS` | 板块 K 线并发线程 | 16 |
| `EASTMONEY_LHB_PAGE_SIZE` | 龙虎榜单页 | 500 |
| `NEWSNOW_BASE_URL` | newsnow 聚合地址 | `https://newsnow.busiyi.world/api/s` |
| `NEWSNOW_NO_PROXY=1` | 财联社请求强制直连 | 未设置 |
| `http_proxy` / `HTTP_PROXY` | 财联社请求代理 | 未设置 |

## 6. 与 FinVue 内的差异

1. **去掉了 `db`/`config`/`main.py` 依赖**——不再有 MySQL 写入和调度器。
2. **`fetch_boards_kline` 现在支持 `progress_cb` 回调**，方便外部项目接到自己的日志/进度通道；不再用 `print` 到 stderr。
3. **保留原行为**：Referer 头、备用直连、SEED_BOARDS 兜底、龙虎榜自动翻页、`is not None` 路径兼容。
4. **没有拆出 `services/feishu_push.py` 那套加权**，因为那是 FinVue 业务层（`hotspot_stock_matcher.py` 里 `cls` 平台 `score *= 12.0`）；外部项目若需要，自行加权即可。

## 7. 直接拷贝策略

最简方案：把 `docs/eastmoney_cls_client.py` 整个文件复制到目标项目 `utils/` 下，`pip install requests pandas` 后即可 `from utils.eastmoney_cls_client import EastMoneyClient, CLSClient`。
