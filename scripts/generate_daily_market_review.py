#!/usr/bin/env python3
"""Generate an A-share daily hot-sector and LHB review as a static HTML file."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import time
import warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", message=r"urllib3 .*doesn't match a supported version.*")

import pandas as pd
import requests
import tushare as ts


ROOT = Path(__file__).resolve().parents[1]
STOCK_PROJECT = Path(os.getenv("DAILY_MARKET_REVIEW_STOCK_PROJECT", str(ROOT / "30_Quant" / "stock_analysis")))
MARKET_LATEST = STOCK_PROJECT / "data" / "processed" / "market_daily_latest.parquet"
OUTPUT_DIR = Path(os.getenv("DAILY_MARKET_REVIEW_OUTPUT_DIR", str(ROOT / "outputs" / "daily-market-review")))
DATA_DIR = Path(os.getenv("DAILY_MARKET_REVIEW_DATA_DIR", str(ROOT / "data" / "daily-market-review")))
TOKEN_FILE = Path.home() / ".tushare" / "token"

EASTMONEY_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": "Mozilla/5.0",
}
SESSION = requests.Session()
SESSION.trust_env = False


def env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        value = int(float(os.getenv(name, str(default))))
    except Exception:
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def progress(stage: str, **fields: Any) -> None:
    payload = {
        "event": "daily_market_review_progress",
        "stage": stage,
        "ts": datetime.now().isoformat(timespec="seconds"),
        **fields,
    }
    print(json.dumps(payload, ensure_ascii=False, default=str), file=sys.stderr, flush=True)

BOARD_EXCLUDE_PATTERNS = re.compile(
    r"(昨日|今日|连板|涨停|首板|打板|热股|题材股|百日|历史新高|融资融券|预盈预增|"
    r"基金|ETF|转债|沪股通|深股通|MSCI|富时|标准普尔|中证|央视|昨日触板)"
)
SEED_BOARDS = pd.DataFrame(
    [
        ("BK0890", "MLCC", "概念"),
        ("BK0976", "被动元件概念", "概念"),
        ("BK0459", "元件", "行业"),
        ("BK1625", "钨", "行业"),
        ("BK1623", "钼", "行业"),
        ("BK1027", "小金属", "行业"),
        ("BK1462", "玻纤制造", "行业"),
        ("BK0546", "玻璃玻纤", "行业"),
        ("BK1592", "通信线缆及配套", "行业"),
        ("BK1327", "分立器件", "行业"),
        ("BK1328", "集成电路封测", "行业"),
        ("BK1339", "被动元件", "行业"),
        ("BK0977", "碳化硅", "概念"),
        ("BK1113", "复合集流体", "概念"),
        ("BK0703", "超级电容", "概念"),
    ],
    columns=["board_code", "board_name", "board_type"],
)
BOARD_INDUSTRY_FALLBACK = {
    "钨": ["小金属"],
    "钼": ["小金属"],
    "小金属": ["小金属"],
    "MLCC": ["元器件", "电子元件", "其他电子", "半导体"],
    "被动元件": ["元器件", "电子元件", "其他电子"],
    "元件": ["元器件", "电子元件", "其他电子"],
    "玻纤": ["玻璃", "化纤", "建材"],
    "通信线缆": ["通信设备", "通信"],
    "分立器件": ["半导体"],
    "集成电路封测": ["半导体"],
    "碳化硅": ["半导体"],
    "复合集流体": ["电气设备", "化工", "塑料"],
    "超级电容": ["元器件", "电气设备"],
}

SOURCE_LINKS = [
    ("东方财富龙虎榜详情", "https://data.eastmoney.com/stock/tradedetail.html"),
    ("证券时报：有色金属资金流", "https://www.stcn.com/article/detail/3962072.html"),
    ("证券时报：MLCC概念表现强势", "https://www.stcn.com/article/detail/3960936.html"),
    ("证券日报：MLCC概念板块大涨", "https://m.zqrb.cn/stock/redian/2026-06-15/A1781494414653.html"),
    ("财联社：AI硬件/CPO/MPO线索", "https://www.cls.cn/detail/2400185"),
    ("新浪财经：AI硬件方向集体爆发", "https://finance.sina.com.cn/jjxw/2026-06-15/doc-inicnpyv5003586.shtml"),
    ("财联社：双星新材MLCC离型膜反证", "https://www.cls.cn/detail/2396144"),
    ("新浪财经：炬光科技光通信占比反证", "https://finance.sina.com.cn/jjxw/2026-06-15/doc-inicnuhr8267817.shtml"),
    ("新浪财经：铜冠铜箔龙虎榜", "https://finance.sina.com.cn/stock/aiassist/lgbzz/2026-06-15/doc-inicnpyr0045395.shtml"),
]

ROTATION_THESES = [
    {
        "path": "MLCC/被动元件高潮 -> PCB材料/玻纤/铜箔扩散",
        "why": "AI服务器提高高端电容、低损耗材料、高速PCB和玻纤布价值量；当MLCC一线标的集体涨停后，资金容易横向切到同属算力硬件材料的铜箔、玻纤、覆铜板、电子树脂。",
        "confirm": "元件、玻纤制造、复合集流体继续放量；龙虎榜机构/股通净买入出现在铜箔、玻纤、覆铜板链条。",
        "fail": "高位MLCC断板后未向上游材料扩散，或龙头放量长上影且机构净卖出。",
    },
    {
        "path": "CPO/MPO光连接 -> 光器件/连接器/光纤路由柔性板",
        "why": "NPO/CPO多通道方案会提高MPO连接器、光器件和光路管理需求，盘后财联社龙虎榜线索也指向MPO连接器龙头获净买入。",
        "confirm": "光库科技、太辰光、长芯博创等继续获得机构/股通净买，且公告或调研能确认订单、客户认证或产能。",
        "fail": "公司公告显示相关业务占比低、仅样品收入，或上游有源芯片供给约束导致提货节奏不及预期。",
    },
    {
        "path": "小金属价格 -> 钨/钼/锗资源与深加工",
        "why": "钨、钼等价格上行带来资源端利润弹性，且六氟化钨、半导体材料国产替代把资源品与AI硬件/半导体支线相连。",
        "confirm": "长单报价继续上调，钨/钼板块量价齐升，资源龙头而非纯主题股领涨。",
        "fail": "商品价格回落，或个股只是低位补涨但无资源储量、加工能力和价格传导。",
    },
    {
        "path": "高潮后的低位补涨 -> 半导体封测/功率器件/碳化硅",
        "why": "当算力硬件主线进入高潮，资金可能沿科技链寻找低位同属性方向，分立器件、封测、碳化硅具备国产替代和周期修复叙事。",
        "confirm": "分立器件、封测指数继续强于大盘，并出现换手充分的机构席位买入。",
        "fail": "只有题材轮动没有订单、价格、稼动率或财报改善。",
    },
]

CANDIDATE_SEEDS = [
    ("光库科技", "300620.SZ", "CPO/MPO光连接", "光器件高弹性龙头之一，龙虎榜显示机构和股通同时参与；适合继续核验客户、产能、订单与业务纯度。", "重点验证"),
    ("长芯博创", "300548.SZ", "CPO/MPO光连接", "20cm涨停且龙虎榜净买额高，机构净买入明显；但需确认其真实产品环节与AI光通信收入占比。", "重点验证"),
    ("太辰光", "300570.SZ", "CPO/MPO光连接", "光通信链条强势股，龙虎榜有机构与股通净买；适合作为MPO/连接器扩散观察锚。", "重点验证"),
    ("铜冠铜箔", "301217.SZ", "PCB/铜箔材料", "铜箔链条与AI高速PCB材料扩散相关，龙虎榜总净买和股通净买强；需核验高频高速铜箔产品结构与客户认证。", "重点验证"),
    ("国际复材", "301526.SZ", "玻纤/PCB材料", "玻纤制造20cm涨停，股通净买较强；逻辑对应AI高速PCB上游玻纤布/材料扩散。", "观察验证"),
    ("中钨高新", "000657.SZ", "钨/硬质合金", "钨板块核心弹性之一，资源价格上行时受益；需要核验钨价传导、库存成本和深加工利润率。", "观察验证"),
    ("厦门钨业", "600549.SH", "钨/稀土/材料平台", "钨板块大市值平台，涨停确认资源线强度；更偏确定性，弹性需看估值和钨价持续性。", "观察验证"),
    ("达利凯普", "301566.SZ", "MLCC/被动元件", "MLCC最强20cm弹性股之一；需核验高端MLCC料号、AI服务器客户和产能瓶颈，防止仅交易板块情绪。", "谨慎追高"),
    ("宏达电子", "300726.SZ", "MLCC/军工电子", "MLCC方向20cm强势，业务相关性较高；需要区分军品/民品和AI服务器高端MLCC的收入贡献。", "谨慎追高"),
    ("双星新材", "002585.SZ", "MLCC离型膜主题", "公告反证较强：MLCC离型膜收入占比不足1%，暂未涉及AI算力相关应用；更像主题映射而非产业核心。", "降级观察"),
    ("炬光科技", "688167.SH", "CPO/光通信映射", "公告反证较强：2025年光通信相关业务收入占比约8%，尚未构成核心业绩支柱；龙虎榜机构净卖出，需谨慎。", "降级观察"),
]


def token() -> str:
    env = ""
    try:
        import os

        env = os.getenv("TUSHARE_TOKEN", "").strip()
    except Exception:
        env = ""
    if env:
        return env
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def pro_api():
    return ts.pro_api(token())


def ymd(date_text: str | pd.Timestamp) -> str:
    return pd.Timestamp(date_text).strftime("%Y%m%d")


def iso_date(date_text: str | pd.Timestamp) -> str:
    return pd.Timestamp(date_text).strftime("%Y-%m-%d")


def coalesce_alias_columns(frame: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    out = frame.copy()
    for source, target in aliases.items():
        if source not in out.columns or source == target:
            continue
        if target in out.columns:
            out[target] = out[target].combine_first(out[source])
            out = out.drop(columns=[source])
        else:
            out = out.rename(columns={source: target})
    return out


def normalize_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize quote cache/API aliases to the column names used by this script."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    aliases = {
        "code": "ts_code",
        "tradeDate": "trade_date",
        "preClose": "pre_close",
        "pctChange": "pct_chg",
        "pct_change": "pct_chg",
        "turnoverRate": "turnover_rate",
        "totalMv": "total_mv",
        "totalMV": "total_mv",
        "marketValue": "total_mv",
    }
    out = coalesce_alias_columns(frame, aliases)
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"].astype(str), errors="coerce").dt.strftime("%Y%m%d")
        out["trade_date"] = out["trade_date"].fillna(frame.get("trade_date", out["trade_date"]).astype(str) if "trade_date" in frame else out["trade_date"])
    for column in ("close", "pre_close", "change", "pct_chg", "amount", "turnover_rate", "pe_ttm", "total_mv"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    if "pct_chg" not in out.columns:
        if {"close", "pre_close"}.issubset(out.columns):
            pre_close = out["pre_close"].replace(0, pd.NA)
            out["pct_chg"] = (out["close"] - out["pre_close"]) / pre_close * 100
        elif {"change", "pre_close"}.issubset(out.columns):
            pre_close = out["pre_close"].replace(0, pd.NA)
            out["pct_chg"] = out["change"] / pre_close * 100
        else:
            out["pct_chg"] = 0.0
    elif out["pct_chg"].isna().any() and {"close", "pre_close"}.issubset(out.columns):
        pre_close = out["pre_close"].replace(0, pd.NA)
        calculated = (out["close"] - out["pre_close"]) / pre_close * 100
        out["pct_chg"] = out["pct_chg"].fillna(calculated)
    elif out["pct_chg"].isna().any() and {"change", "pre_close"}.issubset(out.columns):
        pre_close = out["pre_close"].replace(0, pd.NA)
        calculated = out["change"] / pre_close * 100
        out["pct_chg"] = out["pct_chg"].fillna(calculated)
    out["pct_chg"] = out["pct_chg"].fillna(0.0)
    return out


def normalize_board_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize board cache/API aliases to keep old cache files readable."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    aliases = {
        "ts_code": "board_code",
        "code": "board_code",
        "boardCode": "board_code",
        "name": "board_name",
        "boardName": "board_name",
        "type": "board_type",
        "boardType": "board_type",
        "pctChange": "pct_chg",
        "pct_change": "pct_chg",
        "turnoverRate": "turnover_rate",
    }
    out = coalesce_alias_columns(frame, aliases)
    for column in ("pct_chg", "amount", "turnover_rate"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    if "pct_chg" not in out.columns:
        out["pct_chg"] = 0.0
    if "amount" not in out.columns:
        out["amount"] = 0.0
    if "board_type" not in out.columns:
        out["board_type"] = "概念"
    if "source" not in out.columns:
        out["source"] = "缓存数据"
    return out


def previous_open_date(pro, now: datetime | None = None) -> str:
    now = now or datetime.now()
    end = now.strftime("%Y%m%d")
    start = (now - timedelta(days=20)).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open="1")
    if cal.empty:
        raise RuntimeError("No open trading day found in Tushare calendar.")
    cal = cal.sort_values("cal_date")
    return str(cal.iloc[-1]["cal_date"])


def latest_market_path() -> Path:
    if MARKET_LATEST.exists():
        return MARKET_LATEST
    paths = sorted((STOCK_PROJECT / "data" / "processed").glob("market_daily_*.parquet"))
    if not paths:
        raise FileNotFoundError("No local market_daily parquet found.")
    return paths[-1]


def load_market(pro, trade_date: str) -> pd.DataFrame:
    try:
        df = pd.read_parquet(latest_market_path())
        df = normalize_market_frame(df)
        day = df[df["trade_date"] == trade_date].copy()
        if not day.empty:
            return normalize_market_frame(day)
    except Exception:
        pass

    daily = pro.daily(
        trade_date=trade_date,
        fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    )
    if daily.empty:
        raise RuntimeError(f"No TuShare daily rows for {trade_date}.")
    try:
        basic = pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,turnover_rate,pe_ttm,total_mv",
        )
        if not basic.empty:
            daily = daily.merge(basic, on="ts_code", how="left")
    except Exception:
        daily["turnover_rate"] = float("nan")
        daily["pe_ttm"] = float("nan")
        daily["total_mv"] = float("nan")
    return normalize_market_frame(daily)


def load_latest_available_market(pro, requested_date: str) -> tuple[str, pd.DataFrame]:
    """Resolve an unpublished/current date to the latest open day with daily rows."""
    requested = datetime.strptime(requested_date, "%Y%m%d")
    start = (requested - timedelta(days=35)).strftime("%Y%m%d")
    try:
        calendar = pro.trade_cal(exchange="SSE", start_date=start, end_date=requested_date, is_open="1")
        candidates = sorted({str(item) for item in calendar.get("cal_date", [])}, reverse=True)
    except Exception:
        candidates = [(requested - timedelta(days=offset)).strftime("%Y%m%d") for offset in range(36)]
    if requested_date not in candidates:
        candidates.insert(0, requested_date)
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            market = load_market(pro, candidate)
            if not market.empty:
                return candidate, market
        except Exception as exc:
            last_error = exc
    detail = f"：{last_error}" if last_error else ""
    raise RuntimeError(f"目标日期 {requested_date} 及此前 35 天内没有可用的 TuShare 日线数据{detail}")


def load_stock_basic(pro) -> pd.DataFrame:
    cache = DATA_DIR / "stock_basic_latest.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
        df.to_csv(cache, index=False)
        return df
    except Exception:
        if cache.exists():
            return pd.read_csv(cache)
        raise


def eastmoney_clist(fs: str, pz: int = 500) -> pd.DataFrame:
    params = {
        "pn": 1,
        "pz": pz,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": fs,
        "fields": "f12,f14,f2,f3,f4,f5,f6,f20,f62,f128,f136,f140,f141,f152",
    }
    resp = request_get(EASTMONEY_CLIST, params=params)
    rows = resp.json().get("data", {}).get("diff", []) or []
    return pd.DataFrame(rows)


def board_kline_on_date(code: str, trade_date: str) -> dict[str, Any] | None:
    params = {
        "secid": f"90.{code}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": trade_date,
        "end": trade_date,
    }
    resp = request_get(EASTMONEY_KLINE, params=params)
    data = resp.json().get("data")
    if not data or not data.get("klines"):
        return None
    item = data["klines"][-1].split(",")
    return {
        "board_code": code,
        "board_name": data.get("name", ""),
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


def request_get(url: str, params: dict[str, Any]) -> requests.Response:
    last_error: Exception | None = None
    primary_timeout = env_int("DAILY_MARKET_REVIEW_EASTMONEY_TIMEOUT_SECONDS", 5, 2, 20)
    fallback_timeout = env_int("DAILY_MARKET_REVIEW_EASTMONEY_FALLBACK_TIMEOUT_SECONDS", 7, 2, 30)
    for attempt in range(1):
        try:
            resp = SESSION.get(url, params=params, headers=HEADERS, timeout=primary_timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=fallback_timeout)
        resp.raise_for_status()
        return resp
    except Exception as exc:
        last_error = exc
    raise RuntimeError(f"Eastmoney request failed after retries: {last_error}")


def fetch_tushare_boards(pro, trade_date: str) -> pd.DataFrame:
    """Read rising THS sectors from TuShare before using a public fallback."""
    try:
        daily = pro.ths_daily(
            trade_date=trade_date,
            fields="ts_code,trade_date,close,pct_change,turnover_rate,total_mv,float_mv",
        )
        indexes = pro.ths_index(fields="ts_code,name,count,exchange,list_date,type")
        if daily is None or daily.empty or indexes is None or indexes.empty:
            return pd.DataFrame()
        frame = daily.merge(indexes[["ts_code", "name", "type"]], on="ts_code", how="left")
        typed = frame["type"].astype(str).str.upper()
        if typed.isin(["N", "I"]).any():
            frame = frame[typed.isin(["N", "I"])]
        frame = frame.rename(columns={"ts_code": "board_code", "name": "board_name", "type": "board_type", "pct_change": "pct_chg"})
        frame["amount"] = 0.0
        frame["source"] = "TuShare同花顺"
        frame["board_type"] = frame["board_type"].map({"N": "概念", "I": "行业"}).fillna(frame["board_type"]).fillna("概念")
        frame = normalize_board_frame(frame)
        frame = frame[frame["pct_chg"].notna() & frame["board_name"].notna()]
        frame = frame[~frame["board_name"].astype(str).str.contains(BOARD_EXCLUDE_PATTERNS, na=False)]
        return frame.sort_values(["pct_chg", "turnover_rate"], ascending=[False, False]).reset_index(drop=True)
    except Exception as exc:
        print(f"TuShare sector fallback: {exc}")
        return pd.DataFrame()


def fetch_board_kline_rows(board_type: str, base: pd.DataFrame, trade_date: str, deadline: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates = []
    for _, row in base.iterrows():
        name = str(row["board_name"])
        if BOARD_EXCLUDE_PATTERNS.search(name):
            continue
        candidates.append((str(row["board_code"]), name))
    if not candidates:
        return rows

    workers = env_int("DAILY_MARKET_REVIEW_BOARD_FETCH_WORKERS", 16, 1, 32)
    workers = min(workers, len(candidates))

    def fetch_one(board_code: str, board_name: str) -> dict[str, Any] | None:
        if time.monotonic() >= deadline:
            return None
        try:
            item = board_kline_on_date(board_code, trade_date)
        except Exception:
            return None
        if not item:
            return None
        item["board_type"] = board_type
        item["source"] = "东方财富降级源"
        if not item.get("board_name"):
            item["board_name"] = board_name
        return item

    progress("boards:kline:batch:start", board_type=board_type, candidates=len(candidates), workers=workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_one, code, name) for code, name in candidates]
        while futures:
            remaining = max(0.1, deadline - time.monotonic())
            try:
                for future in as_completed(futures, timeout=remaining):
                    futures.remove(future)
                    item = future.result()
                    if item:
                        rows.append(item)
                    if time.monotonic() >= deadline:
                        break
            except TimeoutError:
                break
            if time.monotonic() >= deadline:
                break
        for future in futures:
            future.cancel()
    progress("boards:kline:batch:done", board_type=board_type, rows=len(rows), timed_out=time.monotonic() >= deadline)
    return rows


def fetch_boards_for_date(pro, trade_date: str, limit_each_type: int = 120, use_cache: bool = True) -> pd.DataFrame:
    cache = DATA_DIR / f"hot_boards_all_{trade_date}.csv"
    if use_cache and cache.exists():
        cached = normalize_board_frame(pd.read_csv(cache))
        seed_only_cache = limit_each_type > 0 and len(cached) <= len(SEED_BOARDS) + 2
        if {"board_code", "board_name", "pct_chg"}.issubset(cached.columns) and not seed_only_cache:
            return cached
    tushare_boards = fetch_tushare_boards(pro, trade_date)
    if not tushare_boards.empty:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tushare_boards.to_csv(cache, index=False)
        return tushare_boards
    board_budget_seconds = env_int("DAILY_MARKET_REVIEW_BOARD_FETCH_SECONDS", 110, 20, 360)
    deadline = time.monotonic() + board_budget_seconds
    frames = []
    for board_type, fs in [("概念", "m:90+t:3"), ("行业", "m:90+t:2")]:
        if time.monotonic() >= deadline:
            progress("boards:fetch:budget_exhausted", board_type=board_type, budget_seconds=board_budget_seconds)
            break
        if limit_each_type <= 0:
            base = SEED_BOARDS[SEED_BOARDS["board_type"] == board_type][["board_code", "board_name"]]
        else:
            try:
                base = eastmoney_clist(fs, pz=limit_each_type)
                if base.empty:
                    continue
                base = base.rename(columns={"f12": "board_code", "f14": "board_name"})
                base = base[["board_code", "board_name"]].drop_duplicates().head(limit_each_type)
            except Exception:
                base = SEED_BOARDS[SEED_BOARDS["board_type"] == board_type][["board_code", "board_name"]]
        rows = fetch_board_kline_rows(board_type, base, trade_date, deadline)
        frames.append(pd.DataFrame(rows))
    non_empty_frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty_frames:
        progress("boards:fetch:seed_fallback", reason="public board source returned no kline rows")
        seed_frames = []
        for _, row in SEED_BOARDS.iterrows():
            try:
                k = board_kline_on_date(str(row["board_code"]), trade_date)
            except Exception:
                k = None
            if k:
                k["board_type"] = row.get("board_type") or "概念"
                k["source"] = "东方财富种子板块降级源"
                seed_frames.append(k)
        if not seed_frames:
            return pd.DataFrame()
        non_empty_frames = [pd.DataFrame(seed_frames)]
    out = normalize_board_frame(pd.concat(non_empty_frames, ignore_index=True))
    out = out.sort_values(["pct_chg", "amount"], ascending=[False, False]).reset_index(drop=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, index=False)
    return out


def em_symbol_to_tscode(symbol: str) -> str | None:
    symbol = str(symbol).zfill(6)
    if symbol.startswith(("6", "9")):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "2", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return None


def board_constituents(pro, board_code: str) -> pd.DataFrame:
    if board_code.endswith(".TI"):
        try:
            members = pro.ths_member(ts_code=board_code, fields="ts_code,con_code,con_name,weight,in_date,out_date,is_new")
            if members is not None and not members.empty:
                return members.rename(columns={"con_code": "ts_code", "con_name": "name"})[["ts_code", "name"]].drop_duplicates("ts_code")
        except Exception as exc:
            print(f"TuShare sector members fallback {board_code}: {exc}")
    try:
        df = eastmoney_clist(f"b:{board_code}", pz=600)
    except Exception:
        df = pd.DataFrame()
    if df.empty:
        return pd.DataFrame(columns=["ts_code", "name"])
    df = df.rename(columns={"f12": "symbol", "f14": "name"})
    df["ts_code"] = df["symbol"].map(em_symbol_to_tscode)
    return df[["ts_code", "name"]].dropna().drop_duplicates()


def limit_up_label(row: pd.Series) -> str:
    pct = float(row.get("pct_chg", 0) or 0)
    code = str(row.get("ts_code", ""))
    if code.endswith(".BJ") and pct >= 29:
        return "30cm"
    if (code.startswith("30") or code.startswith("688")) and pct >= 19:
        return "20cm"
    if pct >= 9.7:
        return "10cm"
    return ""


def leaders_for_board(pro, board_code: str, market: pd.DataFrame, basic: pd.DataFrame, max_rows: int = 16) -> pd.DataFrame:
    cons = board_constituents(pro, board_code)
    if cons.empty:
        board_name = ""
        seed = SEED_BOARDS[SEED_BOARDS["board_code"] == board_code]
        if not seed.empty:
            board_name = str(seed.iloc[0]["board_name"])
        keywords = []
        for key, values in BOARD_INDUSTRY_FALLBACK.items():
            if key in board_name:
                keywords = values
                break
        if not keywords:
            return pd.DataFrame()
        pattern = "|".join(map(re.escape, keywords))
        cons = basic[basic["industry"].astype(str).str.contains(pattern, regex=True, na=False)][["ts_code", "name"]]
    cols = ["ts_code", "close", "pct_chg", "amount", "turnover_rate", "pe_ttm", "total_mv"]
    day = market[[c for c in cols if c in market.columns]].copy()
    merged = cons.merge(day, on="ts_code", how="inner")
    merged = merged.merge(basic[["ts_code", "industry", "market"]], on="ts_code", how="left")
    if merged.empty:
        return merged
    merged["limit_tag"] = merged.apply(limit_up_label, axis=1)
    for column in ("pct_chg", "amount", "turnover_rate", "total_mv"):
        merged[column] = pd.to_numeric(merged.get(column), errors="coerce").fillna(0)
    pct_rank = merged["pct_chg"].rank(pct=True)
    amount_rank = merged["amount"].rank(pct=True)
    turnover_rank = merged["turnover_rate"].rank(pct=True)
    mv_rank = merged["total_mv"].rank(pct=True)
    small_mv_rank = merged["total_mv"].rank(pct=True, ascending=False)
    merged["prosperity_score"] = (pct_rank * 40 + amount_rank * 30 + turnover_rank * 20 + mv_rank * 10).round(1)
    merged["elasticity_score"] = (pct_rank * 45 + turnover_rank * 25 + small_mv_rank * 20 + amount_rank * 10).round(1)
    merged["leadership_score"] = (amount_rank * 45 + mv_rank * 30 + pct_rank * 25).round(1)
    positive = merged.sort_values(["prosperity_score", "pct_chg", "amount"], ascending=[False, False, False]).head(max_rows - 3)
    laggards = merged.sort_values(["pct_chg", "amount"], ascending=[True, False]).head(3)
    return pd.concat([positive, laggards], ignore_index=True).drop_duplicates("ts_code").head(max_rows)


def infer_reason(board_name: str) -> str:
    name = str(board_name)
    if any(k in name for k in ["MLCC", "被动元件", "电容"]):
        return "AI服务器/高端车规带动高规格MLCC需求，叠加海外厂商涨价、交期拉长和国产替代预期。"
    if any(k in name for k in ["PCB", "覆铜板", "电子树脂", "玻纤", "元件"]):
        return "AI算力硬件升级抬升高速PCB、覆铜板、玻纤布、电子树脂等材料价值量，资金沿上游材料扩散。"
    if any(k in name for k in ["CPO", "光通信", "通信线缆", "光模块", "MPO"]):
        return "NPO/CPO多通道方案提高MPO/光连接与高速光通信需求，机构和龙虎榜资金集中验证算力硬件主线。"
    if any(k in name for k in ["钨", "钼", "锗", "小金属", "稀土", "有色"]):
        return "小金属价格上行与供应约束强化资源品利润弹性，钨/锗/钼等方向成为AI硬件之外的资源支线。"
    if any(k in name for k in ["半导体", "分立器件", "集成电路", "封测", "碳化硅"]):
        return "高风险偏好下资金回流科技成长，半导体设备、功率器件和封测受国产替代与周期修复预期带动。"
    if any(k in name for k in ["复合集流体", "超级电容", "锂电"]):
        return "新能源材料处于低位修复，复合集流体/超级电容兼具新技术预期和主题弹性。"
    return "板块涨幅靠前，需继续用公告、订单、价格和财报验证是否有产业基本面变化。"


def get_lhb(pro, trade_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    top = pro.top_list(trade_date=trade_date)
    inst = pro.top_inst(trade_date=trade_date)
    return top, inst


def aggregate_seats(inst: pd.DataFrame) -> pd.DataFrame:
    if inst.empty:
        return pd.DataFrame()
    x = inst.copy()
    x = x.drop_duplicates(["ts_code", "exalter", "buy", "sell", "reason"])
    grouped = x.groupby("ts_code", as_index=False).agg(
        inst_net=("net_buy", lambda s: s[x.loc[s.index, "exalter"].astype(str).str.contains("机构专用")].sum()),
        north_net=("net_buy", lambda s: s[x.loc[s.index, "exalter"].astype(str).str.contains("股通专用")].sum()),
        top_buyer=("exalter", lambda s: str(s.iloc[x.loc[s.index, "buy"].astype(float).argmax()])),
    )
    return grouped


def fmt_num(value: Any, unit: str = "") -> str:
    try:
        v = float(value)
    except Exception:
        return ""
    if math.isnan(v):
        return ""
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿{unit}"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}万{unit}"
    return f"{v:.2f}{unit}"


def fmt_pct(value: Any) -> str:
    try:
        v = float(value)
    except Exception:
        return ""
    if math.isnan(v):
        return ""
    return f"{v:.2f}%"


def fmt_local_amount(value: Any) -> str:
    return fmt_num(float(value) * 1000 if pd.notna(value) else value)


def fmt_daily_basic_mv(value: Any) -> str:
    return fmt_num(float(value) * 10000 if pd.notna(value) else value)


def action_class(action: str) -> str:
    if "重点" in action:
        return "hot"
    if "谨慎" in action:
        return "warm"
    if "降级" in action:
        return "cold"
    return ""


def aggregate_lhb_by_stock(lhb_hot: pd.DataFrame) -> pd.DataFrame:
    if lhb_hot.empty:
        return pd.DataFrame()
    x = lhb_hot.copy()
    agg = x.groupby("ts_code", as_index=False).agg(
        lhb_name=("name", "first"),
        lhb_pct_change=("pct_change", "max"),
        lhb_amount=("amount", "max"),
        lhb_net_amount=("net_amount", "sum"),
        lhb_inst_net=("inst_net", "max"),
        lhb_north_net=("north_net", "max"),
        lhb_top_buyer=("top_buyer", "first"),
        lhb_reason=("reason", "first"),
    )
    return agg


def build_candidate_rows(market: pd.DataFrame, lhb_hot: pd.DataFrame) -> list[dict[str, Any]]:
    lhb = aggregate_lhb_by_stock(lhb_hot)
    rows = []
    for name, code, theme, logic, action in CANDIDATE_SEEDS:
        m = market[market["ts_code"] == code]
        l = lhb[lhb["ts_code"] == code] if not lhb.empty else pd.DataFrame()
        if not m.empty:
            mr = m.iloc[0]
            pct = mr.get("pct_chg")
            amount = mr.get("amount")
            mv = mr.get("total_mv")
            industry = mr.get("industry", "")
        else:
            pct = amount = mv = float("nan")
            industry = ""
        if not l.empty:
            lr = l.iloc[0]
            lhb_text = (
                f"龙虎榜净额{fmt_num(lr.get('lhb_net_amount'))}，"
                f"机构{fmt_num(lr.get('lhb_inst_net'))}，"
                f"股通{fmt_num(lr.get('lhb_north_net'))}；最大买方：{lr.get('lhb_top_buyer')}"
            )
            evidence = "A：交易所公开交易信息/Tushare龙虎榜；"
        else:
            lhb_text = "未进入当日重点龙虎榜或未抓到席位明细"
            evidence = "C：行情与板块强度；"
        if name == "双星新材":
            evidence += "A：公司异动公告称MLCC离型膜收入占比不足1%，暂未涉及AI算力应用"
        elif name == "炬光科技":
            evidence += "A：公司异动公告称2025年光通信相关收入占比约8%，尚未构成核心业绩支柱"
        elif theme in {"钨/硬质合金", "钨/稀土/材料平台"}:
            evidence += "C：钨/钼/小金属价格与板块涨幅线索，待长单报价和财报验证"
        else:
            evidence += "C：产业链媒体线索与板块共振，待公告/调研/订单验证"
        rows.append(
            {
                "theme": theme,
                "name": name,
                "code": code,
                "industry": industry,
                "pct": pct,
                "amount": amount,
                "mv": mv,
                "lhb": lhb_text,
                "logic": logic,
                "evidence": evidence,
                "action": action,
            }
        )
    return rows


def tag_class(v: float) -> str:
    if v >= 8:
        return "hot"
    if v >= 4:
        return "warm"
    if v < 0:
        return "cold"
    return ""


def table_rows(rows: list[str]) -> str:
    return "\n".join(rows)


def fmt_yi(value: Any) -> str:
    try:
        v = float(value)
    except Exception:
        return ""
    if math.isnan(v):
        return ""
    return f"{v / 1e8:.2f}"


def fmt_local_yi(value: Any) -> str:
    try:
        return fmt_yi(float(value) * 1000)
    except Exception:
        return ""


def fmt_mv_yi(value: Any) -> str:
    try:
        return fmt_yi(float(value) * 10000)
    except Exception:
        return ""


def fmt_wan(value: Any) -> str:
    try:
        v = float(value)
    except Exception:
        return ""
    if math.isnan(v):
        return ""
    return f"{v / 1e4:,.0f}"


def board_theme(board_name: str) -> str:
    name = re.sub(r"[ⅠⅡⅢⅣⅤ]+$", "", str(board_name)).strip()
    if any(k in name for k in ["MLCC", "被动元件", "电容"]):
        return "MLCC/被动元件"
    if any(k in name for k in ["钨", "钼", "小金属", "锗", "稀土"]):
        return "小金属/资源"
    if any(k in name for k in ["元件", "玻纤", "复合集流体", "PCB", "铜箔"]):
        return "算力材料/PCB链"
    if any(k in name for k in ["通信", "CPO", "MPO", "光"]):
        return "光连接/CPO"
    if any(k in name for k in ["分立器件", "功率器件"]):
        return "功率半导体/分立器件"
    if any(k in name for k in ["半导体设备", "光刻", "刻蚀"]):
        return "半导体设备"
    if any(k in name for k in ["集成电路制造", "晶圆制造"]):
        return "晶圆制造/半导体"
    if any(k in name for k in ["封测", "集成电路封测"]):
        return "封测"
    if any(k in name for k in ["碳化硅", "SiC"]):
        return "SiC/功率材料"
    if "半导体" in name:
        return "半导体"
    clean = re.sub(r"(概念|指数|板块)$", "", name).strip()
    return clean or "其他强势主题"


def select_hot_boards(boards: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    """Rank boards by tradable heat instead of raw percentage change only."""
    if boards.empty:
        return boards
    ranked = normalize_board_frame(boards)
    ranked["pct_chg"] = pd.to_numeric(ranked.get("pct_chg"), errors="coerce").fillna(0)
    ranked["amount"] = pd.to_numeric(ranked.get("amount"), errors="coerce").fillna(0)
    liquid = ranked[(ranked["pct_chg"] > 0) & (ranked["amount"] >= 3_000_000_000)].copy()
    if liquid.empty:
        liquid = ranked[ranked["pct_chg"] > 0].copy()
    if liquid.empty:
        liquid = ranked.copy()
    amount_factor = liquid["amount"].clip(lower=1).map(math.log10)
    liquid["hot_score"] = liquid["pct_chg"] * 3 + amount_factor / 2
    liquid = liquid.sort_values(["hot_score", "pct_chg", "amount"], ascending=[False, False, False])
    liquid["theme_key"] = liquid["board_name"].map(board_theme)
    liquid = liquid.drop_duplicates(["theme_key", "pct_chg", "amount"])
    return liquid.drop(columns=["hot_score", "theme_key"], errors="ignore").head(top_n).reset_index(drop=True)


def compact_reason(board_name: str) -> str:
    return infer_reason(board_name).replace("。", "")


def infer_chain_stage(theme: str, board_name: str) -> str:
    name = f"{theme}/{board_name}"
    rules = [
        (["钨", "钼", "锗", "稀土", "小金属"], "上游资源与原料"),
        (["玻纤", "铜箔", "覆铜板", "复合集流体", "材料"], "上游关键材料"),
        (["设备", "光刻", "刻蚀", "检测"], "核心设备"),
        (["芯片", "半导体", "分立器件", "碳化硅"], "核心器件与芯片"),
        (["封测", "PCB", "元件", "MLCC", "电容"], "中游制造与封装"),
        (["光模块", "光通信", "通信线缆", "CPO", "MPO"], "高速互联与模块"),
        (["服务器", "数据中心", "机器人", "汽车", "消费电子"], "下游应用与终端"),
    ]
    for keywords, stage in rules:
        if any(keyword in name for keyword in keywords):
            return stage
    return "产业链核心环节"


def render_html(
    trade_date: str,
    market: pd.DataFrame,
    boards: pd.DataFrame,
    board_leaders: dict[str, pd.DataFrame],
    top_lhb: pd.DataFrame,
    lhb_hot: pd.DataFrame,
    news: pd.DataFrame,
) -> str:
    date_display = iso_date(trade_date)
    adv = market["pct_chg"].gt(0).sum()
    dec = market["pct_chg"].lt(0).sum()
    ratio = adv / dec if dec else 0
    limit_count = market.apply(limit_up_label, axis=1).astype(bool).sum()
    turnover = market["amount"].sum() * 1000
    total_names = len(market)
    limit_share = limit_count / total_names if total_names else 0
    mood = "强活跃" if limit_share >= 0.04 and ratio >= 1.6 else "活跃" if ratio >= 1.1 else "分歧"

    board_rows = []
    for _, b in boards.head(12).iterrows():
        leaders = board_leaders.get(b["board_code"], pd.DataFrame())
        top_leader = ""
        if not leaders.empty:
            r0 = leaders.iloc[0]
            top_leader = f"{r0['name']} {r0.get('limit_tag') or fmt_pct(r0['pct_chg'])}"
        board_rows.append(
            "<tr>"
            f"<td><span class='tag'>{html.escape(board_theme(str(b['board_name'])))}</span></td>"
            f"<td><strong>{html.escape(str(b['board_name']))}</strong><br><span class='muted'>{b['board_code']} / {html.escape(str(b['board_type']))}</span></td>"
            f"<td class='num {tag_class(float(b['pct_chg']))}'>{fmt_pct(b['pct_chg'])}</td>"
            f"<td class='num'>{fmt_yi(b['amount'])}</td>"
            f"<td>{html.escape(top_leader)}</td>"
            f"<td>{html.escape(compact_reason(str(b['board_name'])))}</td>"
            "</tr>"
        )

    core: dict[str, dict[str, Any]] = {}
    for bcode, leaders in board_leaders.items():
        bname = boards.loc[boards["board_code"] == bcode, "board_name"]
        board_name = str(bname.iloc[0]) if not bname.empty else bcode
        for _, r in leaders.head(4).iterrows():
            code = str(r["ts_code"])
            item = core.setdefault(
                code,
                {
                    "name": r["name"],
                    "code": code,
                    "pct": r["pct_chg"],
                    "amount": r.get("amount"),
                    "mv": r.get("total_mv"),
                    "industry": r.get("industry", ""),
                    "boards": [],
                    "limit": r.get("limit_tag") or "",
                },
            )
            item["boards"].append(board_name)
    lhb_by_code = aggregate_lhb_by_stock(lhb_hot)
    lhb_map = {str(r["ts_code"]): r for _, r in lhb_by_code.iterrows()} if not lhb_by_code.empty else {}
    core_rows = []
    for item in sorted(core.values(), key=lambda x: (float(x["pct"]), float(x.get("amount") or 0)), reverse=True)[:14]:
        themes = list(dict.fromkeys(board_theme(board) for board in item["boards"]))[:3]
        tags = " ".join(f"<span class='tag'>{html.escape(theme)}</span>" for theme in themes)
        lhb_note = "未入重点龙虎榜，先看承接"
        if item["code"] in lhb_map:
            lr = lhb_map[item["code"]]
            lhb_note = (
                f"榜单净额{fmt_wan(lr.get('lhb_net_amount'))}万，"
                f"机构{fmt_wan(lr.get('lhb_inst_net'))}万，"
                f"股通{fmt_wan(lr.get('lhb_north_net'))}万"
            )
        core_rows.append(
            "<tr>"
            f"<td><strong>{html.escape(str(item['name']))}</strong><br><span class='muted'>{item['code']}</span></td>"
            f"<td>{tags}</td>"
            f"<td class='num {tag_class(float(item['pct']))}'>{fmt_pct(item['pct'])}</td>"
            f"<td class='num'>{fmt_local_yi(item.get('amount'))}</td>"
            f"<td class='num'>{fmt_mv_yi(item.get('mv'))}</td>"
            f"<td>{html.escape(lhb_note)}</td>"
            "</tr>"
        )

    lhb_focus = aggregate_lhb_by_stock(lhb_hot)
    lhb_rows = []
    if not lhb_focus.empty:
        lhb_focus["focus_score"] = (
            lhb_focus["lhb_net_amount"].fillna(0)
            + lhb_focus["lhb_inst_net"].fillna(0).clip(lower=0) * 1.5
            + lhb_focus["lhb_north_net"].fillna(0).clip(lower=0)
        )
        warning_codes = {"688167.SH"}
        picked = pd.concat(
            [
                lhb_focus.sort_values("focus_score", ascending=False).head(8),
                lhb_focus[lhb_focus["ts_code"].isin(warning_codes)],
            ],
            ignore_index=True,
        ).drop_duplicates("ts_code")
        for _, r in picked.head(10).iterrows():
            lhb_rows.append(
                "<tr>"
                f"<td><strong>{html.escape(str(r['lhb_name']))}</strong><br><span class='muted'>{r['ts_code']}</span></td>"
                f"<td class='num {tag_class(float(r['lhb_pct_change']))}'>{fmt_pct(r['lhb_pct_change'])}</td>"
                f"<td>{html.escape(str(r.get('lhb_reason') or ''))}</td>"
                f"<td class='num'>{fmt_wan(r.get('lhb_net_amount'))}</td>"
                f"<td class='num'>{fmt_wan(r.get('lhb_inst_net'))}</td>"
                f"<td class='num'>{fmt_wan(r.get('lhb_north_net'))}</td>"
                f"<td>{html.escape(str(r.get('lhb_top_buyer') or ''))}</td>"
                "</tr>"
            )

    news_rows = []
    for _, r in news.head(10).iterrows():
        news_rows.append(
            "<li>"
            f"<a href='{html.escape(str(r.get('url', '')))}'>{html.escape(str(r.get('title', '')))}</a>"
            f"<span class='muted'> {html.escape(str(r.get('published_at', '')))}</span>"
            "</li>"
        )

    rotation_cards = []
    for item in ROTATION_THESES:
        rotation_cards.append(
            "<div class='path-card'>"
            f"<div class='path-title'>{html.escape(item['path'])}</div>"
            f"<div>{html.escape(item['why'])}</div>"
            "<div class='signal-row'>"
            f"<span class='signal-item'><b>确认</b> {html.escape(item['confirm'])}</span>"
            f"<span class='signal-item'><b>失效</b> {html.escape(item['fail'])}</span>"
            "</div>"
            "</div>"
        )

    strong_rows = []
    warning_rows = []
    for r in build_candidate_rows(market, lhb_hot):
        row = (
            "<tr>"
            f"<td><strong>{html.escape(r['name'])}</strong><br><span class='muted'>{r['code']}</span></td>"
            f"<td>{html.escape(r['theme'])}</td>"
            f"<td>{html.escape(r['logic'])}<br><span class='muted'>{html.escape(r['evidence'])}</span></td>"
            f"<td class='{action_class(r['action'])}'>{html.escape(r['action'])}</td>"
            "</tr>"
        )
        if "降级" in r["action"] or "谨慎" in r["action"]:
            warning_rows.append(row)
        else:
            strong_rows.append(row)

    source_rows = "\n".join(
        f"<li><a href='{html.escape(url)}'>{html.escape(label)}</a></li>" for label, url in SOURCE_LINKS
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A股每日热点复盘 · 优化版 | {date_display}</title>
  <style>
    * {{ box-sizing: border-box; }}
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #1e2a3e;
      --muted: #5b6e8c;
      --line: #e2e8f0;
      --red: #c93535;
      --green: #16794c;
      --amber: #c76f18;
      --blue: #2c628f;
      --gray: #4a5568;
    }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 1400px; margin: 0 auto; padding: 24px 20px 48px; }}
    h1 {{ font-size: 28px; margin: 0 0 6px; letter-spacing: 0; }}
    .toc {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 18px; margin-bottom: 24px; display: flex; flex-wrap: wrap; gap: 16px; box-shadow: 0 1px 2px rgba(0,0,0,.03); }}
    .toc a {{ color: var(--blue); text-decoration: none; font-size: 13px; font-weight: 600; }}
    .section-title {{ font-size: 20px; font-weight: 650; margin: 28px 0 14px; padding-left: 8px; border-left: 4px solid var(--blue); }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 18px 0 20px; }}
    .metric-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }}
    .metric-card .label {{ font-size: 13px; color: var(--muted); }}
    .metric-card .value {{ font-size: 26px; font-weight: 700; margin-top: 6px; line-height: 1.2; }}
    .metric-card .sub {{ font-size: 12px; color: var(--muted); margin-top: 5px; }}
    .emotion-hint {{ background: #fff8e6; border-left: 4px solid var(--amber); padding: 10px 14px; border-radius: 8px; margin: 16px 0 22px; font-size: 13px; }}
    .data-table {{ width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; margin-bottom: 28px; font-size: 13px; }}
    .data-table th {{ background: #f1f4f9; padding: 11px 10px; font-weight: 650; color: #2c3e50; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
    .data-table td {{ padding: 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    tr:last-child td {{ border-bottom: 0; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .hot {{ color: var(--red); font-weight: 700; }}
    .warm {{ color: var(--amber); font-weight: 700; }}
    .cold {{ color: var(--gray); font-weight: 700; }}
    .tag {{ background: #eef2ff; color: var(--blue); font-size: 11px; padding: 2px 8px; border-radius: 999px; display: inline-block; margin: 0 4px 4px 0; white-space: nowrap; }}
    .path-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 15px 16px; margin-bottom: 12px; }}
    .path-title {{ font-weight: 700; font-size: 16px; margin-bottom: 8px; }}
    .signal-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; font-size: 12px; }}
    .signal-item {{ background: #f8fafc; padding: 6px 10px; border-radius: 999px; }}
    .split {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }}
    .note {{ background: #eef3fc; border-radius: 8px; padding: 12px 16px; font-size: 13px; color: #1e3a5f; margin: 16px 0; }}
    a {{ color: var(--blue); text-decoration: none; }}
    .news-list, .source-list {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 20px 14px 28px; }}
    @media (max-width: 900px) {{
      main {{ padding: 16px 12px 32px; }}
      .data-table {{ display: block; overflow-x: auto; white-space: nowrap; }}
      .split {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <nav class="toc">
    <a href="#hotspots">热点主线</a>
    <a href="#core-stocks">核心情绪池</a>
    <a href="#dragon">龙虎榜精选</a>
    <a href="#rotate">轮动推演</a>
    <a href="#watchlist">验证池与警示</a>
    <a href="#news">新闻线索</a>
    <a href="#action">明日观察</a>
  </nav>

  <h1>A股每日热点复盘 · {date_display}</h1>
  <div class="muted">生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 数据源：本地行情 / Tushare 龙虎榜 / 东方财富 / 公开新闻 | 本报告仅作复盘与线索分诊</div>

  <section class="summary-grid">
    <div class="metric-card"><div class="label">上涨/下跌</div><div class="value">{adv} / {dec}</div><div class="sub">涨跌比 {ratio:.2f}</div></div>
    <div class="metric-card"><div class="label">涨停近似统计</div><div class="value">{limit_count}</div><div class="sub">占比 {limit_share:.1%}</div></div>
    <div class="metric-card"><div class="label">全市场成交额</div><div class="value">{fmt_yi(turnover)}亿</div><div class="sub">情绪状态：{mood}</div></div>
    <div class="metric-card"><div class="label">龙虎榜上榜数</div><div class="value">{len(top_lhb)}</div><div class="sub">机构/股通活跃度参考</div></div>
  </section>

  <div class="emotion-hint">情绪观察：强势股集中在 MLCC/被动元件、小金属、算力材料、光连接四条线。高潮次日重点看中军承接与上游扩散，避免把公告反证标的误判成产业核心。</div>

  <h2 id="hotspots" class="section-title">1. 热点主线 · 资金主攻方向</h2>
  <table class="data-table">
    <thead><tr><th>主线主题</th><th>原始细分</th><th>涨幅</th><th>成交额(亿)</th><th>情绪龙头</th><th>驱动核心</th></tr></thead>
    <tbody>{table_rows(board_rows)}</tbody>
  </table>

  <h2 id="core-stocks" class="section-title">2. 核心情绪标的池 · 单主体多板块映射</h2>
  <table class="data-table">
    <thead><tr><th>个股</th><th>所属主线</th><th>涨幅</th><th>成交额(亿)</th><th>总市值(亿)</th><th>资金/承接信号</th></tr></thead>
    <tbody>{table_rows(core_rows)}</tbody>
  </table>

  <h2 id="dragon" class="section-title">3. 龙虎榜 · 机构/股通净买入聚焦</h2>
  <table class="data-table">
    <thead><tr><th>个股</th><th>涨跌幅</th><th>上榜类型</th><th>总净额(万元)</th><th>机构净额(万元)</th><th>股通净额(万元)</th><th>最大买方</th></tr></thead>
    <tbody>{table_rows(lhb_rows)}</tbody>
  </table>
  <div class="note">说明：HTML 只展示资金验证价值最高的席位摘要；完整龙虎榜明细已保存到 data/daily-market-review/lhb_hot_{trade_date}.csv。</div>

  <h2 id="rotate" class="section-title">4. 轮动推演 · 扩散路径与观察阈值</h2>
  {table_rows(rotation_cards)}

  <h2 id="watchlist" class="section-title">5. 重点验证池 & 风险警示表</h2>
  <div class="split">
    <div>
      <h3>强逻辑验证标的</h3>
      <table class="data-table">
        <thead><tr><th>标的</th><th>方向</th><th>验证核心</th><th>动作</th></tr></thead>
        <tbody>{table_rows(strong_rows)}</tbody>
      </table>
    </div>
    <div>
      <h3>主题映射警示</h3>
      <table class="data-table">
        <thead><tr><th>标的</th><th>方向</th><th>警示/反证</th><th>动作</th></tr></thead>
        <tbody>{table_rows(warning_rows)}</tbody>
      </table>
    </div>
  </div>

  <h2 id="news" class="section-title">6. 当日重要新闻 & 产业链印证</h2>
  <ul class="news-list">{table_rows(news_rows)}</ul>

  <h2 id="action" class="section-title">7. 明日盘前观察清单</h2>
  <div class="note">
    <ul>
      <li>MLCC/被动元件：看三环集团是否承接，达利凯普是否高位分歧后仍有换手资金。</li>
      <li>铜箔/玻纤扩散：看铜冠铜箔、国际复材是否继续强于板块，若中军缩量冲高回落则降低扩散预期。</li>
      <li>光连接/CPO：看光库科技、长芯博创、太辰光是否继续有机构/股通买入线索，优先验证订单和客户认证。</li>
      <li>钨/钼资源：盘前核对钨精矿、钼精矿及六氟化钨报价，价格不继续上行则只按情绪支线处理。</li>
      <li>风险过滤：双星新材、炬光科技这类公告反证标的，不按产业核心估值，只作为情绪温度计。</li>
    </ul>
  </div>

  <div class="emotion-hint">复盘结论：当前处于 AI硬件主线高潮后的链内扩散，优先跟踪光连接、铜箔/玻纤材料、被动元件中军。资源支线钨/钼需现货价格持续验证。已有公告反证的标的应降级为主题映射。</div>

  <h2 class="section-title">8. 来源</h2>
  <ul class="source-list">{source_rows}</ul>
</main>
</body>
</html>"""


