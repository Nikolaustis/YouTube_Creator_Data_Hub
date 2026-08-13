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


class DashboardHandler(SimpleHTTPRequestHandler):
    hub: CreatorHub
    output_dir: Path

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.output_dir), **kwargs)

    def log_message(self, fmt, *args):
        # Keep console concise; API errors are returned as JSON.
        return

    def _json(self, obj: Any, status: int = 200):
        data=json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        try:
            n=int(self.headers.get("Content-Length") or 0); raw=self.rfile.read(n) if n else b"{}"
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/api/ping":
            return self._json({"ok":True,"mode":"interactive"})
        return super().do_GET()

    def do_POST(self):
        path=urlparse(self.path).path; b=self._body()
        try:
            if path=="/api/discover":
                return self._json(self.hub.discover(
                    str(b.get("query") or "").strip(), max_results=int(b.get("max_results") or 100),
                    region=(b.get("region") or None), language=(b.get("language") or None), add=False,
                    search_source=str(b.get("search_source") or "web"), target_country=(b.get("target_country") or None),
                    target_group=(b.get("target_group") or None), lookback_days=int(b["lookback_days"]) if b.get("lookback_days") else None,
                    from_date=(b.get("from_date") or None), to_date=(b.get("to_date") or None),
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
            if path=="/api/metric/evaluate":
                return self._json({"ok":True,**self.hub.evaluate_metric_spec(dict(b.get("spec") or {}))})
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
