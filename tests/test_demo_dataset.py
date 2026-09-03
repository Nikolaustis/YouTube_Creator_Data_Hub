from creator_hub.db import connect
from creator_hub.portfolio.demo import create_demo


def test_demo_dataset_is_isolated_and_populated(tmp_path):
    db = tmp_path / "portfolio_demo.sqlite"
    result = create_demo(db, creators=8, videos=64, seed=7, build=False)
    assert result["synthetic"] is True
    assert result["creators"] == 8
    assert result["videos"] == 64
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 64
        assert conn.execute("SELECT COUNT(*) FROM creator_relationships").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM video_taxonomy_assignments").fetchone()[0] == 64
        assert conn.execute("SELECT COUNT(*) FROM creator_business_metrics").fetchone()[0] == 16
        assert conn.execute("SELECT COUNT(*) FROM ai_evidence").fetchone()[0] > 0
