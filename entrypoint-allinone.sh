#!/bin/bash
set -e

# 启动 MariaDB（后台）
echo "[entrypoint] 启动 MariaDB..."
service mariadb start || mariadbd-safe &
sleep 2

# 等待 MariaDB 就绪
echo "[entrypoint] 等待 MariaDB 就绪..."
for i in $(seq 1 30); do
    if mariadb-admin ping -h localhost --silent 2>/dev/null; then
        echo "[entrypoint] MariaDB 已就绪"
        break
    fi
    echo "[entrypoint] 等待 MariaDB... ($i/30)"
    sleep 2
done

# 创建数据库和用户
echo "[entrypoint] 初始化数据库..."
export MYSQL_DATABASE=${MYSQL_DATABASE:-finvue}
export MYSQL_USER=${MYSQL_USER:-finvue}
export MYSQL_PASSWORD=${MYSQL_PASSWORD:-finvue_password}
export ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
export ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin123}
export AUTH_SECRET=${AUTH_SECRET:-dev-only-allinone-auth-secret}

case "$MYSQL_DATABASE" in
    *[!A-Za-z0-9_]*|"")
        echo "[entrypoint] MYSQL_DATABASE 只能包含字母、数字和下划线"
        exit 1
        ;;
esac

case "$MYSQL_USER" in
    *[!A-Za-z0-9_]*|"")
        echo "[entrypoint] MYSQL_USER 只能包含字母、数字和下划线"
        exit 1
        ;;
esac

sql_escape() {
    printf "%s" "$1" | sed "s/'/''/g"
}

MYSQL_DATABASE_SQL=$(sql_escape "$MYSQL_DATABASE")
MYSQL_USER_SQL=$(sql_escape "$MYSQL_USER")
MYSQL_PASSWORD_SQL=$(sql_escape "$MYSQL_PASSWORD")

mariadb -u root -e "CREATE DATABASE IF NOT EXISTS \`${MYSQL_DATABASE_SQL}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;" || true
mariadb -u root -e "CREATE USER IF NOT EXISTS '${MYSQL_USER_SQL}'@'localhost' IDENTIFIED BY '${MYSQL_PASSWORD_SQL}';" || true
mariadb -u root -e "GRANT ALL PRIVILEGES ON \`${MYSQL_DATABASE_SQL}\`.* TO '${MYSQL_USER_SQL}'@'localhost';" || true
mariadb -u root -e "FLUSH PRIVILEGES;" || true
echo "[entrypoint] 数据库初始化完成"

# 运行数据库迁移
echo "[entrypoint] 运行数据库迁移..."
cd /app
export AUTO_MIGRATE=true
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
python3 migrate.py || echo "[entrypoint] 迁移完成或已存在"

# 创建管理员账号
echo "[entrypoint] 创建管理员账号..."
python3 scripts/seed_admin.py || echo "[entrypoint] 管理员账号已存在"

# 启动应用
echo "[entrypoint] 启动 FinVue 应用..."
exec python3 main.py
