# Local API v1

V3.10 introduces a versioned local contract for the future Workbench. The existing `/api/*` endpoints remain for Dashboard compatibility; new consumers should prefer `/api/v1/*`.

## Envelope

Success:

```json
{"ok": true, "data": {}, "meta": {}, "api_version": "v1"}
```

Error:

```json
{"ok": false, "error": {"code": "ValueError", "message": "..."}, "api_version": "v1"}
```

## Core endpoints

- `POST /api/v1/field-registry`
- `POST /api/v1/creators/list`
- `POST /api/v1/videos/list`
- `POST /api/v1/jobs/start`
- `POST /api/v1/jobs/status`
- `POST /api/v1/jobs/list`
- `POST /api/v1/jobs/cancel`
- `POST /api/v1/jobs/retry`
- `POST /api/v1/result-sets/get`
- `POST /api/v1/result-sets/list`
- `POST /api/v1/run-specs/get`
- `POST /api/v1/run-specs/list`
- `POST /api/v1/run-specs/clone`
- `POST /api/v1/run-specs/execute`
- `POST /api/v1/intelligence/weekly-context`
- `POST /api/v1/contracts/effective`
- `POST /api/v1/contracts/history`

This is a localhost API. It is not a public multi-user HTTP service and must not be exposed as a SaaS boundary without a separate authentication/security layer.
