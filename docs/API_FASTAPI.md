# FastAPI surface

Run:

```bat
start-api.cmd
```

Swagger: `http://127.0.0.1:8766/docs`

ReDoc: `http://127.0.0.1:8766/redoc`

Current typed routes:

- `GET /api/v1/health`
- `GET /api/v1/workspaces`
- `GET /api/v1/workspaces/{workspace_id}`
- `POST /api/v1/workspaces`
- `POST /api/v1/workspaces/activate`
- `POST /api/v1/creators/query`
- `POST /api/v1/jobs/query`

New integrations should use this surface. Existing Dashboard JavaScript continues to use the compatibility server until migrated.
