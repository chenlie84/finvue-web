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
CREATORS_DIR = ROOT / "creators"
COMMENTS_DIR = ROOT / "comments"
CREATORS_INDEX_PATH = CREATORS_DIR / "creators.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 aweme"
    ),
    "Referer": "https://www.douyin.com/",
}


def _ensure_dirs() -> None:
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    CREATORS_DIR.mkdir(parents=True, exist_ok=True)
    COMMENTS_DIR.mkdir(parents=True, exist_ok=True)


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
        "publish_at": _timestamp_to_iso(item.get("create_time")),
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


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _int_value(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _timestamp_to_iso(value: Any) -> str:
    timestamp = _int_value(value)
    if timestamp <= 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return ""


def _creator_key(author: dict[str, Any]) -> str:
    return str(author.get("sec_uid") or author.get("unique_id") or author.get("short_id") or "").strip()


def _profile_url(author: dict[str, Any]) -> str:
    sec_uid = str(author.get("sec_uid") or "").strip()
    unique_id = str(author.get("unique_id") or author.get("short_id") or "").strip()
    if sec_uid:
        return f"https://www.douyin.com/user/{sec_uid}"
    if unique_id:
        return f"https://www.douyin.com/search/{unique_id}?type=user"
    return ""


def _load_creators_index() -> dict[str, Any]:
    payload = _read_json(CREATORS_INDEX_PATH, {"creators": {}})
    if not isinstance(payload, dict):
        payload = {"creators": {}}
    if not isinstance(payload.get("creators"), dict):
        payload["creators"] = {}
    return payload


def _save_creators_index(payload: dict[str, Any]) -> None:
    CREATORS_DIR.mkdir(parents=True, exist_ok=True)
    payload["updatedAt"] = _utc_now()
    _write_json(CREATORS_INDEX_PATH, payload)


def _video_record_from_info(info: dict[str, Any], now: str | None = None) -> dict[str, Any]:
    now = now or _utc_now()
    aweme_id = str(info.get("aweme_id") or "")
    stats = info.get("statistics") if isinstance(info.get("statistics"), dict) else {}
    video = info.get("video") if isinstance(info.get("video"), dict) else {}
    duration_ms = _int_value(video.get("duration_ms"))
    duration_seconds = round(duration_ms / 1000) if duration_ms else 0
    create_time = info.get("create_time")
    metrics = {
        "diggCount": _int_value(stats.get("digg_count")),
        "commentCount": _int_value(stats.get("comment_count")),
        "collectCount": _int_value(stats.get("collect_count")),
        "shareCount": _int_value(stats.get("share_count")),
        "playCount": _int_value(stats.get("play_count")),
    }
    return {
        "awemeId": aweme_id,
        "title": info.get("desc") or "",
        "collectedAt": info.get("collected_at") or now,
        "createTime": create_time,
        "publishAt": _timestamp_to_iso(create_time),
        "durationMs": duration_ms,
        "durationSeconds": duration_seconds,
        "metrics": metrics,
        "diggCount": metrics["diggCount"],
        "commentCount": metrics["commentCount"],
        "collectCount": metrics["collectCount"],
        "shareCount": metrics["shareCount"],
        "playCount": metrics["playCount"],
        "audioDownloadUrl": f"/api/data-collection/douyin/{aweme_id}/audio" if aweme_id else "",
        "commentsDownloadUrl": f"/api/data-collection/douyin/{aweme_id}/comments" if aweme_id else "",
    }


def _merge_video_record(video: dict[str, Any], info: dict[str, Any] | None = None) -> tuple[dict[str, Any], bool]:
    merged = dict(video)
    before = json.dumps(merged, sort_keys=True, ensure_ascii=False)
    aweme_id = str(merged.get("awemeId") or "")
    if info:
        from_info = _video_record_from_info(info)
        for key, value in from_info.items():
            if key in {"audioDownloadUrl", "commentsDownloadUrl"}:
                if value and not merged.get(key):
                    merged[key] = value
            elif key == "metrics":
                current = merged.get("metrics") if isinstance(merged.get("metrics"), dict) else {}
                merged["metrics"] = {**from_info["metrics"], **current}
            elif value not in ("", None, 0) and not merged.get(key):
                merged[key] = value
    metrics = merged.get("metrics") if isinstance(merged.get("metrics"), dict) else {}
    for key in ("diggCount", "commentCount", "collectCount", "shareCount", "playCount"):
        metrics[key] = _int_value(metrics.get(key, merged.get(key)))
        merged[key] = metrics[key]
    merged["metrics"] = metrics
    if not merged.get("publishAt"):
        merged["publishAt"] = _timestamp_to_iso(merged.get("createTime"))
    if not merged.get("durationSeconds") and merged.get("durationMs"):
        merged["durationSeconds"] = round(_int_value(merged.get("durationMs")) / 1000)
    if aweme_id and not merged.get("commentsDownloadUrl"):
        merged["commentsDownloadUrl"] = f"/api/data-collection/douyin/{aweme_id}/comments"
    if aweme_id and not merged.get("audioDownloadUrl"):
        merged["audioDownloadUrl"] = f"/api/data-collection/douyin/{aweme_id}/audio"
    after = json.dumps(merged, sort_keys=True, ensure_ascii=False)
    return merged, before != after


def _apply_creator_video_summary(creator: dict[str, Any]) -> None:
    videos = creator.get("videos") if isinstance(creator.get("videos"), list) else []
    creator["videoCount"] = len(videos)
    creator["totalDiggCount"] = sum(_int_value(item.get("diggCount")) for item in videos if isinstance(item, dict))
    creator["totalCommentCount"] = sum(_int_value(item.get("commentCount")) for item in videos if isinstance(item, dict))
    creator["totalCollectCount"] = sum(_int_value(item.get("collectCount")) for item in videos if isinstance(item, dict))
    creator["totalShareCount"] = sum(_int_value(item.get("shareCount")) for item in videos if isinstance(item, dict))
    creator["totalDurationSeconds"] = sum(_int_value(item.get("durationSeconds")) for item in videos if isinstance(item, dict))
    publish_times = [str(item.get("publishAt") or "") for item in videos if isinstance(item, dict) and item.get("publishAt")]
    creator["lastPublishAt"] = max(publish_times) if publish_times else ""


def _upsert_creator(info: dict[str, Any]) -> dict[str, Any]:
    author = info.get("author") if isinstance(info.get("author"), dict) else {}
    key = _creator_key(author)
    if not key:
        return {}
    index = _load_creators_index()
    creators = index["creators"]
    existing = creators.get(key) if isinstance(creators.get(key), dict) else {}
    now = _utc_now()
    videos = [item for item in (existing.get("videos") or []) if isinstance(item, dict)]
    aweme_id = str(info.get("aweme_id") or "")
    videos = [item for item in videos if str(item.get("awemeId")) != aweme_id]
    videos.insert(0, _video_record_from_info(info, now))
    creator = {
        **existing,
        "id": key,
        "nickname": str(author.get("nickname") or existing.get("nickname") or ""),
        "shortId": str(author.get("short_id") or existing.get("shortId") or ""),
        "uniqueId": str(author.get("unique_id") or existing.get("uniqueId") or ""),
        "secUid": str(author.get("sec_uid") or existing.get("secUid") or ""),
        "signature": str(author.get("signature") or existing.get("signature") or ""),
        "avatar": str(author.get("avatar") or existing.get("avatar") or ""),
        "awemeCount": author.get("aweme_count") or existing.get("awemeCount") or 0,
        "followingCount": author.get("following_count") or existing.get("followingCount") or 0,
        "profileUrl": _profile_url(author) or existing.get("profileUrl") or "",
        "tags": existing.get("tags") if isinstance(existing.get("tags"), list) else [],
        "category": str(existing.get("category") or ""),
        "note": str(existing.get("note") or ""),
        "firstCollectedAt": existing.get("firstCollectedAt") or now,
        "lastCollectedAt": now,
        "latestAwemeId": aweme_id,
        "videos": videos[:80],
    }
    _apply_creator_video_summary(creator)
    creators[key] = creator
    _save_creators_index(index)
    return creator


def list_creators() -> list[dict[str, Any]]:
    _ensure_dirs()
    index = _load_creators_index()
    creators = index.get("creators") or {}
    if not creators:
        for path in sorted(METADATA_DIR.glob("*.info.json"), key=lambda item: item.stat().st_mtime):
            info = _read_json(path, {})
            if isinstance(info, dict):
                _upsert_creator(info)
        index = _load_creators_index()
        creators = index.get("creators") or {}
    items = [item for item in creators.values() if isinstance(item, dict)]
    changed = False
    for item in items:
        videos = item.get("videos") if isinstance(item.get("videos"), list) else []
        merged_videos = []
        for video in videos:
            if not isinstance(video, dict):
                continue
            aweme_id = str(video.get("awemeId") or "").strip()
            info = None
            info_path = METADATA_DIR / f"{aweme_id}.info.json"
            if aweme_id and info_path.exists():
                loaded_info = _read_json(info_path, {})
                info = loaded_info if isinstance(loaded_info, dict) else None
            merged_video, video_changed = _merge_video_record(video, info)
            merged_videos.append(merged_video)
            changed = changed or video_changed
        item["videos"] = merged_videos
        before_summary = json.dumps({key: item.get(key) for key in ("videoCount", "totalDiggCount", "totalCommentCount", "totalCollectCount", "totalShareCount", "totalDurationSeconds", "lastPublishAt")}, sort_keys=True, ensure_ascii=False)
        _apply_creator_video_summary(item)
        after_summary = json.dumps({key: item.get(key) for key in ("videoCount", "totalDiggCount", "totalCommentCount", "totalCollectCount", "totalShareCount", "totalDurationSeconds", "lastPublishAt")}, sort_keys=True, ensure_ascii=False)
        changed = changed or before_summary != after_summary
    if changed:
        index["creators"] = {str(item.get("id")): item for item in items if item.get("id")}
        _save_creators_index(index)
    return sorted(items, key=lambda item: str(item.get("lastCollectedAt") or ""), reverse=True)


def update_creator(creator_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dirs()
    creator_id = str(creator_id or "").strip()
    index = _load_creators_index()
    creators = index["creators"]
    creator = creators.get(creator_id)
    if not isinstance(creator, dict):
        raise FileNotFoundError("没有找到该主播记录")
    if "tags" in payload:
        raw_tags = payload.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = re.split(r"[,，\s]+", raw_tags)
        creator["tags"] = [str(item).strip() for item in raw_tags if str(item).strip()][:24]
    if "category" in payload:
        creator["category"] = str(payload.get("category") or "").strip()[:80]
    if "note" in payload:
        creator["note"] = str(payload.get("note") or "").strip()[:500]
    creator["updatedAt"] = _utc_now()
    creators[creator_id] = creator
    _save_creators_index(index)
    return creator


def _normalize_comment(item: dict[str, Any]) -> dict[str, Any]:
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    return {
        "cid": str(item.get("cid") or item.get("id") or ""),
        "text": str(item.get("text") or item.get("content") or ""),
        "createTime": item.get("create_time") or item.get("createTime"),
        "diggCount": item.get("digg_count") or item.get("diggCount") or 0,
        "replyCommentTotal": item.get("reply_comment_total") or item.get("replyCommentTotal") or 0,
        "user": {
            "uid": str(user.get("uid") or ""),
            "secUid": str(user.get("sec_uid") or ""),
            "nickname": str(user.get("nickname") or ""),
            "uniqueId": str(user.get("unique_id") or ""),
            "shortId": str(user.get("short_id") or ""),
        },
    }


def _comment_api_candidates(aweme_id: str, cursor: int, count: int) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "https://www.douyin.com/aweme/v1/web/comment/list/",
            {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "aweme_id": aweme_id,
                "cursor": cursor,
                "count": count,
                "item_type": 0,
            },
        ),
        (
            "https://www.iesdouyin.com/web/api/v2/aweme/comment/",
            {
                "aweme_id": aweme_id,
                "cursor": cursor,
                "count": count,
            },
        ),
    ]


