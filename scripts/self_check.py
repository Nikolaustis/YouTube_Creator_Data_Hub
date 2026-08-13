from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creator_hub.dashboard import build_dashboard
from creator_hub.exporter import export_all
from creator_hub.geography import geography, group_codes, resolve_country_query
from creator_hub.importers import import_v2
from creator_hub.metric_config import import_metric_config, load_metric_config
from creator_hub.service import CreatorHub


def main():
    # Package filenames must be ASCII-only so Windows paths and generated artifacts stay predictable.
    for package_file in ROOT.rglob("*"):
        if package_file.is_file():
            rel_path = package_file.relative_to(ROOT)
            if rel_path.parts and rel_path.parts[0] in {"data", "output", "exports"}:
                continue
            rel = rel_path.as_posix()
            assert all(ord(ch) < 128 for ch in rel), rel
    assert (ROOT / "start-dashboard.cmd").exists()
    assert (ROOT / "open-static-dashboard.cmd").exists()
    assert (ROOT / "upgrade.cmd").exists()

    # Geography: every ISO alpha-2 country/territory is available and assigned to one of the 11 product groups.
    geo = geography()
    assert len(geo.get("countries", [])) == 249
    assert len(geo.get("groups", [])) == 11
    expected_groups = {"东亚", "东南亚", "南亚", "中亚", "中东", "欧洲", "非洲", "北美", "拉美", "巴西", "大洋洲"}
    assert {g["name"] for g in geo["groups"]} == expected_groups
    assert all(c.get("group") for c in geo["countries"])
    assert resolve_country_query("菲律宾")["code"] == "PH"
    assert resolve_country_query("PH")["name_zh"] == "菲律宾"
    assert "PH" in group_codes("southeast_asia")

    tmp = Path(tempfile.mkdtemp(prefix="creator_hub_selfcheck_"))
    try:
        fixture = tmp / "v2" / "creators" / "demo"
        fixture.mkdir(parents=True)
        cid = "UC1234567890123456789012"
        vid = "abcdefghijk"
        (fixture / "channel_metadata.json").write_text(
            json.dumps({
                "channel_id": cid,
                "title": "Demo Creator",
                "country": "PH",
                "subscriber_count": 10000,
                "channel_view_count": 1234567,
                "channel_video_count": 42,
                "uploads_playlist": "UU1234567890123456789012",
            }),
            encoding="utf-8",
        )
        (fixture / "videos_classified.jsonl").write_text(
            json.dumps({
                "video_id": vid,
                "title": "UgPhone AFK Guide",
                "description": "Use https://ugphone.com",
                "tags": ["UgPhone", "AFK"],
                "published_at": "2026-07-31T00:00:00Z",
                "duration_iso8601": "PT5M",
                "duration_seconds": 300,
                "views": 1200,
                "likes": 100,
                "comments": 20,
                "collected_at_utc": "2026-08-01T00:00:00Z",
                "classification": "ugphone",
                "classification_confidence": "confirmed",
                "matched_brands": ["ugphone"],
                "evidence": ["ugphone:title"],
            }) + "\n",
            encoding="utf-8",
        )
        (fixture / "video_snapshots.jsonl").write_text(
            "\n".join([
                json.dumps({"video_id": vid, "collected_at_utc": "2026-07-31T12:00:00Z", "views": 800, "likes": 70, "comments": 10}),
                json.dumps({"video_id": vid, "collected_at_utc": "2026-08-01T00:00:00Z", "views": 1200, "likes": 100, "comments": 20}),
            ]) + "\n",
            encoding="utf-8",
        )

        db = tmp / "hub.sqlite"
        hub = CreatorHub(db)
        result = import_v2(hub, tmp / "v2")
        assert result["creators"] == 1 and result["videos"] == 1
        st = hub.status()
        assert st["videos"] == 1 and st["video_snapshots"] == 2
        assert hub.list_pending_labels(10) == []

        # Human correction is separate from system classification.
        hub.label_video(vid, "competitor", brands=["ldcloud"], actor="self_check", note="manual correction test")

        # Review workflow + boolean queue filtering.
        vid2 = "reviewvideo1"
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO videos(video_id,channel_id,title,description,tags_json,published_at,current_views,current_likes,current_comments,duration_seconds,discovered_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (vid2, cid, "Cloud test", "", json.dumps(["UgPhone"]), "2026-08-02T00:00:00Z", 500, 10, 2, 60, "2026-08-02T00:00:00Z"),
            )
            conn.commit()
        hub.reclassify_videos(only_missing=True)
        assert hub.status()["classification_review"] == 1
        # Classification management lists ALL local videos; pending review is only a filter state.
        cl_all = hub.classification_list(page=1, page_size=30)
        assert cl_all["total"] == 2 and cl_all["all_total"] == 2 and cl_all["pending_total"] == 1
        cl_pending = hub.classification_list(page=1, page_size=30, conditions=[{"field": "review_status", "value": "pending_review"}])
        assert cl_pending["total"] == 1 and cl_pending["rows"][0]["video_id"] == vid2
        rq = hub.review_queue(page=1, page_size=30, conditions=[{"field": "role", "value": "daily"}])
        # Compatibility review_queue remains limited to unresolved review items.
        assert rq["page_size"] == 30 and rq["pages"] >= 1
        rq_all = hub.review_queue(page=1, page_size=30)
        assert rq_all["total"] == 1 and rq_all["rows"][0]["video_id"] == vid2
        rr = hub.reclassify_review_queue()
        assert rr["before"] == 1 and rr["api_calls"] == 0
        hub.review_video(vid2, confirm_system=True, actor="self_check")
        assert hub.status()["classification_review"] == 0

        # Exact-date metric evaluator works fully offline.
        metric = hub.evaluate_metric_spec({
            "type": "constructed",
            "source_field": "current_views",
            "aggregation": "count",
            "from_date": "2026-07-30",
            "to_date": "2026-07-31",
        })
        assert metric["values"][cid] == 1.0
        ratio = hub.evaluate_metric_spec({
            "type": "ratio",
            "numerator_spec": {"source_field": "current_views", "aggregation": "sum", "from_date": "2026-07-30", "to_date": "2026-07-31"},
            "denominator_spec": {"source_field": "current_views", "aggregation": "count", "from_date": "2026-07-30", "to_date": "2026-07-31"},
        })
        assert ratio["values"][cid] == 1200.0

        # Discovery history: rank stays provenance only; list supports boolean filters and score ordering.
        with sqlite3.connect(db) as conn:
            conn.execute(
                """INSERT INTO discovery_hits(query,source,rank,video_id,channel_id,channel_title,title,views,subscribers,country_resolved,country_source,pre_score,opportunity_tier,found_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("demo search", "youtube_api_search", 7, vid, cid, "Demo Creator", "Matched video", 1200, 10000, "PH", "youtube_api", 88.0, "A", "2026-08-13T01:00:00Z"),
            )
            conn.commit()
        hist = hub.discovery_history(page=1, page_size=30, conditions=[{"field": "tier", "value": "A"}], sort="score", direction="desc")
        assert hist["total"] == 1 and hist["rows"][0]["pre_score"] == 88.0

        dash = build_dashboard(db, tmp / "dashboard", hub.settings)
        assert Path(dash["index"]).exists()
        assert (tmp / "dashboard" / "creators" / (cid + ".html")).exists()
        assert (tmp / "dashboard" / "metrics.html").exists()
        for asset in [
            "creator_facts.js", "metric_base.js", "metrics_workspace.js", "metrics_config.js",
            "overview_filters.js", "discovery.js", "table_tools.js", "creator_detail.js", "review.js", "geography.js",
        ]:
            assert (tmp / "dashboard" / "assets" / asset).exists(), asset
        assert not (tmp / "dashboard" / "assets" / "metrics_data.js").exists()

        mh = (tmp / "dashboard" / "metrics.html").read_text(encoding="utf-8")
        assert "指标构建器" in mh and "规则 / 标签构建器" in mh and "应用结果" in mh
        assert 'id="metricOutputType"' in mh and 'value="constructed"' in mh and 'value="ratio"' in mh
        assert 'id="metricInputType"' in mh and 'value="objective"' in mh and 'value="aggregate_label"' in mh
        assert 'value="constructed"' not in mh.split('id="metricInputType"', 1)[1].split('</select>', 1)[0]
        assert 'id="ruleRelation"' not in mh
        assert 'id="ruleConditions"' in mh and 'id="resultFilterConditions"' in mh
        assert "已构建指标" in mh
        assert "resultPageSizeConfirm" in mh and "resultFirst" in mh and "resultLast" in mh and "resultJump" in mh

        index = (tmp / "dashboard" / "index.html").read_text(encoding="utf-8")
        assert "UgPhone视频数" in index and "博主库" in index and 'id="ovFilterConditions"' in index
        assert 'value="ugphone_video_count" selected' in index and '<option value="desc" selected>降序</option>' in index
        assert "查看本地详情" not in index and "查看详情" in index
        assert "竞品博主" not in index and "LDCloud合作博主" in index
        assert 'value="30"' in index and "ovPageSizeConfirm" in index and "ovFirst" in index and "ovLast" in index and "ovJump" in index
        assert "视频指标快照" not in index and "待复核分类" not in index

        labels = (tmp / "dashboard" / "labels.html").read_text(encoding="utf-8")
        assert "离线重新识别全部待复核" in labels
        assert "全部本地视频" in labels and "待人工复核" in labels and "复核状态 / 最终分类" in labels
        assert "当前没有待人工复核的分类" not in labels
        assert 'id="labelFilterConditions"' in labels and 'id="labelPageInfoTop"' in labels
        assert "labelPageSizeConfirm" in labels and "labelFirst" in labels and "labelLast" in labels and "labelJump" in labels
        assert 'value="30"' in labels
        review_js=(tmp / "dashboard" / "assets" / "review.js").read_text(encoding="utf-8")
        assert "/api/videos/classifications" in review_js and "review_status" in review_js and "当前筛选条件下没有视频" in review_js

        disc = (tmp / "dashboard" / "discovery.html").read_text(encoding="utf-8")
        assert "近7天" in disc and "近14天" not in disc
        assert 'id="discoverFromDate"' in disc and 'id="discoverToDate"' in disc
        assert 'id="discoverRegionGroup"' in disc and 'id="discoverCountrySearch"' in disc and 'id="discoverCountry"' in disc
        assert 'id="liveDiscoveryFilters"' in disc and 'id="savedDiscoveryFilters"' in disc
        assert "savedDiscoveryPageSizeConfirm" in disc and "savedDiscoveryFirst" in disc and "savedDiscoveryLast" in disc and "savedDiscoveryJump" in disc
        assert "liveDiscoveryPageSizeConfirm" in disc and "liveDiscoveryFirst" in disc and "liveDiscoveryLast" in disc and "liveDiscoveryJump" in disc
        saved_section = disc.split("已保存的发现记录", 1)[1]
        assert "<th>排名</th>" not in saved_section and "搜索排名" not in saved_section
        geo_js = (tmp / "dashboard" / "assets" / "geography.js").read_text(encoding="utf-8")
        assert "菲律宾" in geo_js and '"PH"' in geo_js and "东南亚" in geo_js

        creator_html = (tmp / "dashboard" / "creators" / (cid + ".html")).read_text(encoding="utf-8")
        assert 'id="detailFilterConditions"' in creator_html and "detailAddFilter" in creator_html
        assert "detailPageSizeConfirm" in creator_html and "detailFirst" in creator_html and "detailLast" in creator_html and "detailJump" in creator_html
        assert "UgPhone优先 + 播放量" in creator_html and "creator_detail.js" in creator_html

        sync_html = (tmp / "dashboard" / "sync.html").read_text(encoding="utf-8")
        assert "syncPageSizeConfirm" in sync_html and "syncFirst" in sync_html and "syncLast" in sync_html and "syncJump" in sync_html
        assert dash["metric_data_mode"] == "python_preaggregated"

        exp = export_all(db, tmp / "exports", "json")
        assert Path(exp["files"][0]).exists()
        assert all(ord(ch) < 128 for ch in Path(exp["files"][0]).name)
        for generated in (tmp / "dashboard").rglob("*"):
            if generated.is_file():
                assert all(ord(ch) < 128 for ch in generated.name), generated.name

        cfg_src = tmp / "metric_cfg.json"
        cfg_dst = tmp / "installed_metrics.json"
        cfg_src.write_text(json.dumps({
            "metrics": [
                {"id": "m1", "name": "UgPhone Median", "type": "constructed", "source_kind": "objective", "source_field": "current_views", "window": "all", "aggregation": "median", "filter_label": "role:ugphone"},
                {"id": "m2", "name": "Ratio", "type": "ratio", "numerator_spec": {"source_field": "current_views", "aggregation": "sum", "window": "all"}, "denominator_spec": {"source_field": "current_views", "aggregation": "count", "window": "all"}},
            ],
            "rules": [{"id": "r1", "name": "Rule", "conditions": [
                {"metric_type": "objective", "metric_key": "subscriber_count", "op": "gte", "value": "1000"},
                {"join": "AND", "metric_type": "constructed", "metric_key": "m1", "op": "gt", "value": "0"},
                {"join": "NOT", "metric_type": "aggregate_label", "metric_key": "unpartnered_creator", "op": "truthy", "value": ""},
            ]}],
            "filters": [{"metric_type": "aggregate_label", "metric_key": "partnered_ugphone", "op": "truthy", "value": ""}],
        }), encoding="utf-8")
        cfg_result = import_metric_config(cfg_src, cfg_dst)
        loaded = load_metric_config(cfg_dst)
        assert cfg_result["metrics"] == 2
        assert loaded["metrics"][1]["type"] == "ratio"
        assert loaded["rules"][0]["conditions"][2]["join"] == "NOT"

        with sqlite3.connect(db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"creators", "videos", "creator_snapshots", "video_snapshots", "discovery_hits", "label_suggestions", "video_labels", "video_label_audit", "sync_runs"}
        assert required <= tables, required - tables

        print("SELF_CHECK_OK")
        print(json.dumps({"tables": len(tables), "dashboard": dash["index"], "status": hub.status(), "geography_countries": len(geo["countries"])}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
