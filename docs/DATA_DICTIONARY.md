# Data Dictionary

## Global Fact Layer

| Table | Purpose |
|---|---|
| `creators` | Current public Creator/channel facts and monitoring state |
| `creator_snapshots` | Historical channel metric snapshots |
| `videos` | Current public video facts |
| `video_snapshots` | Historical video metric snapshots |
| `discovery_runs` | Reproducible discovery run metadata |
| `discovery_hits` | Raw discovery evidence |
| `discovery_creator_results` | Creator-level discovery results |
| `job_runs` | Durable job state, payloads and checkpoints |
| `ai_runs` / `ai_findings` / `ai_evidence` | Auditable AI execution and evidence |
| `data_assertions` | Layered fact/derived/AI/human assertions |

## Workspace Intelligence Layer

| Table | Purpose |
|---|---|
| `workspaces` | Business-semantic isolation boundary |
| `workspace_brands` | Configurable brands/entities for one Workspace |
| `brand_groups` | Workspace-defined brand groups |
| `taxonomy_schemes` / `taxonomy_labels` | Configurable content semantics |
| `video_taxonomy_assignments` | Layered taxonomy assignments |
| `creator_relationships` | Workspace-specific Creator relationships |
| `business_metric_definitions` | Workspace metric definitions |
| `workspace_settings` | Workspace-scoped metric/rule/UI configuration |

## Creator business metrics

`creator_business_metrics` stores point-in-time or period-aware commercial facts separately from public YouTube facts. The interpretation of a metric key is defined by the active Workspace; examples include `revenue`, `orders`, `installs`, `new_users`, or other user-defined measures.

Important fields include `channel_id`, `metric_key`, `metric_value`, `currency`, period fields, source provenance, `captured_at`, and `snapshot_kind`. Historical cumulative snapshots are never implicitly summed unless the Workspace metric definition explicitly requires that aggregation.

## Effective-value precedence

For fields represented in `data_assertions`, effective precedence is:

`human > ai > derived > fact`

The lower layers remain queryable for audit and provenance.
