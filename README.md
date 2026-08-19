# YouTube 博主数据中心 v2.1.0
> v2.1.0 表格交互一致性更新：监控健康默认 30 条/页；所有支持批量操作的表格增加跨全部页面的全选与清空选择。

本项目是一个本地 Python + SQLite 的 YouTube Creator 数据中心。**不需要 Node/npm**。正常使用推荐交互 Dashboard；静态 Dashboard 用于只读快照。

## 首次安装（推荐）

1. 安装 Python 3.10+。推荐让命令行可以运行 `python --version`；如果只有 Windows Python Launcher（`py -3`），新版启动器也会自动使用。
2. 在项目根目录运行：

```powershell
.\setup.cmd
```

`setup.cmd` 会自动安装 Python 依赖、初始化/升级 SQLite、检查 API Key、运行环境诊断并生成 Dashboard。完成后会出现下一步菜单，可直接启动交互 Dashboard、打开静态 Dashboard、安装自动监控或在线验证 API Key。若系统没有 `python` 命令但安装了 Windows Python Launcher，启动脚本会自动尝试 `py -3`。

### 配置 YouTube API Key

推荐执行：

```powershell
.\scripts\set-api-key.cmd
```

API Key 保存在 Windows 用户环境变量 `YOUTUBE_API_KEY`，不需要写入源码或配置文件。检查环境：

```powershell
python .\hub.py doctor
```

进一步验证 API Key 是否真的可用：

```powershell
python .\hub.py doctor --online
```

## 两种 Dashboard

### 交互 Dashboard — 日常使用

```powershell
.\start-dashboard.cmd
```

浏览器通过 `http://127.0.0.1:8765/` 与**本机 Python + 本机 SQLite**通信。支持搜索、抓取、写库、完整筛选/分页、人工复核、联系方式抓取和完整 XLSX 导出。

### 静态 Dashboard — 只读快照

```powershell
.\open-static-dashboard.cmd
```

直接打开生成的 HTML，不启动 Python 服务。适合离线查看；写操作、全库动态筛选和完整 XLSX 导出需要交互模式。

Dashboard 顶部会明确显示“交互模式 / 静态只读”，交互模式还显示 Python、SQLite 和 API Key 状态。完整安装说明见 `docs/INSTALLATION.md`。


## v2.1.0：统一分页与跨页批量选择

- 【监控健康】纳入统一分页体系，默认每页 30 条，可调整每页数量、翻页和跳转。
- 总览博主库、视频分类、本次搜索结果·博主、已保存发现记录·博主统一提供“勾选当前页 / 全选全部结果 / 清空选择”。
- 跨页选择在翻页时保持；搜索或筛选范围变化时清空旧选择，避免误操作。
- 视频分类跨页全选采用服务端 all-matching 选择，不需要把 50 万+ Video ID 先加载到浏览器。
- SQLite Schema 仍为 10，不需要新增数据库结构迁移。

## v2.0.0：长期运行、数据治理与工作流

- 关键业务配置持久化到 SQLite：二次指标/规则和 Query Expansion 配置以 `app_settings` 为交互模式事实源，浏览器 localStorage 仅作为静态模式或临时草稿回退。
- 【数据更新】新增数据库健康、SQLite 一致性备份/恢复和备份列表；恢复前自动创建安全备份。
- 新增监控健康面板、Creator 级同步失败类型、连续失败次数、下次同步/重试时间和异常暂停；失败采用分级退避，连续 5 次异常会暂停重复消耗配额（quota/auth 除外）。
- Snapshot 生命周期管理：近 30 天保留全部，31–180 天按日、181–730 天按周、两年以上按月保留；自动监控任务最多每 7 天执行一次压缩。
- 博主发现新增“未处理 / 感兴趣 / 待联系 / 已入库 / 暂不考虑 / 永久排除”工作流；永久排除默认不会再次出现在本次搜索结果。
- 发现记录增加首次/重复发现、历史发现次数、首次发现时间和最近发现时间。
- 总览、博主发现和视频分类增加批量操作。
- 二次指标增加分组、说明、创建/更新时间和依赖检查；被规则或其他指标引用的指标禁止直接删除。
- 统一展示频道数据、视频指标、分类、联系方式、发现记录和完整同步的新鲜度时间。
- SQLite Schema 升级至 10；旧数据库原地迁移，不删除原始 Creator / Video / Discovery / Label 数据。

