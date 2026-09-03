# Security and data handling

This project is local-first. Production SQLite databases, API keys, exports, backups, logs and business files must not be committed to Git.

The interactive services should remain bound to loopback (`127.0.0.1` / `::1`) unless the deployment is intentionally secured for network access. The default FastAPI service runs on `127.0.0.1:8766`; the compatibility Dashboard runs on `127.0.0.1:8765`.

If credentials are accidentally committed, revoke/rotate them immediately and remove them from Git history. Do not rely on deleting only the latest file revision.

Public demos must use synthetic data created by `create-demo.cmd` / `creator_hub.portfolio.demo`.
