from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(os.getenv("FINVUE_DATA_COLLECTION_ROOT", str(Path.home() / "Documents" / "抖音数据")))
DOWNLOAD_DIR = ROOT / "downloads"
METADATA_DIR = ROOT / "metadata"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 aweme"
    ),
    "Referer": "https://www.douyin.com/",
}


def _ensure_dirs() -> None:
    METADATA_DIR.mkdir(parents=True, exist_ok=True)


def _first_url(value: str) -> str:
    match = re.search(r"https?://[^\s]+", value)
    return match.group(0).rstrip("，。；;") if match else ""


def _video_id_from_text(value: str) -> str:
    patterns = [
        r"/video/(\d+)",
        r"/share/video/(\d+)",
        r"modal_id=(\d+)",
        r"aweme_id=(\d+)",
        r"\b(\d{16,22})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return ""


def _request_get(url: str, timeout: int = 20) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    return response


def resolve_douyin_url(raw: str) -> tuple[str, str]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("请输入抖音分享链接或视频 ID")
    url = _first_url(text)
    video_id = _video_id_from_text(text)
    if not url and video_id:
        url = f"https://www.douyin.com/video/{video_id}"
    if not url:
        raise ValueError("没有识别到有效链接或视频 ID")
    resolved = _request_get(url, timeout=15).url if "v.douyin.com" in url or "iesdouyin.com" in url else url
    video_id = _video_id_from_text(resolved) or video_id
    if video_id and "iesdouyin.com" not in resolved and "share/video" not in resolved:
        resolved = f"https://www.iesdouyin.com/share/video/{video_id}/?from=web_code_link"
    return resolved, video_id


def _extract_router_data(html: str) -> dict[str, Any]:
    match = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})</script>", html, re.S)
    if not match:
        raise RuntimeError("公开分享页没有暴露 _ROUTER_DATA，可能需要重新复制分享链接或页面策略已变化")
    return json.loads(match.group(1))


