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

##  operational state

SQLite is also the persistent store for operational/business state that must survive browser changes and database moves:

- `app_settings`: Secondary Metrics / Rules and Query profiles
- `creator_workflow` + audit: discovery handling state
- `creator_discovery_summary`: first/last/repeat discovery summary
- `creator_sync_attempts`: per-Creator monitoring attempts and errors
- `maintenance_runs`: backup / Snapshot maintenance audit
- `backup_registry`: known consistent backups

The live `creators` row carries category-specific freshness timestamps plus sync/retry state. Browser localStorage is not the source of truth for interactive-mode business configuration.


##  optional AI architecture

```text
AI Copilot (optional)
  ↓ allowlisted read-only tools
Creator Data Hub Core
  ↓
SQLite fact / deterministic / human layers
```

The AI layer is not a prerequisite for importing, syncing, classifying, discovering, monitoring, exporting or maintaining data. `creator_hub.service.CreatorHub` lazily loads the AI layer only when an AI command or AI endpoint is used. AI results live in separate `ai_*` tables.

v3.1 routes AI calls through a small protocol-adapter layer (`openai_responses`, `openai_chat`, `anthropic_messages`, `gemini_generate_content`, `mock`). Base URL and model ID are configuration data rather than hard-coded vendor/model catalogs. API secrets remain outside SQLite/browser state. The AI Search Agent may request the existing controlled YouTube discovery service, but the AI provider never receives arbitrary database or network write access.

## v3.6 commercial fact / workspace layer

- `creator_business_metrics`: period/source-aware commercial facts (GMV, acquisition and future UgPhone backend feeds).
- `saved_views`: persistent UI query/view state, intentionally separate from facts.
- `product_ui.js`: shared Inspector behavior; `saved_views.js`: shared saved-view behavior; `business_metrics.js`: local business-file import client.
- Creator facts expose only aggregated commercial summaries for filtering/sorting/secondary metrics; detailed lineage stays in the business fact table and Inspector.

## v3.10 Core Architecture

```text
Dashboard / future Workbench
        │
        ├── Field Registry v2 (3-level taxonomy)
        ├── /api/v1 contract
        └── Global Job Center
                 │
                 v
             Job Engine
      ┌──────────┼──────────┐
   YouTube       AI       Local/Maintenance
   queue=1     queue=1       queue=2/1
      │           │              │
      └───────────┴──────────────┘
                 │
          CreatorHub facade
       ┌─────────┼───────────┐
  RunService  Intelligence  DataContract
       │           │             │
       └───────────┴─────────────┘
                 │
             SQLite WAL
      ┌──────────┼─────────────┐
   facts      run_specs   data_assertions
      │      job_runs     schema_migrations
      └──────────┴─────────────┘
```

### Field taxonomy

Field selection is not a free-growing single list. The canonical three levels are:

1. **Level 1**: `客观数据 / 博主标签 / 构建指标 / 比值指标`.
2. **Level 2**: objective business dimensions, label dimensions, or the user's own metric group.
3. **Level 3**: the stable field/metric ID.

The same registry is consumed by filters, sorting, rules, ratio operands and Saved Views. Display labels are not persistence keys.

### Job execution

`job_runs` is the durable execution ledger. Jobs enter resource queues instead of creating one unbounded thread per click. Cancellation is cooperative: workers stop at progress/checkpoint boundaries and committed data is retained. Only jobs marked `resumable=1` are requeued after a Dashboard restart; other in-flight jobs become explicit interruptions.

### Run reproducibility

`run_specs` stores an immutable request, final structured plan and execution parameters. AI Search Clone & Re-run reuses the stored final Query list and Fit Criteria; it does **not** call the Planner again. The YouTube facts are intentionally refreshed, producing a new child Result Set/Run Spec so changes in source data remain observable.

### Data decision contract

`data_assertions` is the cross-domain assertion layer. Assertions are one of `fact / derived / ai / human`. The default effective-value priority is `human > ai > derived > fact`. Purpose-built legacy tables remain in place for compatibility while new domains should publish assertions through `DataContractService`.

### Database migrations

Schema evolution is recorded in `schema_migrations`. Migration 17 is the Core Architecture migration. Legacy databases receive a baseline record for their pre-run schema version before registered migrations execute. Migration checksum mismatches are fatal rather than silently accepted.
