# YouTube 博主数据中心 v0.8.0

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

覆盖旧版本后，先双击 `upgrade.cmd`。它会删除旧版遗留的中文命名启动器、运行自检并重新生成 Dashboard。

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

初始状态**没有任何预置已构建指标**。浏览器使用 `cdh-secondary-metrics-v5` 工作区。

全局指标仍按四类展示：

1. **客观数据**：订阅数、频道播放量、本地视频数、UgPhone/竞品/品牌视频数量等系统基础指标；
2. **聚合标签**：只返回 0/1，例如合作过博主、未合作博主、LDCloud/RedFinger/VSPhone 合作博主；
3. **构建指标**：由使用者从【客观数据】或【聚合标签】出发，使用 Count / Sum / Average / Median / Max / Min 生成；视频客观数据可叠加视频分类/品牌和时间范围；
4. **比值指标**：也是指标构建器的输出。分子和分母分别从【客观数据】定义聚合逻辑，再计算比值。

指标构建器现在严格区分输入与输出：

`输入类型：客观数据 / 聚合标签 → 输出类型：构建指标 / 比值指标`

当输出为【比值指标】时，输入固定为【客观数据】，并分别定义分子与分母的数据、视频筛选、聚合方式和时间范围。涉及视频时间时支持全部、近7/30/60/90/180/365天和精确开始/结束日期。

规则 / 标签构建器可直接使用四类指标。第一条条件不带布尔连接，从第二条开始逐条选择 AND / OR / NOT；聚合标签按“存在/为真”判断，不要求填写数字阈值。

总览博主库、二次指标应用结果、博主详情、视频分类、博主发现本次结果与历史记录的筛选也采用多条件 AND / OR / NOT 逻辑。

## 大数据模式

不会把几十万条原始视频塞进浏览器：

```text
SQLite
  ↓
Python预聚合
  ├─ Creator客观事实
  ├─ 品牌视频数量
  ├─ 0/1聚合标签
  ├─ 视频聚合立方体
  └─ 必要Snapshot
  ↓
creator_facts.js + metric_base.js
```

博主详情页的 Snapshot 采用批量查询，避免逐视频 N+1。
## 发现评分说明

完整公式、阈值与 A/B/C/D 分档见 `docs/DISCOVERY_SCORING.md`。
