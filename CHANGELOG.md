# Changelog

## v1.2.1
- Fix Secondary Metrics sorting for constructed and ratio metrics (`findMetric` reference error).
- Harden Overview and Video Classification filter apply actions and show applied-filter feedback.
- Clean the generated Dashboard directory before rebuild during upgrade to prevent mixed-version assets.
- Disable HTTP caching in interactive Dashboard mode so regenerated JS/HTML is always loaded together.

## v1.2.0

- 修复【二次指标 → 应用结果 · 博主库】固定播放指标错误调用不存在的 `side()`，改为使用 `videoSpecValue()`，恢复 Creator 结果表渲染。
- 新增博主标签【疑似不再合作】：仅在历史存在 UgPhone 视频、当前 `monitoring_enabled=1`、最近同步数据仍处于优先级刷新周期 + 6 小时调度宽限内、且最近 UgPhone 视频已超过 30 天时触发。
- 【疑似不再合作】使用橙色背景，并与【合作过博主】历史身份并存；数据过期或未监控时不自动推断。
- 新标签进入总览、二次指标规则/筛选和博主发现身份筛选。
- 增加监控新鲜度与疑似停合作状态的回归检查。

## v1.1.0

- 身份标签视觉分层：UgPhone 合作绿色、未合作蓝色、LDCloud/RedFinger/VSPhone 竞品合作红色。
- 二次指标应用结果不再平铺全部可见指标；身份标签后固定展示 UgPhone / 全部 / 竞品视频播放量中位数，仅额外展示当前排序指标，并以深蓝表头突出当前排序列。
- 博主发现 A/B/C/D 分档分别使用绿/蓝/黄/红背景。
- 视频分类筛选新增播放量、点赞数、评论数、视频时长和发布时间，并支持数值/日期比较与 AND / OR / NOT。
- 所有表格表头统一水平、垂直居中。
- 监控优先级真正参与批量同步调度：高 6h、普通 24h、低 72h、归档 168h；未到期对象自动跳过，`sync --force` 可强制刷新。
- Windows 定时任务改为每 6 小时运行一次，让高优先级 6 小时周期可以实际生效。
- 数据状态文案明确为“XX优先级 / 监控中（或未监控）/ 计划周期 / 最近同步”。

## v1.0.0

- 重构二次指标数据模型，严格区分博主客观数据、博主标签与视频客观数据。
- 指标构建器只对视频客观数据执行 Count / Sum / Average / Median / Max / Min，并输出博主级构建指标。
- 博主客观数据与博主标签不再进入聚合器；博主标签使用“存在 / 不存在”判断。
- 比值指标改为引用博主客观数据或已构建指标，取消在比值内部直接定义两套视频聚合的错误结构。
- 规则与筛选统一使用博主客观数据、博主标签、构建指标、比值指标四类 Creator 级对象。
- 浏览器工作区升级到 `cdh-secondary-metrics-v6`，并提供 v0.x 配置迁移。
- 默认安装级二次指标配置升级为 `data/secondary_metrics_v4.json`，读取时兼容旧 `secondary_metrics_v3.json`。
- 版本升级至 v1.0.0。

## v0.9.3

- 修复【视频分类】首次载入时静态预览行未立即应用每页 30 条限制的问题。
- 页面 JavaScript 初始化后立即执行第一页分页，再检测交互服务并请求 SQLite 数据。
- 修复“顶部显示 1-30，但未操作底部分页前仍能看到大量视频”的显示错位。
- 版本升级至 v0.9.3。

## v0.9.2

- 所有 Creator 级国家/地区筛选统一改为“先选区域，再选该区域内国家/地区”的级联逻辑。
- 【博主发现】本次结果与已保存发现记录：国家筛选不再直接列出 249 个国家，而是先选东亚/东南亚/南亚/中亚/中东/欧洲/非洲/北美/拉美/巴西/大洋洲，再可选具体国家。
- 【总览 · 博主库】新增地理位置筛选类型，同样采用区域 → 国家/地区两级选择。
- 【二次指标 · 应用结果】新增地理位置筛选维度，同样采用区域 → 国家/地区两级选择；规则构建器仍保持四类指标体系不变。
- 搜索新博主本身的区域/国家选择继续保持级联，并支持中文国家名或 ISO 两字母代码直接锁定国家。
- 版本升级至 v0.9.2。

## v0.9.1

- Query Expansion 的每个长尾词新增独立勾选框：勾选表示本次搜索使用，取消勾选表示保留词条但本次不使用。
- 每个长尾词继续保留 × 删除按钮；删除后从当前语言对应 Query Pack 中移除。
- 新增词默认处于勾选状态；“恢复当前语言默认词”会恢复默认词并全部勾选。
- Query Pack 总开关继续控制整组是否参与搜索；实际执行条件为“Pack 已启用 AND 词条已勾选”。
- 旧 v0.9.0 浏览器词库状态会自动迁移，既有词条默认视为已勾选。
- 版本升级至 v0.9.1。

## v0.9.0

