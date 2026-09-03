# Workspaces

V4 将通用 YouTube 事实层与业务语义层分离。

## Global facts

`creators`、`videos`、Snapshot、Discovery、Job、AI 与 Data Contract 属于全局事实层。

## Workspace-owned configuration

每个 Workspace 独立拥有品牌、品牌组、Taxonomy、Creator Relationship、Business Metric Definition、Discovery Profile、二次指标、规则和 Saved View。

## Compatibility packs

行业 / 客户特定语义只能存在于 Template / Workspace 中。Cloud Phone Growth 是现有云手机业务的兼容 Pack，并非 Core 默认假设。

## Stable IDs

Workspace、Brand、Group、Taxonomy、Label、Business Metric Definition 全部使用稳定 ID。显示名称可修改，但持久化引用不得依赖显示文本。
