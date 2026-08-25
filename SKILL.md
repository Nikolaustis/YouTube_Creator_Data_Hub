---
name: youtube-creator-data-hub
description: 本地 Python YouTube creator discovery and monitoring with related-video-to-creator video-to-creator web search, SQLite fact storage, objective channel/video metrics, snapshots, deterministic UgPhone/competitor classification, automatic creator relationship labels, country evidence, public contact scraping, discovery pre-scoring, configurable time-window capture, Chinese Dashboard, and user-defined secondary metrics. No Node/npm is required.
version: 3.10.0
---

# YouTube 博主数据中心


## v3.10.0 Core Architecture

- **三级 Field Taxonomy 是唯一字段目录**：一级固定为客观数据 / 博主标签 / 构建指标 / 比值指标；客观数据二级含基础信息、地理位置、频道规模、内容与品牌、内容表现、商业数据、Discovery/AI、数据健康、视频客观数据；构建/比值指标二级直接读取用户指标组；三级为稳定 field ID。
- **Job Engine**：后台批任务必须走持久队列；YouTube-heavy 与 AI-heavy 默认各最多 1 个并发，Local 默认 2 个；支持 cancel/retry/checkpoint，只有声明 resumable 的任务才允许服务重启后续跑。
- **Migration Runner**：Schema 变更必须注册 migration 并写入 `schema_migrations`；V3.10 Schema=17。不得再把新的结构迁移只写成散落在 `init_db()` 的临时 SQL。
- **API v1**：新 Workbench/API 消费者优先使用 `/api/v1`；响应为 `{ok,data,meta,api_version}`，错误为 `{ok:false,error:{code,message},api_version}`。Legacy `/api/*` 仅用于兼容当前 Dashboard。
- **Run Specification**：可复现实验必须保存请求、最终结构化 Plan、实际 Query、预算、模型/Prompt版本；Clone & Re-run 不得重新规划冻结条件。
- **Data Contract**：统一区分 `fact / derived / ai / human`，业务有效值按 `human > ai > derived > fact` 解析；旧目的表仍保留，但新增判断必须逐步发布 assertion。
- **Intelligence V3**：Brief 的数值/KPI必须确定性生成；去重 AI 候选、Workflow audit、GMV快照变化、同步风险与品牌安全进入 Intelligence Context，LLM只负责解释与行动建议。
- **Service 边界**：Run / Intelligence / Data Contract 已独立 service；CreatorHub facade 保持兼容。新增跨领域能力不得继续直接堆入单个 God Object。

## v3.9.4 配置目录与监控健康规则

- 已构建指标、规则列表必须提供搜索、分组、排序和分页；默认 30 条/页。分组是业务组织字段，可批量移动并通过输入新名称即时创建。
- 监控健康必须提供搜索、结构化筛选和排序；筛选/排序字段对应表头应高亮。
- 监控健康主表只展示有效频道状态与来源、同步健康等结论。系统原始状态、原因、内容状态、监控策略、错误证据和检测历史进入详情 Inspector。
- 所有选择列必须完整显示“选择”，不得省略为“选…”；视觉回归必须覆盖监控健康和二次指标页面。

## v3.9.3 GMV 固定 USD 口径

- **GMV 是 UgPhone 后台 USD 累计快照**：`metric_value` 即 USD 金额，按 `captured_at` 保存时间点累计值；不同采集时间的快照不得相加。
- **禁止 GMV 汇率换算**：不得根据 Creator 国家、币种列或公开汇率重新解释 GMV；Dashboard 不提供 FX 状态、币种补全或在线换算入口。
- **升级自动修复旧 GMV**：所有历史 `gmv` 行统一回填 `currency=USD`、`metric_value_usd=metric_value`，旧的 missing/unresolved FX 状态对 GMV 不再有业务意义。
- **任务中心必须固定尺寸并可清理 UI**：大量已结束任务只能在内部滚动；清除已完成/失败只 dismiss 卡片，不删除 `job_runs`。
- **AI Search 必须区分主题适配与使用场景连续性**：主题视频证明 Creator 与目标游戏/主题的关系；场景视频证明 AFK/自动刷取/多账号等云手机适配行为，二者不得混为同一连续性指标。
- **主表只展示结论**：综合适配、关键证据、场景代表视频、本地状态和工作流；完整维度、主题代表视频、Discovery 命中和运行信息进入 Inspector/导出。
- **Query 漏斗必须可审计**：每条 Query 保存视频命中、Creator 命中、原始候选、最终保留、风险候选。
- **Weekly Brief 的数字必须确定性生成**：AI 不得自行发明或重述冲突数字；首次发现、Discovery 命中、同步任务、卡住任务、AI候选池等指标由本地 SQL 计算。
- Schema 保持 **16**。

