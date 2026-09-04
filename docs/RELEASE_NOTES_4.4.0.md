# 4.4.0 — Workspace Query Pack Editor

Database Schema remains **18**. This release changes Query Expansion configuration, not Creator / Video fact storage.

## Query Pack groups are now editable

Each Query Expansion group is a Workspace-scoped strategy object rather than a fixed card from `config/query_packs.json`.

Supported operations:

- rename a group and edit its description;
- enable or disable a group;
- add and remove terms for the currently selected language;
- add a completely new group;
- duplicate an existing group including all language vocabularies;
- delete any group;
- move groups up or down;
- restore one built-in group to system defaults;
- restore built-in terms for the current language;
- restore the complete system Query Pack catalog.

## Persistence and upgrades

The browser state is stored under a Workspace-scoped v4 key and SQLite uses `query_profile` schema 4 / profile `generic_creator_discovery_v2`.

Existing 4.3 profiles are migrated rather than reset. Enabled state, term additions/removals and active term selections are retained. A one-time backup is written to `query_profile_pre_editor_4_4` before SQLite conversion.

New user groups live only in the active Workspace profile. `config/query_packs.json` is a default template and normal upgrades do not overwrite a schema-4 Workspace profile.

## Compatibility

Schema remains 18 and production Creator / Video / Snapshot / Discovery facts are unchanged.
