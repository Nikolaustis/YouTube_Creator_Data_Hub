# Changelog

## v3.9.0

- Dashboard 表格改为“结论优先”布局：默认主表使用 `width:100% + table-layout:fixed`，不再插入横向滚动轴或顶部横向滚动条；长标题、博主名和说明文本按列宽合理换行。
- 博主库默认列从 12 列收敛为 10 列，移除国家证据、最近发布、竞品细分等常驻过程/次要字段；国家列只显示最终国家结果，详细来源继续保留在 Inspector/导出。
- 身份标签改为逐标签单独一行、单元格居中并限制在当前列内，修复标签侵入后续列的问题。
- 视频分类表继续使用“筛选/排序字段按需显列”，但主表采用固定列预算；视频标题允许多行换行，行内复核控件收拢为“复核”下拉菜单。
- 【博主发现】本次搜索与已保存博主的批量动作统一按“处理状态 / 入库与抓取 / 监控 / 优先级 / 更多”分组；行级联系方式、加入与抓取操作也收拢为“操作”菜单。
- 【已保存的发现记录 · 博主】主表从过程型宽表收敛为 9 个结论列：博主、订阅、国家、发现评分、Query Coverage、命中视频数、最佳命中视频与状态；原关键词、关键词来源、Discovery Run、首次/重复发现、国家证据等移入详情 Inspector。
- 【已保存的发现记录 · 视频命中】移除实际 Query 和国家证据等常驻过程字段，保留博主、订阅、国家、视频、播放量、评分、状态与发现时间。
- 新增发现详情 Inspector 入口，过程/审计数据不删除，只从主表退到按需查看层。
- Schema 保持 15；本版本不修改既有 SQLite 事实。

## v3.8.0

- SmartTable 宽表改为合理最小列宽 + `width:max-content` + 横向滚动，新增顶部横向滚动控制与选择/实体 Sticky 列，解决博主库、已保存发现记录等宽表被强行压缩的问题。
- Job Center 新增最小化、关闭与单任务 dismiss；关闭/隐藏仅影响前端，不终止后台任务，`job_runs` 持久历史继续保留。
- AI Provider 对 read timeout、连接异常、429、500/502/503/504 等瞬时故障最多自动重试两次，并通过 Job Progress 显示重试状态。
- AI Search 流程调整为先执行低成本预过滤，再将 Profile Budget 用于更有潜力的 Creator；Profile 上限显式写入 Result Set 元数据。
- 修复长期制作 Continuity Gate：以频道级主题上下文确认基础主题后，近期 AFK/Auto Farm/Overnight/Multi-account 等场景视频可计入连续性，不再要求每条视频标题重复完整游戏名。
- 未完成 Profile 的候选改为 `Pending Verification / 待验证`，不计作过滤失败且不能进入正式高适配结果；XLSX 增加 Pre-filter Candidates、Profile Budget、Pending Verification。
- Query Planner Prompt 升级至 v6；Schema 保持 15。

## v3.7.0

- 后台任务状态持久化到 `job_runs`；Job Center 在任意 Dashboard 页面启动时自动恢复活动/最近任务，浏览器刷新与页面切换不再丢失进度。服务重启无法续跑的任务明确标记为中断。
- 新增 `creator_availability_overrides` 与审计表：监控健康支持人工确认频道终止/删除/失效、无公开视频、历史视频清空、长期停更及监控策略，且保留系统原始检测。
- AI Query Planner 升级 v5，直接接受 Query Budget，输出最终执行 Query；去除二次大规模重组并修复重复主题 Query。
- “长期制作”从偏好加分改为硬约束，默认最近50条中相关内容 ≥5 且覆盖 ≥3个月；未完成 Profile 的候选不进入正式长期 Creator Result Set。
- AI Result Set 新增内容场景适配、连续性、品牌安全、体量适配、Query Coverage 五维评分及 A/B/C/D 综合等级。
- Creator sourcing 默认剔除云手机官方/产品账号、游戏官方/开发者账号与明确官方预告来源，以及脚本/外挂/漏洞为主的频道；过滤类别、品牌安全标记进入 Result Set 与 XLSX。
- Schema 升至 15，新增 `job_runs`、`creator_availability_overrides`、`creator_availability_override_audit`。

