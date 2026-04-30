# FinVue Web

FinVue 线上版采用 `FastAPI + Jinja2 模板 + 原生 CSS/JS + MySQL`。运行时不依赖 npm、Node 或 Playwright。

## 本地启动

要求 Python `3.10-3.12`，不要使用 Python 3.14。

```bash
cd /Users/beeerjack/Desktop/AI人格/finvue-web
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

默认端口是 `3031`。`python main.py` 会在启动时自动执行 `sql/migrations/*.sql` 中未执行过的迁移，然后启动服务。

## 生产启动

```bash
cd /srv/finvue/finvue-web
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.production.example .env.production
vi .env.production
python main.py
```

生产环境建议用 `systemd` 托管 `python main.py` 和 `python worker.py`，再用 Nginx 反向代理到 `127.0.0.1:3031`。

## 目录说明

- `main.py`：FastAPI 入口，挂载静态资源、渲染 Jinja2 页面、启动自动迁移。
- `api/`：认证、设置、主播库、客户库、逐字稿、报告、任务、后台管理等接口。
- `app/`：Jinja2 页面模板和原生 CSS/JS 静态资源。
- `services/`：抖音同步、融合报告解析、PDF 导出等业务服务。
- `store.py`：MySQL 数据访问层。
- `worker.py`：后台任务 worker。
- `sql/migrations/`：数据库迁移文件。

## 数据库迁移约定

后续修改表结构，只新增 SQL 文件：

```bash
sql/migrations/YYYYMMDD_序号_说明.sql
```

不要修改已经上线执行过的旧迁移文件。服务启动时会自动执行未应用的迁移；迁移失败时服务会启动失败，避免表结构不完整但服务继续运行。

## 初始化管理员

生产环境设置 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 后执行：

```bash
source .venv/bin/activate
python scripts/seed_admin.py
```

脚本会先执行迁移，再创建或更新管理员账号。

本次预置管理员建议：

```bash
ADMIN_USERNAME=finvue_admin ADMIN_PASSWORD='v@GCXP62XHUabc!vG%' python scripts/seed_admin.py
```

如果数据库不可达，脚本会失败，不会写入任何本地文件；修正 `.env.production` 里的 MySQL 配置后重新执行即可。若账号已存在且需要重置密码：

```bash
ADMIN_USERNAME=finvue_admin ADMIN_PASSWORD='新密码' ADMIN_RESET_PASSWORD=true python scripts/seed_admin.py
```

## CEPH S3 文件存储

上传原始文件、导出 PDF 等产物默认写入 CEPH S3，不再依赖代码目录。相关配置在 `config.py` 和 `.env.production.example` 中：

- 报告/导出文件前缀：`CEPH_KEY_PREFIX=finvue/`
- 原始上传文件前缀：`SOURCE_CEPH_KEY_PREFIX=finvue_source/`
- 报告插图前缀：`IMAGE_CEPH_KEY_PREFIX=finvue_images/`

如果本地离线调试不想连接 CEPH，可以在 `.env` 中设置：

```bash
USE_CEPH_S3=false
```

## PDF 导出

PDF 导出不再依赖 Playwright/Chromium。当前使用 Python `reportlab` 将报告 HTML 转成轻量文本 PDF，优先保证部署简单和中文可读。在线环境会同时把 PDF 写入 CEPH，并返回下载文件。
