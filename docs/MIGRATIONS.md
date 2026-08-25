# Database migrations

V3.10 changes the database schema from 16 to 17 and introduces `schema_migrations`.

Each registered migration has:

- integer version
- stable name
- checksum
- transactional application through `init_db()`
- applied timestamp

For a legacy Schema 16 database, V3.10 first records a `legacy_schema_16_baseline`, then applies migration 17. A migration already recorded with a different checksum is treated as an error.

Migration 17 adds the persistent Job Engine columns, `run_specs`, `data_assertions`, and the Result Set → Run Spec link. `upgrade.cmd` still creates a consistent pre-upgrade SQLite backup before migration.
