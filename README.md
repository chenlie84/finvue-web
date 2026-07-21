# FinVue Web

FinVue Web 是一个面向财经直播复盘、主播运营、客户画像、AI 分析和热点追踪的一体化 Web 系统。

它适合用于投顾内容团队、财经直播运营团队和私域客户服务场景：把主播资料、直播记录、市场行情、热点追踪、AI 消息面分析、合规提醒和报告导出放在同一个工作台里，帮助团队更快完成选题发现、观点复盘、客户跟进和内容资产沉淀。

当前项目采用 **FastAPI + Jinja2 + 原生 CSS/JavaScript + MySQL**。运行时不依赖前端构建步骤，`app/` 下的页面由 FastAPI 直接渲染，静态资源从 `/static` 提供。

## 技术栈

| 模块 | 说明 |
| --- | --- |
| Web 框架 | FastAPI |
| 页面模板 | Jinja2 |
| 前端 | 原生 HTML/CSS/JavaScript |
| 数据库 | MySQL 8.x / MariaDB |
| 对象存储 | 本地目录或 CEPH S3 |
| PDF 导出 | reportlab |
| 容器化 | Docker / Docker Compose |
| 后台任务 | `worker.py` 轮询 MySQL 任务表 |

## 主要功能

- 账号登录、注册、权限控制和管理员管理
- AI 供应商配置、提示词管理、AI 生成和流式生成
- AI 聊天、知识库和会话管理
- 主播资料库、合规库、案例库和逐字稿库
- 财经直播报告生成、持久化和 PDF 导出
- 客户档案、客户直播场次、客户趋势分析
- 运营看板、直播/短视频数据导入、在线远程导入
- SOP 管理
- 热点平台抓取、检索、趋势、AI 总览、单条 AI 分析和定时刷新配置

## 目录结构

```text
.
├── main.py                  # FastAPI 入口，挂载页面、静态资源和 API 路由
├── config.py                # 运行时配置和环境变量读取
├── db.py                    # MySQL 连接和基础执行 helper
├── store.py                 # 主要业务数据访问层
├── migrate.py               # SQL 迁移执行器
├── worker.py                # 后台任务 worker
├── api/                     # API 路由
├── app/                     # Jinja2 页面和静态资源
├── services/                # PDF、对象存储、同步、热点抓取和调度等服务
├── sql/migrations/          # 数据库迁移文件
├── scripts/                 # 运维、初始化、备份、镜像构建脚本
├── templates/               # 导入模板
├── Dockerfile               # 标准应用镜像
├── Dockerfile.allinone      # 应用 + MariaDB 的 all-in-one 镜像
└── docker-compose.yml       # 本地/服务器 compose 示例
```

## 本地初始化

项目建议使用 Python `3.10` 到 `3.12`，不要使用 Python `3.14`。当前依赖已在 Python `3.12` 环境下使用。

```bash
cd /Users/beeerjack/Desktop/develop/finvue-web

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

准备本地配置：

```bash
cp .env.production.example .env
```

然后编辑 `.env`，至少确认这些变量：

```bash
ENV=DEV
HOST=0.0.0.0
PORT=8080
AUTH_SECRET=replace-with-local-secret

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=finvue
MYSQL_USER=finvue
MYSQL_PASSWORD=replace-with-mysql-password