## v3.9.1 商业快照、USD 标准化与 AI sourcing 精修

- **商业后台导入必须按 point-in-time total snapshot 解释**：GMV 等累计值锁定在 `captured_at`，历史快照只用于追溯；业务 headline 只使用每个指标最新快照，不跨采集时间累加。
- **历史说明（已被 v3.9.3 覆盖）**：v3.9.1 的通用 FX 规则不再适用于 GMV；GMV 从 v3.9.3 起固定按后台 USD 口径。
- **Creator 内容语言进入 AI Fit Criteria**：Language 不只控制 Query；近期标题有效样本充足时按目标语言占比执行。
- **场景词必须贴近社区表达**：多开/多账号包含 alt/alts/multi-client 等真实表达。
- **风险候选单独标识**：非主要外挂频道但存在 Script/Hack 风险信号时进入风险池，不与普通推荐候选同语义；XLSX 输出独立 Risk Candidates Sheet。
- **Discovery 证据与 Fit 证据分离**：保存最佳搜索命中视频和代表性适配视频。
- **Planner Strategy 由实际 Fit Criteria 生成**：不得让模型自由描述与最终硬约束冲突的策略。Prompt 版本为 `query-planner-v7`。
- **发布必须跑视觉回归**：`scripts/visual_regression.py --strict` 检查主要页面在常见分辨率/125%缩放下没有非预期横向滚动与子元素跨单元格溢出。
- Schema 升至 **16**。

## v3.9.0 结论优先 UI 与详情层

- **主表只展示决策结论**：来源、Run ID、搜索批次、关键词来源、首次/重复发现、规则版本等过程/审计信息默认进入 Inspector 或导出，不得为了“信息完整”常驻主表。
- **默认主表不得依赖横向滚动**：采用固定列预算、`width:100%` 与合理换行；Creator/Video 名称允许多行，禁止文本跨列覆盖。
- **身份标签纵向堆叠**：一个标签一行、单元格内居中、不可溢出到后一列。
- **同类动作必须分组**：批量操作按处理状态、入库与抓取、监控、优先级、更多等语义进入 dropdown；能力不删除，但不得同权重按钮平铺。
- 【已保存的发现记录 · 博主】默认使用结论列；Discovery Run、原关键词/来源、发现次数、首次/最近发现、国家证据、完整命中 Query 放入发现详情 Inspector。
- 【视频分类】继续执行有效分类（人工优先）和筛选/排序蓝色高亮规则；长视频标题必须换行，行级复核操作收拢。
- Schema 保持 **15**。

## v3.8.0 SmartTable、可控 Job Center 与 Continuity Gate 修正

- **宽表必须保持可读列宽而不是压缩进视口**：所有 `.table-wrap > table` 由 SmartTable 增强，使用横向滚动、字段最小宽度和顶部滚动控制；选择列与核心 Creator/Video 实体列可 Sticky。不得通过逐字换行来“塞下”宽表。
- **Job Center 是可隐藏但任务不可被误终止的全局组件**：必须提供最小化、关闭和单任务 dismiss。最小化/关闭只改变 UI；后台 Job 与 `job_runs` 历史继续执行/保留。
- **AI Planner 瞬时故障要自动恢复**：read timeout、连接重置、429 与常见 5xx 最多重试两次，并把重试阶段写入 Job Progress。
- **Creator Profile 前先做低成本预过滤**：先使用 Discovery 已有事实剔除明显超体量、官方来源、脚本外挂、用户排除项及明显主题噪声，再消耗 playlist/profile 请求。Profile Budget 必须显式记录。
- **连续性采用频道级主题上下文**：基础主题通过频道名、最佳命中与最近上传整体确认；确认后，AFK/Auto Farm/Overnight/Multi-account 等相关近期视频可计入连续性，禁止要求每条标题都重复完整游戏名称。
- **未 Profile 不是不合格**：预算不足或 Profile 请求失败的候选进入 `Pending Verification / 待验证`，不计为过滤失败，也不得进入正式高适配 Result Set。
- Query Planner Prompt 为 **query-planner-v6**；Schema 保持 **15**。

