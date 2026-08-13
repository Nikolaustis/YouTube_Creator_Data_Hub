# 数据字典

| 层级 | 表 | 内容 | 含义 |
|---|---|---|---|
| 客观事实 | `creators` | Channel ID、名称、Handle、API国家、订阅数、频道播放量、视频数、最近同步 | 当前公开频道事实 |
| 客观事实 | `creator_snapshots` | 抓取时间 + 频道指标 | 真实历史频道快照 |
| 客观事实 | `videos` | Video ID、标题、完整简介、YouTube Tags、发布时间、时长、分类ID、语言、直播状态、当前播放/点赞/评论 | 当前公开视频事实 |
| 客观事实 | `video_snapshots` | 抓取时间 + 播放/点赞/评论 | 真实历史视频快照 |
| 客观事实 | `discovery_hits` | 搜索词、来源、单次搜索内部排名、命中视频/频道、发现时间 | 博主为何进入数据库 |
| 系统分类 | `label_suggestions` | 系统分类、品牌、置信度、识别证据、规则版本 | Skill自动识别；表名为兼容历史命名 |
| 人工修正 | `video_labels` | 修正后的分类/品牌、操作人、备注、时间 | 仅用于纠错，不是分类成立前提 |
| 审计 | `video_label_audit` | 旧值/新值、操作人、时间 | 人工修正历史 |
| 运营元数据 | `creator_tags` | 博主 + 人工标签 | 团队维护标签 |
| 执行事实 | `sync_runs` | 模式、目标、处理数、配额、状态/错误 | 同步执行记录 |
| 执行事实 | `quota_daily` | 日期 + API估算单位 | 本地配额估算 |

## Dashboard派生数据

`output/dashboard/assets/creator_facts.js` 与 `metric_base.js` 是可重新生成的展示缓存，不是事实源。删除后可从 SQLite 重新生成。

> 单次搜索内部排名仅用于当次搜索与追溯，不在“已保存的发现记录”界面展示。
