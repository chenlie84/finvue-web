# 主播带新计划 · SOP 执行台 集成设计

- **创建日期**：2026-04-20
- **状态**：设计审批中
- **背景**：`/Users/nolan/Code/Creditease/data_viz/index.html` 是一个独立、自包含的 SPA（约 2668 行、90KB），当前通过 `localStorage` 持久化所有数据。本设计将其集成进现有 FastAPI + Jinja2 + MySQL 项目，用数据库替换 `localStorage` 作为最终数据源，保留 `localStorage` 作为输入缓冲。

---

## 1. 目标与非目标

### 目标
1. 原 `index.html` 文件从项目中删除；内容按项目目录约定拆分到 `templates/`、`static/`、`pages/`。
2. 通过 `PageRegistry` 把 SOP 执行台注册成 `/sop` 页面，首页 `/` 的页面列表会自动显示入口。
3. 用 MySQL 作为持久化层，替换 `localStorage` 主数据存储；`localStorage` 仅用作"输入中"缓冲，防止刷新丢失未保存的文本。
4. 团队共享单库：所有运营看到同一份主播数据，任何人都能修改。无鉴权。
5. 提供 RESTful API 支持 SOP 页面上所有交互的保存/加载。

### 非目标
- 不引入账号/鉴权系统。
- 不做多用户冲突检测（采用 last-write-wins）。
- 不引入 ORM 或数据库迁移工具；沿用项目现有的 `pymysql` + 原生 SQL 风格，schema 用一次性 SQL 文件管理。
- 不改动现有 CRS 页面或其它代码。

---

## 2. 核心决策

| 维度 | 决定 | 理由 |
|---|---|---|
| 用户模型 | 团队共享单库，无鉴权 | 与现有 CRS 页面一致；`operator_name` 作审计字段 |
| 数据表结构 | 完全规范化，3 张表 | `action_progress` 用 `-1` 哨兵值合并三层（action/substep/child），UNIQUE 索引正常生效 |
| 字符序 | `utf8mb4` + `utf8mb4_0900_ai_ci` | MySQL 8.0+ 默认字符序，基于 Unicode 9.0.0；已确认本地与线上都是 8.0+ |
| 保存时机 | checkbox 即时 API；文本框靠"保存"按钮批量同步 | 避免每个按键都发请求；勾选是原子操作，适合即时保存 |
| 主播首次创建 | 必须先点"保存"创建 `sop_anchors` 行；创建前 checkbox 禁用 + 顶部提示 | 避免 checkbox 端点携带 `operator_name`，保持 API 职责清晰 |
| 集成方式 | 注册成 `/sop` 页面（走 `PageRegistry`） | 保持项目一致性；首页列表自然显示入口 |
| localStorage | 保留作为输入缓冲 | 即使文本框未保存，刷新后能恢复；批量保存后清理对应缓冲项 |
| 派生字段 `warning` | 不入库，GET 时服务端计算 | 避免冗余；规则：`today - start_date > 28` |

---

## 3. 数据库设计

