# Secondary Metrics

Secondary Metrics converts reusable Creator/Video facts into Workspace-specific analytical fields without embedding a customer, brand, or industry into Core.

## Data grain

- **Creator facts**: subscriber count, channel views, stored videos, freshness, Workspace business metrics.
- **Creator relationships**: Workspace-scoped relationship predicates such as partnership status.
- **Video facts**: views, likes, comments, duration and video count.
- **Workspace taxonomy**: configurable video labels supplied by the active Workspace.
- **Constructed metrics**: aggregate video facts after taxonomy/brand/time filtering.
- **Ratio metrics**: divide two Creator-grain numeric fields or constructed metrics.

## Generic examples

- `近90天教程视频播放中位数`
- `产品评测视频数量`
- `近30天视频平均互动量`
- `Revenue ÷ 本地已存视频数`
- `教程视频播放中位数 ÷ 全部视频播放中位数`

The metric builder must not assume a particular primary brand or competitor. Brand and taxonomy filter options are derived from the active Workspace.

## Workspace isolation

Metric configuration is stored under `workspace_settings.secondary_metrics`. A generic Workspace with no configuration starts with an empty metric/rule set and must not inherit historical global configuration or browser state from another Workspace.
