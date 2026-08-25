---
name: youtube-creator-data-hub
description: 本地 Python YouTube creator discovery and monitoring with related-video-to-creator video-to-creator web search, SQLite fact storage, objective channel/video metrics, snapshots, deterministic UgPhone/competitor classification, automatic creator relationship labels, country evidence, public contact scraping, discovery pre-scoring, configurable time-window capture, Chinese Dashboard, and user-defined secondary metrics. No Node/npm is required.
version: 3.10.3
---
# YouTube 博主数据中心

## 当前版本规则

- 当前源码版本为 **3.10.3**，Schema 为 **17**；源码仓库不得包含 SQLite 业务数据库、API Key、导出结果、备份或缓存。
- 条件选择统一使用三级 Field Taxonomy：一级=客观数据/博主标签/构建指标/比值指标；二级=系统业务维度或用户自定义组；三级=具体指标。
- 规则 / 标签构建器、二次指标应用结果、主博主库必须复用同一套“一条件一行”交互，不允许恢复旧式纵向堆叠三级选择器或独立搜索按钮。
- 已构建指标与规则列表固定 **10 条/页**，使用列表内部纵向滚动，并与对应构建器保持等高；其他业务数据表默认仍按统一 30 条/页分页约定执行，除非页面另有明确设置。
- 人工判断优先于系统/AI 自动判断；事实、派生、AI、人工与有效值必须保持可审计来源。
- GMV 为 USD 累计快照，不做自动汇率换算；不同采集时间快照不得相加。
- 后台长任务走持久 Job Engine；Schema 变更走 Migration Runner；可重复 AI 工作流保存冻结 Run Specification。
- 新 API 消费者优先使用 `/api/v1`；Dashboard 的 Legacy API 只作兼容。

## 操作原则

- **单条 / 批量动作一致性**：支持多选的 Creator / Video 表格中，单条动作必须有对应批量动作；新增单条动作时同步检查批量入口。
- **交互数据实时性**：写 SQLite 后立即刷新相关动态 API 数据；不要把重启服务、`upgrade` 或 `build_dashboard()` 当成日常数据刷新步骤。
- **全历史上限显式化**：当前配置最多扫描/入库 10,000 条上传视频，UI 与批量确认均必须明确显示该上限。
- “搜索到的候选”与“正式博主库”必须分离。
- 每次发现创建 `discovery_runs` 搜索批次，同时保存博主级 `discovery_creator_results` 与视频级 `discovery_hits`；只有用户明确加入或抓取视频后才进入 `creators` 主库。
- UgPhone / 竞品 / 日常分类由系统识别逻辑产生；人工修正只用于纠错。
- Creator 身份标签由本地视频分类自动聚合：存在 UgPhone 视频即“合作过博主”，否则“未合作博主”；存在竞品/具体竞品品牌视频则追加对应身份。历史上合作过、仍在监控、同步数据足够新鲜且连续 30 天没有新的 UgPhone 视频时，额外标记“疑似不再合作”；它是待核查状态，不覆盖历史合作事实。
- 对未合作候选可显示 发现评分；不要把该评分表述为客观 YouTube 字段。

## 交互 Dashboard

用户要直接在网页搜索/抓取时，优先运行：

```powershell
python .\hub.py serve
```

这是 Python 本地服务，不需要 npm。静态只读版仍可用：

```powershell
python .\hub.py dashboard
```

## 博主发现

默认使用 相关视频 → 博主网页搜索：

```powershell
python .\hub.py discover "关键词" --search-source web --max-results 100
```

必要时回退 API：

```powershell
python .\hub.py discover "关键词" --search-source api --lookback-days 7
python .\hub.py discover "关键词" --from-date 2026-08-01 --to-date 2026-08-13 --target-country PH
```

工作流必须遵循：

`相关视频 → 命中视频指标 → 发布 Creator → 频道指标 → 发现预评分 → 发现记录`

不要因为发现候选就自动全历史抓取。


## Query Expansion

博主发现支持 6 个 Query Pack：Core、Farming / 成长收益、AFK / 云手机适配、Active Creator、Commercial / 评测比较、自定义。原关键词始终搜索一次，启用 Pack 后逐项执行 `原关键词 + 长尾词`，跨 Query 统一去重 Creator。

默认语言为 English，并内置拉美西语、巴西葡语、泰语、越南语、印尼语、韩语、日语、繁体中文（台湾）。Dashboard 可逐 Pack 启停、对当前语言长尾词增删，并预览本次实际 Query 数量。


## 指定时间视频入库

```powershell
python .\hub.py capture CHANNEL_ID --days 7
python .\hub.py capture CHANNEL_ID --days 30
python .\hub.py capture CHANNEL_ID --days 60
python .\hub.py capture CHANNEL_ID --days 90
python .\hub.py capture CHANNEL_ID --days 180
python .\hub.py capture CHANNEL_ID --days 365
python .\hub.py capture CHANNEL_ID --from-date 2026-01-01 --to-date 2026-06-30
python .\hub.py capture CHANNEL_ID --full-history
```

