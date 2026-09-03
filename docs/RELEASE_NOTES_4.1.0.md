# 4.1.0 Engineering / Portfolio release

## Highlights

- Adds FastAPI + Pydantic `/api/v1` with OpenAPI documentation.
- Adds deterministic synthetic Demo Dataset and no-key reviewer workflow.
- Adds reproducible S/M/L performance benchmark harness.
- Adds offline and saved-output AI grounding evaluation.
- Hardens Job Engine persistence, checkpoint recovery and durability health.
- Introduces a generic monitoring relationship heuristic while preserving the historical compatibility alias.
- Adds Workspace-oriented batch AI/query indexes to avoid N+1 relationship/Taxonomy reads.
- Adds pytest, Ruff and Windows/Ubuntu GitHub Actions CI.
- Adds repository hygiene rules, contribution/security guidance and public-portfolio documentation.

## Compatibility

Database schema remains 18. Existing Creator/Video facts are not rewritten. The historical Dashboard remains available on port 8765 while new integrations use FastAPI on port 8766.

## Known migration boundary

Historical Dashboard/metric/legacy AI modules still expose some V3 cloud-phone aliases. They are treated as an explicit compatibility boundary, not as reusable Core semantics.
