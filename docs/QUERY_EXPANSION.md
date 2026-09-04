# Query Expansion

Creator Discovery always executes the original search topic once. Optional Query Packs append selected long-tail terms to that topic and execute the resulting queries within the configured query budget.

## Workspace-scoped Query Pack Editor

From 4.4.0, each Query Pack is editable inside the active Workspace. A group contains:

- group name and description;
- enabled state;
- ordering position;
- a separate term list for every supported search language;
- an active/inactive selection for terms in each language.

The default catalog contains `learn`, `review`, `use_case`, `updates`, `community` and `custom`, but these are templates rather than hard-coded business rules.

The UI supports **Edit, Copy, Delete, Move Up, Move Down and Restore Default** per group. The Query Expansion toolbar also supports **Add Group**, **Restore Current Language Defaults** and **Restore System Query Packs**.

Custom groups can replace the default catalog entirely. The original search topic still executes even if every Query Pack is deleted or disabled.

## Persistence

Query Pack configuration is isolated by Workspace.

Browser state uses a Workspace-scoped v4 key. SQLite stores the authoritative interactive configuration in the current Workspace `query_profile` with:

```json
{
  "schema_version": 4,
  "profile": "generic_creator_discovery_v2",
  "language": "en",
  "order": ["learn", "review"],
  "packs": {}
}
```

`config/query_packs.json` supplies only factory defaults. Normal upgrades do not overwrite an existing schema-4 Workspace profile.

When upgrading from 4.3.0, fixed-pack enable states, edited term lists and active selections are migrated into schema 4. A backup is retained under `query_profile_pre_editor_4_4`.

## Query generation

For a base topic such as `AI productivity`, an enabled group with selected terms `tutorial` and `workflow` produces:

```text
AI productivity
AI productivity tutorial
AI productivity workflow
```

Queries are de-duplicated before execution and clipped to the configured maximum query count.