## v3.7.0 持久任务中心、人工频道生命周期与 Sourcing 安全门槛

- **Job Center 必须跨页面连续可见**：长任务状态写入 `job_runs`，每个页面启动后自动恢复正在运行和最近任务；服务重启造成的未完成线程必须标记中断，不得继续显示“运行中”。
- **频道状态采用系统检测 + 人工覆盖**：系统 `creators.availability_*` 永久保留原始检测；`creator_availability_overrides` 保存人工频道状态、内容状态、监控策略、备注和操作者，`creator_availability_override_audit` 保存变更历史。
- 人工可确认：社区准则终止、版权终止、已删除/不存在、失效/未知不可用、暂时不可用；内容状态可标记无公开视频、历史视频已清空、长期停更；终止/停止策略不得删除本地历史。
- **AI Query Budget 由 Planner 直接控制**：Planner v5 最多返回用户指定的 Max Queries 最终执行列表；确定性层仅去重和修复重复主题文本，不另造大规模 Query 列表。
- **长期制作是 Gate，不是加分项**：用户要求长期/持续/经常制作时，默认最近最多50条上传中目标内容 ≥5 且覆盖 ≥3个月；未 Profile 候选不得进入正式高适配 Result Set。
- **AI Fit 必须拆维度**：内容场景适配、连续性、品牌安全、体量适配、Query Coverage 独立输出，综合分只做汇总。
- **Creator sourcing 默认品牌安全剔除**：云手机官方/产品频道、游戏官方/开发者频道或明确官方预告来源，以及以 Script/Hack/Cheat/Exploit/Executor/Keyless/Dupe 等为主的脚本外挂频道，不进入正式 Creator Result Set；除非用户明确要求包含。
- Schema 升至 **15**，新增 `job_runs`、`creator_availability_overrides`、`creator_availability_override_audit`；不得覆盖既有事实、商业指标或人工视频复核。

## v3.6.0 商业表现事实层与产品组件基础

- **商业表现是独立事实层，不得塞回 Creator 主表**：`creator_business_metrics` 保存 `metric_key/value`、周期、币种、Campaign、Region、来源、导入批次、捕获时间和原始行追溯；当前标准键包括 `gmv`、`new_users`、`orders`、`revenue`、`commission`、`cost`。
- 【数据更新 → 商业表现数据】支持 CSV/XLSX/XLSM；只用确定性身份匹配（Channel ID / Channel URL / 唯一 Handle / 唯一精确频道名）。未匹配行必须报告，禁止模糊猜测写库。
- 旧 V2 导入会额外扫描商业表格；也提供 CLI `import-business`。同一文件/Sheet/行/指标重复导入应 upsert，不产生重复记录。
- 博主库必须显示紧凑的 GMV/拉新摘要；GMV/拉新进入 Creator Fact，可用于全库筛选/排序与二次指标。详细商业数据、同步状态、新鲜度等放入右侧 Inspector。
- **Entity Link 是全局规则**：表格中出现 Creator/Video 名称时优先提供 YouTube 外链；本地详情作为次级入口。
- **Context Action Bar 是全局操作设计**：不删除批量能力，但将相近动作按监控、优先级、标签、数据等语义分组，避免同权重按钮平铺。
- **主表摘要 + Inspector**：主表只保留做判断所需核心字段；详细状态、证据、来源、历史按需进入右侧抽屉。
- **Saved Views**：可持久化常用筛选/排序/分页状态；当前至少覆盖博主库与视频分类，为后续 Workbench 多 Tab 形态提供基础。
- Schema 升至 **14**，新增 `creator_business_metrics` 和 `saved_views`；不得覆盖现有 SQLite 事实或人工复核。

## v3.5.0 可见任务进度、表格可解释性与 Creator 可用性生命周期