def fetch_douyin_comments(aweme_id: str, source_url: str = "", limit: int = 50) -> dict[str, Any]:
    aweme_id = str(aweme_id or "").strip()
    if not aweme_id:
        return {"ok": False, "comments": [], "error": "缺少视频 ID"}
    collected: list[dict[str, Any]] = []
    cursor = 0
    errors: list[str] = []
    headers = {
        **HEADERS,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": source_url or f"https://www.douyin.com/video/{aweme_id}",
    }
    while len(collected) < limit:
        page_loaded = False
        for url, params in _comment_api_candidates(aweme_id, cursor, min(20, limit - len(collected))):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=15)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                continue
            raw_comments = data.get("comments") or data.get("comment_list") or data.get("data") or []
            if not isinstance(raw_comments, list):
                raw_comments = []
            collected.extend(_normalize_comment(item) for item in raw_comments if isinstance(item, dict))
            cursor = int(data.get("cursor") or data.get("next_cursor") or cursor + len(raw_comments))
            has_more = bool(data.get("has_more"))
            page_loaded = True
            if not has_more or not raw_comments:
                return {"ok": True, "comments": collected[:limit], "error": "", "cursor": cursor, "hasMore": has_more}
            break
        if not page_loaded:
            return {"ok": False, "comments": collected[:limit], "error": errors[-1] if errors else "评论接口未返回数据"}
    return {"ok": True, "comments": collected[:limit], "error": "", "cursor": cursor, "hasMore": True}


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
    info["collected_at"] = _utc_now()
    if isinstance(info.get("author"), dict):
        info["author"]["profile_url"] = _profile_url(info["author"])

    share_path = METADATA_DIR / f"{aweme_id}.share.html"
    info_path = METADATA_DIR / f"{aweme_id}.info.json"
    play_path = METADATA_DIR / f"{aweme_id}.play_url.txt"
    comments_path = COMMENTS_DIR / f"{aweme_id}.comments.json"
    share_path.write_text(html, encoding="utf-8")
    play_url = _first_url_from_list(info.get("video", {}).get("play_addr"))
    if play_url:
        play_path.write_text(play_url, encoding="utf-8")
    comments_result = fetch_douyin_comments(aweme_id, source_url=share_url, limit=50)
    expected_comments = int((info.get("statistics") or {}).get("comment_count") or 0)
    if expected_comments > 0 and not comments_result.get("comments"):
        comments_result = {
            **comments_result,
            "ok": False,
            "error": comments_result.get("error") or "评论接口未返回明细，可能需要登录态或风控签名参数",
        }
    comments_payload = {
        "awemeId": aweme_id,
        "sourceUrl": share_url,
        "collectedAt": _utc_now(),
        "ok": bool(comments_result.get("ok")),
        "error": comments_result.get("error") or "",
        "comments": comments_result.get("comments") or [],
    }
    _write_json(comments_path, comments_payload)
    info["comments"] = {
        "collected": bool(comments_payload["ok"]),
        "count": len(comments_payload["comments"]),
        "error": comments_payload["error"],
        "path": str(comments_path),
    }
    creator = _upsert_creator(info)
    _write_json(info_path, info)

    files = {
        "info": str(info_path),
        "shareHtml": str(share_path),
        "playUrl": str(play_path) if play_url else "",
        "comments": str(comments_path),
    }
    info["audio_download_url"] = f"/api/data-collection/douyin/{aweme_id}/audio" if play_url else ""
    info["comments_download_url"] = f"/api/data-collection/douyin/{aweme_id}/comments"
    return {"ok": True, "info": info, "creator": creator, "comments": comments_payload, "files": files, "root": str(ROOT)}


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


