#!/bin/bash
set -e

# 等待 MySQL 完全准备好
echo "[entrypoint] 等待 MySQL 就绪..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if python -c "import pymysql; pymysql.connect(host='$MYSQL_HOST', port=$MYSQL_PORT, user='$MYSQL_USER', password='$MYSQL_PASSWORD', database='$MYSQL_DATABASE')" 2>/dev/null; then
        echo "[entrypoint] MySQL 已就绪"
        break
    fi
    WAITED=$((WAITED + 2))
    sleep 2
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "[entrypoint] MySQL 连接超时，继续启动..."
fi

# 自动初始化管理员账号（如果设置了环境变量）
if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
    echo "[entrypoint] 初始化管理员账号: $ADMIN_USERNAME"
    python scripts/seed_admin.py || echo "[entrypoint] 管理员账号已存在或初始化失败，继续启动..."
fi

# 启动应用
exec python main.py