## v3.6.0

- 新增 Creator 商业表现事实层 `creator_business_metrics`：保存 GMV、拉新等指标以及周期、币种、Campaign、Region、来源、导入批次、捕获时间和原始行追溯。
- 【数据更新】新增商业表现 CSV/XLSX/XLSM 导入；按 Channel ID / Channel URL / Handle / 唯一精确频道名确定性匹配，未匹配行只报告不猜测。`import-v2` 同时扫描旧商业表格，并新增 `hub.py import-business`。
- 博主库新增 GMV/拉新摘要和排序，GMV/拉新成为 Creator Fact，可与 YouTube 客观数据、品牌内容、身份标签组合用于二次指标。
- 新增 `saved_views` 与 Saved Views 前端组件，博主库、视频分类可以保存/恢复筛选和排序视图。
- 新增统一 Creator Inspector 右侧抽屉；博主库“数据状态”改为摘要 + 按需详情，商业表现与数据新鲜度在抽屉展开。
- 博主库批量按钮重组为 Context Action Bar（监控 / 优先级 / 标签），保留既有动作但降低视觉噪声。
- Creator/Video 名称在主要表格中统一使用 YouTube 外链；表格采用紧凑单行表头、文本截断和按需列显示，视频分类继续执行“筛选/排序字段自动显列 + 蓝色表头”。
- Schema 升至 14，新增 `creator_business_metrics`、`saved_views`；升级不覆盖既有 Creator/Video/人工复核数据。

## v3.5.0

- 新增长耗时任务进度中心：离线重分类、博主发现、AI 搜索 Agent、批量抓取/同步等可在 Dashboard 固定进度卡中看到阶段、当前/总数、百分比与耗时，不再只有不醒目的等待文字。
- 统一表格可解释性：筛选/排序使用的指标必须在表格中可见，并以蓝色表头突出；视频分类主表默认以“有效分类（人工优先）”作为业务分类；“系统原始分类”默认隐藏，仅在筛选/排序该字段或进行人工/系统不一致审计时自动显列并高亮。
- 新增 Creator 频道可用性生命周期：将频道终止/删除与普通同步失败分离。只有公开 YouTube 页面明确给出社区准则或版权终止信息时才记录具体终止原因；确认终止/删除后停止无意义自动重试，但保留全部本地历史数据。
- 监控健康拆分为“频道状态 / 同步健康 / 监控状态”，支持单条/批量重新检测频道状态。
- Schema 升级至 13，仅增加频道可用性状态字段，不改动既有 Creator/Video 数据口径。


## v3.4.0

- 将“有效分类（人工优先）”确立为视频分类的业务默认口径：筛选、排序、统计、二次指标和导出均优先使用人工分类；系统原始分类保留作审计，并新增分类来源及人工/系统不一致筛选。
- 修复【博主发现 → 已保存的发现记录】启动时先渲染全部历史 DOM、随后才分页的问题：静态兜底预览限制为 30 条，交互模式优先读取第一页 API 数据。
- 【数据更新 → 监控健康】博主名称增加 YouTube 主页链接；明确六种健康状态及原因；新增单条/批量立即同步，支持增量、仅刷新视频指标、仅刷新频道和全历史。
- AI 搜索 Agent 从“AI 只生成 Query”升级为“Query Planning + Fit Criteria + YouTube Discovery + 最近上传抽样 + Objective Fit Filter/Ranking”。
- Planner v4 把订阅范围、基础主题匹配、搜索场景词、排除词和长期制作偏好保存为结构化 Fit Criteria；重要搜索概念优先保证进入实际 Query。
- 对未明确数字的“中小体量”默认采用 ≤100,000 订阅硬约束，并把该默认明确写入 Planner Notes、Result Set 和导出，不作为隐藏规则。
- AI Agent 对最多 100 个候选 Creator 轻量抽样最近最多 50 条上传，不把这些候选视频写入本地库；根据主题命中、目标要求词、连续制作月份、Query Coverage 与订阅约束进行过滤/评分。
- AI Result Set 区分本地“未采集”与真实 0；结果表新增目标适配分/等级/证据、最近样本相关视频与覆盖月份。
- AI Result Set XLSX 补齐原始搜索要求、语言/地区/国家/时间范围、Query 上限、Planner Strategy/Fit Criteria、计划/实际 Query、原始/保留/过滤数量、AI Provider/Model/Prompt Version，并新增 Query Details 工作表。
- Schema 保持 12；无需迁移业务数据。