常用运维命令见 `docs/OPERATIONS.md`。

## v1.6.0：应用结果条件可见性与视频分类性能优化

- 【二次指标 → 应用结果 · 博主库】的当前规则改为临时查看状态，不再跨页面重启/版本升级静默残留；旧 localStorage 中的 activeRule 会在加载时自动归零。
- 【清除全部条件】现在同时清除普通筛选、当前规则和搜索词；结果区明确显示“当前条件”和当前规则名称，避免少量命中被误认为数据缺失。
- 【视频分类】交互模式不再先把 300 条静态预览渲染成“10 页”正式分页，而是先显示“正在连接本机 Python / 正在读取完整数据库第一页”。仅在静态只读模式下才显示 300 条预览分页。
- 视频分类分页查询不再每次重复计算四项全库 KPI；顶部统计拆为独立轻量查询，只在人工复核/重新分类后刷新。
- 默认无筛选的总数查询直接使用 `COUNT(videos)`；仅在筛选条件确实依赖分类/人工标签/Creator 时才加入对应 JOIN。
- Schema 升级至 5，新增全局发布时间、系统分类角色/置信度和人工角色索引，改善 50 万+ 视频下的首页排序与常用筛选。

## v1.5.0：全局二级导航与首次部署引导完善

- 五个一级页面全部启用侧边栏二级导航；点击可平滑定位，滚动时自动高亮，URL Hash 可直接定位。
- 【总览】提供“数据概览 / 身份与监控说明 / 博主库”；【二次指标】覆盖构建器、规则、已保存配置与应用结果；【视频分类】覆盖数据概览、复核说明、筛选与结果；【数据更新】覆盖监控调度、同步记录和 API 配额。
- `setup.cmd` 完成后提供下一步菜单，可直接启动交互 Dashboard、打开静态 Dashboard、安装自动监控或在线验证 API Key。
- 新增 `scripts/python-run.cmd`：优先使用 `python`，不可用时自动尝试 Windows Python Launcher `py -3`；主要 CMD 启动器统一使用该入口。
- `doctor` 新增 `python_executable`、8765 端口可用性及端口错误信息，便于首次部署排查本机 Python / 交互服务问题。
- 自动监控脚本使用同一 Python 解析逻辑，减少“手工能运行、计划任务找不到 Python”的环境差异。

## v1.4.0：博主发现导航与历史关键词恢复

- 【博主发现】左侧边栏在当前页面展开四个二级入口：搜索新博主、本次搜索结果 · 博主、已保存的发现记录 · 博主、已保存的发现记录 · 视频命中；点击后在主区域平滑定位，手动滚动时同步高亮。
- 修复 v1.3.0 将所有旧博主级发现记录原关键词写成 `Legacy Discovery` 的问题。
- v1.3 以前的 `discovery_hits` 原始视频命中证据不删除；升级时只重建派生的历史博主级记录。
- 旧实际 Query 先剥离 Query Pack 已知长尾词，并利用历史中真实出现过的较短基础 Query 辅助恢复原关键词；历史恢复结果明确标记为【历史推断】，不会伪装成精确历史搜索批次。
- 旧数据按“推断原关键词 × Creator”重新聚合，并生成稳定的 `legacy-keyword-*` 历史聚合 Run ID；v1.3+ 正式搜索继续标记为【精确记录】。
- 【已保存的发现记录 · 博主】Dashboard 和 XLSX 均增加【关键词来源】，XLSX 的【原关键词】恢复为 Anime Expeditions、Bee Swarm Simulator、The Tower 等实际基础搜索词，而不再统一为 `Legacy Discovery`。