def read_news(trade_date: str, boards: pd.DataFrame | None = None) -> pd.DataFrame:
    injected = os.getenv("DAILY_MARKET_REVIEW_NEWS_JSON", "").strip()
    if injected:
        try:
            records = json.loads(injected)
            frame = pd.DataFrame(records if isinstance(records, list) else [])
            if not frame.empty:
                frame = frame.rename(columns={"publishedAt": "published_at"})
                for column in ("title", "url", "published_at", "platform", "analysis"):
                    if column not in frame.columns:
                        frame[column] = ""
                terms: set[str] = {"AI", "算力", "芯片", "半导体", "服务器", "机器人", "新能源", "涨价", "订单", "产能", "政策", "业绩", "材料"}
                if boards is not None and not boards.empty:
                    for name in boards.get("board_name", pd.Series(dtype=str)).astype(str):
                        clean = re.sub(r"(概念|板块|行业|及配套|设备)$", "", name).strip()
                        if len(clean) >= 2:
                            terms.add(clean)
                        terms.update(token for token in re.split(r"[/、+\-]", board_theme(name)) if len(token) >= 2)
                pattern = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
                frame["relevance"] = frame["title"].astype(str).str.count(pattern, flags=re.I)
                frame["financePriority"] = frame["platform"].isin(["cls", "wallstreetcn"]).astype(int)
                relevant = frame[frame["relevance"] > 0]
                selected = relevant if not relevant.empty else frame[frame["financePriority"] > 0]
                return selected.sort_values(["relevance", "financePriority", "published_at"], ascending=[False, False, False]).head(40)
        except Exception as exc:
            print(f"Injected finance news unavailable: {exc}")
    paths = [
        STOCK_PROJECT / "data" / "raw" / "news" / f"cls_news_{trade_date}.csv",
        STOCK_PROJECT / "data" / "raw" / "news" / "cls_news_latest.csv",
    ]
    for path in paths:
        if path.exists():
            df = pd.read_csv(path)
            if "as_of_date" in df.columns:
                df = df[df["as_of_date"].astype(str).str.replace("-", "") == trade_date]
            keywords = "AI|硬件|MLCC|MPO|CPO|PCB|钨|钼|锗|有色|龙虎榜|服务器|光通信|六氟化钨"
            if "title" in df.columns:
                hit = df[df["title"].astype(str).str.contains(keywords, regex=True, na=False)]
                return hit if not hit.empty else df
    return pd.DataFrame(columns=["title", "url", "published_at"])