- 博主发现新增 Query Expansion：原关键词始终搜索一次，启用 Query Pack 后逐项执行“原关键词 + 长尾词”。
- 内置 6 个 Query Pack：Core、Farming / 成长收益、AFK / 云手机适配、Active Creator、Commercial / 评测比较、自定义。
- Query Pack 支持逐包启停、当前语言长尾词新增/删除与恢复默认；用户编辑状态保存在浏览器本地。
- 默认 English，并内置拉美西语、巴西葡语、泰语、越南语、印尼语、韩语、日语、繁体中文（台湾）。
- 新增 Query 预览、Query 数量与 API `search.list` quota 估算。
- 网页搜索实现 continuation token 深度加载；API 搜索继续使用 `nextPageToken`。
- 多 Query 搜索统一按 Creator 去重，同一 Creator 保留最高发现评分并记录 Query Coverage。
- 每个实际执行 Query 独立写入 `discovery_hits`，保持发现来源可追溯。
- CLI `discover` 新增可重复的 `--expand-term` 参数。

## v0.8.0

- 修正【视频分类】页面的数据范围：默认展示全部本地视频，不再默认限定为待人工复核队列。
- “待人工复核”改为复核状态筛选项；同时支持已人工复核、未人工复核、仅系统分类。
- 视频分类列表使用完整 SQLite 服务端分页，默认 30 条/页；静态 HTML 仅保留轻量预览。
- 分类列表同时显示系统分类、识别证据、复核状态、最终分类以及人工复核控件。
- 保留离线重新识别全部待复核功能，人工确认/修正继续写入审计记录。
- 新增 `/api/videos/classifications`，旧 `/api/review/list` 保留兼容。

# v0.7.0

- 博主发现发布时间快捷项将“近14天”替换为“近7天”，并新增精确开始/结束日期。搜索候选与抓取候选视频均支持指定日期范围。
- 二次指标中的视频时间窗口增加近7天与精确日期范围；精确日期由 Python/SQLite 服务端计算，不把全量视频加载到浏览器。
- 博主发现地区选择升级为“大洲/区域 → 国家/地区”两级选择，共覆盖 249 个 ISO alpha-2 国家/地区代码。可直接输入简体中文国家名或英文代码锁定对应国家。
- 产品区域固定为：东亚、东南亚、南亚、中亚、中东、欧洲、非洲、北美、拉美、巴西、大洋洲。
- 视频分类页统一为服务端全量分页，默认每页30条，并提供首页/上一页/相邻页码/下一页/末页、页码输入和跳转。
- 博主发现搜索完成后，发现记录立即写入 SQLite，并立即刷新“已保存的发现记录”，无需重建 Dashboard。
- 指标构建器重构为“输入类型：客观数据/聚合标签；输出类型：构建指标/比值指标”。比值指标直接由两个客观数据聚合定义构建。
- 聚合标签作为布尔标签筛选时不再要求填写数值；选择标签本身即表示“存在/为真”。
- 总览博主库、二次指标应用结果、博主详情、视频分类、博主发现本次结果与历史记录均支持多条件 AND / OR / NOT 组合筛选。
- 规则 / 标签构建器取消全局条件关系，从第二条条件开始逐条设置 AND / OR / NOT。
- 版本升级至 v0.7.0。

# v0.6.0

- 指标构建器不再把“构建指标”作为可选输入类型；输入类型调整为【客观数据 / 聚合标签 / 比值指标】。
- 选择客观数据或聚合标签并执行 Count / Sum / Average / Median / Max / Min 后，保存结果统一归类为【构建指标】。
- “已保存指标”更名为“已构建指标”。
- 规则 / 标签构建器改为两级级联选择：先选【客观数据 / 聚合标签 / 构建指标 / 比值指标】，再选择该类型的具体指标。
- 规则现在可以直接使用系统客观数据与0/1聚合标签，不要求先保存为指标。
- 浏览器指标工作区升级为 `cdh-secondary-metrics-v4`，并自动迁移 v3 规则中可识别的旧引用。
- “已保存的发现记录”删除单次搜索“排名”列、排序项与前端数据属性；数据库仍保留内部排名用于单次搜索追溯与代表命中选择。
- 版本升级至 v0.6.0。

# v0.5.0

- 所有分页区域默认每页 30 条；修改每页数量后必须点击“确定”才应用。
- 所有分页区域统一增加：首页、上一页、当前页相邻页码、下一页、最后一页、页码输入与跳转按钮。
- 总览删除“视频指标快照”和“待复核分类”两张卡片。
- 视频分类页升级为完整复核工作台：全量服务端分页读取待人工复核队列、确认系统分类、人工修正分类/品牌、审计记录。
- 新增“离线重新识别全部待复核”：使用当前分类规则重新处理旧导入及低置信度记录，不消耗 YouTube API。
- 未来新视频若分类证据不足，会自动进入同一待人工复核队列。
- 数据更新同步记录也统一使用新版分页。
- 版本升级至 v0.5.0。

# v0.4.0