SQL 文件位置：`sql/sop_schema.sql`。部署时执行 `mysql < sql/sop_schema.sql` 一次。所有表使用 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci`。

### 3.1 `sop_anchors` — 主播元数据

```sql
CREATE TABLE IF NOT EXISTS sop_anchors (
  anchor_name      VARCHAR(64)   NOT NULL COMMENT '主播名，天然主键',
  operator_name    VARCHAR(64)   NOT NULL COMMENT '当前负责的运营',
  start_date       DATE          NOT NULL COMMENT '开始带新日期（创建记录时写入）',
  last_saved_date  DATE          DEFAULT NULL COMMENT '最近一次保存日期',
  current_week     TINYINT       NOT NULL DEFAULT 1 COMMENT '当前周次 1-4',
  status           VARCHAR(16)   NOT NULL DEFAULT '进行中',
  note             TEXT          DEFAULT NULL COMMENT '主播级备注',
  current_blocker  VARCHAR(128)  DEFAULT NULL,
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (anchor_name),
  KEY idx_operator (operator_name),
  KEY idx_status   (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 3.2 `sop_action_progress` — 动作进度（action/substep/child 三层合一）

```sql
CREATE TABLE IF NOT EXISTS sop_action_progress (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  anchor_name  VARCHAR(64)  NOT NULL,
  week         TINYINT      NOT NULL COMMENT '1-4',
  action_index TINYINT      NOT NULL COMMENT '周内第几个动作',
  sub_index    TINYINT      NOT NULL DEFAULT -1 COMMENT '子步骤序号，-1 表示非子步骤层',
  child_index  TINYINT      NOT NULL DEFAULT -1 COMMENT '子子步骤序号，-1 表示非子子层',
  checked      TINYINT(1)   NOT NULL DEFAULT 0,
  note         TEXT         DEFAULT NULL,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_item (anchor_name, week, action_index, sub_index, child_index),
  CONSTRAINT fk_progress_anchor FOREIGN KEY (anchor_name)
    REFERENCES sop_anchors(anchor_name) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

**层级编码规则：**

| 层级 | `sub_index` | `child_index` |
|---|---|---|
| action | `-1` | `-1` |
| substep | ≥0 | `-1` |
| child | ≥0 | ≥0 |

**为什么用 `-1` 而不是 `NULL`：** MySQL 的 UNIQUE KEY 对 NULL 值视为各不相同，允许多行 NULL 重复。用 `-1` 哨兵能让唯一性约束真正生效。

### 3.3 `sop_week_completion` — 每周达标日期

```sql
CREATE TABLE IF NOT EXISTS sop_week_completion (
  anchor_name   VARCHAR(64)  NOT NULL,
  week          TINYINT      NOT NULL,
  completed_at  DATE         NOT NULL COMMENT '手动标记"本周达标"的日期',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (anchor_name, week),
  CONSTRAINT fk_completion_anchor FOREIGN KEY (anchor_name)
    REFERENCES sop_anchors(anchor_name) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

---

## 4. API 设计

所有路由以 `/api/sop/` 为前缀。响应统一 JSON。错误码约定：`400`（JSON 格式错误）、`404`（主播不存在）、`422`（业务校验失败）、`500`（DB 异常）。

### 4.1 端点一览

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/sop/anchors` | 一次性拉所有主播全量状态（页面初始化用） |
| `GET` | `/api/sop/anchors/{anchor_name}` | 拉单个主播（可选，用于强制刷新） |
| `PUT` | `/api/sop/anchors/{anchor_name}` | UPSERT 主播元数据（operator/note/blocker），不存在则创建 |
| `DELETE` | `/api/sop/anchors/{anchor_name}` | 删除主播（级联删进度/周完成行） |
| `PUT` | `/api/sop/anchors/{anchor_name}/progress` | **主力端点**：UPSERT 一条勾选/备注（三层通吃） |
| `POST` | `/api/sop/anchors/{anchor_name}/advance` | 本周达标，进入下一周 |

### 4.2 `GET /api/sop/anchors` 响应

```json
{
  "anchors": [
    {
      "anchorName": "王老师",
      "operatorName": "阿杰",
      "startDate": "2026-04-01",
      "lastSavedDate": "2026-04-20",
      "currentWeek": 2,
      "status": "进行中",
      "note": "镜头感偏弱",
      "currentBlocker": "试讲观察未完成",
      "warning": false,
      "progress": [
        {"week":1,"actionIndex":0,"subIndex":-1,"childIndex":-1,"checked":true,"note":""},
        {"week":1,"actionIndex":0,"subIndex":0,"childIndex":-1,"checked":true,"note":"已完成"},
        {"week":1,"actionIndex":1,"subIndex":1,"childIndex":2,"checked":true,"note":""}
      ],
      "weekCompletions": {"1": "2026-04-07"}
    }
  ]
}
```

**扁平 `progress` 而非嵌套数组的理由：** 嵌套数组维度由前端 `weeklyPlan` 模板决定；模板可能变化（加/删动作）。扁平行存储 + 前端 `buildEmpty*()` 打底 + 覆盖 progress 的方式对模板演进最鲁棒。`warning` 由服务端计算（`today - start_date > 28`），不入库。

### 4.3 `PUT /api/sop/anchors/{anchor_name}` 请求体

```json
{
  "operatorName": "阿杰",
  "note": "...",
  "currentBlocker": "..."
}
```

- 首次调用：`INSERT INTO sop_anchors (anchor_name, operator_name, start_date) VALUES (..., ..., CURDATE())`，其它列用默认值。`operatorName` 首次必填。
- 已存在：仅更新传入字段，同时 `last_saved_date = CURDATE()`。

### 4.4 `PUT /api/sop/anchors/{anchor_name}/progress` 请求体

```json
{
  "week": 2,
  "actionIndex": 1,
  "subIndex": 0,
  "childIndex": -1,
  "checked": true,
  "note": "已完成"
}
```

- `subIndex`、`childIndex` 可选；省略时视为 `-1`。
- `checked`、`note` 都可选（至少传一个）；不传的字段不更新。
- 服务端 SQL（MySQL 8.0.20+ 推荐别名写法）：`INSERT INTO sop_action_progress (...) VALUES (...) AS new_row ON DUPLICATE KEY UPDATE checked = COALESCE(new_row.checked, sop_action_progress.checked), note = COALESCE(new_row.note, sop_action_progress.note)`；命中 `uk_item` 索引。传入 `NULL` 表示"不更新此字段"。
- 若主播不存在，返回 `404`（不自动创建）。

### 4.5 `POST /api/sop/anchors/{anchor_name}/advance`

无 body。事务内：

1. `INSERT INTO sop_week_completion (anchor_name, week, completed_at) VALUES (?, ?, CURDATE()) ON DUPLICATE KEY UPDATE completed_at = CURDATE()`（`week` = 当前 `current_week`）
2. `UPDATE sop_anchors SET current_week = LEAST(current_week + 1, 4), status = CASE WHEN current_week >= 4 THEN '已完成' ELSE status END WHERE anchor_name = ?`
3. 返回更新后的完整主播对象（同单个 GET）

---

## 5. 前端改动

### 5.1 调用策略

| 前端事件 | 触发行为 |
|---|---|
| checkbox 的 `change` | 立即 `PUT /progress`，只传 `{week, actionIndex, subIndex?, childIndex?, checked}` |
| 所有层级的 textarea `input` | 仅写 localStorage，不发 API |
| 运营名 / 主播名 input | 仅写 localStorage |
| 点击"保存全部动作"按钮 | ①首次：`PUT /anchors/{name}`（创建/更新元数据）；②扫描 localStorage 中的脏 textarea，批量调 `PUT /progress`（note）和 `PUT /anchors/{name}`（主播级 note） |
| 点击"本周达标"按钮 | `POST /advance` |

### 5.2 主播创建的 UI 流程

1. 运营输入运营名 + 主播名 → 存 localStorage
2. checkbox 保持禁用状态；顶部面板提示"先点击保存按钮创建主播"
3. 点击"保存全部动作" → `PUT /anchors/{name}` 创建 `sop_anchors` 行
4. 创建成功后：checkbox 启用；之后每次勾选即时入库

### 5.3 localStorage 使用

- 废弃原 `anchor_onboarding_sop_v2`（主数据已迁到服务端）。保留 `anchor_onboarding_sop_draft_v2` 存运营名/主播名草稿。
- 新增键 `anchor_onboarding_sop_dirty_v2`，存"未保存的 textarea 脏值"，按 `${anchorName}|${week}|${actionIndex}|${subIndex}|${childIndex}` 为 key，value 为 textarea 的当前内容。主播级备注用特殊 key `${anchorName}|__main_note__`。
- 页面初始加载：`GET /api/sop/anchors` → 填充页面 → 合并 localStorage 中尚未同步的脏值（本地优先显示，带提示"有未保存的改动"）。
- 保存成功后：清理对应 localStorage 条目。

### 5.4 文件拆分

原 `index.html`（2668 行）按以下方式拆分：

- `<style>` 块（约 1100 行）→ `static/sop.css`
- `<body>` HTML 结构（含 `<datalist>`、主布局）→ `templates/sop.html`
- `<script>` 块（约 1300 行）→ `static/sop.js`，同时改写：
  - 所有 `localStorage.setItem(STORE_KEY, ...)` 的直接写入 → 改为 `fetch('/api/sop/...')`
  - 页面初始化 `loadJson(STORE_KEY, initialState)` → 改为 `await fetch('/api/sop/anchors')`
  - 新增：checkbox change handler 内的 fetch；保存按钮的批量 fetch
  - 保留：localStorage 草稿逻辑（`DRAFT_KEY` 对应的运营名/主播名缓冲），扩展到所有 textarea

---

## 6. 文件改动清单

### 新增

- `templates/sop.html` — Jinja 模板，`<link>` 引用 `/static/sop.css`，`<script>` 引用 `/static/sop.js`
- `static/sop.css` — 从 `index.html` 抽离的全部 `<style>`
- `static/sop.js` — 从 `index.html` 抽离的 JS，API 改写
- `pages/sop_page.py` — 定义 `SOPPage(BasePage)` 类：`page_id="sop"`、`title="主播带新计划执行台"`、`template="sop.html"`；`get_data()` 返回 `[]`
- `db_sop.py` — SOP 三张表的 DAO 函数，沿用 `db_utils.db_cursor()` 上下文管理器
- `sql/sop_schema.sql` — 三张表的 DDL（`CREATE TABLE IF NOT EXISTS ...`）

### 修改

- `main.py` — 添加 `/api/sop/*` 路由（考虑新建 `api/sop.py` + `app.include_router`，若 `main.py` 变得过长）
- `pages/base.py` — `get_data()` 改为非 abstract 的默认实现（`return []`）
- `pages/registry.py` — `init_pages()` 中添加 `PageRegistry.register(SOPPage())`

### 删除

- `index.html`（项目根目录的独立文件，git 当前为 untracked 状态，直接删除安全）

---

## 7. 错误处理与边界情况

- **创建主播时姓名为空/仅空白字符**：服务端返回 `422`，前端高亮输入框。
- **主播名包含特殊字符**：`VARCHAR(64)` + `utf8mb4_0900_ai_ci` 支持中文、emoji、全角标点等；无需特殊转义。
- **同名主播冲突**：PK 决定唯一性。第二次 `PUT /anchors/{name}` 走 UPDATE 分支，不会报错。若是不同运营误用同名，由运营自行协调（界面不做冲突检测）。
- **删除主播**：`DELETE /anchors/{name}` 触发 `ON DELETE CASCADE`，`sop_action_progress` 和 `sop_week_completion` 对应行自动清理。
- **checkbox 点击后 API 失败**：前端回滚 UI 状态（取消勾选），toast 提示"保存失败，请重试"。
- **API 并发**：同一 checkbox 在 1 秒内被两人各点一次 → 最后一个 UPSERT 胜出。业务可接受。
- **weeklyPlan 模板变动**：若将来前端 `weeklyPlan` 增加一个动作（比如第 1 周多一项），旧的 progress 行不受影响（`action_index` 继续生效），新动作位置为空，运营按需勾选即可。

---

## 8. 测试要点

- **DB 建表**：执行 `sql/sop_schema.sql` 两次，第二次不应报错（`IF NOT EXISTS`）。
- **GET 空库**：`GET /api/sop/anchors` 返回 `{"anchors": []}`。
- **创建 → 勾选 → 取消 → 保存备注**：端到端一套流程，验证 DB 行变化符合预期。
- **删除主播后重建同名**：`sop_action_progress` 应全部清空，`start_date` 重置为当天。
- **warning 派生**：`start_date` 改成 30 天前，`GET` 响应中 `warning = true`。
- **页面刷新恢复**：localStorage 中的 dirty textarea 值在刷新后能恢复到输入框。
- **/sop 路由注册**：访问 `/` 能看到"主播带新计划执行台"条目；点击跳到 `/sop` 正常渲染。

---

## 9. 开放问题（非阻塞）

- 未来是否需要主播的"历史变动日志"？当前设计只存当前状态，若需要历史，可加 `sop_audit_log` 表记录每次 PUT 的 `(anchor_name, path, before, after, operator_name, ts)`。本次设计不实现，留作后续扩展点。
- 未来是否多运营需要查看别人的主播？当前所有人看同一份数据，若要做"仅查看我的主播"视图，可在 `GET /anchors` 加 `?operator=` 参数。本次不实现。
