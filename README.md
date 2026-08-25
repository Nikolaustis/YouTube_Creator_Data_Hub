# YouTube 博主数据中心 v3.10.7

> 本仓库是 **YouTube Creator Data Hub v3.10.7** 的完整源码版本。  
> GitHub 仓库只保存源码、配置模板、文档与启动脚本；**不包含业务数据库、API Key、导出结果、备份或运行时缓存**。

## 项目定位

YouTube 博主数据中心是一个本地优先的 Creator Intelligence / KOL 数据工作台，用于完成从 **博主发现 → 数据入库 → 视频抓取 → 分类与人工复核 → 商业数据导入 → 二次指标 → 规则筛选 → AI 分析 → 导出与持续监控** 的完整闭环。

系统以 SQLite 为本地事实源，Dashboard 负责交互与分析，不要求 Node/npm，也不依赖云端数据库。

---

## v3.10.7 当前能力

### 1. 博主库

- 统一管理 Creator 基础信息、国家、订阅数、频道播放量、已存视频数、监控状态与优先级。
- 支持搜索、筛选、排序、分页和 Saved Views。
- 支持当前页选择、全结果选择以及批量操作。
- Creator 名称可直接跳转 YouTube。
- 支持 Creator Inspector 查看详细状态、商业表现、数据新鲜度等信息。
- 筛选和排序所使用的字段会在结果表中体现，避免“隐藏条件”。

### 2. 博主发现

- 基于 YouTube Search / Query Expansion 发现 Creator 与命中视频。
- 支持多语言 Query Pack 与地区/国家筛选。
- 保存 Discovery Run、Query Coverage、命中视频、发现评分和审计信息。
- 单条动作具备对应批量入口，可批量入库、抓取视频、监控和设置优先级。
- 可将发现结果继续进入 Creator 数据库，而不是停留在一次性搜索结果。

### 3. 视频数据与分类

- 抓取 Creator 视频及视频指标。
- 支持增量抓取、指定时间范围和全历史抓取。
- 保存视频播放量、点赞、评论等 Snapshot。
- 分类同时保留：
  - 系统原始判断；
  - 人工复核结果；
  - 最终有效分类。
- 最终业务口径遵循人工优先，系统结果保留用于审计。
- 支持离线重新分类，不需要额外消耗 YouTube API 配额。

### 4. 商业表现数据

- 支持导入 CSV / XLSX / XLSM 商业数据。
- 可保存 GMV、拉新等 Creator 级商业事实。
- GMV 当前业务口径为 **UgPhone 后台 USD 累计快照**，不自动进行汇率换算。
- 商业指标可以进入博主库、排序、二次指标、规则和 AI 分析。

---

## 二次指标系统

### 统一三级 Field Taxonomy

所有需要选择字段的位置统一使用三级结构：

1. **一级指标**
   - 客观数据
   - 博主标签
   - 构建指标
   - 比值指标

2. **二级指标**
   - 客观数据按基础信息、地理位置、频道规模、内容与品牌、内容表现、商业数据、Discovery / AI、数据健康、视频客观数据等业务维度组织；
   - 构建指标和比值指标使用用户自定义分组；
   - 未设置分组时统一进入“未分组”。

3. **三级指标**
   - 具体稳定 Field ID / Metric ID。

显示名称只是 UI 标签，持久化与 Saved View 使用稳定 ID，因此修改显示名称不会破坏既有配置。

### 统一条件构建器

以下入口使用同一套“一条件一行”交互：

- 规则 / 标签构建器；
- 二次指标的“应用结果 · 博主库”；
- 主博主库筛选器。

每条条件统一为：

```text
起始 / AND / OR / NOT
→ 一级指标
→ 二级指标
→ 三级指标
→ 运算符
→ 值
→ 删除
```

三级指标搜索直接内嵌在字段选择器内，不再使用独立搜索按钮。

### 构建指标

构建指标从 **Video grain** 聚合到 **Creator grain**：

```text
视频客观数据
+ 视频分类 / 品牌筛选
+ 时间范围
+ Count / Sum / Average / Median / Max / Min
        ↓
每位 Creator 一个数值
```

典型示例：

- 近 90 天 UgPhone 视频播放中位数
- 近 30 天竞品视频数量
- 全部日常视频平均播放量
- 近 365 天视频评论数最大值

### 比值指标

比值指标运行在 Creator 粒度。

分子和分母可引用：

- Creator 数值型客观数据；
- 已构建指标。

例如：

```text
UgPhone 视频播放中位数 ÷ 日常视频播放中位数
```

### 指标与规则列表

- 已构建指标：**10 条 / 页**
- 规则列表：**10 条 / 页**
- 列表区域内部使用纵向滚动。
- 左侧 Builder 仍然是高度锚点：
  - 已构建指标高度跟随指标构建器；
  - 规则列表高度跟随规则 / 标签构建器。