## v1.3.0：安装引导、XLSX 导出与发现数据模型 v2

- 新增 `setup.cmd`、`scripts/set-api-key.cmd` 和增强版 `doctor / doctor --online`。
- 核心 Dashboard 表格均增加 XLSX 导出；交互模式导出**当前筛选后的全部结果**，不是只导出当前页 30 条。
- 博主发现新增正式搜索批次 `discovery_runs`。
- 同时保存两层发现数据：`discovery_creator_results`（一次搜索 × 一个博主）与 `discovery_hits`（实际 Query × 命中视频）。
- 历史 v1.2 及更早的 `discovery_hits` 完整保留；v1.4.0 起不再使用单一 `Legacy Discovery` 汇总，而是按可恢复的原关键词生成【历史推断】聚合。
- 【博主发现】历史界面分别展示/导出“博主记录”和“视频命中记录”。

## v1.2.1 交互筛选与二次指标排序修复

- 修复【二次指标 → 应用结果 · 博主库】使用构建指标/比值指标排序时的前端函数引用错误。
- 强化【总览】和【视频分类】筛选的应用反馈；点击应用后会显示已应用条件数和命中条数。
- `upgrade.cmd` 会先删除旧 `output/dashboard` 再完整重建，避免覆盖升级后新旧前端资产混用。
- 交互 Dashboard 服务禁用浏览器缓存，确保 HTML 与 JS 始终来自同一版本。
- 保留 v1.2.0 的【疑似不再合作】保守判定及应用结果修复。

## v1.1.0 展示、筛选与监控调度

- 身份标签采用绿/蓝/红色语义背景；发现评分 A/B/C/D 使用绿/蓝/黄/红分档。
- 二次指标应用结果固定核心播放指标，仅突出当前排序指标，避免指标列无限膨胀。
- 视频分类支持视频客观数据筛选。
- 批量监控按优先级刷新周期真正跳过未到期对象；定时任务每 6 小时触发一次。
- 如需 Windows 自动监控，运行 `scripts\install-sync-task.cmd` 安装每 6 小时触发的计划任务。

## v1.0.0 二次指标粒度重构

- 明确区分【博主客观数据】【博主标签】【视频客观数据】三个数据层级。
- 博主客观数据和博主标签直接用于筛选、排序和规则，不再进入 Count / Average / Median 等聚合器。
- 指标构建器只聚合视频客观数据，聚合结果固定输出为每个 Creator 一个【构建指标】。
- 比值指标只允许使用【博主客观数据】或【已构建指标】作为分子/分母，不再在比值内部重复定义视频聚合。
- 旧版“聚合标签构建指标”等错误配置会在浏览器端和配置导入时迁移/丢弃；旧版直接视频比值会迁移为隐藏构建指标 + 比值引用。
- 规则和筛选统一使用四类 Creator 级对象：博主客观数据、博主标签、构建指标、比值指标。

## v0.9.3 视频分类首屏分页修复

- 【视频分类】页面初始化时立即按 30 条/页分页静态预览，不再在交互 API 返回前展示全部预览行。
- 交互模式仍由 SQLite 按 `page=1, page_size=30` 返回首屏数据；分页按钮不再承担“首次应用分页”的隐式职责。
- 修复顶部显示“当前显示 1-30”但页面实际可滚动看到超过 30 条记录的状态错位。



## v0.9.2 地理筛选级联

Creator 级筛选中的国家/地区统一改为“区域 → 国家/地区”两级选择。先选择东亚、东南亚、南亚、中亚、中东、欧洲、非洲、北美、拉美、巴西或大洋洲；如需要进一步收窄，再选择该区域内的具体国家/地区。

## v0.9.1 Query Expansion 逐词启停

- Query Pack 总开关控制整组是否参与；每个扩展词可独立勾选/取消勾选。
- 勾选：本次搜索使用；取消勾选：保留但本次不使用；×：从当前语言词库删除。
- 新增词默认勾选；旧 v0.9.0 本地词库会自动迁移。

