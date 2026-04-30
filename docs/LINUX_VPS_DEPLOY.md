# FinVue Linux VPS 部署

目标环境：Ubuntu 22.04/24.04，Python 3.10-3.12，MySQL 8+，Nginx。运行时不需要 npm、Node、PM2 或 Playwright。

## 1. 安装依赖

```bash
sudo apt update
sudo apt install -y nginx mysql-server git python3.12 python3.12-venv python3-pip
```

## 2. 创建数据库

```sql
CREATE DATABASE finvue CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'finvue'@'%' IDENTIFIED BY 'replace-with-strong-password';
GRANT ALL PRIVILEGES ON finvue.* TO 'finvue'@'%';
FLUSH PRIVILEGES;
```

## 3. 部署代码

```bash
sudo mkdir -p /srv/finvue
sudo chown -R "$USER":"$USER" /srv/finvue
cd /srv/finvue
git clone <your-repo-url> finvue-web
cd finvue-web
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.production.example .env.production
vi .env.production
```

至少配置：

```bash
HOST=127.0.0.1
PORT=3031
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=finvue
MYSQL_USER=finvue
MYSQL_PASSWORD=真实密码
AUTH_SECRET=长随机字符串
PUBLIC_BASE_URL=https://你的域名
USE_CEPH_S3=true
CEPH_KEY_PREFIX=finvue/
SOURCE_CEPH_KEY_PREFIX=finvue_source/
IMAGE_CEPH_KEY_PREFIX=finvue_images/
```

## 4. 一键启动

```bash
source .venv/bin/activate
python main.py
```

`python main.py` 会自动执行 `sql/migrations/*.sql` 中未执行过的迁移，然后启动 FastAPI。

## 5. systemd 托管

创建 API 服务：

```ini
[Unit]
Description=FinVue API
After=network.target mysql.service

[Service]
WorkingDirectory=/srv/finvue/finvue-web
EnvironmentFile=/srv/finvue/finvue-web/.env.production
ExecStart=/srv/finvue/finvue-web/.venv/bin/python /srv/finvue/finvue-web/main.py
Restart=always
RestartSec=3
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

创建 Worker 服务：

```ini
[Unit]
Description=FinVue Worker
After=network.target mysql.service

[Service]
WorkingDirectory=/srv/finvue/finvue-web
EnvironmentFile=/srv/finvue/finvue-web/.env.production
ExecStart=/srv/finvue/finvue-web/.venv/bin/python /srv/finvue/finvue-web/worker.py
Restart=always
RestartSec=3
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now finvue-api
sudo systemctl enable --now finvue-worker
sudo systemctl status finvue-api
sudo systemctl status finvue-worker
```

## 6. Nginx

```nginx
server {
  listen 80;
  server_name finvue.example.com;
  client_max_body_size 100m;

  location / {
    proxy_pass http://127.0.0.1:3031;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
  }
}
```

正式 HTTPS 建议用 `certbot --nginx` 配置证书。

## 7. 数据库迁移规则

后续如果要改表结构，只新增迁移文件：

```bash
sql/migrations/YYYYMMDD_序号_说明.sql
```

规则：

- 不直接手改线上数据库。
- 不修改已经上线执行过的旧迁移文件。
- 文件名按字典序执行。
- 服务启动时自动执行未跑过的迁移。
- 迁移失败时服务启动失败。

## 8. 备份

```bash
set -a
source .env.production
set +a
mkdir -p /srv/finvue/backups
mysqldump -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" | gzip > "/srv/finvue/backups/finvue-$(date +%Y%m%d-%H%M%S).sql.gz"
```

不要把 `.env.production`、备份文件、上传原始文件提交到 Git。

## 9. 管理员账号

初始化管理员：

```bash
set -a
source .env.production
set +a
source .venv/bin/activate
python scripts/seed_admin.py
```

如果使用本次预置账号，`.env.production` 中设置：

```bash
ADMIN_USERNAME=finvue_admin
ADMIN_PASSWORD='v@GCXP62XHUabc!vG%'
```
