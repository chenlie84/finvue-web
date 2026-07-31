# 工程化改造计划

## 阶段 1：冻结现有功能，隔离线上目录

- `finvue-web` 作为新的线上化目录。
- 当前 `3030` 本地实验服务保持不动。
- 大文件数据不复制进新目录，只保留代码和依赖声明。

## 阶段 2：数据层重构

- 客户库、主播库、逐字稿库、报告库迁出 JSON 文件。
- 线上固定使用 MySQL；本地 JSON 只作为一次性迁移来源，不作为运行数据源。
- 所有列表页使用分页、搜索、排序接口。
- 上传源文件、PDF/HTML 导出产物和报告插图写入 CEPH S3，避免多机器部署时依赖代码目录。

## 阶段 3：API 与任务队列

- 建立 `/api/customers/*`、`/api/anchors/*`、`/api/reports/*`、`/api/transcripts/*`。
- 同步抖音数据、AI 批量分析、摘要生成全部做成 job。
- 前端通过 job id 查询状态和结果。

## 阶段 4：前端模块化

- 把 `index.html` 拆成页面模块、数据模块、渲染模块。
- 先保持原生 HTML/JS，稳定后再评估 React/Vite 或 Next.js。

## 当前优化优先级

### P0：先稳住维护边界

- 全站主题基座统一维护在 `app/static/modules/theme-system.css`，后续跨页面视觉样式不要继续写入 `app/index.html`。
- `app/index.html` 继续拆分：版本公告已抽到 `app/static/modules/releases.js`，通用 UI 已抽到 `app/static/modules/ui-core.js`，AI 对话已抽到 `app/static/modules/ai-chat.js`，管理后台核心已抽到 `app/static/modules/admin-core.js`，后台 API/总配置包已抽到 `app/static/modules/admin-config.js`，报告导出中心已抽到 `app/static/modules/export-center.js`，直播/主播直接导出链路已抽到 `app/static/modules/live-report-export.js`，直播分析生成/流式进度/报告渲染已抽到 `app/static/modules/live-analysis.js`；下一步继续拆全局状态和路由。
- 行情复盘生成脚本拆成流水线阶段：交易日解析、行情抓取、板块扫描、成分股补全、新闻证据、AI 归因、渲染落盘和诊断输出。
- 后台定时任务增加数据库分布式锁，避免多 worker 或多容器部署时重复抓取、重复推送、重复生成复盘。
- 为登录、配置包导入、飞书推送、热搜抓取、行情复盘和数据采集补最小冒烟测试。

### P1：提高线上稳定性

- 登录增加限流和失败锁定；生产环境默认关闭开放注册。
- 生产环境 API 错误返回标准错误码和阶段信息，详细异常只写入服务日志。
- `store.py` 和 `api/operation.py` 按业务域拆分，降低单文件修改风险。
- 数据库访问层引入连接池，减少高并发下频繁创建连接的成本。
- 数据采集模块增加临时文件清理、评论文件大小上限和采集记录保留策略。

### P2：体验与可观测性

- 热搜追踪增加主题聚类、跨平台重复话题合并、来源新鲜度和平台异常提示。
- 实时行情和行情复盘统一展示数据源权限状态，例如 TuShare 权限不足时明确显示降级来源。
- 管理后台增加调度任务看板：最近运行时间、耗时、失败阶段、下次执行时间。
- 版本更新已从 `index.html` 内置数组迁移到 `releases.js`；通用 UI 已迁移到 `ui-core.js`；AI 对话脚本已迁移到 `ai-chat.js`；后台分区切换、概览摘要、用户和权限管理已迁移到 `admin-core.js`；后台 API 路由池、AI 配置和总配置包已迁移到 `admin-config.js`；报告导出中心已迁移到 `export-center.js`；直播分析页和主播资料库的直接导出链路已迁移到 `live-report-export.js`；直播分析生成与渲染链路已迁移到 `live-analysis.js`。后续可继续把版本记录演进为后端 JSON 或数据库配置。
- 逐步替换大段 `innerHTML` 和 inline `onclick`，降低 XSS 和样式串扰风险。
