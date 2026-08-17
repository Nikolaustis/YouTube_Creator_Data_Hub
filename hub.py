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
from creator_hub.importers import import_v2
from creator_hub.metric_config import import_metric_config, export_metric_config
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
    p=sub.add_parser("doctor",help="environment and database checks"); common(p)

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

    p=sub.add_parser("dashboard",help="build static offline Dashboard"); common(p); p.add_argument("--output",default=str(DEFAULT_OUTPUT))
    p=sub.add_parser("export",help="export objective data + label layers"); common(p); p.add_argument("--format",choices=["csv","json","xlsx"],default="xlsx"); p.add_argument("--output",default=str(ROOT/"exports"))
    p=sub.add_parser("import-v2",help="offline import from youtube-kol-gmv-intelligence V2 folder"); common(p); p.add_argument("path"); p.add_argument("--no-monitor",action="store_true")
    p=sub.add_parser("metric-config-import",help="install an exported Secondary Metrics JSON as the Dashboard default"); common(p); p.add_argument("path")
    p=sub.add_parser("metric-config-export",help="export the installed Secondary Metrics JSON"); common(p); p.add_argument("path")

    a=ap.parse_args()
    if a.cmd=="init":
        init_db(a.db); dump({"ok":True,"db":str(Path(a.db).resolve()),"version":__version__}); return
    if a.cmd=="doctor":
        init_db(a.db)
        key_env=load_settings(a.settings)["api"].get("api_key_env","YOUTUBE_API_KEY")
        dump({"python":sys.version.split()[0],"db":str(Path(a.db).resolve()),"db_exists":Path(a.db).exists(),"api_key_env":key_env,"api_key_present":bool(read_api_key(key_env)),"npm_required":False}); return
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
    elif a.cmd=="dashboard": dump(build_dashboard(a.db,a.output,hub.settings))
    elif a.cmd=="export": dump(export_all(a.db,a.output,a.format))
    elif a.cmd=="import-v2": dump(import_v2(hub,a.path,monitoring=not a.no_monitor))
    elif a.cmd=="metric-config-import": dump(import_metric_config(a.path))
    elif a.cmd=="metric-config-export": dump(export_metric_config(a.path))


if __name__=="__main__": main()
