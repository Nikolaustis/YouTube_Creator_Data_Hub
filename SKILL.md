---
name: youtube-creator-data-hub
description: 本地 Python YouTube creator discovery and monitoring with related-video-to-creator video-to-creator web search, SQLite fact storage, objective channel/video metrics, snapshots, deterministic UgPhone/competitor classification, automatic creator relationship labels, country evidence, public contact scraping, discovery pre-scoring, configurable time-window capture, Chinese Dashboard, and user-defined secondary metrics. No Node/npm is required.
version: 0.8.0
---

# YouTube 博主数据中心

本 Skill 的唯一事实源是 `data/creator_hub.sqlite`。

## 操作原则

- “搜索到的候选”与“正式博主库”必须分离。
- `discover` 结果先保存到 `discovery_hits`；只有用户明确加入或抓取视频后才进入 `creators` 主库。
- UgPhone / 竞品 / 日常分类由系统识别逻辑产生；人工修正只用于纠错。
- Creator 身份标签由本地视频分类自动聚合：存在 UgPhone 视频即“合作过博主”，否则“未合作博主”；存在竞品/具体竞品品牌视频则追加对应身份。
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

全局展示指标分为四类：

- 客观数据：系统基础事实/确定性统计，可直接用于筛选和规则；
- 聚合标签（0/1）：系统生成的博主身份标签，可直接按“存在/为真”筛选，不要求数字阈值；
- 构建指标：指标构建器从【客观数据】或【聚合标签】输入，通过 Count / Sum / Average / Median / Max / Min 生成；
- 比值指标：指标构建器的另一种输出，分子和分母都只能从【客观数据】定义聚合逻辑，然后计算比值。

指标构建器严格使用：

`输入：客观数据 / 聚合标签 → 输出：构建指标 / 比值指标`

若输出为比值指标，输入自动锁定为客观数据。涉及视频的指标支持全部、近7/30/60/90/180/365天和精确开始/结束日期；精确范围在交互模式下由 Python/SQLite 计算，禁止为此把全量原始视频送入浏览器。

规则 / 标签构建器可引用客观数据、聚合标签、构建指标、比值指标。第一条条件无连接词；从第二条开始，每条条件单独设置 AND / OR / NOT。总览、二次指标结果、博主详情、视频分类、博主发现结果/历史等具备筛选的页面也尽量沿用同一多条件逻辑。

“某品牌视频数量”放入客观数据；“是否与某品牌合作”放入聚合标签。

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