- 博主发现新增 Query Expansion 工作区。原关键词始终执行一次，启用 Query Pack 后再逐项搜索“原关键词 + 长尾词”。
- 内置 6 个可编辑 Query Pack：Core、Farming / 成长收益、AFK / 云手机适配、Active Creator、Commercial / 评测比较、自定义。
- 使用者可逐 Pack 启用/停用，并对当前语言的长尾词增加或删除；交互模式的编辑状态保存到 SQLite，静态只读模式使用浏览器本地回退。
- 默认 English，同时内置拉美西语、巴西葡语、泰语、越南语、印尼语、韩语、日语、繁体中文（台湾）。
- Dashboard 显示本次实际 Query 预览、Query 数量，以及 API 搜索时的预计 `search.list` quota。
- 网页搜索补充 continuation token 深度加载；API 搜索继续通过 `nextPageToken` 翻页。
- 多 Query 结果统一按 Creator 去重；同一 Creator 保留发现评分最高的命中，并显示 Query Coverage。

完整词库与行为见 `config/query_packs.json` 和 `docs/QUERY_EXPANSION.md`。

## v0.8.0 视频分类全量管理

- 【视频分类】页面默认数据范围改为全部本地视频，而不是待人工复核队列。
- “待人工复核”只是复核状态之一，可与“已人工复核 / 未人工复核 / 仅系统分类”一起作为筛选条件。
- 交互模式通过 SQLite 服务端分页浏览完整视频库；静态 HTML 仅保留轻量预览，避免把几十万条视频写入单个网页。
- 每条视频同时显示系统分类、识别证据、复核状态、最终分类与人工复核操作。

- 博主发现的发布时间快捷选项为不限、近7/30/60/90/180/365天，并支持精确开始日期与结束日期。
- 搜索结果抓取入库同样支持近7/30/60/90/180/365天、指定日期范围和全历史。
- 二次指标涉及视频时间窗口时同样支持近7天与精确日期范围；精确日期指标由 Python 直接查询 SQLite 计算。
- 国家/地区选择覆盖 249 个 ISO alpha-2 代码，采用“大洲/区域 → 国家/地区”两级结构；输入中文国家名或英文代码即可锁定国家。
- 区域分组固定为：东亚、东南亚、南亚、中亚、中东、欧洲、非洲、北美、拉美、巴西、大洋洲。
- 视频分类及其它分页表默认30条/页，统一提供首页、上一页、相邻页码、下一页、末页和输入页码跳转。
- 博主发现完成后，发现记录即时写入本地数据库并刷新历史列表。
- 指标构建器的输入类型只有【客观数据 / 聚合标签】，输出类型只有【构建指标 / 比值指标】；选择比值指标时只允许用客观数据定义分子和分母。
- 聚合标签属于布尔条件，筛选时直接按“存在/为真”判断，不显示数值输入框。
- 支持多条件 AND / OR / NOT：总览博主库、二次指标应用结果、博主详情、视频分类、博主发现本次结果与已保存记录均使用同一布尔筛选思想。
- 规则 / 标签构建器从第二条条件开始逐条选择 AND / OR / NOT，不再使用一个全局关系。

## v0.5.0 分页与分类复核

- 所有需要分页的表格默认每页 30 条。修改“每页”数字后点击“确定”才会应用。
- 分页器包含“第一页 / 上一页 / 相邻页码 / 下一页 / 最后一页 / 输入页码跳转”。
- 总览只保留“监控中的博主”和“已存视频”两张核心卡片。
- “待人工复核”不是未分类：系统已有建议分类，但证据强度不足。交互 Dashboard 的“视频分类”页以全部本地视频为数据范围；待人工复核只是一个筛选状态，可对任意视频确认系统分类或人工修正。
- “离线重新识别全部待复核”会使用当前规则重新处理待复核记录，不调用 YouTube API。未来新视频若证据不足，会自动进入同一复核队列。
- CLI 可执行 `python hub.py review-reclassify` 进行同样的离线重识别。


