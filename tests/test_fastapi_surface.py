from fastapi.testclient import TestClient

from creator_hub.api import create_app
from creator_hub.portfolio.demo import create_demo


def test_openapi_and_typed_routes(tmp_path):
    db = tmp_path / "api_demo.sqlite"
    create_demo(db, creators=5, videos=25, build=False)
    client = TestClient(create_app(db))
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["api_version"] == "v1"
    creators = client.post("/api/v1/creators/query", json={"limit": 10})
    assert creators.status_code == 200
    assert creators.json()["data"]["count"] == 5
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert "/api/v1/workspaces" in spec.json()["paths"]