USE_CEPH_S3=false
OBJECT_STORAGE_DIR=/srv/finvue/objects
```

如果只是本地调试，建议设置：

```bash
USE_CEPH_S3=false
```

这样上传文件和导出产物会写到本地目录，而不是对象存储。

## 本地运行

启动 Web 服务：

```bash
source .venv/bin/activate
python main.py
```

默认地址：

```text
http://localhost:8080
```

启动时如果 `AUTO_MIGRATE=true`，并且 MySQL 配置完整，服务会自动执行 `sql/migrations/*.sql` 中尚未应用的迁移。

单独执行迁移：

```bash
source .venv/bin/activate
python migrate.py
```

启动后台任务 worker：

```bash
source .venv/bin/activate
python worker.py
```

初始化或重置管理员：

```bash
source .venv/bin/activate
ADMIN_USERNAME=admin ADMIN_PASSWORD='replace-with-strong-password' python scripts/seed_admin.py
```

重置已有管理员密码：

```bash
ADMIN_USERNAME=admin ADMIN_PASSWORD='new-strong-password' ADMIN_RESET_PASSWORD=true python scripts/seed_admin.py
```

## Docker 运行

使用 compose 启动应用和 MySQL：

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f finvue
```

停止服务：

```bash
docker compose down
```

默认 compose 会启动：

- `finvue`：FastAPI 应用
- `db`：MySQL 8.0
- `mysql_data`：数据库持久化卷
- `finvue_objects`：本地对象文件持久化卷

## Docker 镜像发布

标准镜像：

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t crachenlie/finvue-web:latest \
  --push .
```

all-in-one 镜像：

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -f Dockerfile.allinone \
  -t crachenlie/finvue-web:allinone \
  --push .
```

带版本号发布：

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t crachenlie/finvue-web:v1.4 \
  -t crachenlie/finvue-web:latest \
  --push .
```

仓库里也提供了脚本：

```bash
./scripts/docker-build-push.sh v1.4
```

注意：普通 `docker build && docker push` 通常只会推送当前机器架构的镜像；如果要同时支持 `linux/amd64` 和 `linux/arm64`，优先使用上面的 `docker buildx build --platform ... --push`。

## 环境变量

常用变量如下：

| 变量 | 说明 |
| --- | --- |
| `ENV` | 运行环境，例如 `DEV`、`production` |
| `HOST` | 服务监听地址 |
| `PORT` | 服务端口，默认 `8080` |
| `PUBLIC_BASE_URL` | 对外访问地址 |
| `AUTH_SECRET` | 会话签名密钥，生产环境必须修改 |
| `ALLOW_OPEN_REGISTRATION` | 是否允许开放注册 |
| `AUTO_MIGRATE` | 启动时是否自动执行迁移 |
| `MYSQL_HOST` | MySQL 主机 |
| `MYSQL_PORT` | MySQL 端口 |
| `MYSQL_DATABASE` | MySQL 数据库 |
| `MYSQL_USER` | MySQL 用户 |
| `MYSQL_PASSWORD` | MySQL 密码 |
| `ADMIN_USERNAME` | 初始化管理员用户名 |
| `ADMIN_PASSWORD` | 初始化管理员密码 |
| `USE_CEPH_S3` | 是否启用 CEPH S3 |
| `OBJECT_STORAGE_DIR` | 本地对象文件目录 |
| `MAX_UPLOAD_BYTES` | 最大上传大小 |
| `HTTP_PROXY` / `HTTPS_PROXY` | 外部请求代理 |
| `HOTSPOT_API_ENABLED` | 是否启用热点抓取 |
| `HOTSPOT_API_URL` | 热点接口地址 |

生产环境不要把真实密码、密钥、对象存储凭据写进 Dockerfile 或提交到 Git。请通过 `.env`、`.env.production`、Docker Compose environment、服务器密钥管理或 CI/CD secret 注入。

## 热点追踪模块

热点追踪现在拆分为独立维护入口，后续热搜相关前端逻辑不要继续追加到 `app/index.html` 的大脚本中：

| 文件 | 说明 |
| --- | --- |
| `api/hotspot.py` | 热搜列表、平台配置、手动抓取、单条 AI 分析、AI 热点总览接口 |
| `services/hotspot_fetcher.py` | 多平台热搜抓取和入库 |
| `services/hotspot_scheduler.py` | 服务启动后的后台定时刷新调度 |
| `app/static/modules/hotspot.js` | 热点追踪前端逻辑，包括刷新、AI 总览、单条分析和配置页 |
| `app/static/modules/hotspot.css` | 热点追踪列表、AI 总览和配置页样式 |

页面入口仍在 `app/index.html` 的“热点追踪”区块中，但只保留结构和静态资源引用。热搜页面右上角的“配置”按钮可以设置抓取平台和定时刷新间隔，配置写入 `finvue_hotspot_settings.fetch_interval_minutes`。后台调度器每分钟检查一次是否到期，到期后按配置的平台列表抓取。

生产环境启用后台定时刷新需要设置：

```bash
HOTSPOT_API_ENABLED=true
HOTSPOT_API_URL=https://newsnow.busiyi.world/api/s
```

如果服务部署在 Northflank 或其他容器平台，修改平台/间隔配置后不需要改环境变量；配置保存后会由后台调度器在下一次轮询时读取。

## 行情复盘定时任务

服务启动后会按北京时间检查行情复盘定时任务，默认在每个工作日 `17:40` 后自动生成一次最新交易日复盘。同一天成功后不会重复生成；如果失败，会按重试间隔再次尝试，并把失败状态和诊断信息记录到调度状态中。

生产环境可通过环境变量调整：

```bash
DAILY_MARKET_REVIEW_SCHEDULER_ENABLED=true
DAILY_MARKET_REVIEW_SCHEDULE_TIME=17:40
DAILY_MARKET_REVIEW_RETRY_MINUTES=30
DAILY_MARKET_REVIEW_WEEKDAY_ONLY=true
```

状态接口：

```text
GET /api/daily-review/scheduler
```

## 配置文件导入

管理后台的“备份管理 / FinVue 总配置包”支持上传一个配置文件，一次恢复 TuShare Token、飞书 Webhook、AI API Key、指数池、股票池和定时任务开关。单项页面“TuShare配置”、“飞书推送”和“API 管理”也保留独立导入导出入口。支持 JSON 或 `.env` 键值格式。

总配置包 JSON 示例：

```json
{
  "type": "finvue-config-bundle",
  "version": 1,
  "tushare": {
    "enabled": true,
    "token": "your-tushare-token",
    "intervalMinutes": 60,
    "indexCodes": ["000001.SH", "399001.SZ", "399006.SZ"],
    "stockCodes": ["600519.SH", "300750.SZ"]
  },
  "feishu": {
    "enabled": true,
    "webhookUrl": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
    "dailyPushTime": "09:00",
    "pushRelatedStocks": true,
    "notifyRegistrations": true
  },
  "ai": {
    "providers": [
      {
        "id": "primary-volcengine",
        "label": "火山主路由",
        "baseUrl": "https://ark.cn-beijing.volces.com/api/v3/responses",
        "apiKey": "your-ai-api-key",
        "model": "doubao-seed-2-0-pro-250415",
        "enabled": true,
        "priority": 20,
        "apiFormat": "finvue",
        "apiKeyPlacement": "header",
        "useProxy": true
      }
    ]
  }
}
```

总配置包 `.env` 示例：

```bash
TUSHARE_ENABLED=true
TUSHARE_TOKEN=your-tushare-token
TUSHARE_INTERVAL_MINUTES=60
TUSHARE_INDEX_CODES=000001.SH,399001.SZ,399006.SZ
TUSHARE_STOCK_CODES=600519.SH,300750.SZ

FEISHU_ENABLED=true
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
FEISHU_DAILY_PUSH_TIME=09:00
FEISHU_PUSH_RELATED_STOCKS=true
FEISHU_NOTIFY_REGISTRATIONS=true

AI_PROVIDER_ID=primary-volcengine
AI_PROVIDER_LABEL=火山主路由
AI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/responses
AI_API_KEY=your-ai-api-key
AI_MODEL=doubao-seed-2-0-pro-250415
AI_ENABLED=true
AI_PRIORITY=20
AI_API_FORMAT=finvue
AI_API_KEY_PLACEMENT=header
AI_USE_PROXY=true
```

单项配置仍可单独导入：

TuShare JSON 示例：

```json
{
  "type": "finvue-tushare-config",
  "tushare": {
    "enabled": true,
    "token": "your-tushare-token",
    "intervalMinutes": 60,
    "indexCodes": ["000001.SH", "399001.SZ", "399006.SZ"],
    "stockCodes": ["600519.SH", "300750.SZ"]
  }
}
```

`.env` 示例：

```bash
TUSHARE_ENABLED=true
TUSHARE_TOKEN=your-tushare-token
TUSHARE_INTERVAL_MINUTES=60
TUSHARE_INDEX_CODES=000001.SH,399001.SZ,399006.SZ
TUSHARE_STOCK_CODES=600519.SH,300750.SZ
```

飞书 JSON 示例：

```json
{
  "type": "finvue-feishu-config",
  "feishu": {
    "enabled": true,
    "webhookUrl": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
    "dailyPushTime": "09:00",
    "pushRelatedStocks": true,
    "notifyRegistrations": true
  }
}
```

飞书 `.env` 示例：

```bash
FEISHU_ENABLED=true
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
FEISHU_DAILY_PUSH_TIME=09:00
FEISHU_PUSH_RELATED_STOCKS=true
FEISHU_NOTIFY_REGISTRATIONS=true
```

AI 路由 JSON 示例：

```json
{
  "type": "finvue-ai-config",
  "ai": {
    "providers": [
      {
        "id": "primary-volcengine",
        "label": "火山主路由",
        "baseUrl": "https://ark.cn-beijing.volces.com/api/v3/responses",
        "apiKey": "your-ai-api-key",
        "model": "doubao-seed-2-0-pro-250415",
        "enabled": true,
        "priority": 20,
        "apiFormat": "finvue",
        "apiKeyPlacement": "header",
        "useProxy": true
      }
    ]
  }
}
```

AI 路由 `.env` 示例：

```bash
AI_PROVIDER_ID=primary-volcengine
AI_PROVIDER_LABEL=火山主路由
AI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/responses
AI_API_KEY=your-ai-api-key
AI_MODEL=doubao-seed-2-0-pro-250415
AI_ENABLED=true
AI_PRIORITY=20
AI_API_FORMAT=finvue
AI_API_KEY_PLACEMENT=header
AI_USE_PROXY=true
```

说明：下载当前 AI 配置会包含真实 API Key，仅限管理员接口，请把导出的文件按密钥文件保管。导入模板里的占位 key 或 `********` 时，会保留服务端原有 key，避免覆盖为空。

## 数据库迁移

迁移文件位于：

```text
sql/migrations/
```

命名约定：

```text
YYYYMMDD_序号_说明.sql
```

迁移执行状态记录在 `finvue_schema_migrations`。已经上线执行过的迁移不要修改；需要变更表结构时新增迁移文件。

## 数据导入与模板

导入模板位于：

```text
templates/
```

项目包含客户档案、客户会话、直播数据、短视频数据等导入能力。部分在线导入接口依赖远程数据库配置：

```bash
REMOTE_DB_HOST=
REMOTE_DB_PORT=
REMOTE_DB_DATABASE=
REMOTE_DB_USER=
REMOTE_DB_PASSWORD=
```

## 运维脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/seed_admin.py` | 创建或重置管理员 |
| `scripts/backup-mysql.sh` | MySQL 备份 |
| `scripts/setup-linux.sh` | Linux 服务器初始化辅助 |
| `scripts/hotspot_cron.py` | 热点定时抓取 |
| `scripts/docker-build-push.sh` | 构建并推送 Docker 镜像 |

## 健康检查

服务启动后可以访问：

```text
GET /api/health
```

也可以在浏览器打开：

```text
http://localhost:8080/
```

## 开发注意事项

- 当前前端没有构建步骤，页面和脚本改完后刷新浏览器即可验证。
- 后端接口新增后，需要在 `main.py` 中通过 router include 或现有模块暴露。
- 数据库结构变更只新增迁移，不直接修改旧迁移。
- 本地调试建议关闭 CEPH：`USE_CEPH_S3=false`。
- 生产环境必须替换 `AUTH_SECRET`、数据库密码和管理员密码。
- all-in-one 镜像适合快速演示，不建议作为严肃生产数据库方案。

## 已知维护点

- `config.py` 不再内置真实数据库或对象存储凭据，生产环境必须通过环境变量注入完整配置。
- all-in-one 镜像仍带有演示用默认账号，生产环境请显式设置 `MYSQL_PASSWORD`、`AUTH_SECRET` 和 `ADMIN_PASSWORD`。
- 如果发布多架构镜像，请使用 `docker buildx build --platform linux/amd64,linux/arm64 --push`。

## License

This project is licensed under the [MIT License](LICENSE).
