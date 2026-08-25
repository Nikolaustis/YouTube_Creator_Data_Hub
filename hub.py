#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

from creator_hub.config import DEFAULT_BRANDS,DEFAULT_DB,DEFAULT_OUTPUT,DEFAULT_SETTINGS,load_settings
from creator_hub import __version__
from creator_hub.dashboard import build_dashboard
from creator_hub.db import init_db
from creator_hub.exporter import export_all
from creator_hub.importers import import_v2, import_business_metrics
from creator_hub.metric_config import import_metric_config, export_metric_config, validate_metric_config
from creator_hub.server import serve_dashboard
from creator_hub.service import CreatorHub
from creator_hub.youtube_api import read_api_key
from creator_hub.util import parse_csv_list


def dump(obj):
    print(json.dumps(obj,ensure_ascii=False,indent=2,default=str))


def common(p):
    p.add_argument("--db",default=str(DEFAULT_DB),help="SQLite path")
    p.add_argument("--settings",default=str(DEFAULT_SETTINGS))
    p.add_argument("--brands-config",default=str(DEFAULT_BRANDS))
    p.add_argument("--unit-budget",type=int,default=None,help="hard cap for this invocation")


def make_hub(a): return CreatorHub(a.db,a.settings,a.brands_config,a.unit_budget)


