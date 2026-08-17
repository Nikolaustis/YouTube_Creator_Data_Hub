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
from creator_hub.monitoring import monitoring_data_fresh, suspected_inactive_partner
from creator_hub.util import parse_iso
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

    qp = json.loads((ROOT / "config" / "query_packs.json").read_text(encoding="utf-8"))
    assert qp["default_language"] == "en"
    assert set(qp["languages"]) >= {"en", "es-419", "pt-BR", "th", "vi", "id", "ko", "ja", "zh-TW"}
    assert [p["id"] for p in qp["packs"]] == ["core", "farming", "afk", "active", "commercial", "custom"]
    assert "AFK" in next(p for p in qp["packs"] if p["id"] == "afk")["terms"]["en"]
    assert "掛機刷資源" in next(p for p in qp["packs"] if p["id"] == "afk")["terms"]["zh-TW"]

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
        # Video objective filters are server-side and support comparisons / boolean chains.
        assert hub.classification_list(conditions=[{"field":"views","op":"gte","value":"1000"}])["total"] == 1
        assert hub.classification_list(conditions=[{"field":"likes","op":"gt","value":"50"}])["total"] == 1
        assert hub.classification_list(conditions=[{"field":"duration","op":"lte","value":"60"}])["total"] == 1
        assert hub.classification_list(conditions=[{"field":"published","op":"gte","value":"2026-08-01"}])["total"] == 1
        assert hub.classification_list(conditions=[{"field":"views","op":"gte","value":"1000"},{"join":"OR","field":"duration","op":"lte","value":"60"}])["total"] == 2
        rq = hub.review_queue(page=1, page_size=30, conditions=[{"field": "role", "value": "daily"}])
        # Compatibility review_queue remains limited to unresolved review items.
        assert rq["page_size"] == 30 and rq["pages"] >= 1
        rq_all = hub.review_queue(page=1, page_size=30)
        assert rq_all["total"] == 1 and rq_all["rows"][0]["video_id"] == vid2
        rr = hub.reclassify_review_queue()
        assert rr["before"] == 1 and rr["api_calls"] == 0
        hub.review_video(vid2, confirm_system=True, actor="self_check")
        assert hub.status()["classification_review"] == 0

        # Monitoring status inference: only fresh monitored historical partners can be marked suspected inactive.
        settings_for_status=hub.settings
        fixed_now=parse_iso("2026-08-17T12:00:00Z")
        assert monitoring_data_fresh(settings_for_status, priority="normal", last_synced_at="2026-08-16T12:00:00Z", now=fixed_now)
        assert not monitoring_data_fresh(settings_for_status, priority="normal", last_synced_at="2026-08-15T00:00:00Z", now=fixed_now)
        assert suspected_inactive_partner(settings_for_status, monitoring_enabled=1, priority="normal", last_synced_at="2026-08-16T12:00:00Z", ugphone_video_count=2, latest_ugphone_upload="2026-07-01T00:00:00Z", now=fixed_now)
        assert not suspected_inactive_partner(settings_for_status, monitoring_enabled=0, priority="normal", last_synced_at="2026-08-16T12:00:00Z", ugphone_video_count=2, latest_ugphone_upload="2026-07-01T00:00:00Z", now=fixed_now)
        assert not suspected_inactive_partner(settings_for_status, monitoring_enabled=1, priority="normal", last_synced_at="2026-08-15T00:00:00Z", ugphone_video_count=2, latest_ugphone_upload="2026-07-01T00:00:00Z", now=fixed_now)

        # Monitoring cadence: recently synced normal-priority creators are skipped unless forced.
        from creator_hub.util import now_utc
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE creators SET monitoring_enabled=1,priority='normal',last_synced_at=? WHERE channel_id=?",(now_utc(),cid));conn.commit()
        calls=[]
        original_sync_creator=hub.sync_creator
        hub.sync_creator=lambda channel_id,**kwargs: (calls.append(channel_id) or {"videos_processed":0})
        due_run=hub.sync_all(mode="incremental")
        assert due_run["skipped_not_due"] == 1 and calls == []
        force_run=hub.sync_all(mode="incremental",force=True)
        assert force_run["force"] is True and calls == [cid]
        hub.sync_creator=original_sync_creator

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
        hist_geo = hub.discovery_history(page=1, page_size=30, conditions=[{"field": "geo", "value": "southeast_asia", "country": ""}])
        assert hist_geo["total"] == 1 and hist_geo["rows"][0]["country_resolved"] == "PH"
        hist_country = hub.discovery_history(page=1, page_size=30, conditions=[{"field": "geo", "value": "southeast_asia", "country": "PH"}])
        assert hist_country["total"] == 1
        hist_wrong_geo = hub.discovery_history(page=1, page_size=30, conditions=[{"field": "geo", "value": "east_asia", "country": ""}])
        assert hist_wrong_geo["total"] == 0

        # Query Expansion merges multiple query routes by creator, keeping the best hit and coverage count.
        original_discover = hub.discover
        def fake_discover(q, **kwargs):
            score = {"Demo Game": 60.0, "Demo Game AFK": 91.0, "Demo Game guide": 75.0}[q]
            return {"hits": 2, "results": [{"channel_id": cid, "video_id": vid, "channel_title": "Demo Creator", "pre_score": score, "query": q}]}
        hub.discover = fake_discover
        expanded = hub.discover_expanded("Demo Game", ["Demo Game AFK", "Demo Game guide"], max_results=50)
        hub.discover = original_discover
        assert expanded["query_count"] == 3 and expanded["hits"] == 6 and expanded["unique_creators"] == 1
        assert expanded["results"][0]["pre_score"] == 91.0 and expanded["results"][0]["query_coverage"] == 3

        dash = build_dashboard(db, tmp / "dashboard", hub.settings)
        assert Path(dash["index"]).exists()
        assert (tmp / "dashboard" / "creators" / (cid + ".html")).exists()
        assert (tmp / "dashboard" / "metrics.html").exists()
        for asset in [
            "creator_facts.js", "metric_base.js", "metrics_workspace.js", "metrics_config.js",
            "overview_filters.js", "discovery.js", "table_tools.js", "creator_detail.js", "review.js", "geography.js", "query_packs.js",
        ]:
            assert (tmp / "dashboard" / "assets" / asset).exists(), asset
        assert not (tmp / "dashboard" / "assets" / "metrics_data.js").exists()

        mh = (tmp / "dashboard" / "metrics.html").read_text(encoding="utf-8")
        assert "指标构建器" in mh and "规则 / 标签构建器" in mh and "应用结果" in mh
        assert 'id="metricOutputType"' in mh and 'value="constructed"' in mh and 'value="ratio"' in mh
        assert 'id="metricInputType"' not in mh
        assert "博主客观数据" in mh and "博主标签" in mh and "视频客观数据" in mh
        metrics_js=(tmp / "dashboard" / "assets" / "metrics_workspace.js").read_text(encoding="utf-8")
        assert "function fixedPlaybackValue" in metrics_js and "return videoSpecValue(c," in metrics_js
        assert "return side(c," not in metrics_js
        assert "return metricById(sortKey.slice(7))" in metrics_js
        assert "return findMetric(sortKey.slice(7))" not in metrics_js
        assert "suspected_inactive_partner" in metrics_js and "疑似不再合作" in metrics_js
        assert "视频数据只有经过聚合后才成为博主级构建指标" in mh
        assert 'id="ruleRelation"' not in mh
        assert 'id="ruleConditions"' in mh and 'id="resultFilterConditions"' in mh
        assert "已构建指标" in mh
        assert "resultPageSizeConfirm" in mh and "resultFirst" in mh and "resultLast" in mh and "resultJump" in mh

        index = (tmp / "dashboard" / "index.html").read_text(encoding="utf-8")
        assert "UgPhone视频数" in index and "博主库" in index and 'id="ovFilterConditions"' in index
        assert "identity-partnered" in index and "identity-unpartnered" in index and "identity-competitor" in index
        assert "identity-suspected" in index and "疑似不再合作" in index
        assert "优先级" in index and "监控中" in index and "计划周期" in index
        assert 'value="ugphone_video_count" selected' in index and '<option value="desc" selected>降序</option>' in index
        assert "查看本地详情" not in index and "查看详情" in index
        assert "竞品博主" not in index and "LDCloud合作博主" in index
        assert 'value="30"' in index and "ovPageSizeConfirm" in index and "ovFirst" in index and "ovLast" in index and "ovJump" in index
        assert "视频指标快照" not in index and "待复核分类" not in index
        assert 'id="ovFilterStatus"' in index
        overview_js=(tmp / "dashboard" / "assets" / "overview_filters.js").read_text(encoding="utf-8")
        assert "已应用 ${active.length} 个筛选条件" in overview_js

        labels = (tmp / "dashboard" / "labels.html").read_text(encoding="utf-8")
        assert "离线重新识别全部待复核" in labels
        assert "全部本地视频" in labels and "待人工复核" in labels and "复核状态 / 最终分类" in labels
        assert "当前没有待人工复核的分类" not in labels
        assert 'id="labelFilterConditions"' in labels and 'id="labelPageInfoTop"' in labels
        assert "labelPageSizeConfirm" in labels and "labelFirst" in labels and "labelLast" in labels and "labelJump" in labels
        assert 'value="30"' in labels
        review_js=(tmp / "dashboard" / "assets" / "review.js").read_text(encoding="utf-8")
        assert "/api/videos/classifications" in review_js and "review_status" in review_js and "当前筛选条件下没有视频" in review_js
        assert "renderStatic();fetch('/api/ping')" in review_js
        assert "let page=1,size=30" in review_js
        assert "播放量" in review_js and "点赞数" in review_js and "评论数" in review_js and "视频时长（秒）" in review_js and "发布时间" in review_js
        assert "rf-op" in review_js and "numericFields" in review_js
        assert "已对静态预览应用 ${activeConditions.length} 个筛选条件" in review_js
        assert 'id="labelFilterStatus"' in labels

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
        qp_js = (tmp / "dashboard" / "assets" / "query_packs.js").read_text(encoding="utf-8")
        assert "CDH_QUERY_PACKS" in qp_js and "es-419" in qp_js and "pt-BR" in qp_js and "zh-TW" in qp_js
        assert 'id="queryLanguage"' in disc and 'id="queryPackGrid"' in disc and 'id="queryPreview"' in disc
        assert "Query Expansion" in disc and "每个 Query 视频上限" in disc
        disc_js = (tmp / "dashboard" / "assets" / "discovery.js").read_text(encoding="utf-8")
        assert "buildExpandedQueries" in disc_js and "queries" in disc_js and "query_coverage" in disc_js
        assert "grade-a" in disc_js and "grade-b" in disc_js and "grade-c" in disc_js and "grade-d" in disc_js
        assert "地区 / 国家" in disc_js and "全部该区域" in disc_js and "countriesInGroup" in disc_js
        overview_js = (tmp / "dashboard" / "assets" / "overview_filters.js").read_text(encoding="utf-8")
        assert "地理位置" in overview_js and "全部该区域" in overview_js
        metrics_js = (tmp / "dashboard" / "assets" / "metrics_workspace.js").read_text(encoding="utf-8")
        assert "地理位置" in metrics_js and "全部该区域" in metrics_js
        assert "creator_fact" in metrics_js and "creator_label" in metrics_js and "video_fact" in metrics_js
        assert "博主客观数据" in metrics_js and "博主标签" in metrics_js and "视频客观数据" in metrics_js
        assert "ratioNumerator" in metrics_js and "numerator_ref" in metrics_js
        assert "metricInputType" not in metrics_js
        assert "UgPhone视频播放量" in metrics_js and "总视频播放量" in metrics_js and "竞品视频播放量" in metrics_js
        assert "sort-active" in metrics_js and "identity-partnered" in metrics_js

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
        # Legacy v0.x config should migrate to the v1.0 grain model.
        cfg_src.write_text(json.dumps({
            "metrics": [
                {"id": "m1", "name": "UgPhone Median", "type": "constructed", "source_kind": "objective", "source_field": "current_views", "window": "all", "aggregation": "median", "filter_label": "role:ugphone"},
                {"id": "bad_label_metric", "name": "Bad Label Average", "type": "constructed", "source_kind": "aggregate_label", "source_field": "partnered_ugphone", "aggregation": "avg"},
                {"id": "m2", "name": "Ratio", "type": "ratio", "numerator_spec": {"source_field": "current_views", "aggregation": "sum", "window": "all"}, "denominator_spec": {"source_field": "current_views", "aggregation": "count", "window": "all"}},
            ],
            "rules": [{"id": "r1", "name": "Rule", "conditions": [
                {"metric_type": "objective", "metric_key": "subscriber_count", "op": "gte", "value": "1000"},
                {"join": "AND", "metric_type": "constructed", "metric_key": "m1", "op": "gt", "value": "0"},
                {"join": "AND", "metric_type": "constructed", "metric_key": "bad_label_metric", "op": "gt", "value": "0"},
                {"join": "NOT", "metric_type": "aggregate_label", "metric_key": "unpartnered_ugphone", "op": "truthy", "value": ""},
            ]}],
            "filters": [{"metric_type": "aggregate_label", "metric_key": "partnered_ugphone", "op": "truthy", "value": ""}],
        }), encoding="utf-8")
        cfg_result = import_metric_config(cfg_src, cfg_dst)
        loaded = load_metric_config(cfg_dst)
        assert cfg_result["metrics"] == 2  # m1 + ratio; hidden ratio components are not counted publicly
        assert any(m["id"] == "m1" and m["source_kind"] == "video_fact" for m in loaded["metrics"])
        ratio_metric = next(m for m in loaded["metrics"] if m["id"] == "m2")
        assert ratio_metric["type"] == "ratio" and ratio_metric["numerator_ref"]["kind"] == "constructed"
        assert all(m.get("source_kind") != "aggregate_label" for m in loaded["metrics"])
        assert loaded["rules"][0]["conditions"][0]["metric_type"] == "creator_fact"
        assert any(c["metric_type"] == "creator_label" and c["metric_key"] == "partnered_ugphone" for c in loaded["rules"][0]["conditions"])
        assert loaded["filters"][0]["metric_type"] == "creator_label"

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