def clean_number(value: Any, digits: int = 2) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def build_native_report(
    trade_date: str,
    market: pd.DataFrame,
    boards: pd.DataFrame,
    board_leaders: dict[str, pd.DataFrame],
    lhb_hot: pd.DataFrame,
    news: pd.DataFrame,
) -> dict[str, Any]:
    """Build the structured payload consumed by FinVue's native review page."""
    adv = int(market["pct_chg"].gt(0).sum())
    dec = int(market["pct_chg"].lt(0).sum())
    flat = int(len(market) - adv - dec)
    amount = clean_number(market["amount"].fillna(0).sum() / 100000, 2) or 0
    limit_up = int(market["pct_chg"].ge(9.7).sum())
    limit_down = int(market["pct_chg"].le(-9.7).sum())
    grouped: dict[str, dict[str, Any]] = {}

    for _, board in boards.head(12).iterrows():
        code = str(board.get("board_code") or "")
        name = str(board.get("board_name") or code)
        theme = board_theme(name)
        sector = grouped.setdefault(
            theme,
            {
                "id": re.sub(r"[^a-zA-Z0-9]+", "-", theme).strip("-") or f"sector-{len(grouped) + 1}",
                "name": theme,
                "pctValues": [],
                "subsectors": [],
                "stocks": {},
                "analysis": {
                    "summary": infer_reason(name),
                    "chainLogic": "板块强度向产业链上下游扩散，需结合成交额、龙头承接与基本面证据确认持续性。",
                    "riseReason": infer_reason(name),
                    "fallRisk": "若核心标的放量滞涨、板块涨跌家数快速转弱或产业证据无法验证，行情可能退潮。",
                    "outlook": "次日观察龙头承接、弹性标的换手以及细分赛道是否继续扩散。",
                },
            },
        )
        pct = clean_number(board.get("pct_chg")) or 0
        sector["pctValues"].append(pct)
        leaders = board_leaders.get(code, pd.DataFrame()).copy()
        subsector = {
            "id": code,
            "name": name,
            "type": str(board.get("board_type") or "板块"),
            "pctChange": pct,
            "turnoverRate": clean_number(board.get("turnover_rate")),
            "amount": clean_number(board.get("amount") / 100000 if pd.notna(board.get("amount")) else None),
            "reason": infer_reason(name),
            "chainStage": infer_chain_stage(theme, name),
            "source": str(board.get("source") or "TuShare/东方财富"),
            "upCount": int(leaders["pct_chg"].gt(0).sum()) if not leaders.empty else 0,
            "downCount": int(leaders["pct_chg"].lt(0).sum()) if not leaders.empty else 0,
            "stocks": [],
        }
        if not leaders.empty:
            leaders = leaders.reset_index(drop=True)
            leader_index = int(leaders["amount"].fillna(0).idxmax()) if "amount" in leaders else 0
            elastic_order = leaders["pct_chg"].fillna(-999).sort_values(ascending=False).index.tolist()
            elastic_index = next((idx for idx in elastic_order if idx != leader_index), leader_index)
            prosperity_index = int(leaders["prosperity_score"].fillna(0).idxmax()) if "prosperity_score" in leaders else leader_index
            for idx, row in leaders.head(10).iterrows():
                role = "龙头" if idx == leader_index else "弹性" if idx == elastic_index else "景气" if idx == prosperity_index else "跟踪"
                stock_pct = clean_number(row.get("pct_chg")) or 0
                stock = {
                    "code": str(row.get("ts_code") or ""),
                    "name": str(row.get("name") or row.get("ts_code") or ""),
                    "industry": str(row.get("industry") or name),
                    "role": role,
                    "pctChange": stock_pct,
                    "close": clean_number(row.get("close")),
                    "amount": clean_number(row.get("amount") / 100000 if pd.notna(row.get("amount")) else None),
                    "turnoverRate": clean_number(row.get("turnover_rate")),
                    "marketValue": clean_number(row.get("total_mv") / 10000 if pd.notna(row.get("total_mv")) else None),
                    "limitTag": str(row.get("limit_tag") or ""),
                    "prosperityScore": clean_number(row.get("prosperity_score"), 1),
                    "elasticityScore": clean_number(row.get("elasticity_score"), 1),
                    "leadershipScore": clean_number(row.get("leadership_score"), 1),
                    "reason": (
                        f"随{name}板块共振上涨，当前强度主要来自板块资金聚集与成交放大。"
                        if stock_pct >= 0
                        else f"板块走强但个股回落，可能受获利兑现、基本面分歧或资金承接不足影响。"
                    ),
                    "risk": "关注放量滞涨、板块退潮和公司公告反证。",
                }
                subsector["stocks"].append(stock)
                current = sector["stocks"].get(stock["code"])
                if current is None or abs(stock_pct) > abs(current.get("pctChange") or 0):
                    sector["stocks"][stock["code"]] = stock
        sector["subsectors"].append(subsector)

    sectors: list[dict[str, Any]] = []
    sankey_nodes: list[dict[str, Any]] = []
    sankey_links: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    for sector in grouped.values():
        values = sector.pop("pctValues")
        sector["pctChange"] = round(sum(values) / len(values), 2) if values else 0
        sector["stocks"] = sorted(
            sector["stocks"].values(),
            key=lambda item: (item.get("prosperityScore") or 0, item.get("elasticityScore") or 0),
            reverse=True,
        )[:16]
        sectors.append(sector)
        sector_node = f"板块｜{sector['name']}"
        if sector_node not in seen_nodes:
            sankey_nodes.append({"name": sector_node, "kind": "sector", "pctChange": sector["pctChange"]})
            seen_nodes.add(sector_node)
        for subsector in sector["subsectors"][:4]:
            sub_node = f"赛道｜{subsector['name']}"
            if sub_node not in seen_nodes:
                sankey_nodes.append({"name": sub_node, "kind": "subsector", "pctChange": subsector["pctChange"]})
                seen_nodes.add(sub_node)
            sankey_links.append({"source": sector_node, "target": sub_node, "value": max(1, abs(subsector["pctChange"]))})
            for stock in subsector["stocks"][:6]:
                stock_node = f"标的｜{stock['code']}"
                if stock_node not in seen_nodes:
                    sankey_nodes.append({
                        "name": stock_node,
                        "displayName": stock["name"],
                        "kind": "stock",
                        "pctChange": stock["pctChange"],
                        "role": stock["role"],
                        "code": stock["code"],
                    })
                    seen_nodes.add(stock_node)
                sankey_links.append({"source": sub_node, "target": stock_node, "value": max(0.8, abs(stock["pctChange"]))})

    sectors.sort(key=lambda item: item.get("pctChange") or 0, reverse=True)
    news_items = []
    for _, row in news.head(24).iterrows():
        news_items.append({
            "title": str(row.get("title") or ""),
            "url": str(row.get("url") or ""),
            "publishedAt": str(row.get("published_at") or ""),
            "platform": str(row.get("platform") or ""),
            "relevance": int(row.get("relevance") or 0),
        })
    return {
        "version": 2,
        "tradeDate": trade_date,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "source": "TuShare同花顺板块" if any(str(item.get("source", "")).startswith("TuShare") for _, item in boards.head(12).iterrows()) else "东方财富板块降级源",
        "ai": {"status": "pending", "provider": "", "message": "等待 FinVue AI 路由生成归因"},
        "overview": {
            "advance": adv,
            "decline": dec,
            "flat": flat,
            "advanceDeclineRatio": round(adv / dec, 2) if dec else None,
            "amountYi": amount,
            "limitUp": limit_up,
            "limitDown": limit_down,
            "lhbCount": int(lhb_hot["ts_code"].nunique()) if not lhb_hot.empty else 0,
            "sentiment": "活跃" if adv > dec * 1.3 else "退潮" if dec > adv * 1.3 else "分歧",
        },
        "sectors": sectors[:6],
        "sankey": {"nodes": sankey_nodes, "links": sankey_links},
        "news": news_items,
    }