- Skill、Dashboard 与自动导出文件名统一为英文/数字/ASCII 字符；移除中文命名的根目录启动器，改为 `start-dashboard.cmd` 与 `open-static-dashboard.cmd`；新增 `upgrade.cmd` 清理覆盖升级后遗留的旧文件名。
- 浏览器导出的二次指标配置改名为 `creator_data_hub_metrics_config.json`。
- 总览“博主库”默认按 UgPhone 视频数降序。
- “查看本地详情”统一改为“查看详情”。
- 每个博主详情页改为读取本地全部视频，不再受 5000 条静默截断限制。
- 博主详情页新增搜索、视频分类筛选、品牌筛选、排序、分页和自定义每页数量；默认每页 50 条。
- 博主详情页默认排序为 UgPhone 相关视频优先，同组按播放量降序。

# v0.3.0

- 博主发现的本次搜索结果与已保存发现记录默认按发现评分降序。
- 博主库、二次指标应用结果、视频分类、已保存发现记录统一增加筛选、排序和分页；默认每页 50 条，可自定义。
- 博主与视频名称增加直接跳转 YouTube 的超链接，同时保留本地博主详情入口。
- 身份标签删除通用“竞品博主”，改为 LDCloud合作博主、RedFinger合作博主、VSPhone合作博主。
- 已保存发现记录不再只截取最近 1000 条，静态看板可分页查看完整发现记录。

# Changelog

## 0.2.0 — 2026-08-13

- Dashboard 成品界面移除开发来源名称与制作过程提示。
- 旧版曾提供根目录快速启动器，用于启动交互模式并自动打开浏览器。
- `scripts/open-dashboard.cmd` 默认改为交互模式，并补充静态只读启动脚本。
- 静态博主发现页保留历史查看能力，操作按钮在只读模式下给出面向使用者的启动提示。
- Dashboard、CLI、配置与包元数据版本统一升级为 0.2.0。

## 0.1.0 — 2026-08-12

Initial release as a completely new Skill.

- 本地 Python control surface; removed runtime dependence on Node/npm/web server.
- SQLite fact store centered on Creator ID and Video ID.
- YouTube API discovery and objective channel/video enrichment.
- Full-history, incremental, metrics-only and channel-only refresh modes.
- Real channel/video historical metric snapshots.
- Machine label suggestions separated from human confirmations and audit history.
- UgPhone / competitor / daily / multi-brand / other-cloud-phone / pending label taxonomy.
- Offline import from `youtube-kol-gmv-intelligence V2` folders.
- Static no-server Dashboard with creator detail pages and snapshot sparklines.
- Secondary Metrics workspace reproducing the public demo pattern of metric construction + AND/OR rule application without contaminating the fact store.
- Browser-local metric/rule configurations with JSON export/import and Codex-installable default configurations.
- CSV/JSON/XLSX exports with fact/label separation.
- Windows helpers for install, API-key setup, opening Dashboard and optional scheduled sync.

### 0.1.0 maintenance revision — 2026-08-13

- Dashboard 全面简体中文化。
- 修正“已确认 UgPhone / 竞品”错误口径：默认采用 Skill 系统识别分类，人工标签仅作为可选纠错。
- 恢复并移植成熟 V2 的视频品牌识别逻辑；新增离线 `reclassify` 命令。
- Secondary Metrics 默认模板改用系统/最终分类，不再依赖人工确认。
- 大库模式改为 Python 预聚合，取消向浏览器导出全部视频数组。
- 新增 `creator_facts.js` + `metric_base.js` 聚合缓存。
- 博主详情页 Snapshot 改为按博主批量查询，消除逐视频 N+1 查询。
- Secondary Metrics 结果表固定显示订阅数、频道累计播放量、已存视频数、最近发布，并显示聚合指标。
- 新增 `.cmd` 打开/安装助手，绕过部分 Windows PowerShell 未签名脚本限制。


### 0.1.0 interaction/discovery revision — 2026-08-13

- “博主发现”页新增真实搜索框、相关视频 → 博主“相关视频 → Creator”搜索流程与 API 回退。
- 新增无需 npm 的 Python 交互 Dashboard：`python hub.py serve`；静态 `file://` 看板继续只读。
- 搜索结果持久化到 `discovery_hits`，与正式 `creators` 博主库分离。
- 新增 30/60/90/180/365 天、指定日期后、全历史视频抓取并入库操作。
- 自动生成“合作过博主 / 未合作博主 / 竞品博主 / LDCloud / RedFinger / VSPhone”等关系身份。
- 恢复 博主发现模块 分层国家证据：About > API > 元数据关键词 > 语言提示。
- 恢复公开 Contact Scraping：邮箱、社交链接、网站、联系能力分；不绕过验证码/邮箱验证。
- 恢复 deterministic discovery pre-score 与 A/B/C/D Opportunity Tier，并保留原 Final Score 公式供未来真实深度分析输入使用；当前不伪造 MiniMax 的内容契合/受众契合/品牌安全输入。
- 二次指标工作区清空预置指标，切换到全新配置键；指标类型统一为“客观数据 / 聚合标签 / 构建指标 / 比值指标”。
- 总览博主库与二次指标结果表均加入“指标类别 → 具体指标 → 运算符 → 值”筛选。
