from __future__ import annotations

from typing import Any

LEVEL1 = [
    {"id": "objective", "name": "客观数据", "order": 10},
    {"id": "labels", "name": "标签 / 关系", "order": 20},
    {"id": "constructed", "name": "构建指标", "order": 30},
    {"id": "ratio", "name": "比值指标", "order": 40},
]

OBJECTIVE_LEVEL2 = [
    {"id": "basic_info", "name": "基础信息", "order": 10},
    {"id": "geography", "name": "地理位置", "order": 20},
    {"id": "channel_scale", "name": "频道规模", "order": 30},
    {"id": "content_semantics", "name": "内容语义", "order": 40},
    {"id": "content_performance", "name": "内容表现", "order": 50},
    {"id": "business", "name": "商业数据", "order": 60},
    {"id": "discovery_ai", "name": "Discovery / AI", "order": 70},
    {"id": "data_health", "name": "数据健康", "order": 80},
    {"id": "video_fact", "name": "视频客观数据", "order": 90},
]

LABEL_LEVEL2 = [
    {"id": "relationship", "name": "Creator 关系", "order": 10},
    {"id": "taxonomy", "name": "Workspace Taxonomy", "order": 20},
    {"id": "workflow", "name": "工作流", "order": 30},
    {"id": "monitoring", "name": "监控标签", "order": 40},
    {"id": "compatibility", "name": "历史兼容字段", "order": 90},
    {"id": "manual", "name": "人工标签", "order": 100},
]

LEGACY_COMPAT_KEYS = {
    "partnered_ugphone",
    "unpartnered_ugphone",
    "suspected_inactive_partner",
    "ldcloud_creator",
    "redfinger_creator",
    "vsphone_creator",
    "ugphone_and_competitor",
}


def creator_objective_group(key: str) -> str:
    if key.startswith("business__"):
        return "business"
    if key.startswith("taxonomy_count__") or key.startswith("workspace_content"):
        return "content_semantics"
    if key in {"channel_title", "channel_id", "handle"}:
        return "basic_info"
    if key in {"country", "country_resolved", "country_api", "language", "creator_language"}:
        return "geography"
    if key in {"subscriber_count", "channel_view_count", "channel_video_count", "stored_videos"}:
        return "channel_scale"
    if key in {"gmv_total", "new_users_total", "orders_total", "revenue_total", "commission_total", "cost_total"}:
        return "business"
    if key in {
        "discovery_score", "discovery_pre_score", "query_coverage", "objective_fit_score",
        "topic_affinity_score", "use_case_continuity_score", "brand_safety_score",
    }:
        return "discovery_ai"
    if key in {
        "latest_upload", "last_synced_at", "monitoring_enabled", "priority",
        "last_sync_status", "availability_status", "sync_health", "failure_count",
    }:
        return "data_health"
    if key.endswith("video_count"):
        return "content_semantics"
    return "basic_info"


def creator_label_group(key: str) -> str:
    if key.startswith("relationship__"):
        return "relationship"
    if key.startswith("taxonomy__"):
        return "taxonomy"
    if key in LEGACY_COMPAT_KEYS:
        return "compatibility"
    if key.startswith("workflow_") or key == "workflow_status":
        return "workflow"
    if key.startswith("monitor_") or key in {"monitoring_enabled", "priority"}:
        return "monitoring"
    return "manual"


def registry_payload(
    creator_facts: dict[str, str],
    creator_labels: dict[str, str],
    video_facts: dict[str, str],
    metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []

    def add(**kw: Any) -> None:
        if kw.get("id") and not any(x["id"] == kw["id"] for x in fields):
            fields.append(kw)

    add(id="channel_title", key="channel_title", kind="creator_fact", label="博主名称", level1="objective", level2="basic_info", grain="creator", type="text", filterable=False, sortable=True)
    add(id="country", key="country", kind="geography", label="国家", level1="objective", level2="geography", grain="creator", type="text", filterable=True, sortable=True)
    for key, label in creator_facts.items():
        add(id=key, key=key, kind="creator_fact", label=label, level1="objective", level2=creator_objective_group(key), grain="creator", type="number", filterable=True, sortable=True, ratio=True)
    for key, label in creator_labels.items():
        add(id="label:" + key, key=key, kind="creator_label", label=label, level1="labels", level2=creator_label_group(key), grain="creator", type="boolean", filterable=True, sortable=False)
    for key, label in video_facts.items():
        add(id="video:" + key, key=key, kind="video_fact", label=label, level1="objective", level2="video_fact", grain="video", type="number", filterable=False, sortable=False)
    for metric in metrics or []:
        if not metric or metric.get("internal") or not metric.get("id"):
            continue
        typ = str(metric.get("type") or "constructed")
        level1 = "ratio" if typ == "ratio" else "constructed"
        group = str(metric.get("group") or "").strip() or "未分组"
        add(
            id="metric:" + str(metric["id"]),
            key=str(metric["id"]),
            kind=typ,
            label=str(metric.get("name") or metric["id"]),
            level1=level1,
            level2=group,
            level2_label=group,
            grain="creator",
            type="number",
            filterable=True,
            sortable=bool(metric.get("visible", True)),
            ratio=(typ == "constructed"),
        )
    return {
        "version": 3,
        "level1": LEVEL1,
        "level2": {"objective": OBJECTIVE_LEVEL2, "labels": LABEL_LEVEL2, "constructed": [], "ratio": []},
        "fields": fields,
    }
