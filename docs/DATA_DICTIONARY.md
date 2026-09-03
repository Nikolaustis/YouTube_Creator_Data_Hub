# 数据字典

| 层级 | 表 | 内容 | 含义 |
|---|---|---|---|
| 客观事实 | `creators` | Channel ID、名称、Handle、API国家、订阅数、频道播放量、视频数、最近同步、频道可用性状态/原因/检测时间/连续不可用次数 | 当前公开频道事实与 Creator 生命周期状态 |
| 客观事实 | `creator_snapshots` | 抓取时间 + 频道指标 | 真实历史频道快照 |
| 客观事实 | `videos` | Video ID、标题、完整简介、YouTube Tags、发布时间、时长、分类ID、语言、直播状态、当前播放/点赞/评论 | 当前公开视频事实 |
| 客观事实 | `video_snapshots` | 抓取时间 + 播放/点赞/评论 | 真实历史视频快照 |
| 发现批次 | `discovery_runs` | Run ID、原关键词、关键词来源、搜索源、Query Expansion语言与Query列表、时间/地区条件、执行状态、命中数 | 正式搜索为一次完整任务；历史聚合明确标记为推断 |
| 发现结果 | `discovery_creator_results` | Run ID + Channel ID、最佳命中视频、发现评分、Query Coverage、命中Query、命中视频数 | 一次搜索 × 一个博主的去重结果 |
| 发现证据 | `discovery_hits` | Run ID、实际Query、命中视频/频道、单次Query内部排名、发现时间 | 视频级原始发现证据；旧记录内容保留，v1.4.0 仅补充派生历史关键词族关联 |
| 系统分类 | `label_suggestions` | 系统分类、品牌、置信度、识别证据、规则版本 | Skill自动识别；表名为兼容历史命名 |
| 人工修正 | `video_labels` | 修正后的分类/品牌、操作人、备注、时间 | 仅用于纠错，不是分类成立前提 |
| 审计 | `video_label_audit` | 旧值/新值、操作人、时间 | 人工修正历史 |
| 运营元数据 | `creator_tags` | 博主 + 人工标签 | 团队维护标签 |
| 执行事实 | `sync_runs` | 模式、目标、处理数、配额、状态/错误 | 同步执行记录 |
| 执行事实 | `quota_daily` | 日期 + API估算单位 | 本地配额估算 |

## Dashboard派生数据

`output/dashboard/assets/creator_facts.js` 与 `metric_base.js` 是可重新生成的展示缓存，不是事实源。删除后可从 SQLite 重新生成。

> 单次搜索内部排名仅用于当次搜索与追溯，不在“已保存的发现记录”界面展示。

## 历史发现迁移

v1.3.0 以前的 `discovery_hits` 没有原关键词和真实搜索批次 ID，因此仍然不会根据时间间隔猜测旧批次。v1.4.0 升级时保留全部旧视频命中证据，只删除并重建 v1.3.0 自动生成的 `legacy-history` 派生记录。系统依据 Query Pack 已知长尾词以及历史中实际出现过的基础 Query，恢复“关键词族”，并按“推断原关键词 × Creator”聚合为稳定的 `legacy-keyword-*` 历史 Run；这些记录的 `base_query_source=inferred`，Dashboard/XLSX 显示为【历史推断】。v1.3.0 以后正式搜索的 `base_query_source=exact`，显示为【精确记录】。


## Creator 频道可用性字段（v3.5.0）

`creators.availability_status` 与普通同步健康分离。允许值包括 `available`、`unavailable_pending`、`terminated_community`、`terminated_copyright`、`deleted`、`unavailable_unknown`。`availability_reason` 保存可审计原因，`availability_source` 保存判定来源，`availability_checked_at` 保存最近检测时间，`availability_failures` 记录连续不可用次数。API 单次未返回频道不得直接推断社区准则/版权违规；具体终止原因只在公开 YouTube 页面给出明确标记时记录。终止/删除状态不删除本地 Creator/Video 历史。

## Persistent Jobs & Manual Creator Availability（v3.9.0）

- `job_runs`：Dashboard 后台任务的持久状态，包含任务类型、阶段、消息、current/total、percent、开始/完成时间、结果和错误。页面切换/刷新可恢复显示；服务进程重启后无法续跑的线程会被标记为中断。
- `creator_availability_overrides`：人工覆盖频道可用性、内容状态、监控策略与备注。该表不覆盖 `creators.availability_*` 的系统原始检测，因此“系统检测”和“有效状态（人工优先）”可同时审计。
- `creator_availability_override_audit`：人工频道状态覆盖的旧值/新值、操作人和时间。

终止/删除/停止监控只停止未来普通同步，不删除既有 Creator、Video、Snapshot 或商业指标历史。

## Creator Business Metrics（v3.9.3）

`creator_business_metrics` 是独立于 `creators` 的商业事实表。GMV 采用 UgPhone 后台既定的 **USD 累计快照**口径。

| Field | Meaning |
|---|---|
| `channel_id` | 对应 Creator |
| `metric_key` | 标准指标键；当前支持 `gmv` / `new_users` / `orders` / `revenue` / `commission` / `cost` |
| `metric_value` | 指标原值；对 `gmv` 即 USD 累计 GMV |
| `currency` | `gmv` 固定为 `USD`；其他指标保留来源值（如有） |
| `metric_value_usd` | 兼容字段；对 `gmv` 恒等于 `metric_value` |
| `fx_rate_to_usd` / `fx_rate_date` / `fx_provider` / `fx_status` | Schema 16 兼容字段；对 `gmv` 固定为 native USD 元数据，不提供业务换算功能 |
| `snapshot_kind` | 当前为 `point_in_time_total`，表示采集时间点累计总量 |
| `period_start` / `period_end` | 指标统计周期（源表提供时保留） |
| `campaign` / `region` | 可选 Campaign / 市场维度 |
| `source_type` / `source_ref` | 数据来源类型和可追溯来源行 |
| `import_batch` | 导入批次 |
| `captured_at` | 业务数据采集/快照时间；优先取源表，缺失时取用户输入，再缺失才用导入时间 |
| `note` / `raw_json` | 备注和原始行审计信息 |

同一 Creator 存在多个历史累计 GMV 快照时，Headline/博主库/二次指标只使用**最新 `captured_at` 快照**；不同采集时间的累计值不得相加。V3.9.3 不再执行 GMV 汇率换算，也不根据 Creator 国家推断币种。

`saved_views` 保存页面级筛选/排序显示状态，只影响工作区视图，不改变事实数据。

## V3.10 Core Architecture tables

- `schema_migrations`: applied schema migration version, name, checksum and timestamp.
- `run_specs`: immutable reproducibility specification for AI/analysis runs. Stores request, final plan, execution parameters, fingerprint and parent/source links.
- `data_assertions`: cross-domain assertion contract. Key dimensions are entity, stable field ID, layer (`fact/derived/ai/human`), value, confidence/source, rule version and observation time.
- `job_runs` V3.10 columns: persisted payload, resource class, cancel request, checkpoint, resumable flag, retry lineage and worker ID. These fields turn the historical task ledger into the Job Engine state store.
