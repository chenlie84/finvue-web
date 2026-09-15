"""
东方财富 & 财联社 (newsnow) 独立客户端
=========================================

从 FinVue-Web 仓库 `scripts/generate_daily_market_review.py` 与
`services/hotspot_fetcher.py` 抽离出的自包含客户端，不依赖项目内
任何数据库/配置/调度器，可直接拷贝到其他项目使用。

提供：

- ``EastMoneyClient``  : 板块列表、板块/股票 K 线、龙虎榜
- ``CLSClient``        : 财联社热搜（走 newsnow 公共聚合 API）

依赖：
    pip install requests pandas
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import pandas as pd
import requests

warnings.filterwarnings("ignore", message=r"urllib3 .*doesn't match a supported version.*")

logger = logging.getLogger("eastmoney_cls")


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

EASTMONEY_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"

DEFAULT_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": "Mozilla/5.0",
}

# 行情中心板块分类代号
FS_CONCEPT = "m:90+t:3"
FS_INDUSTRY = "m:90+t:2"


@dataclass(frozen=True)
class SeedBoard:
    """TuShare 板块日线不可用时的兜底种子板块（与原脚本 SEED_BOARDS 一致）。"""

    code: str
    name: str
    type: str  # "概念" or "行业"


SEED_BOARDS: tuple[SeedBoard, ...] = (
    SeedBoard("BK0890", "MLCC", "概念"),
    SeedBoard("BK0976", "被动元件概念", "概念"),
    SeedBoard("BK0459", "元件", "行业"),
    SeedBoard("BK1625", "钨", "行业"),
    SeedBoard("BK1623", "钼", "行业"),
    SeedBoard("BK1027", "小金属", "行业"),
    SeedBoard("BK1462", "玻纤制造", "行业"),
    SeedBoard("BK0546", "玻璃玻纤", "行业"),
    SeedBoard("BK1592", "通信线缆及配套", "行业"),
    SeedBoard("BK1327", "分立器件", "行业"),
    SeedBoard("BK1328", "集成电路封测", "行业"),
    SeedBoard("BK1339", "被动元件", "行业"),
    SeedBoard("BK0977", "碳化硅", "概念"),
    SeedBoard("BK1113", "复合集流体", "概念"),
    SeedBoard("BK0703", "超级电容", "概念"),
)


# ---------------------------------------------------------------------------
# 通用请求工具
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    try:
        value = int(float(os.getenv(name, str(default))))
    except Exception:
        value = default
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def iso_date(date_text: str | datetime) -> str:
    """``yyyyMMdd`` 或 ``datetime`` -> ``yyyy-MM-dd``。"""
    if isinstance(date_text, datetime):
        return date_text.strftime("%Y-%m-%d")
    return pd.Timestamp(str(date_text)).strftime("%Y-%m-%d")


def ymd(date_text: str | datetime) -> str:
    """``yyyyMMdd`` 或 ``datetime`` -> ``yyyyMMdd``。"""
    if isinstance(date_text, datetime):
        return date_text.strftime("%Y%m%d")
    return pd.Timestamp(str(date_text)).strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# 东方财富
# ---------------------------------------------------------------------------


@dataclass
class EastMoneyClient:
    """东方财富公共接口客户端（无鉴权，仅需正确 Referer）。

    Parameters
    ----------
    primary_timeout, fallback_timeout:
        主请求与备用直连请求的超时（秒）。可通过环境变量
        ``EASTMONEY_TIMEOUT_SECONDS`` / ``EASTMONEY_FALLBACK_TIMEOUT_SECONDS`` 覆盖。
    board_fetch_seconds:
        并发抓板块 K 线的总预算（秒）。原脚本默认 110。
    board_fetch_workers:
        并发抓板块 K 线的线程数。
    lhb_page_size:
        龙虎榜单页条数。
    session:
        可选 ``requests.Session``。若不传则使用默认 ``trust_env=False`` 会话。
    proxy:
        可选代理，例如 ``http://127.0.0.1:7890``。留空则走环境变量或直连。
    """

    primary_timeout: float = field(default_factory=lambda: float(_env_int("EASTMONEY_TIMEOUT_SECONDS", 5, 1, 60)))
    fallback_timeout: float = field(default_factory=lambda: float(_env_int("EASTMONEY_FALLBACK_TIMEOUT_SECONDS", 7, 1, 60)))
    board_fetch_seconds: int = field(default_factory=lambda: _env_int("BOARD_FETCH_SECONDS", 110, 10, 600))
    board_fetch_workers: int = field(default_factory=lambda: _env_int("BOARD_FETCH_WORKERS", 16, 1, 64))
    lhb_page_size: int = field(default_factory=lambda: _env_int("EASTMONEY_LHB_PAGE_SIZE", 500, 50, 2000))
    session: requests.Session | None = None
    proxy: str | None = None

    def __post_init__(self) -> None:
        self._owns_session = self.session is None
        if self.session is None:
            self.session = requests.Session()
            self.session.trust_env = False
        self._proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

    # ------------------------------------------------------------------
    # 内部：HTTP 封装（主请求 + 备用直连）
    # ------------------------------------------------------------------
    def _request(self, url: str, params: dict[str, Any], headers: dict[str, str] | None = None) -> requests.Response:
        hdrs = {**DEFAULT_HEADERS, **(headers or {})}
        last_error: Exception | None = None

        # 第一次：使用主 session（可能携带代理）
        try:
            resp = self.session.get(
                url,
                params=params,
                headers=hdrs,
                timeout=self.primary_timeout,
                proxies=self._proxies,
            )
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_error = exc
            logger.debug("eastmoney primary request failed: %s", exc)

        # 第二次：强制直连
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=self.fallback_timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_error = exc

        raise RuntimeError(f"Eastmoney request failed after retry: {last_error}")

    # ------------------------------------------------------------------
    # 板块 / 股票列表
    # ------------------------------------------------------------------
    def clist(self, fs: str, page_size: int = 500) -> pd.DataFrame:
        """``fs`` 过滤条件拉板块/股票列表。返回原始字段（``f12, f14, f2, ...``）。"""
        params = {
            "pn": 1,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": fs,
            "fields": "f12,f14,f2,f3,f4,f5,f6,f20,f62,f128,f136,f140,f141,f152",
        }
        resp = self._request(EASTMONEY_CLIST, params=params)
        rows = (resp.json().get("data") or {}).get("diff") or []
        return pd.DataFrame(rows)

    def list_concept_boards(self, page_size: int = 500) -> pd.DataFrame:
        return self.clist(FS_CONCEPT, page_size=page_size)

    def list_industry_boards(self, page_size: int = 500) -> pd.DataFrame:
        return self.clist(FS_INDUSTRY, page_size=page_size)

    def list_constituents(self, board_code: str, page_size: int = 600) -> pd.DataFrame:
        """拉取某板块的成分股。``board_code`` 例如 ``BK0890``。"""
        return self.clist(f"b:{board_code}", page_size=page_size)

    # ------------------------------------------------------------------
    # K 线（板块 / 个股）
    # ------------------------------------------------------------------
    def kline(self, code: str, trade_date: str, secid_prefix: str = "90") -> dict[str, Any] | None:
        """拉单个标的的 K 线快照。

        - ``code``     : 板块 ``BKxxxx`` 或股票 6 位代码
        - ``trade_date``: ``yyyyMMdd`` 或 ``yyyy-MM-dd``
        - ``secid_prefix``: 板块 ``"90"``，股票 ``"0"`` (深) / ``"1"`` (沪) / ``"0/1/2/3/4/8"`` (北) 等
        """
        date = ymd(trade_date)
        params = {
            "secid": f"{secid_prefix}.{code}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",  # 日线
            "fqt": "1",  # 前复权
            "beg": date,
            "end": date,
        }
        resp = self._request(EASTMONEY_KLINE, params=params)
        data = resp.json().get("data")
        if not data or not data.get("klines"):
            return None
        item = data["klines"][-1].split(",")
        return {
            "code": code,
            "name": data.get("name", ""),
            "date": item[0],
            "open": float(item[1]),
            "close": float(item[2]),
            "high": float(item[3]),
            "low": float(item[4]),
            "volume": float(item[5]),
            "amount": float(item[6]),
            "amplitude": float(item[7]),
            "pct_chg": float(item[8]),
            "change": float(item[9]),
            "turnover": float(item[10]),
        }

    def board_kline_on_date(self, board_code: str, trade_date: str) -> dict[str, Any] | None:
        """便捷方法：板块日 K 线快照。"""
        return self.kline(board_code, trade_date, secid_prefix="90")

    # ------------------------------------------------------------------
    # 并发拉板块 K 线（带预算 + SEED_BOARDS 兜底）
    # ------------------------------------------------------------------
    def fetch_boards_kline(
        self,
        trade_date: str,
        concept_boards: pd.DataFrame | None = None,
        industry_boards: pd.DataFrame | None = None,
        per_type_limit: int = 120,
        use_seed_fallback: bool = True,
        progress_cb: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> pd.DataFrame:
        """并发拉取概念/行业板块在 ``trade_date`` 的 K 线。

        Parameters
        ----------
        concept_boards, industry_boards:
            候选板块 ``DataFrame``，至少含 ``f12``（code）和 ``f14``（name）。
            缺省时自动从 ``clist`` 拉取前 ``per_type_limit`` 个。
        per_type_limit:
            每类板块最多取的候选数；``<=0`` 时只取 ``SEED_BOARDS``。
        use_seed_fallback:
            当抓不到任何 K 线时，是否使用 ``SEED_BOARDS`` 单点抓取兜底。
        progress_cb:
            进度回调，签名 ``cb(stage: str, fields: dict) -> None``。
        """

        def _emit(stage: str, **fields: Any) -> None:
            if progress_cb:
                try:
                    progress_cb(stage, fields)
                except Exception:
                    logger.exception("progress_cb raised")

        deadline = time.monotonic() + self.board_fetch_seconds
        frames: list[pd.DataFrame] = []

        for board_type, fs in (("概念", FS_CONCEPT), ("行业", FS_INDUSTRY)):
            if time.monotonic() >= deadline:
                _emit("boards:fetch:budget_exhausted", board_type=board_type)
                break

            if per_type_limit <= 0:
                candidates = [(b.code, b.name) for b in SEED_BOARDS if b.type == board_type]
            else:
                if board_type == "概念" and concept_boards is not None and not concept_boards.empty:
                    base = concept_boards
                elif board_type == "行业" and industry_boards is not None and not industry_boards.empty:
                    base = industry_boards
                else:
                    try:
                        base = self.clist(fs, pz=per_type_limit)
                        if base.empty:
                            continue
                    except Exception as exc:
                        logger.warning("eastmoney clist failed for %s: %s", board_type, exc)
                        base = pd.DataFrame()
                if base.empty:
                    candidates = [(b.code, b.name) for b in SEED_BOARDS if b.type == board_type]
                else:
                    base = base.rename(columns={"f12": "board_code", "f14": "board_name"})
                    base = base[["board_code", "board_name"]].drop_duplicates().head(per_type_limit)
                    candidates = list(zip(base["board_code"].astype(str), base["board_name"].astype(str)))

            rows = self._fetch_boards_kline_concurrent(
                board_type=board_type,
                candidates=candidates,
                trade_date=trade_date,
                deadline=deadline,
                source_tag="东方财富降级源",
                progress_cb=_emit,
            )
            frames.append(pd.DataFrame(rows))

        non_empty = [f for f in frames if not f.empty]
        if not non_empty and use_seed_fallback:
            _emit("boards:fetch:seed_fallback", reason="public board source returned no kline rows")
            seed_rows: list[dict[str, Any]] = []
            for b in SEED_BOARDS:
                if time.monotonic() >= deadline:
                    break
                try:
                    k = self.board_kline_on_date(b.code, trade_date)
                except Exception:
                    k = None
                if k:
                    k["board_type"] = b.type
                    k["source"] = "东方财富种子板块降级源"
                    seed_rows.append(k)
            if seed_rows:
                non_empty = [pd.DataFrame(seed_rows)]
        if not non_empty:
            return pd.DataFrame()
        out = pd.concat(non_empty, ignore_index=True)
        return out.sort_values(["pct_chg", "amount"], ascending=[False, False]).reset_index(drop=True)

    def _fetch_boards_kline_concurrent(
        self,
        board_type: str,
        candidates: list[tuple[str, str]],
        trade_date: str,
        deadline: float,
        source_tag: str,
        progress_cb: Callable[[str, dict[str, Any]], None],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not candidates:
            return rows
        workers = min(self.board_fetch_workers, len(candidates))

        def fetch_one(code: str, name: str) -> dict[str, Any] | None:
            if time.monotonic() >= deadline:
                return None
            try:
                item = self.board_kline_on_date(code, trade_date)
            except Exception as exc:
                logger.debug("kline fetch failed %s: %s", code, exc)
                return None
            if not item:
                return None
            item["board_type"] = board_type
            item["source"] = source_tag
            if not item.get("name"):
                item["name"] = name
            return item

        progress_cb("boards:kline:batch:start", board_type=board_type, candidates=len(candidates), workers=workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fetch_one, code, name) for code, name in candidates]
            try:
                for future in as_completed(futures, timeout=max(0.1, deadline - time.monotonic())):
                    item = future.result()
                    if item:
                        rows.append(item)
                    if time.monotonic() >= deadline:
                        break
            except Exception:
                pass
            for future in futures:
                future.cancel()
        progress_cb("boards:kline:batch:done", board_type=board_type, rows=len(rows))
        return rows

    # ------------------------------------------------------------------
    # 龙虎榜
    # ------------------------------------------------------------------
    def lhb(self, trade_date: str) -> pd.DataFrame:
        """拉取 ``trade_date`` 的龙虎榜汇总（无营业部明细）。"""
        iso = iso_date(trade_date)
        columns = ",".join(
            [
                "SECURITY_CODE",
                "SECUCODE",
                "SECURITY_NAME_ABBR",
                "TRADE_DATE",
                "EXPLAIN",
                "CLOSE_PRICE",
                "CHANGE_RATE",
                "BILLBOARD_NET_AMT",
                "BILLBOARD_BUY_AMT",
                "BILLBOARD_SELL_AMT",
                "BILLBOARD_DEAL_AMT",
                "ACCUM_AMOUNT",
                "DEAL_NET_RATIO",
                "TURNOVERRATE",
                "FREE_MARKET_CAP",
            ]
        )

        rows: list[dict[str, Any]] = []
        pages = 1
        for page in range(1, 101):
            params = {
                "sortColumns": "TRADE_DATE,SECURITY_CODE",
                "sortTypes": "-1,1",
                "pageSize": self.lhb_page_size,
                "pageNumber": page,
                "reportName": "RPT_DAILYBILLBOARD_DETAILS",
                "columns": columns,
                "filter": f"(TRADE_DATE='{iso}')",
            }
            resp = self._request(EASTMONEY_DATACENTER, params=params)
            payload = resp.json().get("result") or {}
            if page == 1:
                try:
                    pages = max(1, min(100, int(payload.get("pages") or 1)))
                except Exception:
                    pages = 1
            rows.extend(payload.get("data") or [])
            if page >= pages:
                break
        if not rows:
            return pd.DataFrame()
        raw = pd.DataFrame(rows)
        frame = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(raw.get("TRADE_DATE"), errors="coerce")
                .dt.strftime("%Y%m%d")
                .fillna(ymd(trade_date)),
                "ts_code": raw.get("SECUCODE", pd.Series(dtype=str)).astype(str),
                "name": raw.get("SECURITY_NAME_ABBR", pd.Series(dtype=str)).astype(str),
                "close": pd.to_numeric(raw.get("CLOSE_PRICE"), errors="coerce"),
                "pct_change": pd.to_numeric(raw.get("CHANGE_RATE"), errors="coerce"),
                "amount": pd.to_numeric(raw.get("BILLBOARD_DEAL_AMT"), errors="coerce"),
                "net_amount": pd.to_numeric(raw.get("BILLBOARD_NET_AMT"), errors="coerce"),
                "buy": pd.to_numeric(raw.get("BILLBOARD_BUY_AMT"), errors="coerce"),
                "sell": pd.to_numeric(raw.get("BILLBOARD_SELL_AMT"), errors="coerce"),
                "reason": raw.get("EXPLAIN", pd.Series(dtype=str)).astype(str),
                "source": "东方财富龙虎榜",
            }
        )
        frame = frame[frame["ts_code"].str.contains(r"\.(?:SH|SZ|BJ)$", regex=True, na=False)]
        return frame.drop_duplicates(["ts_code", "reason", "amount", "net_amount"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 财联社（通过 newsnow 公共聚合）
# ---------------------------------------------------------------------------


@dataclass
class CLSClient:
    """财联社热搜客户端（基于 newsnow 公共聚合 API）。

    ``newsnow_id`` 默认 ``"cls"``，对应财联社热门电报。

    环境变量：

    - ``NEWSNOW_BASE_URL`` : 默认 ``https://newsnow.busiyi.world/api/s``
    - ``NEWSNOW_NO_PROXY`` : ``"1"`` 时强制直连
    """

    base_url: str | None = None
    newsnow_id: str = "cls"
    timeout: float = 30.0
    proxy: str | None = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url or os.getenv("NEWSNOW_BASE_URL", "https://newsnow.busiyi.world/api/s")
        if os.getenv("NEWSNOW_NO_PROXY") == "1":
            self.proxy = None
        elif self.proxy is None:
            http_proxy = os.getenv("http_proxy") or os.getenv("HTTP_PROXY")
            if http_proxy and "://" in http_proxy:
                self.proxy = http_proxy.strip()
        self._proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

    def fetch(self, latest: bool = True, limit: int = 50) -> list[dict[str, Any]]:
        """拉取财联社热门电报列表。

        适配 newsnow 的三种返回格式：
            1. ``{"items": [{id, title, url, mobileUrl}]}``
            2. ``{"code": 200, "data": [...]}``
            3. ``{ "<id>": { "<title>": {"ranks": [...], "url": "...", "mobileUrl": "..."} } }``
        """
        url = f"{self.base_url}?id={self.newsnow_id}" + ("&latest" if latest else "")
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            timeout=self.timeout,
            proxies=self._proxies,
        )
        resp.raise_for_status()
        data = resp.json()

        items: list[dict[str, Any]] = []

        if isinstance(data, dict):
            if "items" in data and isinstance(data["items"], list):
                for idx, news in enumerate(data["items"]):
                    title = (news.get("title") or "").strip()
                    if not title:
                        continue
                    items.append(
                        {
                            "rank": idx + 1,
                            "title": title,
                            "url": news.get("url") or news.get("mobileUrl") or "",
                            "id": str(news.get("id") or ""),
                            "published_at": _epoch_to_iso(news.get("pubDate") or news.get("publishTime") or news.get("date")),
                            "source_updated_at": _epoch_to_iso(data.get("updatedTime")) if isinstance(data, dict) else None,
                        }
                    )
            elif data.get("code") == 200 and isinstance(data.get("data"), list):
                for idx, news in enumerate(data["data"]):
                    title = (news.get("title") or "").strip()
                    if not title:
                        continue
                    items.append(
                        {
                            "rank": idx + 1,
                            "title": title,
                            "url": news.get("url") or news.get("sourceUrl") or "",
                            "id": str(news.get("id") or news.get("sourceId") or ""),
                            "hot": str(news.get("hotValue") or news.get("hot") or news.get("score") or ""),
                            "published_at": _epoch_to_iso(news.get("pubDate") or news.get("publishTime") or news.get("date")),
                        }
                    )
            elif self.newsnow_id in data and isinstance(data[self.newsnow_id], dict):
                platform_data = data[self.newsnow_id]
                for idx, (title, info) in enumerate(platform_data.items()):
                    if not title or not isinstance(info, dict):
                        continue
                    ranks = info.get("ranks") or []
                    current_rank = ranks[0] if ranks else (idx + 1)
                    items.append(
                        {
                            "rank": current_rank,
                            "title": title.strip(),
                            "url": info.get("url") or info.get("mobileUrl") or "",
                            "id": "",
                            "hot": "",
                        }
                    )
                items.sort(key=lambda x: x["rank"])
        elif isinstance(data, list):
            for idx, news in enumerate(data):
                title = (news.get("title") or "").strip()
                if not title:
                    continue
                items.append(
                    {
                        "rank": idx + 1,
                        "title": title,
                        "url": news.get("url") or news.get("mobileUrl") or "",
                        "id": str(news.get("id") or ""),
                    }
                )

        if limit and len(items) > limit:
            items = items[:limit]
        return items


def _epoch_to_iso(value: Any) -> str | None:
    if not value:
        return None
    try:
        num = float(value)
    except Exception:
        return None
    if num <= 0:
        return None
    if num > 10_000_000_000:
        num = num / 1000
    try:
        return datetime.fromtimestamp(num, timezone.utc).isoformat()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_table(df: pd.DataFrame, max_rows: int = 30) -> None:
    if df.empty:
        print("(空)")
        return
    with pd.option_context(
        "display.max_columns",
        None,
        "display.width",
        200,
        "display.max_colwidth",
        40,
    ):
        print(df.head(max_rows).to_string(index=False))


def _cli() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="东方财富 & 财联社 独立客户端")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_boards = sub.add_parser("boards", help="拉取某日概念/行业板块 K 线（带 SEED_BOARDS 兜底）")
    p_boards.add_argument("--date", required=True, help="交易日 yyyyMMdd 或 yyyy-MM-dd")
    p_boards.add_argument("--limit", type=int, default=120, help="每类板块候选数")
    p_boards.add_argument("--budget", type=int, default=None, help="总抓取预算秒（覆盖默认值）")
    p_boards.add_argument("--workers", type=int, default=None, help="并发线程数")
    p_boards.add_argument("--out", default=None, help="可选 csv 输出路径")

    p_lhb = sub.add_parser("lhb", help="拉取某日龙虎榜")
    p_lhb.add_argument("--date", required=True)
    p_lhb.add_argument("--out", default=None)

    p_const = sub.add_parser("constituents", help="拉取板块成分股")
    p_const.add_argument("--code", required=True, help="板块代码，如 BK0890")
    p_const.add_argument("--limit", type=int, default=600)
    p_const.add_argument("--out", default=None)

    p_cls = sub.add_parser("cls", help="拉取财联社热搜（newsnow 聚合）")
    p_cls.add_argument("--limit", type=int, default=30)
    p_cls.add_argument("--out", default=None)
    p_cls.add_argument("--base-url", default=None)
    p_cls.add_argument("--no-proxy", action="store_true")

    args = p.parse_args()

    if args.cmd == "boards":
        kwargs: dict[str, Any] = {}
        if args.budget is not None:
            kwargs["board_fetch_seconds"] = args.budget
        if args.workers is not None:
            kwargs["board_fetch_workers"] = args.workers
        client = EastMoneyClient(**kwargs)
        df = client.fetch_boards_kline(
            trade_date=args.date,
            per_type_limit=args.limit,
            progress_cb=lambda stage, fields: print(json.dumps({"stage": stage, **fields}, ensure_ascii=False)),
        )
        _print_table(df)
        if args.out:
            df.to_csv(args.out, index=False)
            print(f"# saved {len(df)} rows -> {args.out}")
        return 0

    if args.cmd == "lhb":
        client = EastMoneyClient()
        df = client.lhb(args.date)
        _print_table(df)
        if args.out:
            df.to_csv(args.out, index=False)
            print(f"# saved {len(df)} rows -> {args.out}")
        return 0

    if args.cmd == "constituents":
        client = EastMoneyClient()
        df = client.list_constituents(args.code, page_size=args.limit)
        _print_table(df)
        if args.out:
            df.to_csv(args.out, index=False)
            print(f"# saved {len(df)} rows -> {args.out}")
        return 0

    if args.cmd == "cls":
        kwargs = {}
        if args.base_url:
            kwargs["base_url"] = args.base_url
        if args.no_proxy:
            os.environ["NEWSNOW_NO_PROXY"] = "1"
        client = CLSClient(**kwargs)
        items = client.fetch(limit=args.limit)
        for it in items:
            print(f"{it['rank']:>3}. {it['title']}  {it['url']}")
        if args.out:
            pd.DataFrame(items).to_csv(args.out, index=False)
            print(f"# saved {len(items)} rows -> {args.out}")
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
