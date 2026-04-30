"""Ceph S3 storage helpers for uploaded sources and generated artifacts."""
from __future__ import annotations

import hashlib
import mimetypes
import random
import re
import time
from pathlib import Path
from typing import Optional

import config


def _safe_name(value: str | None, fallback: str = "file") -> str:
    name = str(value or fallback).strip()
    name = re.sub(r"[\\/:*?\"<>|\r\n]+", "-", name).strip(" .-")
    return name or fallback


def _timestamp_key(prefix: str, file_name: str | None) -> str:
    safe = _safe_name(file_name)
    ts = time.strftime("%Y%m%d%H%M%S")
    nonce = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=8))
    return f"{prefix.rstrip('/')}/{ts}_{nonce}_{safe}"


def _client():
    if not config.has_ceph_config():
        raise RuntimeError("Ceph S3 未配置或已关闭")
    try:
        from boto3.session import Session
        from botocore.config import Config
    except Exception as exc:  # pragma: no cover - depends on deployment package
        raise RuntimeError("S3 组件未安装，请先执行：pip install -r requirements.txt") from exc
    session = Session(
        aws_access_key_id=config.CEPH_ACCESS_KEY,
        aws_secret_access_key=config.CEPH_SECRET_KEY,
    )
    return session.client(
        "s3",
        endpoint_url=config.CEPH_URL,
        region_name=config.CEPH_REGION,
        config=Config(proxies={}),
    )


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _sign(sign_data: dict, timestamp: int, nonce: str) -> str:
    params = [f"{key}={value}" for key, value in sign_data.items()]
    raw = ":".join(
        [
            config.PAN_ACCESS_KEY,
            "&".join(sorted(params)),
            str(timestamp),
            nonce,
            config.PAN_SECRET_KEY,
        ]
    )
    return _md5(raw)


def share_url(key: str) -> Optional[str]:
    """Generate a public CDN URL for an object key."""
    try:
        import requests
    except Exception:
        return direct_url(key)

    timestamp = int(time.time())
    nonce = "".join(str(random.randint(0, 9)) for _ in range(4))
    sign_data = {
        "bucket": config.PAN_BUCKET,
        "name": config.PAN_NAME,
        "public": "true",
        "sharer": config.PAN_SHARER,
        "targetPath": key,
        "validTime": config.PAN_VALID_MINUTES,
    }
    query = {
        "accessKey": config.PAN_ACCESS_KEY,
        "timestamp": timestamp,
        "nonce": nonce,
        "sign": _sign(sign_data, timestamp, nonce),
    }
    body = {
        "bucket": config.PAN_BUCKET,
        "targetPath": key,
        "validTime": config.PAN_VALID_MINUTES,
        "sharer": config.PAN_SHARER,
        "name": config.PAN_NAME,
        "public": True,
    }
    try:
        response = requests.post(config.PAN_URL_BASE, params=query, json=body, timeout=8, proxies={"http": None, "https": None})
        response.raise_for_status()
        data = response.json()
    except Exception:
        return direct_url(key)
    if isinstance(data.get("data"), dict) and data["data"].get("origin"):
        return str(data["data"]["origin"])
    if data.get("origin"):
        return str(data["origin"])
    return direct_url(key)


def direct_url(key: str) -> str:
    return f"{config.CEPH_URL.rstrip('/')}/{config.CEPH_BUCKET}/{key}"


def upload_bytes(
    data: bytes,
    *,
    file_name: str,
    prefix: str | None = None,
    content_type: str | None = None,
) -> dict:
    if not data:
        raise RuntimeError("上传内容为空")
    key = _timestamp_key(prefix or config.CEPH_KEY_PREFIX, file_name)
    content_type = content_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    _client().put_object(Bucket=config.CEPH_BUCKET, Key=key, Body=data, ContentType=content_type)
    url = share_url(key)
    return {"key": key, "url": url, "bytes": len(data), "fileName": _safe_name(file_name), "contentType": content_type}


def upload_file(path: str | Path, *, key: str | None = None, prefix: str | None = None, content_type: str | None = None) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        raise RuntimeError(f"源文件不存在：{file_path}")
    data = file_path.read_bytes()
    if key:
        content_type = content_type or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        _client().put_object(Bucket=config.CEPH_BUCKET, Key=key, Body=data, ContentType=content_type)
        return {"key": key, "url": share_url(key), "bytes": len(data), "fileName": file_path.name, "contentType": content_type}
    return upload_bytes(data, file_name=file_path.name, prefix=prefix, content_type=content_type)
