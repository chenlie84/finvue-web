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

默认端口是 `8080`。`python main.py` 会在启动时自动执行 `sql/migrations/*.sql` 中未执行过的迁移，然后启动服务。

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

生产环境建议用 `systemd` 托管 `python main.py` 和 `python worker.py`，再用 Nginx 反向代理到 `127.0.0.1:8080`。

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

## AI 路由与代理

系统默认内置公司内网 AIGC 路由：

- 路由名：`公司内网 AIGC`
- 模型：`gemini-3.1-flash-image-preview`
- 地址：`http://aigc-api.aigc.paas.corp/v1/chat/completions`
- Key 传递方式：Header 中的 `Authorization: Bearer ...`
- 调用方式：非流式 `chat/completions`，请求体固定 `stream: false`
- 是否走代理：否

外部 AI 接口默认使用代理：

```bash
http_proxy=http://nginx-proxy.jishu.idc:80
https_proxy=http://nginx-proxy.jishu.idc:80
```

---

## 数据导出脚本 (export_all_data.js)

### 概述

`export_all_data.js` 是一个一次性导出三个数据文件的 Node.js 脚本，用于将本地和远程数据库的数据导出为 CSV 文件。

### 执行方法

```bash
cd /Users/beeerjack/Desktop/develop/finvue-web
node export_all_data.js
```

### 数据源配置

#### 本地数据库 (finvue) - 客户运营数据

| 配置项 | 值 |
|--------|-----|
| host | 127.0.0.1 |
| port | 3306 |
| database | finvue |

**数据表**:
- `customer_profiles` - 客户档案表
- `customer_sessions` - 客户直播场次表

#### 远程数据库 (demo) - 主播直播数据

| 配置项 | 值 |
|--------|-----|
| host | 10.170.32.218 |
| port | 3306 |
| database | demo |

**数据表**:
- `douyin_creator_live_overview` - 主播直播数据概览表

---

### 导出文件说明

#### 1. customer_profiles_export.csv (客户档案)

**数据量**: ~94,000 条

| 字段名 | 说明 |
|--------|------|
| 客户ID | 用户唯一标识 |
| 客户名称 | 用户昵称 |
| 主播名称 | 最近观看的主播 |
| 最近分析时间 | 最近分析时间（北京时间） |
| 最近直播主题 | 最近观看的直播主题 |
| 最近排名 | 最近一次观看排名 |
| 最佳排名 | 历史最高排名 |
| 平均观看时长 | 平均观看时长（秒） |

#### 2. customer_sessions_export.csv (客户会话)

**数据量**: ~326,000 条

| 字段名 | 说明 |
|--------|------|
| 场次ID | 会话唯一标识 |
| 客户ID | 关联的客户ID |
| 主播名称 | 该场直播主播 |
| 直播间ID | 抖音直播间ID |
| 直播主题 | 该场直播主题 |
| 分析时间 | 分析时间（北京时间） |
| 观看时长秒 | 该场观看时长（秒） |

#### 3. live_data_export.csv (直播数据)

**数据量**: ~952 条

| 字段名 | 说明 | 数据库字段 |
|--------|------|-----------|
| 账号名称 | 主播账号 | `account` |
| 直播id | 直播间ID | `room_id` |
| 开播时间 | 开始时间（北京时间） | `startTime` |
| 关播时间 | 结束时间（北京时间） | `endTime` |
| 峰值人数 | 最高在线人数 | `pcu` |
| 观看人数 | 观看用户数 | `watchUcnt` |
| 涨粉人数 | 新增粉丝数 | `followUcnt` |

---

### 时区处理逻辑

**问题**: 数据库存储时间为 UTC 时间，需转换为北京时间（UTC+8）

**转换规则**: 北京时间 = UTC时间 + 8小时

```javascript
function formatBeijingTime(date) {
  if (!date) return '';
  const d = new Date(date);  // 自动处理时区
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}
```

**示例**:
- 数据库时间: `2026-05-12 07:44:06 UTC`
- 导出时间: `2026-05-12 15:44:06 北京时间`

---

### 各主播直播场次统计

| 主播名称 | 直播场次 |
|---------|---------|
| 财经葛先生 | 274场 |
| 戴维李 | 240场 |
| 老桑财知道 | 192场 |

---

### 输出文件

```
/Users/beeerjack/Desktop/develop/10-data/
├── customer_profiles_export.csv    (~24 MB)
├── customer_sessions_export.csv       (~87 MB)
├── live_data_export.csv (~319 KB)
```

### 依赖安装

```bash
npm install mysql2
```

### 执行时间

约 **10-15 秒**，主要耗时在数据库查询和文件写入。

### 注意事项

1. **时区一致性**: 所有时间字段均为北京时间（UTC+8）
2. **字段映射**: 导出字段名称已转换为中文
3. **数据排序**: 按 `updated_at` 或 `startTime` 降序排列
4. **CSV 编码**: UTF-8 编码，支持中文
