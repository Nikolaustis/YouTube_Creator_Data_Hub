# 4.3.0 — Generic Creator Discovery

Database Schema remains **18**. This release does not delete production Creator / Video facts.

## What changed

- Replaced the historical discovery Query Pack catalog with six domain-neutral packs: `learn`, `review`, `use_case`, `updates`, `community`, `custom`.
- Removed default discovery vocabulary tied to a specific entertainment category or compatibility business.
- Changed the Creator Discovery search placeholder and validation copy to accept any topic, product, brand or keyword.
- Scoped browser Query Pack state to Workspace-specific schema v3 storage and stopped inheriting unscoped v1/v2 states.
- Generic Workspace `query_profile` rows that contain historical pack vocabulary are backed up to `query_profile_pre_neutral_4_3` and reset.
- Replaced fixed partnership/competitor identity filters on the Discovery page with generic Workspace relationship presence.
- Updated AI Query Planner prompt to be industry-neutral by default.
- Replaced the public `gaming_creator` template with `creator_discovery`.
- Moved compatibility-only Workspace and brand configuration under `creator_hub/compat/`; the top-level public template/query configuration is domain-neutral.
- Extended the public-surface regression check to generated `discovery.html`, `assets/discovery.js`, `assets/query_packs.js`, Query Pack source and AI prompts.

## Compatibility

Historical compatibility facts are retained. Compatibility configuration is still available internally for explicit migration/use, but it is not part of the default Workspace/template surface.

## Upgrade

Run:

```bat
upgrade.cmd
```

For the synthetic reviewer demo:

```bat
setup-demo.cmd
start-demo.cmd
```