- 右侧列表不会反向把左侧构建器拉高。
- 搜索、排序、分页不会改变外部 Card 高度。
- Builder 内容或窗口尺寸变化后会自动重新同步对应列表高度。

### V3.10.7 规则 / 标签构建器固定工作区

V3.10.7 重新实现了规则区的滚动与固定外壳逻辑，采用**固定条件 viewport + 非收缩条件行 + 冻结外壳**：

- 条件 viewport 固定为约 **3 条完整条件**的高度；
- 每一条条件设置 `flex-shrink:0`，不会为了塞进 viewport 而被压扁；
- 第 4 条及以后只在 `ruleConditions` 内部通过**垂直滚动条**查看；
- 垂直滚动条使用 `overflow-y:scroll` 并预留 scrollbar gutter；
- 不再给每条条件单独生成横向滚动条；
- 如窗口过窄，只在整个条件 viewport 底部出现一个共享横向滚动；
- `添加条件`紧跟条件 viewport；
- `保存规则 / 清空`紧跟其后，不再使用 `margin-top:auto` 制造中间空白；
- 规则构建器在结构完成后根据真实内容测量一次高度并冻结；
- 条件数量变化不会重新计算外壳高度；
- `规则列表`冻结为完全相同高度；
- 规则卡片继续保持自然高度并禁止 stretch；
- 规则列表继续 **10 条 / 页**。

核心布局：

```text
冻结的 Rule Builder 外壳
├─ 规则元数据
├─ 条件标题
├─ ruleConditions：固定约 3 行高度
│  ├─ 条件 1
│  ├─ 条件 2
│  ├─ 条件 3
│  └─ 条件 4+ → 内部纵向滚动
├─ 添加条件
├─ 保存规则 / 清空
└─ 说明
```

条件数量只影响内部 `scrollHeight`，不影响外壳高度。

---

## Job Engine

长耗时任务由持久化 Job Engine 管理，而不是每次点击无限创建线程。

支持：

- 持久化 `job_runs`
- YouTube / AI / Local 等资源队列
- 并发限制
- 任务进度
- 取消
- 重试
- checkpoint
- 可恢复任务安全恢复
- Dashboard 重启后任务状态恢复

任务中心只是 UI，执行状态保存在数据库中。

---

## 可重复执行与 AI

### Run Specification

AI Search / Ask Hub 等任务保存结构化运行规格，包括：

- 原始请求
- 最终计划
- Query
- Fit Criteria
- 执行参数
- 父子 Run 关系

复制并重新执行时可以复用已经冻结的最终条件，而不是重新让 Planner 改写任务定义。

### Data Contract

系统将判断来源区分为：

- `fact`：客观事实
- `derived`：确定性计算结果
- `ai`：AI 判断
- `human`：人工判断

默认有效值优先级：

```text
human > ai > derived > fact
```

因此人工复核不会被后续自动判断无意覆盖。

### Creator Intelligence

Creator Intelligence Engine 采用：

```text
SQLite facts
→ 确定性 KPI / SQL
→ 事实上下文
→ LLM 解释与行动建议
```

AI 不负责重新制造基础事实。

AI 功能是可选模块；不启用 AI 仍可正常使用 Creator 数据中心的核心能力。

---

## 数据库与迁移

### 本地事实源

默认数据库：

```text
data/creator_hub.sqlite
```

当前数据库 Schema Version：

```text
17
```

核心持久数据包括但不限于：

- Creators
- Creator snapshots
- Videos
- Video snapshots
- Discovery runs / hits / Creator results
- 视频系统分类与人工复核
- Creator tags
- 商业表现
- Saved Views
- Job runs
- AI runs / findings / evidence
- Run specifications
- Data assertions
- 应用设置
- 二次指标 / 规则配置
- Schema migration history

### Migration Runner

Schema 迁移通过 `schema_migrations` 管理。

升级时统一运行：

```text
upgrade.cmd
```

流程包括：

1. 创建一致性 SQLite 升级前备份；
2. 执行数据库 Schema / Migration；
3. 运行自检；
4. 清理旧 Dashboard 输出；
5. 重新构建 Dashboard。

不要通过手工删表或修改 SQLite Schema 的方式升级。

---

## 安装

### 环境要求

- Windows 10 / 11
- Python 3.10+
- YouTube Data API v3 API Key
- 网络连接
- **不需要 Node/npm**

### 首次安装

在项目根目录运行：

```bat
setup.cmd
```

首次安装会完成：

- Python 环境检查
- 安装 `requirements.txt`
- 初始化 SQLite
- 配置 / 检查 YouTube API Key
- 自检
- 构建 Dashboard

