# 架构

```text
Codex 对话
  ↓
hub.py
  ↓
SQLite（唯一事实源）
  ↓
Python Dashboard Builder
  ├─ 博主客观事实
  ├─ 视频分类统计
  ├─ 二次指标预聚合基础数据
  └─ 必要历史 Snapshot
  ↓
静态中文 Dashboard
```

## 原则

1. 不运行 Node/npm/Next.js/localhost 服务。
2. Dashboard 是可删除、可重建的缓存，不是数据库。
3. 视频分类由 Skill 自动运行；人工分类表仅用于修正错误。
4. 二次指标属于分析层，不回写事实表。
5. 大数据量下禁止浏览器加载全量原始视频做聚合。
6. 博主详情页 Snapshot 按博主批量读取，避免逐视频查询。

## 二次指标数据文件

- `assets/creator_facts.js`：博主级客观事实和分类计数。
- `assets/metric_base.js`：Python 根据全部视频预先计算的聚合立方体。
- `assets/metrics_workspace.js`：浏览器侧指标/规则构建逻辑。
- `assets/metrics_config.js`：可选默认指标配置。

聚合立方体按：博主 × 分类/品牌 × 时间窗口 × 度量字段 × 聚合方式组织，因此浏览器可以即时建立常用运营指标而不携带几十万条视频记录。
