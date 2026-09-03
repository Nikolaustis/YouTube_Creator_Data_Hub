# YouTube Creator Intelligence Hub v4.0.2

本项目是一个本地优先的 **YouTube Creator Intelligence / Creator Data Management** 产品。它把 YouTube Creator / Video 的客观事实与具体业务语义拆开：基础数据全局共享，品牌、关系、分类、商业指标、发现策略、二次指标和规则由 Workspace 定义。

> GitHub 仓库只保存源码、配置模板和文档。业务数据库、API Key、导出结果、备份和运行缓存不得提交。

## V4 核心变化

### Global Fact Layer

Core 只认识稳定、通用的数据实体：

- Creator
- Video
- Creator / Video Snapshot
- Discovery Run / Hit
- Job
- AI Run / Finding / Evidence
- Run Specification
- Data Assertion

Core 不再要求某个特定品牌、竞品集合、行业分类或商业指标必须存在。

### Workspace Intelligence Layer

每个 Workspace 可以独立定义：

- Brand
- Brand Group
- Taxonomy / Label
- Creator Relationship
- Business Metric Definition
- Discovery Profile
- Constructed Metric / Ratio Metric
- Rule
- Saved View
- Workspace Preset

同一个 Creator / Video 不会因为进入多个项目而复制多份基础事实。

## Workspace 模板

系统内置：

- **Blank Workspace**：空白通用工作区
- **Brand / Influencer Marketing**：品牌 / 达人营销
- **Affiliate / Performance Marketing**：联盟 / 效果营销
- **Gaming Creator Discovery**：游戏 Creator 发现
- **Cloud Phone Growth**：云手机增长兼容 Workspace

Cloud Phone Growth 保留既有云手机分类、品牌和商业数据能力，但这些概念现在属于 Workspace 配置，不属于 Core。

## Workspace 数据模型

```text
Global Fact Layer
├─ creators
├─ videos
├─ creator_snapshots
├─ video_snapshots
├─ discovery_*
├─ job_runs
├─ run_specs
└─ data_assertions

Workspace Intelligence Layer
├─ workspaces
├─ workspace_settings
├─ workspace_brands
├─ brand_groups
├─ brand_group_members
├─ taxonomy_schemes
├─ taxonomy_labels
├─ video_taxonomy_assignments
├─ creator_relationships
├─ business_metric_definitions
├─ discovery_profiles
└─ workspace_presets
```

## 工作区切换

Dashboard 新增 **工作区** 页面。

切换 Workspace 后会重新构建 Dashboard，使当前页面使用新的：

- 品牌配置
- Taxonomy
- Creator Relationship
- 商业指标定义
- 二次指标 / 规则
- Saved Views
- Discovery Profile

Creator、Video 和 Snapshot 不会被复制或删除。

## 三级 Field Taxonomy

字段选择继续使用统一三级结构：

```text
一级
├─ 客观数据
├─ 标签 / 关系
├─ 构建指标
└─ 比值指标
```

二级由 Core 业务维度和 Workspace / 用户分组共同生成，三级是稳定 Field ID。

Workspace 还可以动态向字段注册表提供：

- `business__<metric_key>` 商业指标
- `relationship__<type>__<status>` Creator Relationship
- Workspace Taxonomy 视频筛选项

Cloud Phone Growth 中保留的旧字段只作为兼容别名，保证既有指标和规则能够继续执行。

## 二次指标与规则隔离

`secondary_metrics` 现在按当前 Workspace 持久化到 `workspace_settings`。

Saved Views 也按 Workspace 隔离。切换 Workspace 后不会看到其他 Workspace 的规则视图配置，但共享 Creator / Video 基础事实。

## 品牌与分类

分类器从当前 Workspace 读取品牌配置。

- 通用 Workspace 不需要任何预设品牌。
- Brand Workspace 可维护自己的 Brand / Brand Group。
- Cloud Phone Growth 使用兼容品牌配置，以保证既有分类结果不丢失。

## 商业数据

`creator_business_metrics` 仍是通用事实表，`metric_key` 可以是任意业务指标。

Workspace 通过 `business_metric_definitions` 声明哪些指标属于当前项目，例如：

- Revenue
- GMV
- Orders
- New Users
- Installs
- Leads
- Trials

二次指标只暴露当前 Workspace 定义的业务指标。

## Data Contract

统一来源层继续使用：

```text
fact < derived < ai < human
```

有效值优先级：

```text
human > ai > derived > fact
```

Workspace 只改变业务上下文，不改变事实审计原则。

## Job Engine 与 Run Specification

后台长任务继续使用持久 Job Engine，包括：

- 资源队列
- 进度
- 取消
- 重试
- Checkpoint
- 可恢复任务

可重复 AI / Discovery 工作流继续保存 Run Specification，避免重新执行时条件漂移。

## 数据库

默认数据库：

```text
data/creator_hub.sqlite
```

当前 Schema：

```text
18
```

Schema 迁移由 Migration Runner 管理，不应手工修改数据库结构。


