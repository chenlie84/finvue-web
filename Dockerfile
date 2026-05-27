FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

# 复制代码
COPY . .

# 创建数据目录
RUN mkdir -p /srv/finvue/objects

# 复制并设置 entrypoint 脚本权限
RUN chmod +x docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["./docker-entrypoint.sh"]
