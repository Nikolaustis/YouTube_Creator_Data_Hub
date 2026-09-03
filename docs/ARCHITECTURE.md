# Architecture

## Target architecture

The system is organized around two layers.

**Global Fact Layer** stores reusable Creator/Video facts, snapshots, discovery provenance, job state, run specifications, assertions and AI evidence.

**Workspace Intelligence Layer** stores brand definitions, taxonomies, Creator relationships, business metric definitions, discovery profiles, secondary metrics, rules and saved views.

New reusable code must be domain-neutral. Business-specific behavior belongs in Workspace templates or `creator_hub/compat/`.

## Migration strategy

V4.1 uses a strangler migration. The typed FastAPI layer, generic monitoring heuristic, new Workspace query utilities and portfolio/evaluation tooling use the target model. Historical Dashboard modules remain a compatibility boundary until their saved-view and UI contracts can be migrated without breaking existing databases.

Known compatibility-boundary files include `creator_hub/dashboard.py`, `creator_hub/metric_workspace.py`, `creator_hub/ai/local_tools.py`, `creator_hub/server.py`, and `creator_hub/compat/`.

This boundary is intentional and auditable; `scripts/check_core_portability.py` prevents new domain-specific semantics from entering the new reusable surfaces.

## HTTP surfaces

- `127.0.0.1:8765`: historical interactive Dashboard compatibility server.
- `127.0.0.1:8766`: FastAPI `/api/v1`, OpenAPI, Swagger and ReDoc.

FastAPI write endpoints are loopback-only by default.

## Job durability

Resumable jobs persist payload and checkpoint state in SQLite. Checkpoint writes are durability-critical: a failed durable write is retried and then surfaced as an explicit `JobPersistenceError`. `durability_health()` exposes degradation state rather than silently swallowing persistence errors.