一个以 Codex 对话和 Python 为操作入口的 YouTube KOL 数据 Skill。**无需 Node.js / npm / Next.js**。

```text
Codex / 交互 Dashboard
        ↓
      Python
        ↓
      SQLite
        ↓
   Python 预聚合
        ↓
中文 Dashboard
```

## v0.4.0 表格与详情页

- 博主库、二次指标应用结果、视频分类、已保存发现记录统一支持筛选、排序和分页。
- v0.4.0 时默认每页 50 条；v0.5.0 起调整为默认每页 30 条，并需点击“确定”后应用。
- 博主发现的本次搜索结果与已保存发现记录默认按发现评分降序。
- 博主名称和视频名称可直接打开对应 YouTube 页面；博主库同时保留“查看详情”。
- 身份标签不再使用笼统的“竞品博主”，改为 LDCloud合作博主、RedFinger合作博主、VSPhone合作博主。

- 总览博主库默认按 UgPhone 视频数降序。
- 每个博主详情页对本地全部视频提供搜索、分类/品牌筛选、排序和分页；v0.5.0 起默认每页 30 条。
- 博主详情默认排序为 UgPhone 相关视频优先，同组按播放量降序。
- Skill、导出文件和 Dashboard 生成文件名统一使用英文/数字/ASCII 符号，不生成中文文件名。


## 推荐启动方式

覆盖旧版本后，先双击 `upgrade.cmd`。v2.1.0 会先使用 SQLite Backup API 对现有 `data/creator_hub.sqlite` 创建 `backups/pre_upgrade_*.sqlite` 一致性备份，再执行 Schema 迁移、自检、清理旧 Dashboard 并重新生成。

覆盖安装后，直接双击 Skill 根目录的 `start-dashboard.cmd`。它会启动本地 Python 交互服务并自动打开浏览器，搜索、抓取视频和获取联系方式等按钮均可直接使用。

如只需要查看已生成结果，可双击 `open-static-dashboard.cmd`。

## 两种 Dashboard 模式

### 静态只读

```powershell
python .\hub.py dashboard
```

打开 `output\dashboard\index.html`。适合查看数据。

### Python 交互模式

```powershell
python .\hub.py serve
```

默认打开 `http://127.0.0.1:8765/`。不需要 npm。本模式下“博主发现”页可以直接执行：

- YouTube 网页搜索（相关视频 → 博主：相关视频 → Creator）；
- API 搜索回退；
- 保存发现记录；
- 加入博主库；
- 抓取该 Creator 近 7 / 30 / 60 / 90 / 180 / 365 天、指定日期范围或全历史视频；
- 抓取公开联系方式与更强国家证据。

Windows 也可运行：

```cmd
scripts\open-interactive-dashboard.cmd
```

## 博主身份标签

身份由本地视频事实和系统分类自动聚合，不要求人工逐条确认：

- **合作过博主**：存在 UgPhone 视频；
- **未合作博主**：本地库中不存在 UgPhone 视频；
- **LDCloud / RedFinger / VSPhone 合作博主**：存在对应品牌视频；
- 人工修正只用于系统误判。

## 博主发现能力

### Web Search

`discover` 默认优先 YouTube 网页搜索，失败时可显式使用 API：

```powershell
python .\hub.py discover "Anime Expeditions" --search-source web --max-results 100
python .\hub.py discover "Anime Expeditions" --search-source api --lookback-days 7
python .\hub.py discover "Anime Expeditions" --from-date 2026-08-01 --to-date 2026-08-13 --target-country PH
```

搜索结果单独保存在 `discovery_hits`，**不会因为“被搜索到”就自动进入主博主库**。

### 国家证据

国家证据强度：

1. `youtube_about_popup`：公开 About 页；
2. `youtube_api`：YouTube API Country；
3. `metadata_keyword`：标题/频道简介元数据；
4. `language_hint`：语言弱证据。

### Contact Scraping

