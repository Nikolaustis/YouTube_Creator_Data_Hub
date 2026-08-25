# Changelog

## v3.10.4

- 二次指标四面板改为“左侧 Builder 自然高度为锚点”：指标构建器 / 规则标签构建器不再被右侧列表反向撑高。
- 已构建指标与规则列表只跟随对应 Builder 高度，超出部分在 Card Body 内纵向滚动；继续固定 10 条/页。
- 搜索、排序、分页不再改变外层 Card 高度；Builder 内容变化和窗口尺寸变化会自动重新同步右侧高度。
- Schema 不变，不修改 SQLite 业务数据。

## 3.10.3

- 三级 Field Taxonomy 为唯一字段选择结构。
- 规则 / 标签构建器、二次指标应用结果、主博主库三处统一为同一套一行式三级条件选择器。
- 淘汰纵向堆叠三级选择器和独立搜索按钮；三级指标搜索内嵌。
- 已构建指标与规则列表固定 10 条/页，使用面板内部垂直滚动，并与对应构建器保持等高。
- 保留持久 Job Engine、Migration Runner、API v1、冻结 Run Specification、统一 Data Contract 与 Creator Intelligence Engine。
- Schema 17；源码包不包含业务数据库或任何密钥。
