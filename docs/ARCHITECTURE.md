# 架构

```text
Codex 对话
  ↓
hub.py
  ↓
SQLite（唯一事实源）
  ├─ Python Dashboard Builder → 静态只读 Dashboard
  └─ 本机 Python HTTP（127.0.0.1:8765）→ 交互 Dashboard
       ├─ 博主客观事实 / 视频分类
       ├─ 二次指标预聚合基础数据
       ├─ 博主发现搜索与写入
       └─ XLSX 导出 / 人工复核
```

## 原则

1. 不需要 Node/npm/Next.js；交互模式使用本机 Python HTTP 服务 `127.0.0.1:8765`，静态模式不启动服务。
2. Dashboard 是可删除、可重建的缓存，不是数据库。
3. 视频分类由 Skill 自动运行；人工分类表仅用于修正错误。
4. 二次指标属于分析层，不回写事实表；Creator 粒度事实/标签与 Video 粒度事实必须分离，Video 数据只有聚合后才能成为 Creator 构建指标。
5. 大数据量下禁止浏览器加载全量原始视频做聚合。
6. 博主详情页 Snapshot 按博主批量读取，避免逐视频查询。

## 二次指标数据文件

- `assets/creator_facts.js`：博主级客观事实和分类计数。
- `assets/metric_base.js`：Python 根据全部视频预先计算的聚合立方体。
- `assets/metrics_workspace.js`：浏览器侧指标/规则构建逻辑。
- `assets/metrics_config.js`：可选默认指标配置。

聚合立方体按：博主 × 分类/品牌 × 时间窗口 × 度量字段 × 聚合方式组织，因此浏览器可以即时建立常用运营指标而不携带几十万条视频记录。

## 博主发现历史

- `discovery_hits` 保存实际 Query × 视频命中的原始证据。
- `discovery_creator_results` 保存 Run × Creator 的去重结果。
- `discovery_runs.base_query_source=exact` 表示 v1.3+ 正式记录；`inferred` 表示 v1.4 对旧数据恢复出的关键词族。
- 历史推断只恢复基础关键词，不根据时间间隔伪造旧搜索批次。

## v2.1.0 operational state

SQLite is also the persistent store for operational/business state that must survive browser changes and database moves:

- `app_settings`: Secondary Metrics / Rules and Query profiles
- `creator_workflow` + audit: discovery handling state
- `creator_discovery_summary`: first/last/repeat discovery summary
- `creator_sync_attempts`: per-Creator monitoring attempts and errors
- `maintenance_runs`: backup / Snapshot maintenance audit
- `backup_registry`: known consistent backups

The live `creators` row carries category-specific freshness timestamps plus sync/retry state. Browser localStorage is not the source of truth for interactive-mode business configuration.