- **Long-running Job Visibility 是全局规则**：博主发现、抓取并入库、同步、离线重分类、批量复核、AI 搜索/Ask Hub/Brief/Compare/七日简报等长耗时操作通过后台 Job 执行；Dashboard 固定显示阶段、消息、进度、已处理/总量和耗时，完成/失败使用明确状态色。
- **Filter/Sort Explainability 是全局规则**：任何参与当前筛选或排序的指标必须出现在对应表格中；相关表头统一以蓝色背景高亮，排序字段同时保留方向语义。二次指标的非默认筛选指标会动态加列。
- 【视频分类】主表默认显示“有效分类（人工优先）”；系统原始分类降为审计字段并默认隐藏，仅在筛选/排序系统原始分类或检查人工/系统不一致时自动显列并以蓝色表头突出。人工分类存在时，业务筛选、排序、统计、二次指标与导出均以人工结果覆盖系统结果。
- **Creator Availability Lifecycle 与同步健康分离**：新增可用、暂时不可用待确认、社区准则终止、版权终止、已删除/不存在、不可用原因未知等频道状态；只有公开 YouTube 页面给出明确终止原因时才标记社区准则/版权终止。
- 频道明确终止/删除或连续不可用升级为终止态后，停止无意义的自动监控与重试，但永久保留本地 Creator/视频历史；【监控健康】提供“重新检测频道状态”以支持恢复。
- 【监控健康】分别显示频道状态、同步健康和监控状态，博主名称直接链接 YouTube 主页；普通同步失败继续使用退避策略。
- SQLite Schema 升至 **13**，仅增加 Creator 可用性状态字段；升级不会覆盖现有业务数据。

## v3.4.0 有效分类、发现首屏、监控同步与 AI Agent 目标适配

- **有效分类（人工优先）是业务默认口径**：`video_labels.human_role` 存在时覆盖 `label_suggestions.suggested_role` 用于筛选、排序、统计、二次指标与导出；系统原始分类继续保留作审计。Dashboard 显示分类来源，并支持筛选“人工结果 ≠ 系统结果”。
- 【博主发现 → 已保存的发现记录】交互模式不得先把全部历史记录写入 DOM；生成 HTML 只保留 30 条静态兜底预览，页面首先检测交互服务并直接请求第一页。
- 【数据更新 → 监控健康】博主名称链接到 YouTube 主页；界面解释正常/已到期/数据过期/等待重试/同步失败/已暂停，并提供单条与批量“立即同步”，支持增量、仅指标、仅频道和全历史模式。
- **AI 搜索 Agent 不再只生成 Query**：Planner 同时输出结构化 Fit Criteria；本机执行 Query 后，对候选 Creator 最近最多 50 条上传做轻量抽样，再按基础主题、搜索要求、订阅范围、长期制作证据进行过滤和目标适配排序。
- 对“中小体量”等没有数字的要求，v3.4.0 默认 `subscriber_max=100,000`，并在 Dashboard、Result Set 和 XLSX 中显式记录；用户在 Prompt 中写明数值时以用户要求为准。
- AI Result Set 区分“已采集且数量=0”和“未采集”；XLSX 完整导出搜索主题、原 Prompt、语言/区域/国家/时间、Query 限额、Planner Strategy/Fit Criteria、计划与实际 Query、过滤统计、AI Provider/Model/Prompt Version，并新增 `Query Details` 工作表。
- Schema 保持 12。

## v3.3.2 分类证据分层

- AFK、Auto Farm、24/7、multi-instance 属于 Creator Discovery / use-case 信号，不得单独触发视频【其他云手机】分类。
- 只有明确云手机实体词（cloud phone / cloud emulator / 云手机等）或品牌证据才能判定云手机相关分类。
- 已知品牌弱证据进入【待复核】，不得兜底为【其他云手机】。
- Dashboard 支持离线重新识别全部系统分类；该操作不调用 YouTube API，并保留 `video_labels` 中的人工修正。

## v3.3.1 批量动作一致性与交互实时刷新

- **Action Parity 是硬规则**：任何支持多选的 Creator / Video 表格，只要存在单条可执行动作，就必须提供语义等价的批量动作；不能出现“单条能做、批量不能做”。
- 【博主发现 → 本次搜索结果】与【已保存的发现记录 · 博主】均支持批量加入博主库、批量抓取并入库、抓取公开联系方式、工作流、监控开关与优先级。
- 批量抓取使用统一的“抓取范围”选择器：近7/30/60/90/180/365天、指定日期范围、全历史；全历史在 UI 中明确标注“最多10,000条”。
- **Live Data Refresh 是硬规则**：交互 Dashboard 的任何写库动作完成后，相关事实、统计、身份、本地视频数和二次指标必须直接重新读取 SQLite；不得要求用户重启 Dashboard 或运行 upgrade 才看到新数据。
- 静态 Dashboard 仍是生成时快照；只有静态详情页/HTML 文件本身需要 `build_dashboard()` 重新生成。交互模式不得为了刷新统计而逐 Creator 重建整个 Dashboard。
- Schema 保持 12。