def main():
    ap=argparse.ArgumentParser(prog="hub.py",description=f"YouTube Creator Data Hub v{__version__}")
    sub=ap.add_subparsers(dest="cmd",required=True)

    p=sub.add_parser("init",help="initialize SQLite without API calls"); common(p)
    p=sub.add_parser("doctor",help="environment, dependency, database and API checks"); common(p); p.add_argument("--online",action="store_true",help="validate the API key with one low-cost videos.list request")

    p=sub.add_parser("discover",help="discover creators from YouTube video search"); common(p)
    p.add_argument("query"); p.add_argument("--max-results",type=int,default=100); p.add_argument("--region"); p.add_argument("--language"); p.add_argument("--add",action="store_true",help="add discovered creators to monitoring")
    p.add_argument("--search-source",choices=["web","api"],default="web"); p.add_argument("--target-country"); p.add_argument("--target-group"); p.add_argument("--lookback-days",type=int); p.add_argument("--from-date"); p.add_argument("--to-date")
    p.add_argument("--expand-term",action="append",default=[],help="repeatable long-tail suffix; base query is always searched")


    p=sub.add_parser("capture",help="add a creator and capture videos from a selected time window"); common(p)
    p.add_argument("ref"); p.add_argument("--days",type=int,choices=[7,30,60,90,180,365]); p.add_argument("--from-date"); p.add_argument("--to-date"); p.add_argument("--full-history",action="store_true"); p.add_argument("--priority",choices=["high","normal","low","archive"],default="normal")

    p=sub.add_parser("contact",help="scrape public contact links/email and stronger country evidence"); common(p); p.add_argument("ref")

    p=sub.add_parser("serve",help="start the interactive Python Dashboard; no npm required"); common(p); p.add_argument("--output",default=str(DEFAULT_OUTPUT)); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,default=8765); p.add_argument("--no-browser",action="store_true")

    p=sub.add_parser("add",help="resolve and add a creator to monitoring"); common(p)
    p.add_argument("ref"); p.add_argument("--priority",choices=["high","normal","low","archive"],default="normal"); p.add_argument("--full-history",action="store_true")

    p=sub.add_parser("monitor",help="enable/disable monitoring"); common(p)
    p.add_argument("ref"); p.add_argument("state",choices=["on","off"]); p.add_argument("--priority",choices=["high","normal","low","archive"])

    p=sub.add_parser("sync",help="sync one creator or all monitored creators"); common(p)
    p.add_argument("ref",nargs="?"); p.add_argument("--mode",choices=["incremental","full-history","metrics-only","channel-only"],default="incremental")
    p.add_argument("--priority",choices=["high","normal","low","archive"]); p.add_argument("--metric-days",type=int); p.add_argument("--all-videos",action="store_true"); p.add_argument("--limit",type=int); p.add_argument("--force",action="store_true",help="force all monitored creators, ignoring refresh cadence")

    p=sub.add_parser("label",help="confirm a human video label"); common(p)
    p.add_argument("video_id"); p.add_argument("role",choices=["ugphone","competitor","daily","multi_brand","other_cloud_phone","pending"]); p.add_argument("--brands",default=""); p.add_argument("--by",default="operator"); p.add_argument("--note",default="")
    p=sub.add_parser("unlabel",help="remove current human label, preserving audit"); common(p); p.add_argument("video_id"); p.add_argument("--by",default="operator")

    p=sub.add_parser("tag",help="add creator tag"); common(p); p.add_argument("ref"); p.add_argument("tag"); p.add_argument("--by",default="operator")

    p=sub.add_parser("status",help="show fact-store status"); common(p)
    p=sub.add_parser("creators",help="list creators"); common(p); p.add_argument("--monitored",action="store_true"); p.add_argument("--limit",type=int,default=100)
    p=sub.add_parser("pending-labels",help="list classifications that may need review"); common(p); p.add_argument("--limit",type=int,default=100)
    p=sub.add_parser("reclassify",help="offline re-run system video classification from stored metadata"); common(p); p.add_argument("--only-missing",action="store_true"); p.add_argument("--limit",type=int)
    p=sub.add_parser("review-reclassify",help="offline re-run only unresolved review classifications"); common(p)

    p=sub.add_parser("db-health",help="SQLite health, size and integrity summary"); common(p); p.add_argument("--full",action="store_true",help="run full integrity_check instead of quick_check")
    p=sub.add_parser("backup",help="create a consistent SQLite backup using the SQLite backup API"); common(p); p.add_argument("--output")
    p=sub.add_parser("restore",help="restore SQLite from a validated backup and create a pre-restore safety backup"); common(p); p.add_argument("path"); p.add_argument("--yes",action="store_true",help="required confirmation")
    p=sub.add_parser("monitoring-health",help="show per-creator monitoring health and retry state"); common(p); p.add_argument("--limit",type=int,default=200)
    p=sub.add_parser("workflow",help="set discovery workflow status for a creator"); common(p); p.add_argument("channel_id"); p.add_argument("status",choices=["unreviewed","interested","to_contact","added","defer","excluded"]); p.add_argument("--note",default="")
    p=sub.add_parser("maintenance",help="database maintenance operations"); common(p); p.add_argument("kind",choices=["snapshots"]); p.add_argument("--dry-run",action="store_true"); p.add_argument("--auto",action="store_true")

    p=sub.add_parser("ai-status",help="show optional AI copilot status; no model call"); common(p)
    p=sub.add_parser("ai-config",help="configure optional AI layer"); common(p); g=p.add_mutually_exclusive_group(); g.add_argument("--enable",action="store_true"); g.add_argument("--disable",action="store_true"); p.add_argument("--protocol",choices=["openai_responses","openai_chat","anthropic_messages","gemini_generate_content","mock","disabled"]); p.add_argument("--provider",help="legacy alias: openai/mock/disabled"); p.add_argument("--base-url"); p.add_argument("--model"); p.add_argument("--api-key-env"); p.add_argument("--daily-limit",type=int)
    p=sub.add_parser("ai-models",help="list models from the currently configured AI API"); common(p)
    p=sub.add_parser("ai-test",help="test the currently configured AI API with one small request"); common(p)
    p=sub.add_parser("ai-brief",help="generate an evidence-grounded Creator Brief"); common(p); p.add_argument("ref"); p.add_argument("--force",action="store_true")
    p=sub.add_parser("ai-compare",help="compare 2-5 local creators"); common(p); p.add_argument("refs",nargs="+"); p.add_argument("--force",action="store_true")
    p=sub.add_parser("ai-query-plan",help="AI plans discovery queries without executing them (diagnostic/backward-compatible)"); common(p); p.add_argument("query"); p.add_argument("--language",default="en"); p.add_argument("--objective",default="creator discovery"); p.add_argument("--force",action="store_true")
    p=sub.add_parser("ai-query-search",help="AI plans queries and executes them through the existing YouTube API discovery tool"); common(p); p.add_argument("query"); p.add_argument("--language",default="en"); p.add_argument("--objective",default="creator discovery"); p.add_argument("--max-queries",type=int,default=12); p.add_argument("--max-results",type=int,default=25); p.add_argument("--lookback-days",type=int); p.add_argument("--target-country"); p.add_argument("--target-group"); p.add_argument("--force",action="store_true")
    p=sub.add_parser("ai-ask",help="natural-language read-only query over local Creator facts"); common(p); p.add_argument("question"); p.add_argument("--force",action="store_true")
    p=sub.add_parser("ai-weekly",help="generate a seven-day Creator Intelligence brief"); common(p); p.add_argument("--force",action="store_true")

    p=sub.add_parser("dashboard",help="build static offline Dashboard"); common(p); p.add_argument("--output",default=str(DEFAULT_OUTPUT))
    p=sub.add_parser("export",help="export objective data + label layers"); common(p); p.add_argument("--format",choices=["csv","json","xlsx"],default="xlsx"); p.add_argument("--output",default=str(ROOT/"exports"))
    p=sub.add_parser("import-v2",help="offline import from youtube-kol-gmv-intelligence V2 folder"); common(p); p.add_argument("path"); p.add_argument("--no-monitor",action="store_true")
    p=sub.add_parser("import-business",help="import point-in-time creator GMV/new-user/business snapshots from CSV/XLSX or a folder"); common(p); p.add_argument("path"); p.add_argument("--source-type",default="manual_import"); p.add_argument("--capture-at",default=None,help="snapshot capture time; row-level capture-time column overrides this value")
    p=sub.add_parser("metric-config-import",help="install an exported Secondary Metrics JSON as the Dashboard default"); common(p); p.add_argument("path")
    p=sub.add_parser("metric-config-export",help="export the installed Secondary Metrics JSON"); common(p); p.add_argument("path")

    a=ap.parse_args()
    if a.cmd=="init":
        init_db(a.db); dump({"ok":True,"db":str(Path(a.db).resolve()),"version":__version__}); return
    if a.cmd=="doctor":
        init_db(a.db)
        import importlib.util, sqlite3, tempfile
        settings=load_settings(a.settings); key_env=settings["api"].get("api_key_env","YOUTUBE_API_KEY")
        py_ok=sys.version_info>=(3,10); pip_ok=importlib.util.find_spec("pip") is not None; ox_ok=importlib.util.find_spec("openpyxl") is not None
        dbp=Path(a.db); outp=Path(DEFAULT_OUTPUT); data_write=True; output_write=True
        try:
            dbp.parent.mkdir(parents=True,exist_ok=True); t=dbp.parent/".write_test"; t.write_text("ok"); t.unlink()
        except Exception: data_write=False
        try:
            outp.mkdir(parents=True,exist_ok=True); t=outp/".write_test"; t.write_text("ok"); t.unlink()
        except Exception: output_write=False
        schema=None
        try:
            with sqlite3.connect(dbp) as cc:
                r=cc.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone(); schema=r[0] if r else None
        except Exception: pass
        key_present=bool(read_api_key(key_env)); online=None; online_error=None
        port_available=True; port_error=None
        try:
            import socket
            sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            try:
                sock.bind(("127.0.0.1",8765))
            finally:
                sock.close()
        except OSError as e:
            port_available=False; port_error=f"{type(e).__name__}: {e}"
        if a.online:
            if not key_present: online=False; online_error="YOUTUBE_API_KEY not configured"
            else:
                try:
                    h=make_hub(a); h.api.call("videos",part="id",id="dQw4w9WgXcQ",maxResults=1); online=True
                except Exception as e:
                    online=False; online_error=f"{type(e).__name__}: {e}"
        h=make_hub(a); ai=h.ai_status()
        dump({"python":sys.version.split()[0],"python_executable":sys.executable,"python_ok":py_ok,"python_required":">=3.10","pip_present":pip_ok,"openpyxl_present":ox_ok,"db":str(dbp.resolve()),"db_exists":dbp.exists(),"schema_version":schema,"data_dir_writable":data_write,"output_dir_writable":output_write,"api_key_env":key_env,"api_key_present":key_present,"api_key_online_valid":online,"api_key_online_error":online_error,"interactive_url":"http://127.0.0.1:8765/","interactive_port":8765,"interactive_port_available":port_available,"interactive_port_error":port_error,"npm_required":False,"ai_optional":True,"ai":ai}); return
    hub=make_hub(a)
    if a.cmd=="discover":
        qs=[f"{a.query} {t}" for t in (a.expand_term or []) if str(t).strip()]
        res=hub.discover_expanded(a.query,queries=qs,max_results=a.max_results,region=a.region,language=a.language,search_source=a.search_source,target_country=a.target_country,target_group=a.target_group,lookback_days=a.lookback_days,from_date=a.from_date,to_date=a.to_date)
        if a.add:
            for c in res.get("results") or []:
                try: hub.ensure_creator(c.get("channel_id") or "",monitoring=True,source="discovery_cli")
                except Exception: pass
        dump(res)
    elif a.cmd=="capture": dump(hub.capture_window(a.ref,days=a.days,from_date=a.from_date,to_date=a.to_date,full_history=a.full_history,priority=a.priority))
    elif a.cmd=="contact": dump(hub.scrape_contact(a.ref))
    elif a.cmd=="serve": serve_dashboard(hub,a.output,a.host,a.port,not a.no_browser)
    elif a.cmd=="add":
        row=hub.ensure_creator(a.ref,monitoring=True,priority=a.priority,source="manual")
        res={"creator":row,"monitoring":True}
        if a.full_history: res["sync"]=hub.sync_creator(row["channel_id"],mode="full-history")
        dump(res)
    elif a.cmd=="monitor": dump({"channel_id":hub.set_monitoring(a.ref,a.state=="on",a.priority),"monitoring":a.state})
    elif a.cmd=="sync":
        if a.ref: dump(hub.sync_creator(a.ref,mode=a.mode,metric_days=a.metric_days,all_videos=a.all_videos,priority=a.priority))
        else: dump(hub.sync_all(mode=a.mode,priority=a.priority,metric_days=a.metric_days,all_videos=a.all_videos,limit=a.limit,force=a.force))
    elif a.cmd=="label": dump(hub.label_video(a.video_id,a.role,brands=parse_csv_list(a.brands),actor=a.by,note=a.note))
    elif a.cmd=="unlabel": hub.clear_label(a.video_id,a.by); dump({"video_id":a.video_id,"human_label":None})
    elif a.cmd=="tag": dump({"channel_id":hub.tag_creator(a.ref,a.tag,a.by),"tag":a.tag})
    elif a.cmd=="status": dump(hub.status())
    elif a.cmd=="creators": dump(hub.list_creators(a.monitored,a.limit))
    elif a.cmd=="pending-labels": dump(hub.list_pending_labels(a.limit))
    elif a.cmd=="reclassify": dump(hub.reclassify_videos(only_missing=a.only_missing,limit=a.limit))
    elif a.cmd=="review-reclassify": dump(hub.reclassify_review_queue())
    elif a.cmd=="db-health": dump(hub.database_health(full=a.full))
    elif a.cmd=="backup": dump(hub.backup_database(destination=a.output if a.output else None))
    elif a.cmd=="restore":
        if not a.yes: raise SystemExit("restore requires --yes; a pre-restore safety backup will be created")
        dump(hub.restore_database(a.path,create_pre_backup=True))
    elif a.cmd=="monitoring-health": dump(hub.monitoring_health(limit=a.limit))
    elif a.cmd=="workflow": dump(hub.set_creator_workflow(a.channel_id,a.status,note=a.note,actor="cli"))
    elif a.cmd=="maintenance":
        if a.kind=="snapshots": dump(hub.compact_snapshots(dry_run=a.dry_run,auto=a.auto))
    elif a.cmd=="ai-status": dump(hub.ai_status())
    elif a.cmd=="ai-config":
        patch={}
        if a.enable: patch["enabled"]=True
        if a.disable: patch["enabled"]=False
        if a.protocol: patch["protocol"]=a.protocol
        if a.provider: patch["provider"]=a.provider
        if a.base_url: patch["base_url"]=a.base_url
        if a.model: patch["model"]=a.model
        if a.api_key_env: patch["api_key_env"]=a.api_key_env
        if a.daily_limit: patch["daily_request_soft_limit"]=a.daily_limit
        dump(hub.configure_ai(patch))
    elif a.cmd=="ai-models": dump(hub.ai_models())
    elif a.cmd=="ai-test": dump(hub.ai_test())
    elif a.cmd=="ai-brief": dump(hub.ai_creator_brief(a.ref,force=a.force))
    elif a.cmd=="ai-compare": dump(hub.ai_compare_creators(a.refs,force=a.force))
    elif a.cmd=="ai-query-plan": dump(hub.ai_query_planner(a.query,language=a.language,objective=a.objective,force=a.force))
    elif a.cmd=="ai-query-search": dump(hub.ai_query_search(a.query,language=a.language,objective=a.objective,max_queries=a.max_queries,max_results=a.max_results,lookback_days=a.lookback_days,target_country=a.target_country,target_group=a.target_group,force=a.force))
    elif a.cmd=="ai-ask": dump(hub.ai_ask(a.question,force=a.force))
    elif a.cmd=="ai-weekly": dump(hub.ai_weekly_brief(force=a.force))
    elif a.cmd=="dashboard": dump(build_dashboard(a.db,a.output,hub.settings))
    elif a.cmd=="export": dump(export_all(a.db,a.output,a.format))
    elif a.cmd=="import-v2": dump(import_v2(hub,a.path,monitoring=not a.no_monitor))
    elif a.cmd=="import-business": dump(import_business_metrics(hub,a.path,source_type=a.source_type,capture_at=a.capture_at))
    elif a.cmd=="metric-config-import":
        obj=validate_metric_config(json.loads(Path(a.path).read_text(encoding="utf-8")))
        file_result=import_metric_config(a.path)
        db_result=hub.set_setting("secondary_metrics",obj)
        dump({**file_result,"sqlite":db_result})
    elif a.cmd=="metric-config-export":
        obj=hub.get_setting("secondary_metrics",None)
        if obj is not None:
            dst=Path(a.path);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            dump({"ok":True,"path":str(dst.resolve()),"metrics":sum(1 for m in obj.get("metrics",[]) if not m.get("internal")),"rules":len(obj.get("rules",[])),"source":"sqlite"})
        else: dump(export_metric_config(a.path))


if __name__=="__main__": main()