## V4.0.2 本机交互服务地址修复

交互 Dashboard 的本机监听地址统一为 **`127.0.0.1:8765`**。本版清理历史遗留的无效 Host `.1`：

- `hub.py serve` 默认 `--host 127.0.0.1`；
- `start-dashboard.cmd` 显式使用 `--host 127.0.0.1 --port 8765`；
- `doctor` 的端口探测绑定 `127.0.0.1`，并返回 `http://127.0.0.1:8765/`；
- `serve_dashboard()` 默认 Host 改为 `127.0.0.1`；
- 本机敏感 API 的来源校验允许 `127.0.0.1` / `::1`；
- Setup、Dashboard 提示、导出提示和安装/架构文档中的地址同步修正。

Schema 仍为 18，不修改 Creator、Video、Workspace、指标、规则或其他业务数据。

## Dashboard 构建性能

当前 Dashboard Builder 针对大数据库全量重建进行了以下优化：

- **Metric Cube 去 N+1**：视频事实与当前 Workspace Taxonomy 各批量读取一次，再按 `channel_id` 在 Python 内分组；不再对每位 Creator 单独执行视频查询和 Taxonomy 查询。
- **Creator Detail 批量加载**：全部视频与 Creator Tag 一次读取；Snapshot 历史按 32 位 Creator 分块读取，不再对每位 Creator 单独执行窗口查询。
- **Creator Detail 增量缓存**：同一版本后续重建会对未变化的 Creator Detail HTML 直接命中缓存，只重建发生数据变化的 Creator。
- **Metric Cube 缓存**：`metric_base.js` 根据视频、分类、Taxonomy、Creator Relationship 与 Workspace 定义生成签名；数据未变化时直接复用。
- **不再删除整个 Dashboard 输出目录**：升级重建保留可复用缓存，同时构建器会主动删除已经不存在的 Creator 页面。
- **全过程进度输出**：控制台显示 `[Dashboard 1/8]` 至 `[Dashboard 8/8]`、Creator 页面进度、Metric Cube 进度、缓存命中及累计耗时。

首次建立 Creator Detail 缓存时仍需要完成一次页面重建；但查询已改为批量方式，Metric Cube 的旧 N+1 路径已被移除。后续同版本重建会显著减少重复工作。


## 安装与升级

### 首次安装

```bat
setup.cmd
```

### 覆盖升级

```bat
upgrade.cmd
```

升级会：

1. 创建一致性 SQLite 备份；
2. 覆盖当前源码；
3. 执行 Migration Runner；
4. 初始化 / 迁移 Workspace；
5. 运行 self-check；
6. 清理并重建 Dashboard。

### 日常启动

```bat
start-dashboard.cmd
```

## 覆盖包命名规范

从本版本起，覆盖包内部的升级辅助文件全部使用稳定文件名：

```text
upgrade.cmd
apply_upgrade.py
README.md
PATCH_MANIFEST.json
overlay/
```

不再生成带版本号的 `apply_*`、额外 README、Patch Manifest 或补丁脚本文件，因此下一次覆盖无需手工清理历史升级辅助文件。

升级器还会自动清理由早期覆盖包遗留的版本化升级辅助文件。

## API

Workspace API：

```text
POST /api/v1/workspaces/list
POST /api/v1/workspaces/context
POST /api/v1/workspaces/create
POST /api/v1/workspaces/set-active
```

其他新 API 消费者仍优先使用 `/api/v1`。

## GitHub 与本地数据分离

以下内容不得提交：

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
CSV / XLSX 业务文件
虚拟环境
缓存
日志
```

## 跨设备迁移

Creator / Video 等业务数据仍以 SQLite 为主。

迁移建议：

1. 停止 Dashboard 和写库任务；
2. 创建一致性数据库备份；
3. 在新设备部署相同或更新版本源码；
4. 将数据库放到 `data/creator_hub.sqlite`；
5. 重新配置本机 API Key；
6. 运行 `upgrade.cmd`；
7. 启动 Dashboard。

Workspace、品牌、Taxonomy、关系、二次指标配置等都保存在 SQLite 中，因此会随数据库迁移。

## 项目结构

```text
YouTube_Creator_Data_Hub/
├─ config/
│  ├─ workspace_templates.json
│  ├─ brands.json
│  ├─ geography.json
│  ├─ query_packs.json
│  └─ settings.json
├─ creator_hub/
│  ├─ ai/
│  ├─ services/
│  ├─ static/
│  ├─ workspace.py
│  ├─ field_registry.py
│  ├─ metric_workspace.py
│  ├─ migrations.py
│  ├─ dashboard.py
│  ├─ server.py
│  └─ service.py
├─ docs/
├─ scripts/
├─ README.md
├─ SKILL.md
├─ VERSION
├─ hub.py
├─ setup.cmd
├─ start-dashboard.cmd
└─ upgrade.cmd
```

## 版本

```text
YouTube Creator Intelligence Hub
Version: 4.0.2
Database Schema: 18
```
