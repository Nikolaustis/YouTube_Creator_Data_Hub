# 数据字典

| 层级 | 表 | 内容 | 含义 |
|---|---|---|---|
| 客观事实 | `creators` | Channel ID、名称、Handle、API国家、订阅数、频道播放量、视频数、最近同步 | 当前公开频道事实 |
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