## v3.2.0 AI Result Set 与可操作检索工作流

- Ask Hub / AI 搜索 Agent 每次执行自动留档为 Result Set，默认30条/页，支持筛选、排序、跨页选择和完整 XLSX 导出。
- 新增 AI 检索历史，可回看每次问题/搜索主题、结果数、AI Run 与 Discovery Run。
- Creator Brief / Creator 对比统一使用本地 Creator Picker：搜索候选、点击锁定，多选对比以标签显示。
- AI 搜索 Agent 的自由文本字段明确为“AI 搜索要求”，区域/国家/时间等继续作为结构化硬约束。
- `ai_runs` 保存输入/结果快照；cache hit 也留下独立用户调用记录。
- Schema 升至 12，新增 `ai_result_sets` / `ai_result_items`，AI 搜索可显式关联 Discovery Run。
- AI 仍是可选增强层；未配置 AI API 时全部既有核心功能保持可用。

## v3.1.0 开放式 AI API 配置与搜索 Agent

- AI 配置改为接口协议 + 自定义 Base URL + 本机 API Key + 自由模型 ID；不维护易过期的固定模型目录。
- 支持 Responses、OpenAI-compatible Chat Completions、Anthropic Messages、Gemini generateContent 与 Mock 协议适配器。
- Dashboard 可读取 API 返回的模型列表，也允许任何模型 ID 手工输入；`setup-ai.cmd` 不再 OpenAI 专用。
- API Key 使用供应商中立的 `CREATOR_HUB_AI_API_KEY` 本机密钥槽，不进入 SQLite/浏览器。
- AI 搜索 Agent 将规划后的 Query 交给现有 YouTube API Discovery 执行、去重、评分并保存发现记录。
- AI 仍为可选增强层；Schema 保持 11。

## v3.0.0 可插拔 AI Copilot

- AI 默认关闭；不配置 AI API 时，全部既有核心功能完整可用。
- 新增 Ask Hub、Creator Brief、Creator 对比、AI Query Planner、七日 Intelligence Brief 与 AI 调用记录。
- AI 仅通过 allowlist 本地工具读取数据，不直接执行任意 SQL；v3.0.0 不提供 AI 自动写库动作。
- AI Finding/Evidence 与确定性评分、系统分类、人工复核分层存储。
- OpenAI API Key 使用环境变量 `OPENAI_API_KEY`，不进入 SQLite 或浏览器。
- Schema 版本为 11。

## v2.1.0 统一分页与跨页批量选择

- 所有大型表格继续执行默认 30 条/页；监控健康现在也使用标准分页。
- 所有支持多选批量操作的表格均提供当前页全选、全部结果全选和清空选择。
- 视频分类的跨页全选由服务端解析当前筛选条件，可覆盖全库而不把全部 Video ID 发送到浏览器。
- Schema 保持 10。

## v2.0.0 长期运行与数据治理

- 交互模式的二次指标/规则与 Query Expansion 配置持久化到 SQLite；浏览器存储只作为静态/临时回退。
- 数据更新页提供监控健康、数据库健康、一致性备份/恢复和 Snapshot 生命周期维护。
- Creator 同步记录失败类型、连续失败、下次重试和暂停状态；失败采用退避并支持批量恢复。
- 博主发现支持处理工作流、永久排除、首次/重复发现与批量操作。
- 二次指标支持分组/说明/依赖保护；Creator 页面统一呈现各类数据新鲜度。
- Schema 版本为 10；升级只迁移结构和派生状态，不覆盖现有业务数据库。

## v1.6.0 应用结果状态与视频分类性能

