#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.production"

cd "$ROOT_DIR"

step() {
  printf "\n\033[1;33m==> %s\033[0m\n" "$1"
}

die() {
  printf "\n\033[1;31m%s\033[0m\n" "$1" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "缺少 $1，请先安装。"
}

ask() {
  local label="$1"
  local default_value="$2"
  local value
  read -r -p "$label [$default_value]: " value
  printf "%s" "${value:-$default_value}"
}

ask_secret() {
  local label="$1"
  local value=""
  while [[ ${#value} -lt 1 ]]; do
    read -r -s -p "$label: " value
    printf "\n"
    [[ ${#value} -ge 1 ]] || printf "不能为空，请重新输入。\n"
  done
  printf "%s" "$value"
}

random_secret() {
  "$PYTHON_CMD" - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
}

select_python() {
  for candidate in "${PYTHON:-}" python3.12 python3.11 python3.10 python3; do
    [[ -n "$candidate" ]] || continue
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)
PY
    then
      printf "%s" "$candidate"
      return 0
    fi
  done
  return 1
}

write_env() {
  cat > "$ENV_FILE" <<EOF
ENV=production
HOST=0.0.0.0
PORT=$PORT_VALUE
RELOAD=false
PUBLIC_BASE_URL=$PUBLIC_BASE_URL_VALUE
ALLOW_OPEN_REGISTRATION=false
AUTH_SECRET=$AUTH_SECRET_VALUE

MYSQL_HOST=$MYSQL_HOST_VALUE
MYSQL_PORT=$MYSQL_PORT_VALUE
MYSQL_DATABASE=$MYSQL_DATABASE_VALUE
MYSQL_USER=$MYSQL_USER_VALUE
MYSQL_PASSWORD=$MYSQL_PASSWORD_VALUE
MYSQL_SSL=$MYSQL_SSL_VALUE
MYSQL_POOL_MAX=10
AUTO_MIGRATE=true

ADMIN_USERNAME=$ADMIN_USERNAME_VALUE
ADMIN_PASSWORD=$ADMIN_PASSWORD_VALUE

MAX_UPLOAD_BYTES=52428800
OBJECT_STORAGE_DIR=$OBJECT_STORAGE_DIR_VALUE
ANCHOR_DASHBOARD_PYTHON=$PYTHON_BIN_VALUE

OPENAI_API_KEY=
DEEPSEEK_API_KEY=
EOF
  chmod 600 "$ENV_FILE"
}

load_env() {
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
}

step "检查基础命令"
need mysql
need mysqldump
PYTHON_CMD="$(select_python)" || die "需要 Python 3.10-3.12。当前 python3 版本不适合部署，请安装 python3.11 或 python3.12。"
printf "使用 Python：%s\n" "$("$PYTHON_CMD" --version)"

if [[ -f "$ENV_FILE" ]]; then
  read -r -p ".env.production 已存在。是否覆盖？输入 yes 才覆盖: " OVERWRITE
  if [[ "$OVERWRITE" == "yes" ]]; then
    rm -f "$ENV_FILE"
  else
    step "使用已有 .env.production"
  fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
  step "生成生产环境配置"
  PUBLIC_BASE_URL_VALUE="$(ask "线上域名" "https://finvue.example.com")"
  PORT_VALUE="$(ask "FastAPI 服务端口" "3031")"
  MYSQL_HOST_VALUE="$(ask "MySQL Host" "127.0.0.1")"
  MYSQL_PORT_VALUE="$(ask "MySQL Port" "3306")"
  MYSQL_DATABASE_VALUE="$(ask "MySQL Database" "finvue")"
  MYSQL_USER_VALUE="$(ask "MySQL User" "finvue")"
  MYSQL_PASSWORD_VALUE="$(ask_secret "MySQL 密码")"
  MYSQL_SSL_VALUE="$(ask "MySQL SSL true/false" "false")"
  ADMIN_USERNAME_VALUE="$(ask "管理员账号" "admin")"
  ADMIN_PASSWORD_VALUE="$(ask_secret "管理员密码")"
  OBJECT_STORAGE_DIR_VALUE="$(ask "对象/导出文件目录" "/srv/finvue/objects")"
  PYTHON_BIN_VALUE="$(ask "Python 路径" "$(command -v "$PYTHON_CMD")")"
  AUTH_SECRET_VALUE="$(random_secret)"
  write_env
  printf "已写入：%s\n" "$ENV_FILE"
fi

load_env

step "创建对象目录"
mkdir -p "${OBJECT_STORAGE_DIR:-/srv/finvue/objects}" || true

step "安装 Python 依赖"
"$PYTHON_CMD" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

step "代码检查"
python -m py_compile main.py config.py migrate.py db.py worker.py security.py store.py ai_router.py api/*.py services/*.py scripts/seed_admin.py

step "数据库迁移"
python migrate.py

step "初始化管理员"
python scripts/seed_admin.py

step "完成"
cat <<EOF
配置文件：$ENV_FILE
启动 API：source .venv/bin/activate && python main.py
启动 Worker：source .venv/bin/activate && python worker.py
systemd 示例：deploy/finvue-api.service.example、deploy/finvue-worker.service.example
Nginx 示例：deploy/nginx.conf.example
部署文档：docs/LINUX_VPS_DEPLOY.md
EOF