def save_frames(trade_date: str, boards: pd.DataFrame, top_lhb: pd.DataFrame, lhb_hot: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    boards.to_csv(DATA_DIR / f"hot_boards_{trade_date}.csv", index=False)
    top_lhb.to_csv(DATA_DIR / f"lhb_top_list_{trade_date}.csv", index=False)
    lhb_hot.to_csv(DATA_DIR / f"lhb_hot_{trade_date}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Trade date, YYYYMMDD. Defaults to latest open day.")
    parser.add_argument("--top-boards", type=int, default=12)
    parser.add_argument("--board-scan-limit", type=int, default=120)
    args = parser.parse_args()

    progress(
        "start",
        requested_arg=args.date,
        top_boards=args.top_boards,
        board_scan_limit=args.board_scan_limit,
        output_dir=str(OUTPUT_DIR),
        data_dir=str(DATA_DIR),
    )
    pro = pro_api()
    progress("tushare_client_ready")
    requested_date = args.date or previous_open_date(pro)
    progress("date_resolved", requested_date=requested_date)
    progress("market:load:start", requested_date=requested_date)
    trade_date, market = load_latest_available_market(pro, requested_date)
    progress("market:load:done", trade_date=trade_date, market_rows=len(market))
    progress("stock_basic:load:start")
    basic = load_stock_basic(pro)
    progress("stock_basic:load:done", rows=len(basic))
    market = market.merge(basic[["ts_code", "name", "industry", "market"]], on="ts_code", how="left")
    market = normalize_market_frame(market)
    progress("market:normalize:done", rows=len(market), columns=list(market.columns))

    progress("boards:fetch:start", trade_date=trade_date, limit_each_type=args.board_scan_limit)
    boards = fetch_boards_for_date(pro, trade_date, limit_each_type=args.board_scan_limit)
    progress("boards:fetch:done", rows=len(boards), columns=list(boards.columns))
    boards = normalize_board_frame(boards)
    progress("boards:normalize:done", rows=len(boards), columns=list(boards.columns))
    if boards.empty or "board_code" not in boards.columns:
        raise RuntimeError(f"{trade_date} 没有获取到可用的行业或概念板块数据")
    hot_boards = select_hot_boards(boards, max(args.top_boards, 12))
    progress(
        "boards:select_hot:done",
        rows=len(hot_boards),
        names=hot_boards.get("board_name", pd.Series(dtype=str)).head(args.top_boards).tolist(),
    )
    board_leaders: dict[str, pd.DataFrame] = {}
    for index, row in hot_boards.head(args.top_boards).reset_index(drop=True).iterrows():
        code = str(row["board_code"])
        name = str(row.get("board_name", ""))
        progress("leaders:fetch:start", index=index + 1, board_code=code, board_name=name)
        try:
            board_leaders[code] = leaders_for_board(pro, code, market, basic)
            progress("leaders:fetch:done", index=index + 1, board_code=code, board_name=name, rows=len(board_leaders[code]))
        except Exception as exc:
            board_leaders[code] = pd.DataFrame()
            progress("leaders:fetch:failed", index=index + 1, board_code=code, board_name=name, error=str(exc))
        time.sleep(0.05)

    progress("lhb:fetch:start", trade_date=trade_date)
    try:
        top_lhb, inst = get_lhb(pro, trade_date)
    except Exception as exc:
        print(f"TuShare LHB unavailable: {exc}", file=sys.stderr, flush=True)
        top_lhb, inst = pd.DataFrame(), pd.DataFrame()
        progress("lhb:fetch:failed", error=str(exc))
    else:
        progress("lhb:fetch:done", top_rows=len(top_lhb), inst_rows=len(inst))
    if top_lhb.empty:
        lhb_hot = pd.DataFrame()
    else:
        seats = aggregate_seats(inst)
        lhb = top_lhb.merge(seats, on="ts_code", how="left") if not seats.empty else top_lhb.copy()
        for column in ("inst_net", "north_net", "top_buyer"):
            if column not in lhb.columns:
                lhb[column] = 0 if column != "top_buyer" else ""
        lhb_hot = lhb[(lhb["pct_change"] > 0) | (lhb["net_amount"] > 0)].sort_values(
            ["pct_change", "net_amount"], ascending=[False, False]
        )
    progress("lhb:filter_hot:done", rows=len(lhb_hot))
    progress("news:read:start", trade_date=trade_date)
    news = read_news(trade_date, hot_boards)
    progress("news:read:done", rows=len(news))
    progress("render:start")
    html_text = render_html(trade_date, market, hot_boards, board_leaders, top_lhb, lhb_hot, news)
    progress("render:html:done", chars=len(html_text))
    native_report = build_native_report(trade_date, market, hot_boards, board_leaders, lhb_hot, news)
    progress("render:native_report:done", sector_count=len(native_report.get("sectors", [])))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"a_share_daily_review_{trade_date}.html"
    progress("write:html:start", path=str(out))
    out.write_text(html_text, encoding="utf-8")
    data_out = OUTPUT_DIR / f"a_share_daily_review_{trade_date}.json"
    progress("write:json:start", path=str(data_out))
    data_out.write_text(json.dumps(native_report, ensure_ascii=False, indent=2), encoding="utf-8")
    progress("write:frames:start")
    save_frames(trade_date, hot_boards, top_lhb, lhb_hot)
    progress("done", html=str(out), json=str(data_out), boards=len(hot_boards), lhb=len(top_lhb))
    print(json.dumps({"requested_date": requested_date, "trade_date": trade_date, "date_fallback": trade_date != requested_date, "html": str(out), "json": str(data_out), "boards": len(hot_boards), "lhb": len(top_lhb)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