def _first_url_from_list(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("url_list")
    if isinstance(value, list):
        for item in value:
            if item:
                return str(item)
    return ""


def _extract_item(router_data: dict[str, Any]) -> dict[str, Any]:
    loader = router_data.get("loaderData") if isinstance(router_data.get("loaderData"), dict) else {}
    page = loader.get("video_(id)/page") if isinstance(loader.get("video_(id)/page"), dict) else {}
    info = page.get("videoInfoRes") if isinstance(page.get("videoInfoRes"), dict) else {}
    items = info.get("item_list") if isinstance(info.get("item_list"), list) else []
    if not items:
        raise RuntimeError("没有在分享页里找到视频 item_list")
    return items[0]


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    music = item.get("music") if isinstance(item.get("music"), dict) else {}
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
    text_extra = item.get("text_extra") if isinstance(item.get("text_extra"), list) else []
    play_urls = video.get("play_addr", {}).get("url_list") if isinstance(video.get("play_addr"), dict) else []
    cover = _first_url_from_list(video.get("cover"))
    avatar = _first_url_from_list(author.get("avatar_thumb"))
    return {
        "aweme_id": str(item.get("aweme_id") or item.get("group_id_str") or ""),
        "desc": str(item.get("desc") or ""),
        "create_time": item.get("create_time"),
        "statistics": {
            "aweme_id": str(statistics.get("aweme_id") or item.get("aweme_id") or ""),
            "comment_count": statistics.get("comment_count") or 0,
            "digg_count": statistics.get("digg_count") or 0,
            "play_count": statistics.get("play_count") or 0,
            "share_count": statistics.get("share_count") or 0,
            "collect_count": statistics.get("collect_count") or 0,
        },
        "risk_infos": item.get("risk_infos") if isinstance(item.get("risk_infos"), dict) else {},
        "author": {
            "nickname": str(author.get("nickname") or ""),
            "short_id": str(author.get("short_id") or ""),
            "unique_id": str(author.get("unique_id") or ""),
            "sec_uid": str(author.get("sec_uid") or ""),
            "signature": str(author.get("signature") or ""),
            "aweme_count": author.get("aweme_count") or 0,
            "following_count": author.get("following_count") or 0,
            "avatar": avatar,
        },
        "music": {
            "mid": str(music.get("mid") or ""),
            "title": str(music.get("title") or ""),
            "author": str(music.get("author") or ""),
            "duration_seconds": music.get("duration") or 0,
        },
        "video": {
            "width": video.get("width") or 0,
            "height": video.get("height") or 0,
            "duration_ms": video.get("duration") or 0,
            "play_addr": play_urls if isinstance(play_urls, list) else [],
            "cover": cover,
        },
        "hashtags": [str(item.get("hashtag_name")) for item in text_extra if item.get("hashtag_name")],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_audio_from_url(play_url: str, aweme_id: str) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法抽取音频")
    temp_dir = Path(tempfile.mkdtemp(prefix="finvue-douyin-audio-"))
    audio_path = temp_dir / f"{aweme_id}.audio.m4a"
    header_text = "".join(f"{key}: {value}\r\n" for key, value in HEADERS.items())
    try:
        subprocess.run(
            [ffmpeg, "-y", "-headers", header_text, "-i", play_url, "-vn", "-acodec", "copy", str(audio_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return audio_path


def collect_douyin_video(source: str) -> dict[str, Any]:
    _ensure_dirs()
    share_url, hinted_id = resolve_douyin_url(source)
    html = _request_get(share_url, timeout=25).text
    router_data = _extract_router_data(html)
    info = _normalize_item(_extract_item(router_data))
    aweme_id = info.get("aweme_id") or hinted_id
    if not aweme_id:
        raise RuntimeError("未能识别视频 ID")
    info["aweme_id"] = aweme_id
    info["source_url"] = share_url
    info["collected_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    share_path = METADATA_DIR / f"{aweme_id}.share.html"
    info_path = METADATA_DIR / f"{aweme_id}.info.json"
    play_path = METADATA_DIR / f"{aweme_id}.play_url.txt"
    share_path.write_text(html, encoding="utf-8")
    _write_json(info_path, info)
    play_url = _first_url_from_list(info.get("video", {}).get("play_addr"))
    if play_url:
        play_path.write_text(play_url, encoding="utf-8")

    files = {"info": str(info_path), "shareHtml": str(share_path), "playUrl": str(play_path) if play_url else ""}
    info["audio_download_url"] = f"/api/data-collection/douyin/{aweme_id}/audio" if play_url else ""
    return {"ok": True, "info": info, "files": files, "root": str(ROOT)}


def info_for_aweme(aweme_id: str) -> dict[str, Any]:
    path = METADATA_DIR / f"{aweme_id}.info.json"
    if not path.exists():
        raise FileNotFoundError("没有找到该视频的采集记录，请先采集一次")
    return json.loads(path.read_text(encoding="utf-8"))


def build_audio_download(aweme_id: str) -> Path:
    info = info_for_aweme(aweme_id)
    play_url = _first_url_from_list(info.get("video", {}).get("play_addr"))
    if not play_url:
        raise RuntimeError("该记录没有可用播放地址，无法抽取音频")
    return _extract_audio_from_url(play_url, aweme_id)


def recent_items(limit: int = 20) -> list[dict[str, Any]]:
    _ensure_dirs()
    items = []
    for path in sorted(METADATA_DIR.glob("*.info.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        aweme_id = str(info.get("aweme_id") or path.stem.replace(".info", ""))
        items.append({
            "awemeId": aweme_id,
            "title": info.get("desc") or "",
            "author": (info.get("author") or {}).get("nickname") or "",
            "collectedAt": info.get("collected_at") or datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "infoPath": str(path),
            "audioDownloadUrl": f"/api/data-collection/douyin/{aweme_id}/audio" if _first_url_from_list((info.get("video") or {}).get("play_addr")) else "",
        })
    return items
