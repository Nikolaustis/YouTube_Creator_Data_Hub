# 4.2.0 — Neutral Public Surface

Database schema remains **18**.

## What changed

- Generic/default Workspaces no longer inherit global historical Secondary Metrics.
- Browser metric state is namespaced by Workspace; unscoped historical state is ignored on generic Workspaces.
- Default Dashboard examples, result columns, Creator relationships, detail sorting, classification brand choices and exports are Workspace-driven/domain-neutral.
- Compatibility templates are hidden from the public template catalog and are never auto-activated.
- Existing compatibility data is retained in its Workspace; no production Creator/Video facts are deleted.
- Existing generic Workspace metric configurations are scanned for legacy domain-specific references. Removed entries are backed up once under `secondary_metrics_pre_neutral_4_2`.
- Demo setup runs a neutral-surface migration before building synthetic data and validates the resulting UI.
- Windows entrypoints now run the neutrality gate as a module; the checker also bootstraps the repository root onto `sys.path`, so direct file execution is safe.

## Upgrade

Run `upgrade.cmd`. A consistent pre-upgrade database backup is created first.

To validate the public/demo surface independently:

```bat
setup-demo.cmd
```

or:

```bash
python -m scripts.check_public_surface_neutrality
```