## v3.3.2

- 分类器将 `AFK / Auto Farm / 24/7 / multi-instance` 从“云手机实体证据”拆为“使用场景/发现信号”；这些词单独出现时不再触发【其他云手机】。
- 新增 `cloud_entity_terms` 与 `use_case_terms` 分层；只有明确云手机实体词或已知品牌证据才能进入云手机分类。
- 已知品牌弱证据不再错误兜底为【其他云手机】，而是进入【待复核】。
- 官方品牌域名 + 产品/登录/下载/推广路径可升级为品牌 `probable` 证据；覆盖 `cloudemulator.net/app/sign-in` 等 RedFinger 场景。
- 【多品牌云手机】扩展为任意两个及以上强识别云手机品牌，不再要求必须包含 UgPhone。
- Dashboard【视频分类】新增“离线重新识别全部系统分类”，可修复旧规则已经稳定写入的历史系统分类；0 YouTube API 调用，并保留人工修正。
- 系统分类单元格显示分类规则版本，并在证据列保留 `use_case_not_cloud_evidence:*` / `cloud_entity_term:*` 审计原因。

## v3.3.1

- 修复已配置 `CREATOR_HUB_AI_API_KEY` 的 Windows 环境中运行 `upgrade.cmd` 时，Mock AI 自检错误读取真实 API Key 并触发 AssertionError 的问题。
- `mock` / `disabled` 协议现在明确不读取、不暴露任何真实 AI API Key；切换回在线协议时原有 Key 不受影响。
- Self-check 新增“机器已预先配置 AI Key”回归场景，确保升级检查不再依赖用户宿主环境的密钥状态。
- Schema 保持 12；无需恢复数据库备份，也没有数据迁移变化。

## v3.3.0

- 统一 Creator / Video 的 Action Parity：只要表格支持多选，单条可执行动作必须有对应批量入口；博主发现与已保存发现博主新增按时间范围批量抓取并入库。
- 批量抓取支持近7/30/60/90/180/365天、指定日期范围与“全历史（最多10,000条）”；后端逐 Creator 隔离失败，不在循环中重建 Dashboard。
- 交互 Dashboard 新增实时事实/统计/指标接口；抓取、入库、同步状态、人工复核、标签与工作流等写库后，总览和二次指标直接重新读取 SQLite，无需重启服务或执行 upgrade。
- 总览动态刷新 Creator Facts、Dashboard Stats 与 Secondary Metric Cubes；二次指标页面在数据变更/重新聚焦时刷新事实与指标立方体。
- 监控健康表补齐多选、当前页全选、全部结果全选和批量恢复异常同步，使单条“恢复同步”具备批量等价操作。
- 批量开启监控/设置优先级对已入库 Creator 仅更新 SQLite，只有发现结果尚未入库时才请求频道信息，避免无意义消耗 YouTube API 配额。
- Schema 保持 12；本次不新增业务表，不改变现有数据库事实。

## v3.2.0

- AI 检索统一引入 Result Set：Ask Hub 与 AI 搜索 Agent 每次执行均自动留档，可重新打开、筛选、排序、30条/页分页和按当前条件导出 XLSX。
- 新增 `ai_result_sets` / `ai_result_items`，Schema 升至 12；AI 搜索 Result Set 同时关联 AI Run 与 Discovery Run。
- `ai_runs` 新增输入/结果快照与 cache-hit 标记；即使命中本地 AI 缓存，每次用户执行仍形成独立调用记录。
- Ask Hub 将业务结果上限与 Dashboard 分页拆开；除非用户明确要求 Top N，否则本地查询返回全部匹配 Creator，再按30条/页展示。
- Creator Brief 改为本地 Creator 搜索候选 + 单选锁定；Creator 对比改为候选搜索 + 2–5个标签式锁定。
- “搜索目标”重命名为“AI 搜索要求（可选）”，并补充区域、国家等结构化硬约束。
- AI 结果集支持跨页批量选择语义和后续 Creator 批量操作接口。
- Creator Brief、Creator 对比、七日 Brief 均可导出当前分析结果；分析结果继续保留在 AI Run / Finding 体系。