def comments_file_for_aweme(aweme_id: str) -> Path:
    _ensure_dirs()
    aweme_id = str(aweme_id or "").strip()
    if not re.match(r"^\d{16,22}$", aweme_id):
        raise ValueError("视频 ID 不合法")
    path = (COMMENTS_DIR / f"{aweme_id}.comments.json").resolve()
    if COMMENTS_DIR.resolve() not in path.parents:
        raise ValueError("评论文件路径不合法")
    if not path.exists() or not path.is_file():
        info = info_for_aweme(aweme_id)
        payload = {
            "awemeId": aweme_id,
            "sourceUrl": info.get("source_url") or "",
            "collectedAt": _utc_now(),
            "ok": False,
            "error": (info.get("comments") or {}).get("error") or "该视频暂无评论明细文件，已生成空评论导出占位",
            "expectedCommentCount": (info.get("statistics") or {}).get("comment_count") or 0,
            "comments": [],
        }
        _write_json(path, payload)
    return path


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
            "creatorId": _creator_key(info.get("author") or {}),
            "creatorProfileUrl": (info.get("author") or {}).get("profile_url") or _profile_url(info.get("author") or {}),
            "collectedAt": info.get("collected_at") or datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "createTime": info.get("create_time"),
            "publishAt": _timestamp_to_iso(info.get("create_time")),
            "durationMs": _int_value((info.get("video") or {}).get("duration_ms")),
            "durationSeconds": round(_int_value((info.get("video") or {}).get("duration_ms")) / 1000) if _int_value((info.get("video") or {}).get("duration_ms")) else 0,
            "statistics": info.get("statistics") if isinstance(info.get("statistics"), dict) else {},
            "infoPath": str(path),
            "commentsPath": str(COMMENTS_DIR / f"{aweme_id}.comments.json"),
            "commentsCollected": bool((info.get("comments") or {}).get("collected")),
            "commentsCount": (info.get("comments") or {}).get("count") or 0,
            "commentsDownloadUrl": f"/api/data-collection/douyin/{aweme_id}/comments",
            "audioDownloadUrl": f"/api/data-collection/douyin/{aweme_id}/audio" if _first_url_from_list((info.get("video") or {}).get("play_addr")) else "",
        })
    return items
