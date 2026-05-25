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
mariadb -u root -e "CREATE DATABASE IF NOT EXISTS finvue CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;" || true
mariadb -u root -e "CREATE USER IF NOT EXISTS 'finvue'@'localhost' IDENTIFIED BY 'finvue_password';" || true
mariadb -u root -e "GRANT ALL PRIVILEGES ON finvue.* TO 'finvue'@'localhost';" || true
mariadb -u root -e "FLUSH PRIVILEGES;" || true
echo "[entrypoint] 数据库初始化完成"

# 运行数据库迁移
echo "[entrypoint] 运行数据库迁移..."
cd /app
export AUTO_MIGRATE=true
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_DATABASE=finvue
export MYSQL_USER=finvue
export MYSQL_PASSWORD=finvue_password
python3 migrate.py || echo "[entrypoint] 迁移完成或已存在"

# 创建管理员账号
echo "[entrypoint] 创建管理员账号..."
export ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
export ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin123}
python3 scripts/seed_admin.py || echo "[entrypoint] 管理员账号已存在"

# 启动应用
echo "[entrypoint] 启动 FinVue 应用..."
exec python3 main.py