## v3.1.0

- Replace provider/model presets with protocol-oriented AI configuration: protocol + custom Base URL + local API Key + free-form model ID.
- Add protocol adapters for OpenAI Responses, OpenAI-compatible Chat Completions, Anthropic Messages, Gemini generateContent and Mock without adding a mandatory AI SDK dependency.
- Add Dashboard API-key entry/clear, model discovery and connection test; API keys are persisted only in a provider-neutral local secret slot and never in SQLite/browser storage.
- Make `setup-ai.cmd` provider-neutral and allow manual model IDs even when a remote model-list endpoint is unavailable.
- Upgrade AI Query Planner to AI Search Agent: planned queries are executed through the existing YouTube Data API discovery pipeline and persist normal discovery run/creator/video records.
- Add `ai-models`, `ai-test` and `ai-query-search` CLI commands while retaining plan-only diagnostics.
- Preserve v3.0 persisted provider settings during migration to the new protocol field. Schema remains 11.

## v3.0.0

- Add an optional AI Copilot layer while preserving a complete AI-OFF product path. AI is disabled by default and the core dependency set does not require an AI SDK.
- Add Ask Hub: AI converts natural language into an allowlisted read-only Creator query plan; SQLite executes the plan locally.
- Add evidence-grounded Creator Brief, 2-5 Creator comparison, discovery Query Planner and seven-day Creator Intelligence Brief.
- Add provider abstraction (`disabled` / `mock` / `openai`), request caching, daily local request soft limit and prompt-version tracking.
- Add `ai_runs`, `ai_findings`, `ai_evidence`, `ai_feedback` and `ai_cache`; AI findings stay separate from deterministic facts, scores and human labels.
- Add `setup-ai.cmd`, `scripts/set-ai-key.cmd`, `docs/AI.md`, AI Dashboard page and CLI commands.
- OpenAI mode reads `OPENAI_API_KEY` only from the environment and does not persist it in SQLite/browser state; remote response storage is off by default.
- Bump SQLite Schema to 11; existing Creator/Video/Discovery/Label data remains unchanged.


## v2.1.0

- 【数据更新 → 监控健康】改为标准分页表格，默认每页 30 条，并提供页码、跳转和每页数量设置。
- 所有支持批量操作的表格统一增加“勾选当前页 / 全选全部结果 / 清空选择”：总览博主库、视频分类、本次发现博主、已保存发现博主。
- 跨页选择会保留翻页后的勾选状态；筛选条件变化时会主动清空旧选择，避免把旧筛选范围误用于新结果。
- 视频分类的“全选全部结果”使用服务端 all-matching 选择器，不把 50 万+ Video ID 全部传到浏览器；允许在当前筛选范围内执行批量确认/修改/清除。
- 已保存发现博主增加服务端跨页 ID 解析；本次搜索结果与总览则直接对当前完整筛选结果执行全选。
- 优化批量视频复核写入，单次事务分块处理并保留人工复核审计，避免跨页大批量操作逐视频反复打开 SQLite 连接。
- SQLite Schema 保持 10；不改变现有业务数据。

## v2.0.1

- Windows batch compatibility hotfix: normalize every `.cmd` launcher to CRLF line endings and ASCII-only command text.
- Remove `chcp 65001` from batch launchers; Python/PowerShell handle their own Unicode output instead of changing CMD parsing mode mid-script.
- Simplify `upgrade.cmd` to avoid non-ASCII legacy filenames during critical migration steps.
- Extend `SELF_CHECK` to reject LF-only or non-ASCII `.cmd` files in future release packages.
- No schema or business-data changes relative to v2.0.0; Schema remains 10.

## v2.0.0

