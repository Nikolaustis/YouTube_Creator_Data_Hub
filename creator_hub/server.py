from __future__ import annotations

import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .dashboard import build_dashboard
from .service import CreatorHub
from .exporter import xlsx_bytes, safe_export_filename


class DashboardHandler(SimpleHTTPRequestHandler):
    hub: CreatorHub
    output_dir: Path

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.output_dir), **kwargs)

    def log_message(self, fmt, *args):
        # Keep console concise; API errors are returned as JSON.
        return

    def end_headers(self):
        # Dashboard assets are regenerated during upgrades and server startup.
        # Disable browser caching so HTML and JS from different versions cannot mix.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _json(self, obj: Any, status: int = 200):
        data=json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)

    def _xlsx(self, data: bytes, filename: str):
        self.send_response(200)
        self.send_header("Content-Type","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition",f'attachment; filename="{safe_export_filename(filename,"export.xlsx")}"')
        self.send_header("Content-Length",str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        try:
            n=int(self.headers.get("Content-Length") or 0); raw=self.rfile.read(n) if n else b"{}"
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/api/ping":
            import sys, os
            from .youtube_api import read_api_key
            key_env=self.hub.settings.get("api",{}).get("api_key_env","YOUTUBE_API_KEY")
            return self._json({"ok":True,"mode":"interactive","version":getattr(__import__('creator_hub'), '__version__', ''),"python":sys.version.split()[0],"db":str(self.hub.db_path),"db_exists":Path(self.hub.db_path).exists(),"api_key_present":bool(read_api_key(key_env))})
        return super().do_GET()

    def do_POST(self):
        path=urlparse(self.path).path; b=self._body()
        try:
            if path=="/api/settings/get":
                key=str(b.get("key") or "")
                return self._json({"ok":True,"key":key,"value":self.hub.get_setting(key,None)})
            if path=="/api/settings/set":
                return self._json({"ok":True,**self.hub.set_setting(str(b.get("key") or ""),b.get("value"))})
            if path=="/api/settings/list":
                return self._json({"ok":True,"settings":self.hub.list_settings()})
            if path=="/api/workflow/set":
                return self._json({"ok":True,**self.hub.set_creator_workflow(str(b.get("channel_id") or ""),str(b.get("status") or "unreviewed"),note=str(b.get("note") or ""),actor=str(b.get("actor") or "dashboard"))})
            if path=="/api/creators/batch":
                return self._json({"ok":True,**self.hub.batch_creators(list(b.get("channel_ids") or []),str(b.get("action") or ""),value=str(b.get("value") or ""),actor=str(b.get("actor") or "dashboard-batch"))})
            if path=="/api/review/batch":
                selection=dict(b.get("selection") or {})
                if selection.get("mode")=="all_matching":
                    return self._json({"ok":True,**self.hub.batch_review_matching(selection,str(b.get("action") or ""),role=str(b.get("role") or ""),brands=list(b.get("brands") or []),actor=str(b.get("actor") or "dashboard-batch"))})
                return self._json({"ok":True,**self.hub.batch_review(list(b.get("video_ids") or []),str(b.get("action") or ""),role=str(b.get("role") or ""),brands=list(b.get("brands") or []),actor=str(b.get("actor") or "dashboard-batch"))})
            if path=="/api/monitoring/health":
                return self._json({"ok":True,**self.hub.monitoring_health(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30))})
            if path=="/api/maintenance/health":
                return self._json({"ok":True,**self.hub.database_health(full=bool(b.get("full")),run_check=bool(b.get("run_check",False)))})
            if path=="/api/maintenance/backups":
                return self._json({"ok":True,"backups":self.hub.list_backups()})
            if path=="/api/maintenance/backup":
                return self._json({"ok":True,**self.hub.backup_database(note=str(b.get("note") or "dashboard"))})
            if path=="/api/maintenance/restore":
                result=self.hub.restore_database(str(b.get("name") or b.get("path") or ""),create_pre_backup=True)
                build_dashboard(self.hub.db_path,self.output_dir,self.hub.settings)
                return self._json({"ok":True,**result})
            if path=="/api/maintenance/snapshots":
                return self._json({"ok":True,**self.hub.compact_snapshots(dry_run=bool(b.get("dry_run")),auto=False)})
            if path=="/api/freshness":
                return self._json({"ok":True,"channel_id":str(b.get("channel_id") or ""),"freshness":self.hub.data_freshness(str(b.get("channel_id") or ""))})
            if path=="/api/discover":
                queries=b.get("queries") if isinstance(b.get("queries"),list) else []
                return self._json(self.hub.discover_expanded(
                    str(b.get("query") or "").strip(), queries=[str(x) for x in queries],
                    max_results=int(b.get("max_results") or 50), region=(b.get("region") or None),
                    language=(b.get("language") or None), search_source=str(b.get("search_source") or "web"),
                    target_country=(b.get("target_country") or None), target_group=(b.get("target_group") or None),
                    lookback_days=int(b["lookback_days"]) if b.get("lookback_days") else None,
                    from_date=(b.get("from_date") or None), to_date=(b.get("to_date") or None),
                    max_queries=int(b.get("max_queries") or 80), query_language=(b.get("query_language") or None),
                ))
            if path=="/api/add":
                row=self.hub.ensure_creator(str(b.get("channel_id") or b.get("ref") or ""), monitoring=True,
                                            priority=str(b.get("priority") or "normal"), source="discovery")
                return self._json({"ok":True,"creator":row})
            if path=="/api/capture":
                mode=str(b.get("window") or "30")
                if mode=="full": res=self.hub.capture_window(str(b.get("channel_id")),full_history=True,priority=str(b.get("priority") or "normal"))
                elif mode in {"date","date_range"}: res=self.hub.capture_window(str(b.get("channel_id")),from_date=str(b.get("from_date") or ""),to_date=str(b.get("to_date") or ""),priority=str(b.get("priority") or "normal"))
                else: res=self.hub.capture_window(str(b.get("channel_id")),days=int(mode),priority=str(b.get("priority") or "normal"))
                return self._json({"ok":True,**res})
            if path=="/api/contact":
                return self._json({"ok":True,**self.hub.scrape_contact(str(b.get("channel_id") or b.get("ref") or ""))})
            if path=="/api/discovery/list":
                return self._json({"ok":True,**self.hub.discovery_history(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),search=str(b.get("search") or ""),conditions=list(b.get("conditions") or []),sort=str(b.get("sort") or "score"),direction=str(b.get("dir") or "desc"))})
            if path=="/api/discovery/creators":
                return self._json({"ok":True,**self.hub.discovery_creator_history(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),search=str(b.get("search") or ""),conditions=list(b.get("conditions") or []),sort=str(b.get("sort") or "score"),direction=str(b.get("dir") or "desc"))})
            if path=="/api/discovery/creator-ids":
                return self._json({"ok":True,**self.hub.discovery_creator_ids(search=str(b.get("search") or ""),conditions=list(b.get("conditions") or []))})
            if path=="/api/export/xlsx":
                source=str(b.get("source") or "rows")
                filename=str(b.get("filename") or "creator_data_hub_export.xlsx")
                sheet=str(b.get("sheet") or "Data")
                columns_raw=list(b.get("columns") or [])
                columns=[(str(x.get("key") or ""),str(x.get("label") or x.get("key") or "")) for x in columns_raw if isinstance(x,dict) and x.get("key")]
                if source=="rows":
                    rows=list(b.get("rows") or [])
                    if not columns and rows:
                        columns=[(str(k),str(k)) for k in rows[0].keys()]
                    return self._xlsx(xlsx_bytes(sheet,columns,rows,metadata=[("Exported At",__import__('creator_hub.util',fromlist=['now_utc']).now_utc())]),filename)
                if source=="classifications":
                    payload={"search":str(b.get("search") or ""),"conditions":list(b.get("conditions") or []),"sort":str(b.get("sort") or "published"),"direction":str(b.get("dir") or "desc")}
                    cols=columns or [("video_id","Video ID"),("title","视频"),("channel_title","博主"),("published_at","发布时间"),("current_views","播放量"),("current_likes","点赞数"),("current_comments","评论数"),("duration_seconds","视频时长（秒）"),("final_role","最终分类"),("brands","最终品牌"),("confidence","系统置信度"),("review_status","复核状态")]
                    def it():
                        pg=1
                        while True:
                            x=self.hub.classification_list(page=pg,page_size=5000,**payload)
                            for r in x.get("rows") or []: yield r
                            if pg>=int(x.get("pages") or 1): break
                            pg+=1
                    return self._xlsx(xlsx_bytes(sheet or "Video Classifications",cols,it(),metadata=[("Search",payload["search"]),("Conditions",payload["conditions"])]),filename)
                if source in {"discovery_creators","discovery_videos"}:
                    fn=self.hub.discovery_creator_history if source=="discovery_creators" else self.hub.discovery_history
                    payload={"search":str(b.get("search") or ""),"conditions":list(b.get("conditions") or []),"sort":str(b.get("sort") or "score"),"direction":str(b.get("dir") or "desc")}
                    if source=="discovery_creators":
                        cols=columns or [("run_id","Run ID"),("base_query","原关键词"),("keyword_source_label","关键词来源"),("channel_title","博主"),("channel_id","Channel ID"),("subscribers","订阅数"),("country_resolved","国家/地区"),("best_video_title","最佳命中视频"),("best_video_views","最佳视频播放量"),("best_discovery_score","发现评分"),("opportunity_tier","分档"),("query_coverage","Query Coverage"),("matched_queries","命中Query"),("hit_video_count","命中视频数"),("workflow_label","处理状态"),("discovery_freshness","首次/重复"),("discovery_run_count","历史发现次数"),("first_seen_at","首次发现"),("last_seen_at","最近发现"),("found_at","本次发现时间")]
                    else:
                        cols=columns or [("run_id","Run ID"),("query","实际Query"),("channel_title","博主"),("channel_id","Channel ID"),("video_id","Video ID"),("title","视频"),("views","播放量"),("subscribers","订阅数"),("country_resolved","国家/地区"),("pre_score","发现评分"),("opportunity_tier","分档"),("workflow_label","处理状态"),("discovery_freshness","首次/重复"),("discovery_run_count","历史发现次数"),("found_at","发现时间")]
                    def it2():
                        pg=1
                        while True:
                            x=fn(page=pg,page_size=5000,**payload)
                            for r in x.get("rows") or []: yield r
                            if pg>=int(x.get("pages") or 1): break
                            pg+=1
                    return self._xlsx(xlsx_bytes(sheet,cols,it2(),metadata=[("Search",payload["search"]),("Conditions",payload["conditions"])]),filename)
                raise ValueError("unsupported export source")
            if path=="/api/metric/evaluate":
                return self._json({"ok":True,**self.hub.evaluate_metric_spec(dict(b.get("spec") or {}))})
            if path=="/api/videos/classification-stats":
                return self._json({"ok":True,**self.hub.classification_stats()})
            if path in {"/api/videos/classifications","/api/review/list"}:
                fn=self.hub.classification_list if path=="/api/videos/classifications" else self.hub.review_queue
                return self._json({"ok":True,**fn(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),search=str(b.get("search") or ""),role=str(b.get("role") or ""),brand=str(b.get("brand") or ""),conditions=list(b.get("conditions") or []),sort=str(b.get("sort") or "published"),direction=str(b.get("dir") or "desc"))})
            if path=="/api/review/save":
                return self._json({"ok":True,"result":self.hub.review_video(str(b.get("video_id") or ""),confirm_system=bool(b.get("confirm_system")),role=(str(b.get("role")) if b.get("role") else None),brands=list(b.get("brands") or []))})
            if path=="/api/review/reclassify":
                return self._json({"ok":True,**self.hub.reclassify_review_queue()})
            if path=="/api/rebuild-dashboard":
                return self._json({"ok":True,**build_dashboard(self.hub.db_path,self.output_dir,self.hub.settings)})
            self._json({"ok":False,"error":"unknown endpoint"},404)
        except Exception as e:
            self._json({"ok":False,"error":f"{type(e).__name__}: {e}"},500)


def serve_dashboard(hub: CreatorHub, output_dir: str | Path, host: str="127.0.0.1", port: int=8765, open_browser: bool=True):
    out=Path(output_dir); build_dashboard(hub.db_path,out,hub.settings)
    class H(DashboardHandler): pass
    H.hub=hub; H.output_dir=out
    server=ThreadingHTTPServer((host,port),H)
    url=f"http://{host}:{port}/index.html"
    if open_browser:
        threading.Timer(0.7,lambda:webbrowser.open(url)).start()
    print(json.dumps({"url":url,"mode":"interactive","npm_required":False},ensure_ascii=False))
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
