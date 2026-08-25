from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creator_hub.dashboard import build_dashboard, creator_facts_payload, metric_base_payload, dashboard_stats_payload
from creator_hub.db import init_db, SCHEMA_VERSION
from creator_hub.exporter import export_all
from creator_hub.geography import geography, group_codes, resolve_country_query
from creator_hub.importers import import_v2, import_business_metrics
from creator_hub.metric_config import import_metric_config, load_metric_config
from creator_hub.monitoring import monitoring_data_fresh, suspected_inactive_partner
from creator_hub.util import parse_iso
from creator_hub.service import CreatorHub
from creator_hub.classifier import suggest_label
from creator_hub.jobs import JobStore


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
    assert (ROOT / "setup.cmd").exists()
    assert (ROOT / "scripts" / "set-api-key.cmd").exists()
    assert (ROOT / "scripts" / "set-ai-key.cmd").exists()
    assert (ROOT / "setup-ai.cmd").exists()
    assert (ROOT / "docs" / "AI.md").exists()
    assert (ROOT / "scripts" / "ai_setup.py").exists()
    assert (ROOT / "scripts" / "python-run.cmd").exists()
    assert (ROOT / "scripts" / "pre_upgrade_backup.py").exists()
    assert (ROOT / "docs" / "INSTALLATION.md").exists()
    assert (ROOT / "docs" / "OPERATIONS.md").exists()
    # Windows CMD release safety: batch launchers must be ASCII-only and use CRLF.
    for batch_file in ROOT.rglob("*.cmd"):
        batch_bytes = batch_file.read_bytes()
        assert b"\r\n" in batch_bytes, f"CMD must use CRLF: {batch_file.relative_to(ROOT)}"
        assert batch_bytes.count(b"\n") == batch_bytes.count(b"\r\n"), f"CMD contains LF-only lines: {batch_file.relative_to(ROOT)}"
        assert all(byte < 128 for byte in batch_bytes), f"CMD must be ASCII-only: {batch_file.relative_to(ROOT)}"
    assert SCHEMA_VERSION == 17

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

    #  classifier regression: discovery/use-case terms are not cloud-phone evidence.
    brand_cfg = json.loads((ROOT / "config" / "brands.json").read_text(encoding="utf-8"))
    assert "afk" not in {x.lower() for x in brand_cfg["classification"]["cloud_entity_terms"]}
    assert "afk" in {x.lower() for x in brand_cfg["classification"]["use_case_terms"]}
    scene_only = suggest_label({"video_id":"6OawBubrO24","title":"Roblox Rivals Script Auto Farm 24/7 AFK","description":"Aimbot ESP auto win","tags":["multi-instance"]}, brand_cfg)
    assert scene_only["suggested_role"] == "daily" and any(str(x).startswith("use_case_not_cloud_evidence:") for x in scene_only["evidence"])
    scene_only_2 = suggest_label({"video_id":"g1wWnYX__eE","title":"AFK Auto Farm Guide","description":"Run 24/7 on PC","tags":[]}, brand_cfg)
    assert scene_only_2["suggested_role"] == "daily"
    redfinger_link = suggest_label({"video_id":"W6jW1fccRic","title":"Anime Origin guide","description":"Refingers download https://cloudemulator.net/app/sign-in?from=creator","tags":[]}, brand_cfg)
    assert redfinger_link["suggested_role"] == "competitor" and "redfinger" in redfinger_link["brands"]
    explicit_cloud = suggest_label({"video_id":"cloudentity01","title":"Best cloud phone for Android","description":"","tags":[]}, brand_cfg)
    assert explicit_cloud["suggested_role"] == "other_cloud_phone"

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
        # v3.6 business metrics fixture: old/manual Creator commercial performance stays in an independent fact layer.
        from openpyxl import Workbook
        biz_book = Workbook()
        biz_ws = biz_book.active
        biz_ws.title = "Creator Business"
        biz_ws.append(["博主名称", "GMV", "拉新", "币种", "周期开始", "周期结束", "采集时间", "备注"])
        biz_ws.append(["Demo Creator", 32735.86, 149145, "USD", "2026-01-01", "2026-06-30", "2026-08-01T00:00:00Z", "legacy signed creator data"])
        biz_book.save(tmp / "v2" / "business_metrics.xlsx")

        # v1.4 legacy discovery migration: preserve raw hits, recover keyword families,
        # remove the v1.3 single Legacy Discovery derived summary, and label provenance.
        legacy_db = tmp / "legacy.sqlite"
        init_db(legacy_db)
        with sqlite3.connect(legacy_db) as conn:
            conn.execute("DELETE FROM meta WHERE key='legacy_discovery_inference_version'")
            legacy_rows = [
                ("Anime Expeditions", "lv1", "lc1", "Legacy One", 80.0),
                ("Anime Expeditions review", "lv2", "lc1", "Legacy One", 92.0),
                ("Anime Expeditions multiple accounts", "lv3", "lc1", "Legacy One", 88.0),
                ("Bee Swarm Simulator", "lv4", "lc2", "Legacy Two", 70.0),
                ("Bee Swarm Simulator guide", "lv5", "lc2", "Legacy Two", 85.0),
                ("the tower", "lv6", "lc3", "Legacy Three", 75.0),
                ("the tower farm while sleeping", "lv7", "lc3", "Legacy Three", 89.0),
            ]
            for i,(q,v,legacy_cid,title,score) in enumerate(legacy_rows):
                conn.execute("INSERT INTO discovery_hits(query,source,video_id,channel_id,channel_title,title,pre_score,found_at) VALUES(?,?,?,?,?,?,?,?)",
                             (q,"web",v,legacy_cid,title,"Video "+v,score,f"2026-08-{10+i:02d}T00:00:00Z"))
            conn.execute("INSERT INTO discovery_runs(run_id,base_query,search_source,started_at,status) VALUES('legacy-history','Legacy Discovery','legacy','2026-08-10T00:00:00Z','legacy')")
            conn.execute("INSERT INTO discovery_creator_results(run_id,channel_id,channel_title,found_at) VALUES('legacy-history','lc1','Legacy One','2026-08-10T00:00:00Z')")
            conn.commit()
        init_db(legacy_db)
        legacy_hub = CreatorHub(legacy_db)
        lhist = legacy_hub.discovery_creator_history(page=1,page_size=100,sort="title",direction="asc")
        assert lhist["total"] == 3
        lbases = {r["base_query"].casefold() for r in lhist["rows"]}
        assert {"anime expeditions","bee swarm simulator","the tower"} == lbases
        assert all(r["base_query_source"] == "inferred" and r["keyword_source_label"] == "历史推断" for r in lhist["rows"])
        anime = next(r for r in lhist["rows"] if r["base_query"].casefold()=="anime expeditions")
        assert anime["query_coverage"] == 3 and anime["hit_video_count"] == 3
        with sqlite3.connect(legacy_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM discovery_hits").fetchone()[0] == len(legacy_rows)
            assert conn.execute("SELECT COUNT(*) FROM discovery_runs WHERE run_id='legacy-history'").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM discovery_hits WHERE run_id LIKE 'legacy-keyword-%'").fetchone()[0] == len(legacy_rows)

        db = tmp / "hub.sqlite"
        hub = CreatorHub(db)
        result = import_v2(hub, tmp / "v2")
        assert result["creators"] == 1 and result["videos"] == 1
        assert result["business_metrics"]["metric_values_upserted"] == 2
        biz = hub.creator_business_metrics(cid)
        assert round(biz["totals"]["gmv"]["value"], 2) == 32735.86
        assert biz["totals"]["gmv"]["currency"] == "USD"
        assert biz["totals"]["gmv"]["captured_at"].startswith("2026-08-01")
        assert int(biz["totals"]["new_users"]["value"]) == 149145
        assert biz["snapshot_semantics"] == "latest_point_in_time_total"

        #  business-metric semantics: GMV from the UgPhone backend is native USD.
        # Currency / FX columns in a legacy workbook are ignored for GMV and no conversion occurs.
        snap_book = Workbook()
        snap_ws = snap_book.active
        snap_ws.title = "Backend Snapshot"
        snap_ws.append(["博主名称", "GMV", "币种", "兑美元汇率", "采集时间"])
        snap_ws.append(["Demo Creator", 100.0, "USD", 1.0, "2026-08-20T00:00:00Z"])
        snap_ws.append(["Demo Creator", 1000.0, "CNY", 0.14, "2026-08-20T00:00:00Z"])
        snap_path = tmp / "business_snapshot.xlsx"
        snap_book.save(snap_path)
        snap_result = import_business_metrics(hub, snap_path, source_type="backend_export")
        assert snap_result["metric_values_upserted"] == 2 and snap_result["gmv_usd_rows"] == 2
        biz_latest = hub.creator_business_metrics(cid)
        assert round(biz_latest["totals"]["gmv"]["value"], 2) == 1100.0
        assert biz_latest["totals"]["gmv"]["currency"] == "USD"
        assert biz_latest["totals"]["gmv"]["captured_at"].startswith("2026-08-20")
        with sqlite3.connect(db) as conn:
            gmv_rows = conn.execute("SELECT metric_value,currency,metric_value_usd,fx_rate_to_usd,fx_status,captured_at,snapshot_kind FROM creator_business_metrics WHERE channel_id=? AND metric_key='gmv' ORDER BY captured_at", (cid,)).fetchall()
            assert any(round(float(r[0]),2)==1000.0 and r[1]=="USD" and round(float(r[2]),2)==1000.0 and float(r[3])==1.0 for r in gmv_rows)
            assert all(r[6] == "point_in_time_total" for r in gmv_rows)
        # Upgrade compatibility: unresolved legacy GMV is automatically normalized to USD.
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO creator_business_metrics(channel_id,metric_key,metric_value,currency,metric_value_usd,fx_status,snapshot_kind,source_type,import_batch,captured_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (cid,"gmv",55.0,"",None,"missing_currency","point_in_time_total","legacy_import","legacy-gmv","2026-08-21T00:00:00Z"))
            conn.commit()
        init_db(db)
        with sqlite3.connect(db) as conn:
            row=conn.execute("SELECT currency,metric_value,metric_value_usd,fx_rate_to_usd,fx_provider,fx_status FROM creator_business_metrics WHERE import_batch='legacy-gmv'").fetchone()
        assert row[0]=="USD" and row[1]==55.0 and row[2]==55.0 and row[3]==1.0 and row[4]=="ugphone_backend_usd" and row[5]=="native_usd"
        assert not hasattr(hub,"business_fx_status") and not hasattr(hub,"resolve_business_fx")
        # Saved Views persist query/display state instead of forcing repeated filter reconstruction.
        sv = hub.save_view("creator_library", "Self Check View", {"sort":"gmv_total","dir":"desc","conditions":[{"field":"gmv_total","op":"gte","value":"1000"}]})
        assert hub.saved_views("creator_library")[0]["config"]["sort"] == "gmv_total"
        assert hub.delete_view(sv["id"])["deleted"] == 1
        st = hub.status()
        assert st["videos"] == 1 and st["video_snapshots"] == 2
        assert hub.list_pending_labels(10) == []

        # v2.0 persistent application settings and discovery workflow.
        hub.set_setting("query_profile", {"language":"en","packs":{"afk":True}})
        assert hub.get_setting("query_profile")["language"] == "en"
        wf=hub.set_creator_workflow(cid,"interested",note="self-check",actor="self_check")
        assert wf["status"] == "interested"
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT status FROM creator_workflow WHERE channel_id=?",(cid,)).fetchone()[0] == "interested"
            assert conn.execute("SELECT COUNT(*) FROM creator_workflow_audit WHERE channel_id=?",(cid,)).fetchone()[0] >= 1

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
        cl_all = hub.classification_list(page=1, page_size=30, include_stats=True)
        assert cl_all["total"] == 2 and cl_all["all_total"] == 2 and cl_all["pending_total"] == 1
        fast_page = hub.classification_list(page=1, page_size=30)
        assert fast_page["total"] == 2 and "all_total" not in fast_page
        cls_stats = hub.classification_stats()
        assert cls_stats["all_total"] == 2 and cls_stats["pending_total"] == 1
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
        calls.clear()
        selected_run=hub.sync_selected([cid],mode="incremental")
        assert selected_run["creators_processed"] == 1 and calls == [cid]
        hub.sync_creator=original_sync_creator

        # Monitoring observability distinguishes due vs stale and stores retry state fields.
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE creators SET last_synced_at='2026-01-01T00:00:00Z',last_sync_status='success',sync_suspended=0 WHERE channel_id=?",(cid,));conn.commit()
        mh=hub.monitoring_health(limit=10)
        assert mh["total"] == 1 and mh["rows"][0]["health_state"] == "stale"

        # v3.5 channel lifecycle: a channels.list miss alone is not a Community Guidelines label;
        # an explicit public-page marker is terminal and leaves historical data intact.
        lifecycle_db = tmp / "lifecycle.sqlite"
        lifecycle_hub = CreatorHub(lifecycle_db)
        lcid="LC"+"1"*22; pcid="PC"+"2"*22
        with sqlite3.connect(lifecycle_db) as conn:
            conn.execute("INSERT INTO creators(channel_id,channel_title,monitoring_enabled,priority,created_at) VALUES(?,?,?,?,?)",(lcid,"Terminated Creator",1,"normal",now_utc()))
            conn.execute("INSERT INTO creators(channel_id,channel_title,monitoring_enabled,priority,created_at) VALUES(?,?,?,?,?)",(pcid,"Pending Creator",1,"normal",now_utc()))
            conn.commit()
        lifecycle_hub._probe_public_channel_page=lambda channel_id: ({"status":"terminated_community","reason":"explicit community marker","source":"public_page","terminal":True} if channel_id==lcid else {"status":"unavailable_pending","reason":"API miss only","source":"public_page","terminal":False})
        terminal=lifecycle_hub._record_sync_failure(lcid,mode="incremental",attempt_id=None,exc=Exception("未找到频道"))
        pending=lifecycle_hub._record_sync_failure(pcid,mode="incremental",attempt_id=None,exc=Exception("未找到频道"))
        assert terminal["availability_status"]=="terminated_community" and terminal["sync_suspended"] is True and terminal["next_retry_at"] is None
        assert pending["availability_status"]=="unavailable_pending" and pending["sync_suspended"] is False and pending["next_retry_at"]
        with sqlite3.connect(lifecycle_db) as conn:
            lr=conn.execute("SELECT availability_status,monitoring_enabled,sync_suspended,next_retry_at FROM creators WHERE channel_id=?",(lcid,)).fetchone()
            pr=conn.execute("SELECT availability_status,monitoring_enabled,sync_suspended,next_retry_at FROM creators WHERE channel_id=?",(pcid,)).fetchone()
        assert tuple(lr[:3])==("terminated_community",0,1) and lr[3] is None
        assert tuple(pr[:3])==("unavailable_pending",1,0) and pr[3]
        lhealth=lifecycle_hub.monitoring_health(page=1,page_size=30)
        termrow=next(x for x in lhealth["rows"] if x["channel_id"]==lcid)
        assert termrow["channel_status"]=="terminated_community" and termrow["health_state"]=="not_applicable" and termrow["monitoring_state"]=="stopped"

        # v3.7 manual availability/content/monitoring overrides preserve system detection for audit.
        ov=lifecycle_hub.set_creator_availability_override([pcid], availability_status="terminated_community", content_status="history_cleared", monitoring_policy="stopped", note="manual confirmation", actor="self_check")
        assert ov["processed"]==1
        ohealth=lifecycle_hub.monitoring_health(page=1,page_size=30)
        orow=next(x for x in ohealth["rows"] if x["channel_id"]==pcid)
        assert orow["channel_status"]=="terminated_community" and orow["system_channel_status"]=="unavailable_pending" and orow["channel_status_source"]=="人工覆盖"
        assert orow["content_status"]=="history_cleared" and orow["monitoring_policy"]=="stopped" and orow["health_state"]=="not_applicable"
        cleared=lifecycle_hub.clear_creator_availability_override([pcid],actor="self_check")
        assert cleared["processed"]==1
        chealth=lifecycle_hub.monitoring_health(page=1,page_size=30)
        crow=next(x for x in chealth["rows"] if x["channel_id"]==pcid)
        assert crow["channel_status"]=="unavailable_pending" and crow["channel_status_source"]=="系统检测"
        with sqlite3.connect(lifecycle_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM creator_availability_override_audit WHERE channel_id=?",(pcid,)).fetchone()[0] >= 2

        # v3.7 persistent Job Center: progress survives page navigation/refresh and completed history survives server recreation.
        js=JobStore(db)
        def job_runner(progress):
            progress(stage="阶段一",message="处理中",current=1,total=2)
            progress(stage="阶段二",message="完成",current=2,total=2)
            return {"processed":2}
        started=js.start(task="selfcheck",title="Self Check Job",runner=job_runner)
        for _ in range(100):
            jj=js.get(started["job_id"])
            if jj and jj["state"] in {"complete","failed"}: break
            time.sleep(0.01)
        assert jj and jj["state"]=="complete" and jj["percent"]==100 and jj["result"]["processed"]==2 and jj["stage"]=="完成"
        js_reloaded=JobStore(db)
        persisted=js_reloaded.get(started["job_id"]); persisted_list=js_reloaded.list(limit=20)
        assert persisted and persisted["state"]=="complete" and any(x["job_id"]==started["job_id"] for x in persisted_list)
        # v3.10 Job Engine: resource queues, cooperative cancel, retry/checkpoint metadata.
        blocker=__import__('threading').Event()
        def cancellable(progress):
            for i in range(50):
                progress(stage="loop",current=i,total=50,checkpoint={"current":i})
                time.sleep(0.002)
            return {"ok":True}
        cj=js.start(task="cancel-test",title="Cancel Test",runner=cancellable,payload={"ids":[1,2]},resource_class="local",resumable=True)
        time.sleep(0.01);js.cancel(cj["job_id"])
        for _ in range(100):
            cc=js.get(cj["job_id"])
            if cc and cc["state"] in {"cancelled","complete","failed"}: break
            time.sleep(0.01)
        assert cc and cc["state"]=="cancelled" and cc["resource_class"]=="local" and isinstance(cc.get("checkpoint"),dict)

        # v3.10 provenance contract: Human overrides AI/Derived/Fact deterministically.
        hub.contracts.assert_value("creator",cid,"demo.field","fact",1,source_ref="self_check")
        hub.contracts.assert_value("creator",cid,"demo.field","derived",2,source_ref="self_check")
        hub.contracts.assert_value("creator",cid,"demo.field","ai",3,source_ref="self_check")
        hub.contracts.assert_value("creator",cid,"demo.field","human",4,source_ref="self_check")
        eff=hub.effective_value("creator",cid,"demo.field")
        assert eff and eff["value"]==4 and eff["effective_layer"]=="human"

        # v3.10 immutable Run Specification can be saved/cloned.
        rspec=hub.runs.save("ask_hub","Spec Test",{"request":{"question":"test"}})
        clone=hub.clone_run_spec(rspec["id"]); assert clone["parent_spec_id"]==rspec["id"] and clone["spec"]==rspec["spec"]
        # Clone & Re-run must pass the stored final plan/queries back to AI Search rather than re-plan.
        frozen=hub.runs.save("ai_query_search","Frozen Spec",{"request":{"query":"Anime Expeditions","language":"en","search_requirements":"AFK","max_queries":2,"max_results":10},"plan":{"queries":["Anime Expeditions","Anime Expeditions AFK"],"fit_criteria":{"prefer_long_term":True}},"execution":{"queries":["Anime Expeditions","Anime Expeditions AFK"],"profile_budget":25,"prompt_version":"frozen-v1"}})
        ai_obj=hub._ai(); original_qs=ai_obj.query_search; original_hub_ai=hub._ai; captured={}
        def _fake_qs(query,**kwargs): captured.update(query=query,**kwargs); return {"ok":True,"frozen":True}
        ai_obj.query_search=_fake_qs; hub._ai=lambda: ai_obj
        try: frozen_out=hub.execute_run_spec(frozen["id"])
        finally: ai_obj.query_search=original_qs; hub._ai=original_hub_ai
        assert frozen_out["frozen"] is True and captured["frozen_plan"]["fit_criteria"]["prefer_long_term"] is True and captured["frozen_execution"]["queries"][1].endswith("AFK") and captured["parent_spec_id"]==frozen["id"]

        # v2.1 unified table policy: monitoring health defaults to 30 rows/page.
        health_db = tmp / "health_paging.sqlite"
        health_hub = CreatorHub(health_db)
        with sqlite3.connect(health_db) as conn:
            for i in range(65):
                hcid = f"HC{i:022d}"[:24]
                conn.execute("INSERT INTO creators(channel_id,channel_title,monitoring_enabled,priority,created_at,last_synced_at) VALUES(?,?,?,?,?,?)",
                             (hcid,f"Health Creator {i:02d}",1,"normal",now_utc(),"2026-08-01T00:00:00Z"))
            conn.commit()
        hp1=health_hub.monitoring_health(page=1,page_size=30); hp2=health_hub.monitoring_health(page=2,page_size=30); hp3=health_hub.monitoring_health(page=3,page_size=30)
        assert hp1["total"] == 65 and hp1["pages"] == 3 and len(hp1["rows"]) == 30
        assert len(hp2["rows"]) == 30 and len(hp3["rows"]) == 5
        #  monitoring table filtering/sorting is server-backed and shares effective status semantics.
        hf=health_hub.monitoring_health(page=1,page_size=30,search="Health Creator 05",filters={"health_state":"stale","priority":"normal"},sort="channel_title",direction="desc")
        assert hf["total"] == 1 and hf["rows"][0]["channel_title"] == "Health Creator 05" and hf["sort"] == "channel_title"
        hs=health_hub.monitoring_health(page=1,page_size=5,sort="channel_title",direction="desc")
        assert hs["rows"][0]["channel_title"] > hs["rows"][-1]["channel_title"]

        # v2.1 classification cross-page selection resolves the whole current filter server-side.
        select_db = tmp / "selection.sqlite"
        select_hub = CreatorHub(select_db)
        scid="SC"+"1"*22
        with sqlite3.connect(select_db) as conn:
            conn.execute("INSERT INTO creators(channel_id,channel_title,created_at) VALUES(?,?,?)",(scid,"Selection Creator",now_utc()))
            for i in range(70):
                svid=f"sv{i:09d}"[:11]
                conn.execute("INSERT INTO videos(video_id,channel_id,title,tags_json,published_at,current_views,discovered_at) VALUES(?,?,?,?,?,?,?)",
                             (svid,scid,f"Selection {i}","[]","2026-08-01T00:00:00Z",i,now_utc()))
                srole="ugphone" if i<40 else "daily"
                conn.execute("INSERT INTO label_suggestions(video_id,suggested_role,brands_json,confidence,evidence_json,generated_at,rule_version) VALUES(?,?,?,?,?,?,?)",
                             (svid,srole,"[]","high","[]",now_utc(),"self_check"))
            conn.commit()
        mids=select_hub.classification_matching_ids(conditions=[{"field":"role","value":"ugphone"}])
        assert len(mids) == 40
        batch=select_hub.batch_review_matching({"conditions":[{"field":"role","value":"ugphone"}],"exclude_ids":mids[:2]},"confirm_system",actor="self_check")
        assert batch["processed"] == 38 and not batch["errors"]
        with sqlite3.connect(select_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM video_labels").fetchone()[0] == 38
            # Human correction is the effective business classification; system suggestion remains auditable.
            changed=mids[2]
            conn.execute("UPDATE video_labels SET human_role='daily' WHERE video_id=?",(changed,));conn.commit()
        eff=select_hub.classification_list(conditions=[{"field":"role","value":"daily"},{"field":"human_system_mismatch","value":"mismatch"}],page_size=100)
        assert any(r["video_id"]==changed and r["effective_role"]=="daily" and r["suggested_role"]=="ugphone" and r["classification_source"]=="human" for r in eff["rows"])

        # Consistent backup/restore through SQLite Backup API.
        hub.set_setting("dashboard_preferences", {"selfcheck":1})
        backup_path=tmp / "safe.sqlite"
        bk=hub.backup_database(destination=backup_path,note="self_check")
        assert bk["ok"] and backup_path.exists() and str(bk["quick_check"]).lower()=="ok"
        hub.set_setting("dashboard_preferences", {"selfcheck":2})
        rs=hub.restore_database(backup_path,create_pre_backup=False)
        assert rs["ok"] and hub.get_setting("dashboard_preferences")["selfcheck"] == 1
        light_health=hub.database_health(run_check=False)
        assert light_health["check"] == "not_run" and light_health["ok"] is None
        checked=hub.database_health()
        assert checked["ok"] is True and str(checked["check"]).lower()=="ok"

        # Snapshot lifecycle compaction preserves recent snapshots and compacts old same-bucket duplicates.
        with sqlite3.connect(db) as conn:
            for i in range(3):
                conn.execute("INSERT OR IGNORE INTO video_snapshots(video_id,captured_at,views,likes,comments) VALUES(?,?,?,?,?)",(vid,f"2025-01-01T0{i}:00:00Z",100+i,1,1))
            conn.commit()
        dry=hub.compact_snapshots(dry_run=True)
        assert dry["video_snapshots_to_delete"] >= 2
        compact=hub.compact_snapshots()
        assert compact["video_snapshots_deleted"] >= 2

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
        with sqlite3.connect(db) as conn:
            src = conn.execute("SELECT base_query,base_query_source FROM discovery_runs WHERE run_id=?",(expanded["run_id"],)).fetchone()
            assert src and src[0] == "Demo Game" and src[1] == "exact"

        # v3.1 AI-OFF guarantee: AI is optional and core startup remains healthy without a key/provider.
        ai_off = hub.ai_status()
        assert ai_off["enabled"] is False and ai_off["available"] is False
        assert hub.status()["videos"] >= 2

        # Offline Mock provider validates the AI enhancement layer without network/API credentials.
        cid2 = "UC2234567890123456789012"
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO creators(channel_id,channel_title,handle,subscriber_count,channel_view_count,monitoring_enabled,priority,created_at) VALUES(?,?,?,?,?,?,?,?)",(cid2,"Second Creator","@secondcreator",5000,500000,1,"normal",now_utc()))
            conn.commit()
        # A real API key may already be configured on the user's machine. Mock must
        # ignore it completely rather than leaking that host state into self-check.
        prior_ai_key = os.environ.get("CREATOR_HUB_AI_API_KEY")
        os.environ["CREATOR_HUB_AI_API_KEY"] = "self-check-key-that-mock-must-ignore"
        try:
            hub.configure_ai({"enabled":True,"protocol":"mock","model":"mock-v1","daily_request_soft_limit":100})
            ai_on = hub.ai_status()
            assert ai_on["enabled"] and ai_on["available"] and ai_on["protocol"] == "mock" and ai_on["api_key_present"] is False
        finally:
            if prior_ai_key is None:
                os.environ.pop("CREATOR_HUB_AI_API_KEY", None)
            else:
                os.environ["CREATOR_HUB_AI_API_KEY"] = prior_ai_key
        ab = hub.ai_creator_brief(cid)
        assert ab["result"]["summary"] and ab["finding_id"]
        ac = hub.ai_compare_creators([cid,cid2])
        assert len(ac["result"]["ranking"]) == 2
        aq = hub.ai_query_planner("Demo Game", language="en")
        assert len(aq["result"]["queries"]) >= 1 and "fit_criteria" in aq["result"]
        aq_fit=hub.ai_query_planner("Anime Expeditions",language="en",objective="优先寻找长期制作AFK、挂机、多开等适配云手机使用场景的的中小体量博主")
        assert aq_fit["result"]["fit_criteria"]["subscriber_max"] == 100000 and aq_fit["result"]["fit_criteria"]["prefer_long_term"] is True
        assert {"AFK","multi-instance","multi account"}.issubset(set(aq_fit["result"]["fit_criteria"]["search_concepts"]))
        fitc=aq_fit["result"]["fit_criteria"]
        assert fitc["long_term_min_videos"]==5 and fitc["long_term_min_months"]==3
        assert fitc["exclude_official_channels"] is True and fitc["exclude_script_cheat_channels"] is True
        assert {"multiple accounts","alt account","alts"} <= {str(x).casefold() for x in fitc.get("search_concepts",[])}
        assert "≤100,000" in str(aq_fit["result"].get("strategy") or "") or "100,000" in str(aq_fit["result"].get("strategy") or "")
        assert len(aq_fit["result"]["queries"]) <= 12
        agent=hub._ai()
        assert agent._canonical_query("Anime Expeditions","Anime Expeditions Anime Expeditions") == "Anime Expeditions"

        #  Creator sourcing gate: channel-level topic context validates continuity;
        # language is checked on recent titles; unsafe but non-primary channels are separated into a risk pool;
        # scripts/official sources are removed; unprofiled candidates remain pending rather than failed.
        good="AG"+"1"*22; mildrisk="AR"+"7"*22; foreignc="AL"+"8"*22; scriptc="AS"+"2"*22; cloudc="AC"+"3"*22; gamec="AO"+"4"*22; offvid="AV"+"5"*22; unprofiled="AU"+"6"*22
        months=["2026-01-01T00:00:00Z","2026-01-15T00:00:00Z","2026-02-01T00:00:00Z","2026-02-15T00:00:00Z","2026-03-01T00:00:00Z","2026-03-15T00:00:00Z"]
        def recent(prefix, suffix="Anime Expeditions AFK Farm Guide"):
            return [{"title":f"{suffix} {i}","published_at":d,"video_id":f"x{i:010d}"[:11]} for i,d in enumerate(months)]
        risk_recent=recent("r")
        risk_recent[0]={"title":"How To AFK Farm Hack Guide","published_at":months[0],"video_id":"risk0000001"}
        thai_recent=[{"title":f"วิธีฟาร์มออโต้ AFK เกมนี้ {i}","published_at":d,"video_id":f"t{i:010d}"[:11]} for i,d in enumerate(months)]
        profiles={
            good:recent("g"), mildrisk:risk_recent, foreignc:thai_recent,
            scriptc:recent("s","AFK Script Hack Keyless"), cloudc:recent("c"), gamec:recent("o"), offvid:recent("v"), unprofiled:[],
        }
        pmeta={
            "profiled_creators":7,"profile_api_calls":0,"profile_errors":[],
            "profile_status":{good:"profiled",mildrisk:"profiled",foreignc:"profiled",scriptc:"profiled",cloudc:"profiled",gamec:"profiled",offvid:"profiled",unprofiled:"profile_error"},
            "channel_details":{
                good:{"title":"Good Creator","description":"Anime Expeditions guides"},
                mildrisk:{"title":"Risk Creator","description":"Anime Expeditions guides"},
                foreignc:{"title":"Thai Creator","description":"Anime Expeditions guides"},
                scriptc:{"title":"Script Hub","description":""},
                cloudc:{"title":"UgPhone Cloud Phone","description":""},
                gamec:{"title":"Anime Expeditions Official","description":"Official YouTube channel"},
                offvid:{"title":"Roblox Official","description":"Official YouTube channel"},
                unprofiled:{"title":"Unverified Creator","description":""},
            },
        }
        rows=[
            {"channel_id":good,"channel_title":"Good Creator","subscribers":20000,"title":"Anime Expeditions AFK Guide","query_coverage":3},
            {"channel_id":mildrisk,"channel_title":"Risk Creator","subscribers":20000,"title":"Anime Expeditions AFK Guide","query_coverage":3},
            {"channel_id":foreignc,"channel_title":"Thai Creator","subscribers":20000,"title":"Anime Expeditions AFK Guide","query_coverage":3},
            {"channel_id":scriptc,"channel_title":"Script Hub","subscribers":20000,"title":"Anime Expeditions AFK Script Hack","query_coverage":3},
            {"channel_id":cloudc,"channel_title":"UgPhone Cloud Phone","subscribers":20000,"title":"Anime Expeditions AFK Guide","query_coverage":3},
            {"channel_id":gamec,"channel_title":"Anime Expeditions Official","subscribers":20000,"title":"Anime Expeditions AFK Guide","query_coverage":3},
            {"channel_id":offvid,"channel_title":"Roblox Official","subscribers":20000,"title":"Anime Expeditions Official Trailer","query_coverage":3},
            {"channel_id":unprofiled,"channel_title":"Unverified Creator","subscribers":20000,"title":"Anime Expeditions AFK Guide","query_coverage":3},
        ]
        fit_plan={"fit_criteria":{
            "subscriber_min":None,"subscriber_max":100000,"search_concepts":["AFK","multiple accounts","alt account"],"preferred_terms":["AFK","multiple accounts","alt account"],
            "exclude_terms":[],"continuity_terms":["AFK"],"require_topic_match":True,"prefer_long_term":True,
            "long_term_min_videos":5,"long_term_min_months":3,"exclude_official_channels":True,"exclude_script_cheat_channels":True,
            "creator_language":"en","creator_language_min_ratio":0.60,
        }}
        orig_profiles=agent._recent_upload_profiles
        agent._recent_upload_profiles=lambda _rows,limit=100,progress=None:(profiles,pmeta)
        try:
            retained,fit_meta=agent._agent_fit("Anime Expeditions","寻找长期制作AFK、挂机、多开的中小体量博主",fit_plan,{"results":rows})
        finally:
            agent._recent_upload_profiles=orig_profiles
        assert [r["channel_id"] for r in retained] == [good,mildrisk]
        assert retained[0]["candidate_pool"] == "推荐候选" and retained[1]["candidate_pool"].startswith("风险候选")
        assert retained[0]["continuity_gate_passed"] is True and retained[0]["profile_verification_status"]=="已验证"
        assert retained[0]["creator_language_status"] == "匹配" and float(retained[0]["creator_language_ratio"]) >= 0.60
        assert retained[0]["representative_fit_video_id"] and retained[0]["representative_fit_video_title"]
        assert retained[0]["representative_topic_video_title"] and retained[0]["representative_use_case_video_title"]
        assert all(k in retained[0] for k in ["topic_affinity_score","use_case_continuity_score","content_fit_score","continuity_fit_score","brand_safety_score","audience_size_fit_score","query_coverage_score"])
        cats=fit_meta["filtered_categories"]
        assert cats.get("script_cheat",0)>=1 and cats.get("official_cloud_phone",0)>=1 and cats.get("official_game",0)>=1 and cats.get("official_game_video",0)>=1
        assert cats.get("creator_language",0)>=1
        assert fit_meta.get("pending_verification",0)>=1 and cats.get("profile_unverified",0)==0
        assert fit_meta.get("recommended_candidates",0)>=1 and fit_meta.get("risk_candidates",0)>=1
        assert retained[0].get("channel_topic_context_verified") is True and retained[0].get("objective_recent_videos") == 6
        assert hub.ai_models({"enabled":True,"protocol":"mock","model":"mock-v1"})["models"] == ["mock-v1"]
        assert hub.ai_test()["result"]["message"]
        original_expanded = hub.discover_expanded
        def fake_ai_expanded(base_query, queries=None, **kwargs):
            assert kwargs.get("search_source") == "api"
            with sqlite3.connect(db) as conn:
                conn.execute("INSERT OR REPLACE INTO discovery_runs(run_id,base_query,search_source,started_at,status) VALUES(?,?,?,?,?)",("ai-search-test",base_query,"api",now_utc(),"complete"));conn.commit()
            return {"run_id":"ai-search-test","query_count":1+len(queries or []),"hits":7,"unique_creators":2,"queries_executed":[base_query]+list(queries or []),"results":[{"channel_id":cid,"channel_title":"Demo Creator","subscribers":10000,"country_resolved":"PH","pre_score":88.0,"title":"Matched video","views":1200,"query_coverage":2},{"channel_id":cid2,"channel_title":"Second Creator","subscribers":5000,"country_resolved":"TH","pre_score":70.0,"title":"Second video","views":500,"query_coverage":1}]}
        hub.discover_expanded = fake_ai_expanded
        asearch = hub.ai_query_search("Demo Game",language="en",max_queries=5,max_results=10)
        hub.discover_expanded = original_expanded
        assert asearch["youtube_api_used"] is True and asearch["discovery"]["unique_creators"] == 2 and asearch["result_set_id"]
        ars=hub.ai_result_set(asearch["result_set_id"],page=1,page_size=30)
        assert ars["total"] == 2 and all("objective_fit_score" in r and "local_data_status" in r for r in ars["rows"])
        assert "query_funnel" in (ars.get("result_set",{}).get("metadata") or {})
        aa = hub.ai_ask("show creators")
        assert "plan" in aa and isinstance(aa["rows"],list) and aa["result_set_id"] and aa["count"] >= 2
        ar=hub.ai_result_set(aa["result_set_id"],page=1,page_size=1,sort="subscribers",direction="desc")
        assert ar["total"] == aa["count"] and len(ar["rows"]) == 1 and ar["pages"] >= 2
        arf=hub.ai_result_set(aa["result_set_id"],conditions=[{"field":"subscribers","op":">=","value":"9000"}])
        assert arf["total"] >= 1
        arh=hub.ai_result_history(page=1,page_size=30)
        assert arh["total"] >= 2 and arh["page_size"] == 30
        sugg=hub.creator_suggestions("Demo",limit=10)
        assert sugg and sugg[0]["channel_id"] == cid
        aa2=hub.ai_ask("show creators")
        assert aa2["cached"] is True and aa2["run_id"] != aa["run_id"] and aa2["result_set_id"] != aa["result_set_id"]
        aw = hub.ai_weekly_brief()
        assert aw["result"]["headline"] and aw.get("brief_metrics")
        ah = hub.ai_history(page=1,page_size=30)
        assert ah["total"] >= 5 and ah["page_size"] == 30
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM ai_findings").fetchone()[0] >= 1
            assert conn.execute("SELECT COUNT(*) FROM ai_evidence").fetchone()[0] >= 1
            assert conn.execute("SELECT COUNT(*) FROM ai_result_sets").fetchone()[0] >= 3
            assert conn.execute("SELECT COUNT(*) FROM ai_result_items").fetchone()[0] >= 2
            assert {r[1] for r in conn.execute("PRAGMA table_info(ai_runs)")} >= {"source_json","result_json","cache_hit"}
            linked=conn.execute("SELECT ai_run_id FROM discovery_runs WHERE run_id='ai-search-test'").fetchone()
            assert linked and linked[0]
        hub.configure_ai({"enabled":False,"protocol":"openai_responses","model":""})
        assert hub.ai_status()["enabled"] is False

        # v3.3 live Dashboard payloads and batch capture: write SQLite once, refresh facts/cubes without rebuilding HTML.
        live_facts=creator_facts_payload(db,hub.settings)
        live_stats=dashboard_stats_payload(db)
        live_base=metric_base_payload(db,hub.settings)
        assert any(x["channel_id"]==cid and int(x["stored_videos"] or 0)>=2 for x in live_facts["creators"])
        assert live_stats["videos"] >= 2 and cid in live_base["cubes"]
        original_capture=hub.capture_window
        capture_calls=[]
        def fake_capture(ref, **kwargs):
            capture_calls.append((ref,kwargs));return {"channel_id":ref,"videos_processed":3}
        hub.capture_window=fake_capture
        batch_capture=hub.batch_capture_creators([cid,"UC9999999999999999999999"],window="full")
        hub.capture_window=original_capture
        assert batch_capture["processed"]==2 and batch_capture["videos_processed"]==6
        assert all(call[1].get("full_history") is True for call in capture_calls)

        dash = build_dashboard(db, tmp / "dashboard", hub.settings)
        assert Path(dash["index"]).exists()
        assert (tmp / "dashboard" / "creators" / (cid + ".html")).exists()
        assert (tmp / "dashboard" / "metrics.html").exists()
        for asset in [
            "creator_facts.js", "metric_base.js", "field_registry.js", "metrics_workspace.js", "metrics_config.js",
            "overview_filters.js", "discovery.js", "table_tools.js", "creator_detail.js", "review.js", "geography.js", "query_packs.js", "section_nav.js", "maintenance.js", "ai_copilot.js", "product_ui.js", "saved_views.js", "business_metrics.js",
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
        assert "activeRule:''" in metrics_js and "state.activeRule=''" in metrics_js
        assert "当前条件：" in metrics_js and "当前规则：" in metrics_js
        assert "清除全部条件" in mh and 'id="resultConditionStatus"' in mh
        assert "视频数据只有经过聚合后才成为博主级构建指标" in mh
        assert 'id="ruleRelation"' not in mh
        assert 'id="ruleConditions"' in mh and 'id="resultFilterConditions"' in mh
        assert "已构建指标" in mh
        assert "resultPageSizeConfirm" in mh and "resultFirst" in mh and "resultLast" in mh and "resultJump" in mh
        assert 'data-section-nav="metrics-builder"' in mh and 'data-section-nav="metrics-results"' in mh
        for anchor in ["metrics-builder","metrics-rule-builder","metrics-saved","metrics-rules","metrics-results"]:
            assert f'id="{anchor}"' in mh

        index = (tmp / "dashboard" / "index.html").read_text(encoding="utf-8")
        assert "UgPhone视频数" in index and "博主库" in index and 'id="ovFilterConditions"' in index
        assert "identity-partnered" in index and "identity-unpartnered" in index and "identity-competitor" in index
        assert "identity-suspected" in index and "疑似不再合作" in index
        assert "商业表现" in index and "GMV" in index and ">详情</button>" in index
        assert 'id="ovSavedView"' in index and 'product_ui.js' in index and 'saved_views.js' in index
        assert 'value="ugphone_video_count" selected' in index and '<option value="desc" selected>降序</option>' in index
        assert "查看本地详情" not in index and ">详情</button>" in index
        assert "竞品博主" not in index and "LDCloud合作博主" in index
        assert 'value="30"' in index and "ovPageSizeConfirm" in index and "ovFirst" in index and "ovLast" in index and "ovJump" in index
        assert "视频指标快照" not in index and "待复核分类" not in index
        assert 'id="ovFilterStatus"' in index
        assert 'id="ovSelectAllResults"' in index and 'id="ovClearSelection"' in index and 'id="ovSelectionStatus"' in index
        assert 'data-section-nav="overview-summary"' in index and 'data-section-nav="overview-library"' in index
        assert 'id="overview-summary"' in index and 'id="overview-identity"' in index and 'id="overview-library"' in index
        overview_js=(tmp / "dashboard" / "assets" / "overview_filters.js").read_text(encoding="utf-8")
        assert "已应用 ${active.length} 个筛选条件" in overview_js
        assert "/api/creators/facts" in overview_js and "/api/dashboard/stats" in overview_js and "/api/metrics/base" in overview_js
        assert "cdh-data-revision" in overview_js
        job_js=(tmp / "dashboard" / "assets" / "job_progress.js").read_text(encoding="utf-8")
        assert "/api/jobs/start" in job_js and "/api/jobs/status" in job_js and "job-dock" in job_js
        assert "cdhJobMin" in job_js and "cdhJobClose" in job_js and "job-card-dismiss" in job_js and "job-launcher" in job_js
        table_js=(tmp / "dashboard" / "assets" / "table_tools.js").read_text(encoding="utf-8")
        assert "highlightHeaders" in table_js and "filter-sort-active" in table_js
        assert "enhanceSmartTable" in table_js and "smart-scroll-top" not in table_js and "table-layout:fixed" in (ROOT / "creator_hub" / "dashboard.py").read_text(encoding="utf-8")

        labels = (tmp / "dashboard" / "labels.html").read_text(encoding="utf-8")
        assert "离线重新识别全部系统分类" in labels and "仅重新识别待复核" in labels
        assert "全部本地视频" in labels and "待人工复核" in labels and "有效分类（人工优先）" in labels and "系统原始分类" in labels
        assert "当前没有待人工复核的分类" not in labels
        assert 'id="labelFilterConditions"' in labels and 'id="labelPageInfoTop"' in labels
        assert "labelPageSizeConfirm" in labels and "labelFirst" in labels and "labelLast" in labels and "labelJump" in labels
        assert 'value="30"' in labels
        assert 'id="reviewSelectAllResults"' in labels and 'id="reviewClearSelection"' in labels and 'id="reviewSelectionStatus"' in labels
        assert 'data-section-nav="labels-summary"' in labels and 'data-section-nav="labels-results"' in labels
        for anchor in ["labels-summary","labels-policy","labels-filter","labels-results"]:
            assert f'id="{anchor}"' in labels
        review_js=(tmp / "dashboard" / "assets" / "review.js").read_text(encoding="utf-8")
        assert "/api/videos/classifications" in review_js and "review_status" in review_js and "当前筛选条件下没有视频" in review_js
        assert "staticRows.forEach(r=>r.style.display='none')" in review_js and "正在读取完整数据库第一页" in review_js
        assert "/api/videos/classification-stats" in review_js and "/api/review/reclassify-all" in review_js
        assert "cdh-data-revision" in review_js
        assert "let page=1,size=30" in review_js
        assert "播放量" in review_js and "点赞数" in review_js and "评论数" in review_js and "视频时长（秒）" in review_js and "发布时间" in review_js
        assert "rf-op" in review_js and "numericFields" in review_js
        assert "已对静态预览应用 ${activeConditions.length} 个筛选条件" in review_js
        assert 'id="labelFilterStatus"' in labels
        assert 'id="labelTable"' in labels and 'data-field="role effective_role"' in labels and 'data-field="system_role"' in labels
        assert 'data-col="system_role"' in labels and 'syncVisibleColumns' in (ROOT / 'creator_hub' / 'static' / 'review.js').read_text(encoding='utf-8')
        assert hub.classification_list(page=1,page_size=30,sort='system_role',direction='asc')['total'] == cl_all['total']

        disc = (tmp / "dashboard" / "discovery.html").read_text(encoding="utf-8")
        assert "近7天" in disc and "近14天" not in disc
        assert 'id="discoverFromDate"' in disc and 'id="discoverToDate"' in disc
        assert 'id="discoverRegionGroup"' in disc and 'id="discoverCountrySearch"' in disc and 'id="discoverCountry"' in disc
        assert 'id="liveDiscoveryFilters"' in disc and 'id="savedDiscoveryFilters"' in disc and 'id="savedCreatorFilters"' in disc
        assert 'id="liveDiscoveryExport"' in disc and 'id="savedCreatorExport"' in disc and 'id="savedDiscoveryExport"' in disc
        assert '已保存的发现记录 · 博主' in disc and '已保存的发现记录 · 视频命中' in disc
        assert 'id="discovery-search"' in disc and 'id="discovery-current-creators"' in disc and 'id="discovery-saved-creators"' in disc and 'id="discovery-saved-videos"' in disc
        assert 'data-section-nav="discovery-search"' in disc and 'section_nav.js' in disc
        assert '<th data-field="query">原关键词</th>' not in disc and '<th data-field="run">搜索批次</th>' not in disc and '博主 / 首次重复' not in disc
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
        assert 'id="liveSelectAllResults"' in disc and 'id="liveClearSelection"' in disc and 'id="liveSelectionStatus"' in disc
        assert 'id="savedCreatorSelectAllResults"' in disc and 'id="savedCreatorClearSelection"' in disc and 'id="savedCreatorSelectionStatus"' in disc
        disc_js = (tmp / "dashboard" / "assets" / "discovery.js").read_text(encoding="utf-8")
        assert "buildExpandedQueries" in disc_js and "queries" in disc_js and "query_coverage" in disc_js
        assert "/api/settings/get" in disc_js and "query_profile" in disc_js
        assert "workflow" in disc_js and "永久排除" in disc_js and "首次发现" in disc_js and "重复发现" in disc_js
        assert "/api/creators/batch" in disc_js
        assert "/api/creators/capture-batch" in disc_js and "FULL_HISTORY_LIMIT" in disc_js
        assert "入库与抓取 ▾" in disc and "抓取并入库" in disc and "全历史（最多 10,000 条）" in disc
        assert "/api/discovery/creators" in disc_js and "discovery_creators" in disc_js and "discovery_videos" in disc_js
        assert "keyword_source_label" in disc_js and "历史推断" in disc_js
        section_js=(tmp / "dashboard" / "assets" / "section_nav.js").read_text(encoding="utf-8")
        assert "scrollIntoView" in section_js and "section-active" in section_js and "data-section-nav" in section_js
        server_src=(ROOT / "creator_hub" / "server.py").read_text(encoding="utf-8")
        assert '("base_query","原关键词"),("keyword_source_label","关键词来源")' in server_src
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
        assert "/api/settings/get" in metrics_js and "/api/settings/set" in metrics_js
        assert "/api/creators/facts" in metrics_js and "/api/metrics/base" in metrics_js and "cdh-data-revision" in metrics_js
        assert "metricDependencies" in metrics_js and "指标分组" in mh and "业务说明" in mh
        assert 'id="metricCatalogSearch"' in mh and 'id="metricGroupFilter"' in mh and 'id="metricCatalogSort"' in mh
        assert 'id="metricCatalogPageSize"' in mh and 'id="metricCatalogFirst"' in mh and 'id="metricCatalogLast"' in mh and 'id="metricMoveGroupBtn"' in mh
        assert 'id="ruleCatalogSearch"' in mh and 'id="ruleGroupFilter"' in mh and 'id="ruleCatalogSort"' in mh
        assert 'id="ruleCatalogPageSize"' in mh and 'id="ruleCatalogFirst"' in mh and 'id="ruleCatalogLast"' in mh and 'id="ruleMoveGroupBtn"' in mh
        assert "metricCatalogSelected" in metrics_js and "ruleCatalogSelected" in metrics_js and "moveMetricGroup" in metrics_js and "moveRuleGroup" in metrics_js
        assert "metricCatalogSize=30" in metrics_js and "ruleCatalogSize=30" in metrics_js and "__ungrouped__" in metrics_js
        field_js=(tmp / "dashboard" / "assets" / "field_registry.js").read_text(encoding="utf-8")
        assert "CDHFieldRegistry" in field_js and "field-picker-search" in field_js and "LS_RECENT" in field_js and "LS_FAV" in field_js
        assert "resultSortEntries" in metrics_js and "mountFieldPicker" in metrics_js and "metricFieldEntries" in metrics_js
        assert "assets/field_registry.js" in mh and "assets/field_registry.js" in index
        metric_base_js=(tmp / "dashboard" / "assets" / "metric_base.js").read_text(encoding="utf-8")
        assert "field_registry" in metric_base_js and "video_fact" in metric_base_js
        assert '客观数据' in field_js and '博主标签' in field_js and '构建指标' in field_js and '比值指标' in field_js
        assert 'field-level1' in field_js and 'field-level2' in field_js and 'field-level3' in field_js
        assert "overviewSortEntries" in overview_js and "mountPicker" in overview_js and "overviewFieldEntries" in overview_js

        sync_html=(tmp / "dashboard" / "sync.html").read_text(encoding="utf-8")
        maintenance_js=(tmp / "dashboard" / "assets" / "maintenance.js").read_text(encoding="utf-8")
        assert 'id="healthSelectVisible"' in sync_html and 'id="healthSelectAllResults"' in sync_html and 'id="healthBatchResume"' in sync_html
        assert "health-select" in maintenance_js and "batchResumeHealth" in maintenance_js and "batchSyncHealth" in maintenance_js and "/api/monitoring/sync" in maintenance_js and "cdh-data-revision" in maintenance_js
        assert "/api/monitoring/override" in maintenance_js and "batchOverrideHealth" in maintenance_js and "batchClearOverrideHealth" in maintenance_js
        assert 'id="healthBatchOverride"' in sync_html and 'id="healthManualAvailability"' in sync_html and 'id="healthManualContent"' in sync_html and 'id="healthManualPolicy"' in sync_html
        assert '/api/dashboard/stats' in server_src and '/api/creators/facts' in server_src and '/api/metrics/base' in server_src and '/api/creators/capture-batch' in server_src
        assert '/api/monitoring/sync' in server_src and 'Query Details' in server_src and 'Search Requirements' in server_src
        dashboard_src=(ROOT / "creator_hub" / "dashboard.py").read_text(encoding="utf-8")
        assert 'discovery_creator_results r' in dashboard_src and 'LIMIT 30' in dashboard_src

        ai_html = (tmp / "dashboard" / "ai.html").read_text(encoding="utf-8")
        assert "AI 助手" in ai_html and "Ask Hub" in ai_html and "Creator Brief" in ai_html and "AI 搜索 Agent" in ai_html
        assert 'data-section-nav="ai-status"' in ai_html and 'data-section-nav="ai-history"' in ai_html
        for anchor in ["ai-status","ai-ask","ai-brief","ai-compare","ai-planner","ai-weekly","ai-result-history","ai-history"]:
            assert f'id="{anchor}"' in ai_html
        ai_js=(tmp / "dashboard" / "assets" / "ai_copilot.js").read_text(encoding="utf-8")
        assert "/api/ai/ask" in ai_js and "/api/ai/creator-brief" in ai_js and "/api/ai/query-search" in ai_js and "/api/ai/models" in ai_js and "/api/ai/test" in ai_js
        assert "/api/ai/result-set" in ai_js and "/api/ai/result-history" in ai_js and "/api/creators/suggest" in ai_js and "导出当前结果 XLSX" in ai_js
        assert "AI 搜索要求（可选）" in ai_html and "picker-locks" in ai_html and "AI 检索历史" in ai_html
        assert "最近上传轻量抽样" in ai_html and "综合适配分" in ai_js and "local_data_status" in ai_js and "objective_fit_score" in ai_js
        assert "brand_safety_score" in ai_js and "continuity_fit_score" in ai_js and "profile_verification_status" in ai_js
        assert "待验证" in ai_js and "不计为过滤失败" in ai_js
        ai_service_src=(ROOT / "creator_hub" / "ai" / "service.py").read_text(encoding="utf-8")
        assert "AI 请求重试" in ai_service_src and "channel_topic_context" in ai_service_src and "profile_budget" in ai_service_src

        creator_html = (tmp / "dashboard" / "creators" / (cid + ".html")).read_text(encoding="utf-8")
        assert 'id="detailFilterConditions"' in creator_html and "detailAddFilter" in creator_html
        assert 'data-section-nav=' not in creator_html  # detail page keeps the active top-level item but no invalid overview anchors
        assert "detailPageSizeConfirm" in creator_html and "detailFirst" in creator_html and "detailLast" in creator_html and "detailJump" in creator_html
        assert "UgPhone优先 + 播放量" in creator_html and "creator_detail.js" in creator_html
        assert "AI 可选增强" in creator_html and "../ai.html?brief=" in creator_html

        sync_html = (tmp / "dashboard" / "sync.html").read_text(encoding="utf-8")
        assert "syncPageSizeConfirm" in sync_html and "syncFirst" in sync_html and "syncLast" in sync_html and "syncJump" in sync_html
        assert 'id="syncExport"' in sync_html and 'id="quotaExport"' in sync_html
        assert 'id="sync-health"' in sync_html and 'id="sync-database"' in sync_html and 'id="sync-maintenance"' in sync_html
        assert "监控健康" in sync_html and "数据库健康" in sync_html and "Snapshot" in sync_html
        assert "商业表现数据" in sync_html and 'id="businessImportFile"' in sync_html and 'business_metrics.js' in sync_html
        assert 'businessFxResolve' not in sync_html and 'businessFxBatch' not in sync_html and '汇率状态与补全' not in sync_html
        assert 'GMV 默认且固定为 USD 累计快照' in sync_html
        assert 'id="healthPageSize"' in sync_html and 'id="healthPageSizeConfirm"' in sync_html
        assert 'id="healthSearch"' in sync_html and 'id="healthChannelFilter"' in sync_html and 'id="healthStateFilter"' in sync_html and 'id="healthPriorityFilter"' in sync_html
        assert 'id="healthSort"' in sync_html and 'id="healthSortDir"' in sync_html and 'id="healthClearFilters"' in sync_html
        assert 'data-field="selection">选择</th>' in sync_html and 'data-field="channel_status">频道状态</th>' in sync_html
        assert 'id="healthFirst"' in sync_html and 'id="healthLast"' in sync_html and 'id="healthJump"' in sync_html and 'id="healthSummary"' in sync_html
        maint_js=(tmp / "dashboard" / "assets" / "maintenance.js").read_text(encoding="utf-8")
        assert "/api/monitoring/health" in maint_js and "/api/maintenance/backup" in maint_js and "/api/maintenance/snapshots" in maint_js
        assert "page_size:healthSize" in maint_js and "healthPageSizeConfirm" in maint_js
        assert "healthFilters()" in maint_js and "healthSort" in maint_js and "healthClearFilters" in maint_js and "highlightHeaders" in maint_js
        assert "healthDetail" in maint_js and "状态详情" in maint_js and "channel_status_reason" in maint_js
        # Main health-row template is conclusion-first: detailed reason/system/content/policy live in Inspector.
        row_template=maint_js.split("box.innerHTML=(x.rows||[]).map",1)[1].split("if(summary)",1)[0]
        assert "channel_status_reason" not in row_template and "system_channel_status" not in row_template and "content_status" not in row_template and "last_sync_error" not in row_template
        assert 'runtimeStatus' in index and 'runtime_status.js' in index and 'export_tools.js' in index
        job_js=(tmp / "dashboard" / "assets" / "job_progress.js").read_text(encoding="utf-8")
        assert "/api/jobs/list" in job_js and "任务中心" in job_js and "cdhJobDock" in job_js
        assert "cdhJobClearComplete" in job_js and "cdhJobClearFailed" in job_js and "cdhJobClearEnded" in job_js
        assert dash["metric_data_mode"] == "python_preaggregated"

        exp_xlsx = export_all(db, tmp / "exports_xlsx", "xlsx")
        assert Path(exp_xlsx["files"][0]).exists()
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
        required = {"creators", "videos", "creator_snapshots", "video_snapshots", "discovery_runs", "discovery_creator_results", "discovery_hits", "label_suggestions", "video_labels", "video_label_audit", "sync_runs", "app_settings", "creator_workflow", "creator_workflow_audit", "creator_discovery_summary", "creator_sync_attempts", "maintenance_runs", "backup_registry", "ai_runs", "ai_findings", "ai_evidence", "ai_feedback", "ai_cache", "ai_result_sets", "ai_result_items", "creator_business_metrics", "saved_views", "job_runs", "creator_availability_overrides", "creator_availability_override_audit", "schema_migrations", "run_specs", "data_assertions"}
        assert required <= tables, required - tables
        with sqlite3.connect(db) as conn:
            run_cols={r[1] for r in conn.execute("PRAGMA table_info(discovery_runs)")}
            assert {"base_query_source","ai_run_id"} <= run_cols
            assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "17"
            idx={r[1] for r in conn.execute("PRAGMA index_list('videos')").fetchall()}
            assert "idx_videos_published" in idx
            sidx={r[1] for r in conn.execute("PRAGMA index_list('label_suggestions')").fetchall()}
            assert {"idx_label_suggestions_role","idx_label_suggestions_confidence"} <= sidx
            creator_cols={r[1] for r in conn.execute("PRAGMA table_info(creators)")}
            assert {"channel_data_at","video_metrics_at","classification_data_at","last_sync_attempt_at","last_sync_status","last_sync_error","sync_error_type","consecutive_sync_failures","next_sync_at","next_retry_at","sync_suspended"} <= creator_cols
            business_cols={r[1] for r in conn.execute("PRAGMA table_info(creator_business_metrics)")}
            assert {"metric_value_usd","fx_rate_to_usd","fx_rate_date","fx_provider","fx_status","snapshot_kind"} <= business_cols
            job_cols={r[1] for r in conn.execute("PRAGMA table_info(job_runs)")}
            assert {"payload_json","resource_class","cancel_requested","checkpoint_json","resumable","retry_count","parent_job_id","worker_id"} <= job_cols
            assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=17").fetchone()[0] == 1


        sync_html=(tmp / "dashboard" / "sync.html").read_text(encoding="utf-8")
        assert 'data-section-nav="sync-monitoring"' in sync_html and 'data-section-nav="sync-quota"' in sync_html
        assert 'id="businessCaptureAt"' in sync_html and "累计快照" in sync_html and "USD" in sync_html
        for anchor in ["sync-monitoring","sync-health","sync-business","sync-database","sync-maintenance","sync-runs","sync-quota"]:
            assert f'id="{anchor}"' in sync_html
        section_nav_js=(tmp / "dashboard" / "assets" / "section_nav.js").read_text(encoding="utf-8")
        assert "aria-current" in section_nav_js and "scrollIntoView" in section_nav_js
        print("SELF_CHECK_OK")
        print(json.dumps({"tables": len(tables), "dashboard": dash["index"], "status": hub.status(), "geography_countries": len(geo["countries"])}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