### 已有环境升级

```bat
upgrade.cmd
```

### 日常启动

推荐使用交互模式：

```bat
start-dashboard.cmd
```

交互模式支持数据库写入、抓取、筛选、AI、批量操作和完整导出。

如果只需要查看已生成的静态快照：

```bat
open-static-dashboard.cmd
```

静态模式是只读模式，不能替代日常交互 Dashboard。

---

## API Key 与敏感信息

### YouTube API Key

使用 Windows 用户环境变量：

```text
YOUTUBE_API_KEY
```

推荐运行：

```bat
scripts\set-api-key.cmd
```

### AI API Key

AI 使用独立的本机密钥配置，不应写入 GitHub 仓库。

可以运行：

```bat
setup-ai.cmd
```

### 检查环境

```bat
scripts\python-run.cmd hub.py doctor
```

在线验证 YouTube API Key：

```bat
scripts\python-run.cmd hub.py doctor --online
```

---

## 常用命令

```bat
scripts\python-run.cmd hub.py init
scripts\python-run.cmd hub.py doctor
scripts\python-run.cmd hub.py doctor --online
scripts\python-run.cmd hub.py dashboard
scripts\python-run.cmd hub.py serve
scripts\python-run.cmd hub.py backup
scripts\python-run.cmd hub.py restore
scripts\python-run.cmd hub.py db-health
scripts\python-run.cmd hub.py monitoring-health
scripts\python-run.cmd hub.py import-business
scripts\python-run.cmd hub.py metric-config-export
scripts\python-run.cmd hub.py metric-config-import
```

完整命令以：

```bat
scripts\python-run.cmd hub.py --help
```

为准。

---

## GitHub 仓库与本地数据分离

本仓库是 **源码仓库**。

以下内容不应提交：

```text
data/creator_hub.sqlite
*.sqlite-wal
*.sqlite-shm
output/
exports/
backups/
_upgrade_backups/
.env*
API Key
CSV / XLSX / XLSM 业务文件
虚拟环境
缓存
日志
```

源码包中的：

```text
data/
output/
exports/
```

只保留 `.gitkeep`，用于维持目录结构。

---

## 跨设备迁移

如果要把当前业务数据迁移到另一台电脑：

1. 停止正在运行的 Dashboard 和所有写库任务；
2. 使用项目备份功能生成一致性数据库备份，或在完全停止写入后复制：
   ```text
   data/creator_hub.sqlite
   ```
3. 在新设备部署同版或更新版源码；
4. 将数据库放回：
   ```text
   data/creator_hub.sqlite
   ```
5. 重新配置 YouTube API Key 和 AI API Key；
6. 运行：
   ```bat
   upgrade.cmd
   ```
7. 再运行：
   ```bat
   start-dashboard.cmd
   ```

复制 SQLite 是**数据快照迁移**，不是两台设备之间的实时双向同步。

---

## 项目结构

```text
YouTube_Creator_Data_Hub/
├─ agents/
│  └─ openai.yaml
├─ config/
│  ├─ brands.json
│  ├─ geography.json
│  ├─ query_packs.json
│  └─ settings.json
├─ creator_hub/
│  ├─ ai/
│  ├─ services/
│  ├─ static/
│  ├─ dashboard.py
│  ├─ db.py
│  ├─ field_registry.py
│  ├─ jobs.py
│  ├─ metric_workspace.py
│  ├─ migrations.py
│  ├─ server.py
│  └─ service.py
├─ data/
│  └─ .gitkeep
├─ docs/
├─ exports/
│  └─ .gitkeep
├─ output/
│  └─ .gitkeep
├─ scripts/
├─ CHANGELOG.md
├─ PACKAGE_MANIFEST.json
├─ README.md
├─ SKILL.md
├─ VERSION
├─ hub.py
├─ requirements.txt
├─ setup.cmd
├─ setup-ai.cmd
├─ start-dashboard.cmd
└─ upgrade.cmd
```

---

## 进一步文档

详细设计和操作说明位于：

- `docs/ARCHITECTURE.md` — 系统架构
- `docs/INSTALLATION.md` — 安装与首次运行
- `docs/OPERATIONS.md` — 日常维护、备份、监控
- `docs/SECONDARY_METRICS.md` — 二次指标体系
- `docs/DATA_DICTIONARY.md` — 数据字典
- `docs/DISCOVERY_SCORING.md` — 博主发现评分
- `docs/QUERY_EXPANSION.md` — Query Expansion
- `docs/AI.md` — AI 模块
- `docs/CODEX_EXAMPLES.md` — Codex 使用示例

---

## 版本

```text
YouTube Creator Data Hub
Version: 3.10.7
Database Schema: 17
```
