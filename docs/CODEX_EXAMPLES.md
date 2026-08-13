# Codex conversation examples

The user should normally speak naturally. Codex maps the request to deterministic CLI actions.

| User intent | Deterministic action |
|---|---|
| 搜索 100 个 Anime Expeditions KOL | `python hub.py discover "Anime Expeditions" --max-results 100` |
| 搜菲律宾 Roblox AFK | `python hub.py discover "Roblox AFK" --target-country PH` |
| 搜最近7天菲律宾 Roblox AFK | `python hub.py discover "Roblox AFK" --target-country PH --lookback-days 7` |
| 搜 8月1日至8月13日菲律宾 Roblox AFK | `python hub.py discover "Roblox AFK" --target-country PH --from-date 2026-08-01 --to-date 2026-08-13` |
| 把 @abc 加入重点监控 | `python hub.py add "@abc" --priority high` |
| 抓 @abc 最近7天视频 | `python hub.py capture "@abc" --days 7` |
| 抓 @abc 指定日期视频 | `python hub.py capture "@abc" --from-date 2026-08-01 --to-date 2026-08-13` |
| 把 @abc 全历史抓完 | `python hub.py sync "@abc" --mode full-history` |
| 更新所有人 | `python hub.py sync --mode incremental` |
| 只刷新播放量 | `python hub.py sync --mode metrics-only` |
| abc123def45 是 UgPhone | `python hub.py label abc123def45 ugphone --brands ugphone --by operator` |
| 离线重识别待复核分类 | `python hub.py review-reclassify` |
| 打开交互 Dashboard | `python hub.py serve` |
| 生成只读 Dashboard | `python hub.py dashboard` |
| 导 Excel | `python hub.py export --format xlsx` |
| 导入旧 V2 | `python hub.py import-v2 "..."` |
