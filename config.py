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
MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql0200.3337-wm.db.idc")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3337"))
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "process_analysis")
MYSQL_USER = os.environ.get("MYSQL_USER", "process_analysis")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "ns7ubvy96ncHncOTOeHS")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
OBJECT_STORAGE_DIR = Path(os.environ.get("OBJECT_STORAGE_DIR", str(BASE_DIR / ".objects")))
ANCHOR_DASHBOARD_PYTHON = os.environ.get("ANCHOR_DASHBOARD_PYTHON", "/usr/bin/python3")

# CEPH S3 object storage. Generated reports and uploaded source files should not
# depend on local disk when deployed across multiple machines.
CEPH_ACCESS_KEY = os.environ.get("CEPH_ACCESS_KEY", "A9GB4FCO9BJZOWY60OOV")
CEPH_SECRET_KEY = os.environ.get("CEPH_SECRET_KEY", "x3ecBEjD7ZABGf5yW51CegFh442f865LqLVFxeAZ")
CEPH_URL = os.environ.get("CEPH_URL", "http://s3.creditease.corp")
CEPH_REGION = os.environ.get("CEPH_REGION", "default")
CEPH_BUCKET = os.environ.get("CEPH_BUCKET", "yxd-risk-public-read")
CEPH_KEY_PREFIX = os.environ.get("CEPH_KEY_PREFIX", "finvue/")
SOURCE_CEPH_KEY_PREFIX = os.environ.get("SOURCE_CEPH_KEY_PREFIX", "finvue_source/")
IMAGE_CEPH_KEY_PREFIX = os.environ.get("IMAGE_CEPH_KEY_PREFIX", "finvue_images/")

PAN_ACCESS_KEY = os.environ.get("PAN_ACCESS_KEY", CEPH_ACCESS_KEY)
PAN_SECRET_KEY = os.environ.get("PAN_SECRET_KEY", CEPH_SECRET_KEY)
PAN_BUCKET = os.environ.get("PAN_BUCKET", CEPH_BUCKET)
PAN_NAME = os.environ.get("PAN_NAME", "yxd-risk")
PAN_SHARER = os.environ.get("PAN_SHARER", "xuzhao29")
PAN_VALID_MINUTES = int(os.environ.get("PAN_VALID_MINUTES", str(60 * 24 * 365)))
PAN_URL_BASE = os.environ.get("PAN_URL_BASE", "http://pan.paas.paas.idc/share/gen")
USE_CEPH_S3 = os.environ.get("USE_CEPH_S3", "true").lower() == "true"


def has_mysql_config() -> bool:
    return bool(MYSQL_URL or (MYSQL_HOST and MYSQL_DATABASE and MYSQL_USER))


def has_ceph_config() -> bool:
    return bool(USE_CEPH_S3 and CEPH_ACCESS_KEY and CEPH_SECRET_KEY and CEPH_URL and CEPH_BUCKET)