- 应用结果的 activeRule 不再作为持久筛选跨会话残留；“清除全部条件”同时清除普通筛选、规则和搜索词，并在结果区明确显示当前条件。
- 视频分类交互模式直接连接完整 SQLite，不先展示 300 条静态预览的 10 页分页；静态预览只在只读模式使用。
- 视频分类页面查询与全局 KPI 统计拆分；无筛选总数直接 COUNT(videos)，并新增关键 SQLite 索引。
- 数据库 Schema 版本为 5。

## v1.5.0 全局二级导航与首次部署引导

- 五个一级 Dashboard 页面都提供当前页二级导航，支持锚点定位、平滑滚动、滚动高亮和 URL Hash。
- `setup.cmd` 完成后提供交互/静态 Dashboard、自动监控和 API 在线验证入口。
- `scripts/python-run.cmd` 统一解析 `python` / `py -3`，并用于主要启动器与自动监控脚本。
- `doctor` 输出实际 Python 路径并检查本地 8765 端口是否可用于交互服务。

## v1.4.0 博主发现导航与历史关键词恢复

- 【博主发现】当前页面在左侧展开四个锚点导航，并随主区域滚动同步高亮。
- v1.3 前历史发现不再统一显示 `Legacy Discovery`；保留原始 `discovery_hits`，只重建派生博主结果。
- 历史实际 Query 通过 Query Pack 长尾词和已出现基础 Query 恢复关键词族，按“推断原关键词 × Creator”聚合；来源标记为 `inferred / 历史推断`，不声称恢复了旧搜索批次边界。
- v1.3+ 正式搜索的 `base_query_source=exact`；博主级发现 XLSX 同时导出【原关键词】与【关键词来源】。

## v1.3.0 安装引导、XLSX 导出与发现数据模型 v2

- 首次安装推荐运行 `setup.cmd`；API Key 推荐通过 `scripts\set-api-key.cmd` 写入 Windows 用户环境变量 `YOUTUBE_API_KEY`。
- `doctor` 检查 Python/pip/openpyxl/SQLite/写权限/API Key；`doctor --online` 进一步验证 API Key。
- 静态 Dashboard 只读；交互 Dashboard 由 `start-dashboard.cmd` 启动本机 Python 服务并连接本机 SQLite。
- 核心表格可导出 XLSX；完整筛选结果导出需要交互模式。
- 博主发现每次搜索产生一个 `discovery_runs.run_id`；同时保存博主级 `discovery_creator_results` 与视频级 `discovery_hits`。旧 discovery hits 不臆造真实 run 边界；v1.4.0 起按恢复的基础关键词生成带【历史推断】来源的聚合。

## v1.2.1 交互筛选与二次指标排序修复

- 修复构建指标/比值指标排序分支的前端引用错误。
- 总览与视频分类筛选增加明确的“已应用条件 / 命中数量”反馈。
- 升级时清理旧 Dashboard 输出并重建；交互 HTTP 服务禁用静态资产缓存，避免混用旧 JS。
- 保留【疑似不再合作】标签及其“历史合作 + 监控中 + 数据新鲜 + 30 天无 UgPhone 新视频”的保守判定。


本 Skill 的唯一事实源是 `data/creator_hub.sqlite`。

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

网页搜索 v0.9.0 起尝试跟随 YouTube continuation token 深度加载；API 搜索继续使用 `nextPageToken`。每个实际 Query 都独立写入 `discovery_hits`，同一 Creator 的结果保留最高发现评分并记录 Query Coverage。详见 `docs/QUERY_EXPANSION.md`。

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

## v1.1.0 二次指标粒度重构

- 禁止将博主标签作为视频聚合输入。
- 指标构建器只接受视频客观数据并输出博主级构建指标。
- 比值指标引用博主客观数据或构建指标。
- 规则/筛选四类对象统一为博主客观数据、博主标签、构建指标、比值指标。

## v0.9.3 视频分类首屏分页修复

- 视频分类页面加载脚本后立即将静态预览压缩为第一页 30 条。
- 交互 API 完成后再以 SQLite 返回的第一页 30 条替换预览，避免初始化期间出现超过 30 条可见记录。
- 所有后续翻页、每页条数确认、筛选和排序逻辑保持不变。

## v0.9.2 地理筛选

Dashboard 中所有 Creator 级国家/地区筛选统一使用区域 → 国家/地区级联：先选业务区域，再可选该区域内具体国家；不要直接向使用者展示 249 个国家的单层下拉框。