```powershell
python .\hub.py contact CHANNEL_ID
```

抓取公开邮箱、社交链接、网站、About 国家证据和联系能力分。若邮箱受 YouTube 验证限制，只记录 `gated / manual_action_required`，不绕过验证。

### 发现评分

保留 博主发现模块 的确定性 Pre-Score：

- 订阅量区间适配；
- 播放/订阅比；
- Engagement Rate；
- Comment Rate；
- Relative Velocity；
- A/B/C/D Opportunity Tier。

该评分只作为**未合作候选博主**的筛选参考，不写入 YouTube 客观事实层。原发现模块的 Final Score 公式也已保留在代码中，但它还需要真实的内容契合、受众契合、品牌安全三个深度分析输入；Data Hub 当前不会伪造这些值，因此发现页默认只展示 deterministic Pre-Score。

## 指定时间抓取 Creator 视频

```powershell
python .\hub.py capture CHANNEL_ID --days 7
python .\hub.py capture CHANNEL_ID --days 30
python .\hub.py capture CHANNEL_ID --days 180
python .\hub.py capture CHANNEL_ID --from-date 2026-01-01 --to-date 2026-06-30
python .\hub.py capture CHANNEL_ID --full-history
```

## 二次指标

初始状态不预置业务指标。交互模式将二次指标/规则配置持久化到 SQLite `app_settings`；浏览器 `cdh-secondary-metrics-v6` 仅作为迁移来源、静态模式回退和临时草稿缓存。

数据粒度严格分层：

1. **博主客观数据**：每位 Creator 已经只有一个值，例如订阅数、频道累计播放量、本地视频数、UgPhone/LDCloud/RedFinger/VSPhone 视频数量。它们直接用于筛选、排序、规则与比值，不再做二次聚合。
2. **博主标签**：每位 Creator 的布尔身份，例如合作过博主、未合作博主、LDCloud/RedFinger/VSPhone 合作博主。它们只用于“存在 / 不存在”筛选与规则，不参与 Average / Median / Sum。
3. **视频客观数据**：单条视频的播放量、点赞数、评论数、时长和视频条目。它们只能作为指标构建器的数据源。
4. **构建指标**：对某位 Creator 的视频数据按分类/品牌/时间筛选后执行 Count / Sum / Average / Median / Max / Min，得到每位 Creator 一个数值。
5. **比值指标**：以博主客观数据或已构建指标为分子/分母执行 A ÷ B。

典型构建流程：

```text
视频客观数据
  + 视频分类/品牌条件
  + 时间范围
  + Count/Sum/Average/Median/Max/Min
        ↓
博主级构建指标
        ↓
可与博主客观数据或另一构建指标组成比值
        ↓
规则 / 筛选 / 排序
```

例如“近90天 UgPhone 视频播放中位数”是构建指标；“UgPhone 视频播放中位数 ÷ 日常视频播放中位数”是比值指标；“订阅数”是博主客观数据；“合作过博主”是博主标签。

规则 / 标签构建器与应用结果筛选只在 Creator 粒度执行，可引用：博主客观数据、博主标签、构建指标、比值指标。第一条条件不带布尔连接，从第二条开始逐条选择 AND / OR / NOT。博主标签使用“存在 / 不存在”，不填写数字阈值。

视频构建指标支持全部、近7/30/60/90/180/365天和精确开始/结束日期；精确范围由 Python/SQLite 在交互模式下聚合，不把全量视频送进浏览器。

## 大数据模式

不会把几十万条原始视频塞进浏览器：

```text
SQLite
  ↓
Python预聚合
  ├─ Creator客观事实
  ├─ 品牌视频数量
  ├─ Creator布尔标签
  ├─ 视频聚合立方体
  └─ 必要Snapshot
  ↓
creator_facts.js + metric_base.js
```

博主详情页的 Snapshot 采用批量查询，避免逐视频 N+1。
## 发现评分说明

完整公式、阈值与 A/B/C/D 分档见 `docs/DISCOVERY_SCORING.md`。
