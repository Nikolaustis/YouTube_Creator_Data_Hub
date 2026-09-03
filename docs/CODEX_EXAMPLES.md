# Command examples

| Goal | Command |
|---|---|
| Initialize / migrate SQLite | `python hub.py init` |
| Add a Creator | `python hub.py add "@creator"` |
| Capture recent videos | `python hub.py capture "@creator" --days 90` |
| Capture full history | `python hub.py sync "@creator" --mode full-history` |
| Update monitored Creators | `python hub.py sync --mode incremental` |
| Refresh video metrics | `python hub.py sync --mode metrics-only` |
| Build Dashboard | `python hub.py dashboard` |
| Start interactive Dashboard | `python hub.py serve` |
| Start typed API | `start-api.cmd` |
| Create synthetic portfolio demo | `create-demo.cmd` |
| Run benchmark | `python -m creator_hub.portfolio.benchmark --profile small` |
| Run offline AI evaluation | `python -m creator_hub.portfolio.ai_eval` |

Workspace-specific labels and relationships should be configured through Workspace taxonomy/relationship primitives rather than fixed CLI examples tied to one business domain.