- Persist secondary-metric/rule configuration and Query Expansion profiles in SQLite `app_settings`; use browser storage only as a fallback/cache.
- Add database health, SQLite backup/restore, backup registry and maintenance audit records.
- Add Creator-level monitoring health, typed sync errors, consecutive failure counters, next-sync/retry timestamps, exponential retry backoff and suspension after repeated failures.
- Add Snapshot lifecycle compaction: full <=30d, daily 31–180d, weekly 181–730d, monthly thereafter; scheduled sync performs auto maintenance no more than weekly.
- Add Discovery workflow states (unreviewed/interested/to-contact/added/defer/excluded), workflow audit, exclusion hiding, first/repeat discovery and discovery-history summaries.
- Add batch Creator and batch classification actions.
- Extend Secondary Metrics with groups, descriptions, timestamps, dependency display and delete protection.
- Add unified freshness timestamps for channel facts, video metrics, classification, contacts, discovery and complete sync.
- Extend Data Update Dashboard with monitoring health, backup/restore and Snapshot maintenance controls.
- Bump SQLite schema to 10; migrations preserve existing objective data, discovery hits and human labels.

## v1.6.0

- Make the Secondary Metrics active rule a transient viewing condition instead of a silently persistent localStorage filter.
- Rename the result reset action to “清除全部条件” and clear filters, active rule, and search together; show active conditions/rule in the result summary.
- In interactive Video Classification mode, hide the 300-row static preview while connecting and load the real SQLite first page directly; static preview pagination is now only used in read-only mode.
- Split classification KPI totals from paged list queries so every page/filter/sort no longer repeats the full global aggregation.
- Use direct `COUNT(videos)` for the unfiltered total and only add classification/Creator joins to COUNT queries when the active conditions need them.
- Bump SQLite schema to 5 and add indexes for global publish-time ordering, system role/confidence, and human role.

## v1.5.0

- Expand the sidebar section navigation from Discovery-only to all five top-level Dashboard pages.
- Add stable anchors for Overview, Secondary Metrics, Video Classification, Discovery, and Data Update sections; section navigation supports smooth scroll, active-section tracking, and URL hashes.
- Improve first-run `setup.cmd` with a post-install next-step menu for interactive/static Dashboard, monitoring task installation, and online API-key validation.
- Add `scripts/python-run.cmd` with `python` -> `py -3` fallback and route the primary CMD launchers / scheduled sync through the same resolver.
- Extend `doctor` with the actual Python executable path and local port 8765 availability diagnostics.

## v1.4.0

- 【博主发现】侧边栏新增四项页面内二级导航，支持锚点直达、平滑滚动与当前区块自动高亮。
- Schema 升级至 4，`discovery_runs` 新增 `base_query_source`，区分精确记录与历史推断。
- 移除 v1.3.0 单一 `legacy-history / Legacy Discovery` 派生模型；保留全部原始 `discovery_hits`，仅重建历史派生 Run 与 Creator 结果。
- 基于 Query Pack 已知长尾词和历史实际 Query 前缀恢复旧基础关键词，并按“推断原关键词 × Creator”重新聚合。
- 旧历史聚合使用稳定 `legacy-keyword-*` Run ID，并明确标记【历史推断】，不伪造旧搜索时间批次。
- 博主级发现 Dashboard 与 XLSX 增加【关键词来源】，修复【原关键词】列全部为 `Legacy Discovery`。

## v1.3.0

- 新增首次安装入口 `setup.cmd`、CMD 版 API Key 配置入口和增强版 `doctor / doctor --online`。
- Dashboard 顶部显示当前运行模式；明确区分静态只读与 `127.0.0.1:8765` 本地交互模式。
- 核心表格增加 XLSX 导出；交互模式按当前筛选与排序导出全部命中结果，而不是仅当前页。
- 博主发现新增 `discovery_runs` 搜索批次和 `discovery_creator_results` 博主级结果；`discovery_hits` 继续保存视频命中证据。
- 新搜索完成后同时即时保存博主级结果和视频级命中；历史旧数据完整保留，并以 `Legacy Discovery` 方式生成博主级聚合而不臆造旧搜索批次。
- 【博主发现】分别提供“博主记录”和“视频命中记录”的筛选、分页与 XLSX 导出。

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
