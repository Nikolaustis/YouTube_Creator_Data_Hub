# Query Expansion

博主发现以“相关视频 → 发布视频的 Creator”为核心流程。 起，每次搜索都可以在原游戏关键词上叠加 Query Expansion。

## 规则

- 原关键词始终执行一次。
- 选中的 Query Pack 会将当前语言下的每个长尾词与原关键词组合，例如：
  - `Anime Expeditions`
  - `Anime Expeditions AFK`
  - `Anime Expeditions AFK farm`
- 同一搜索中的 Video ID 与 Creator ID 会统一去重。
- 同一个 Creator 被多个 Query 命中时，结果保留发现评分最高的命中视频，同时记录 Query Coverage。
- 每个实际执行的 Query 仍独立写入 `discovery_hits.query`，保留完整发现来源。

## 六个 Query Pack

1. `core`：玩法、攻略、教程。
2. `farming`：刷资源、成长、自动刷图与效率。
3. `afk`：AFK、24/7、过夜、多账号等云手机适配场景。
4. `active`：更新、活动、兑换码、排行、技巧与 F2P。
5. `commercial`：评测、比较、值不值得等低优先级补充发现。
6. `custom`：使用者自行维护。

Dashboard 允许对当前语言的每个 Pack 增加或删除长尾词，并逐 Pack 启用/停用。每个词条还有独立勾选框：勾选表示本次检索使用；取消勾选表示保留该词但本次不使用；点击 × 才会从当前语言词库删除。新增词默认勾选。交互 Dashboard 会将编辑后的 Query Profile 持久化到 SQLite `app_settings`；静态只读模式才使用浏览器本地回退。`config/query_packs.json` 保留出厂默认词库。

## 语言

默认语言是 English。内置：

- English
- Español (Latinoamérica)
- Português (Brasil)
- ไทย
- Tiếng Việt
- Bahasa Indonesia
- 한국어
- 日本語
- 繁體中文（台灣）

切换语言后，Pack 会使用该语言对应的长尾词。自定义 Pack 也按语言分别保存。

## 搜索深度

“每个 Query 视频上限”控制每一个生成 Query 的目标视频数。网页搜索会尝试跟随 YouTube continuation token 继续加载；API 搜索通过 `nextPageToken` 翻页。

API 搜索的 `search.list` 成本较高：每页（最多 50 个结果）约 100 quota units。Dashboard 会根据 Query 数量和每 Query 上限显示预计 search quota；实际执行仍受每日软上限保护。
