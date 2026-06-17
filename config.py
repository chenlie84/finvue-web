"""FinVue FastAPI runtime configuration."""
from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(BASE_DIR / ".env.production")
_load_env_file(BASE_DIR / ".env")


ENV = os.environ.get("ENV") or os.environ.get("NODE_ENV") or os.environ.get("environment", "DEV")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
RELOAD = os.environ.get("RELOAD", "false").lower() == "true"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8080")
ALLOW_OPEN_REGISTRATION = os.environ.get("ALLOW_OPEN_REGISTRATION", "true").lower() == "true"
AUTH_SECRET = os.environ.get("AUTH_SECRET") or "dev-only-local-auth-secret"
SESSION_COOKIE_NAME = "lab_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
AUTO_MIGRATE = os.environ.get("AUTO_MIGRATE", "true").lower() != "false"

MYSQL_URL = os.environ.get("MYSQL_URL", "")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "")
MYSQL_USER = os.environ.get("MYSQL_USER", "")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
OBJECT_STORAGE_DIR = Path(os.environ.get("OBJECT_STORAGE_DIR", str(BASE_DIR / ".objects")))
ANCHOR_DASHBOARD_PYTHON = os.environ.get("ANCHOR_DASHBOARD_PYTHON", "/usr/bin/python3")
DAILY_MARKET_REVIEW_ROOT = Path(os.environ.get("DAILY_MARKET_REVIEW_ROOT", str(OBJECT_STORAGE_DIR / "market-review")))
DAILY_MARKET_REVIEW_OUTPUT_DIR = Path(
    os.environ.get("DAILY_MARKET_REVIEW_OUTPUT_DIR", str(DAILY_MARKET_REVIEW_ROOT / "outputs" / "daily-market-review"))
)
DAILY_MARKET_REVIEW_SCRIPT = Path(
    os.environ.get("DAILY_MARKET_REVIEW_SCRIPT", str(BASE_DIR / "scripts" / "generate_daily_market_review.py"))
)


def _proxy_url(value: str) -> str:
    raw = str(value or "").strip()
    if raw and "://" not in raw:
        return f"http://{raw}"
    return raw


HTTP_PROXY = _proxy_url(os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY") or "")
HTTPS_PROXY = _proxy_url(os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or "")

# CEPH S3 object storage. Generated reports and uploaded source files should not
# depend on local disk when deployed across multiple machines.
CEPH_ACCESS_KEY = os.environ.get("CEPH_ACCESS_KEY", "")
CEPH_SECRET_KEY = os.environ.get("CEPH_SECRET_KEY", "")
CEPH_URL = os.environ.get("CEPH_URL", "")
CEPH_REGION = os.environ.get("CEPH_REGION", "default")
CEPH_BUCKET = os.environ.get("CEPH_BUCKET", "")
CEPH_KEY_PREFIX = os.environ.get("CEPH_KEY_PREFIX", "finvue/")
SOURCE_CEPH_KEY_PREFIX = os.environ.get("SOURCE_CEPH_KEY_PREFIX", "finvue_source/")
IMAGE_CEPH_KEY_PREFIX = os.environ.get("IMAGE_CEPH_KEY_PREFIX", "finvue_images/")

PAN_ACCESS_KEY = os.environ.get("PAN_ACCESS_KEY", CEPH_ACCESS_KEY)
PAN_SECRET_KEY = os.environ.get("PAN_SECRET_KEY", CEPH_SECRET_KEY)
PAN_BUCKET = os.environ.get("PAN_BUCKET", CEPH_BUCKET)
PAN_NAME = os.environ.get("PAN_NAME", "")
PAN_SHARER = os.environ.get("PAN_SHARER", "")
PAN_VALID_MINUTES = int(os.environ.get("PAN_VALID_MINUTES", str(60 * 24 * 365)))
PAN_URL_BASE = os.environ.get("PAN_URL_BASE", "")
USE_CEPH_S3 = os.environ.get("USE_CEPH_S3", "false").lower() == "true"


def has_mysql_config() -> bool:
    return bool(MYSQL_URL or (MYSQL_HOST and MYSQL_DATABASE and MYSQL_USER))


def has_ceph_config() -> bool:
    return bool(USE_CEPH_S3 and CEPH_ACCESS_KEY and CEPH_SECRET_KEY and CEPH_URL and CEPH_BUCKET)

# 远程数据源数据库配置（用于在线导入直播和短视频数据）
REMOTE_DB_HOST = os.environ.get("REMOTE_DB_HOST", "")
REMOTE_DB_PORT = int(os.environ.get("REMOTE_DB_PORT", "3306"))
REMOTE_DB_DATABASE = os.environ.get("REMOTE_DB_DATABASE", "")
REMOTE_DB_USER = os.environ.get("REMOTE_DB_USER", "")
REMOTE_DB_PASSWORD = os.environ.get("REMOTE_DB_PASSWORD", "")

def has_remote_db_config() -> bool:
    return bool(REMOTE_DB_HOST and REMOTE_DB_DATABASE and REMOTE_DB_USER)

# 热点抓取配置
# 设置 HOTSPOT_API_ENABLED=true 启用自动抓取
# 数据源使用 newsnow.busiyi.world（与 TrendRadar 项目一致的稳定 API）
HOTSPOT_API_ENABLED = os.environ.get("HOTSPOT_API_ENABLED", "false").lower() == "true"
HOTSPOT_API_URL = os.environ.get("HOTSPOT_API_URL", "https://newsnow.busiyi.world/api/s")