## 国家证据

证据优先级：

`YouTube About > YouTube API > 元数据关键词 > 语言提示`

保存 `country_resolved / country_source / country_evidence_json`。弱证据不得冒充 API 或 About 的强证据。

Dashboard 国家选择必须覆盖 `config/geography.json` 中全部 249 个 ISO alpha-2 国家/地区，并按东亚、东南亚、南亚、中亚、中东、欧洲、非洲、北美、拉美、巴西、大洋洲两级展示；输入中文国家名或英文代码应直接锁定对应国家。

## 公开联系方式

```powershell
python .\hub.py contact CHANNEL_ID
```

只抓公开可见邮箱、社交链接、网站和 About 国家信息。遇到验证/门槛记录 `gated`，不得绕过 CAPTCHA 或 YouTube 验证。

## 发现评分

保留 deterministic Pre-Score：

`30% subscriber fit + 30% view/sub + 20% engagement + 10% comment + 10% relative velocity`

A≥85，B≥70，C≥55，否则D。用于未合作候选参考。原 Final Score 公式也保留，但只有在真实获得 content-fit / audience-fit / brand-safety 输入后才允许计算；不得用常数或猜测补齐。

## 二次指标

二次指标必须严格区分数据粒度：

- **博主客观数据**：订阅数、频道累计播放量、本地视频数、各品牌视频数量等，每位 Creator 一个数值；直接用于规则/筛选/排序/比值，不允许再做 Average / Median / Sum。
- **博主标签**：合作过博主、未合作博主、LDCloud/RedFinger/VSPhone合作博主等布尔身份；只允许“存在 / 不存在”判断，不允许数值聚合。
- **视频客观数据**：播放量、点赞数、评论数、视频时长、视频条目；只作为指标构建器的数据源。
- **构建指标**：视频客观数据经过视频分类/品牌/时间筛选，再通过 Count / Sum / Average / Median / Max / Min 聚合为每位 Creator 一个数值。
- **比值指标**：只允许在博主级数值之间计算，分子/分母可选博主客观数据或已构建指标；不得在比值指标内部重新定义视频聚合逻辑。

正确的数据流：

`Video facts → per-Creator aggregation → constructed metric → optional ratio → Creator rule/filter/sort`

涉及视频的构建指标支持全部、近7/30/60/90/180/365天和精确开始/结束日期；精确范围在交互模式下由 Python/SQLite 计算，禁止为此把全量原始视频送进浏览器。

规则 / 标签构建器可引用博主客观数据、博主标签、构建指标、比值指标。第一条条件无连接词；从第二条开始，每条条件单独设置 AND / OR / NOT。总览、二次指标结果、博主详情、视频分类、博主发现结果/历史等具备筛选的页面也尽量沿用同一多条件逻辑。

“某品牌视频数量”属于博主客观数据；“是否与某品牌合作”属于博主标签。

## Dashboard 文件名与详情页

- 所有 Skill 自带文件、自动导出文件、Dashboard 页面/资源文件名必须使用英文、数字或 ASCII 符号，不得生成中文文件名。
- 总览博主库默认按 UgPhone 视频数降序。
- 博主详情页必须展示本地全部视频，并提供搜索、分类/品牌筛选、排序、分页；默认每页 30 条。
- 博主详情默认排序：UgPhone 相关视频优先，其次按播放量降序。
- 博主库中的本地入口文案使用“查看详情”。

## 大数据 Dashboard

必须继续执行 Python 预聚合，禁止把全量原始视频数组送进浏览器。总览与二次指标结果页均须支持“指标类别 → 具体指标 → 运算符 → 值”筛选。

## 视频分类与人工复核

【视频分类】页面的数据全集必须是 `videos` 中的全部本地视频，不得默认限定为待复核队列。系统分类与复核状态是两个不同维度：

- 系统分类：UgPhone / 竞品 / 日常视频 / 多品牌云手机 / 其他云手机 / 待复核；
- 复核状态：待人工复核 / 已人工复核 / 未人工复核 / 仅系统分类。

“待人工复核”表示系统已有分类或待定结果，但证据强度不足；它只是筛选状态。交互 Dashboard 必须使用 SQLite 服务端分页浏览全部视频，默认 30 条/页。可：

- 对全部视频搜索、筛选、排序和分页；
- 按复核状态筛选待人工复核、已人工复核、未人工复核、仅系统分类；
- 离线重新识别全部待复核（不消耗 YouTube API）；
- 对任意视频逐条“确认系统分类”；
- 对任意视频逐条修改分类和品牌；
- 所有人工确认/修正写入 `video_labels` 与 `video_label_audit`，并覆盖系统建议用于后续统计。

Codex 也可运行 `python hub.py review-reclassify`。


发现评分的公式和分档口径见 `docs/DISCOVERY_SCORING.md`。
