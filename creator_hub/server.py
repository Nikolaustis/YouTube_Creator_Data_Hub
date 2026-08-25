from __future__ import annotations

import json
import threading
import base64
import tempfile
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .dashboard import build_dashboard, creator_facts_payload, metric_base_payload, dashboard_stats_payload
from .service import CreatorHub
from .exporter import xlsx_bytes, safe_export_filename
from .util import safe_filename
from .jobs import JobStore


class DashboardHandler(SimpleHTTPRequestHandler):
    hub: CreatorHub
    output_dir: Path
    jobs = JobStore()

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

    def _v1(self, data: Any=None, *, meta: dict[str,Any] | None=None, status: int=200):
        return self._json({"ok":True,"data":data,"meta":meta or {},"api_version":"v1"},status)

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

    def _job_runner(self, task: str, b: dict[str, Any]):
        hub=self.hub
        resume_from=max(0,int((b.get("_resume_checkpoint") or {}).get("current") or 0))
        def resumed_ids(key="channel_ids"):
            all_ids=list(b.get(key) or []); return all_ids[resume_from:],len(all_ids)
        def offset_progress(progress,total):
            if resume_from<=0:return progress
            def wrapped(**kw):
                if kw.get("current") is not None: kw["current"]=resume_from+int(kw["current"] or 0)
                kw["total"]=total
                progress(**kw)
            return wrapped
        if task=="review_reclassify_all":
            return lambda progress: hub.reclassify_videos(only_missing=False, progress=progress)
        if task=="review_reclassify_pending":
            return lambda progress: hub.reclassify_review_queue(progress=progress)
        if task=="monitoring_sync":
            ids,total=resumed_ids(); return lambda progress: hub.sync_selected(ids, mode=str(b.get("mode") or "incremental"), metric_days=(int(b.get("metric_days")) if b.get("metric_days") else None), all_videos=bool(b.get("all_videos")), progress=offset_progress(progress,total))
        if task=="monitoring_recheck":
            ids,total=resumed_ids(); return lambda progress: hub.recheck_channel_availability(ids, restore_monitoring=bool(b.get("restore_monitoring")), progress=offset_progress(progress,total))
        if task=="capture_batch":
            ids,total=resumed_ids(); return lambda progress: hub.batch_capture_creators(ids, window=str(b.get("window") or "30"), from_date=str(b.get("from_date") or ""), to_date=str(b.get("to_date") or ""), priority=str(b.get("priority") or "normal"), actor=str(b.get("actor") or "dashboard-capture-batch"), progress=offset_progress(progress,total))
        if task=="discovery_search":
            queries=b.get("queries") if isinstance(b.get("queries"),list) else []
            return lambda progress: hub.discover_expanded(str(b.get("query") or "").strip(), queries=[str(x) for x in queries], max_results=int(b.get("max_results") or 50), region=(b.get("region") or None), language=(b.get("language") or None), search_source=str(b.get("search_source") or "web"), target_country=(b.get("target_country") or None), target_group=(b.get("target_group") or None), lookback_days=int(b["lookback_days"]) if b.get("lookback_days") else None, from_date=(b.get("from_date") or None), to_date=(b.get("to_date") or None), max_queries=int(b.get("max_queries") or 80), query_language=(b.get("query_language") or None), progress=progress)
        if task=="ai_query_search":
            return lambda progress: hub.ai_query_search(str(b.get("query") or ""), language=str(b.get("language") or "en"), objective=str(b.get("objective") or "creator discovery"), max_queries=int(b.get("max_queries") or 12), max_results=int(b.get("max_results") or 25), lookback_days=(int(b.get("lookback_days")) if b.get("lookback_days") else None), target_country=(str(b.get("target_country") or "") or None), target_group=(str(b.get("target_group") or "") or None), force=bool(b.get("force")), progress=progress)
        if task=="ai_ask":
            def run(progress):
                progress(stage="Ask Hub",message="正在解析问题并查询本地 Creator 数据",percent=12)
                out=hub.ai_ask(str(b.get("question") or ""),force=bool(b.get("force")))
                progress(stage="Ask Hub",message="结果已生成并留档",percent=100)
                return out
            return run
        if task=="ai_creator_brief":
            def run(progress):
                progress(stage="Creator Brief",message="正在读取本地证据",percent=15)
                out=hub.ai_creator_brief(str(b.get("ref") or b.get("channel_id") or ""),force=bool(b.get("force")))
                progress(stage="Creator Brief",message="Brief 已生成",percent=100)
                return out
            return run
        if task=="ai_compare":
            def run(progress):
                progress(stage="Creator 对比",message="正在读取本地证据并生成比较",percent=15)
                out=hub.ai_compare_creators([str(x) for x in list(b.get("refs") or [])],force=bool(b.get("force")))
                progress(stage="Creator 对比",message="对比已生成",percent=100)
                return out
            return run
        if task=="ai_weekly":
            def run(progress):
                progress(stage="七日 Intelligence Brief",message="正在汇总最近七日数据并生成简报",percent=12)
                out=hub.ai_weekly_brief(force=bool(b.get("force")))
                progress(stage="七日 Intelligence Brief",message="简报已生成",percent=100)
                return out
            return run
        if task=="ai_result_batch":
            def run(progress):
                progress(stage="AI Result Set 批量操作",message="正在解析当前筛选与选择范围",percent=5)
                ids=hub.ai_result_channel_ids(int(b.get("result_set_id") or 0),search=str(b.get("search") or ""),conditions=list(b.get("conditions") or []))
                excluded={str(x) for x in list(b.get("excluded") or [])}; ids=[x for x in ids if x not in excluded]
                if str(b.get("selection_mode") or "")!="all_matching":
                    wanted={str(x) for x in list(b.get("channel_ids") or [])}; ids=[x for x in ids if x in wanted]
                return hub.batch_creators(ids,str(b.get("action") or ""),value=str(b.get("value") or ""),actor="ai-result-batch",progress=progress)
            return run
        if task=="creator_batch":
            ids,total=resumed_ids()
            def run(progress):
                return hub.batch_creators(ids,str(b.get("action") or ""),value=str(b.get("value") or ""),actor=str(b.get("actor") or "dashboard-batch"),progress=offset_progress(progress,total))
            return run
        if task=="review_batch":
            def run(progress):
                progress(stage="批量复核",message="正在写入人工复核结果",percent=10)
                selection=dict(b.get("selection") or {})
                if selection.get("mode")=="all_matching":
                    out=hub.batch_review_matching(selection,str(b.get("action") or ""),role=str(b.get("role") or ""),brands=list(b.get("brands") or []),actor=str(b.get("actor") or "dashboard-batch"))
                else:
                    out=hub.batch_review(list(b.get("video_ids") or []),str(b.get("action") or ""),role=str(b.get("role") or ""),brands=list(b.get("brands") or []),actor=str(b.get("actor") or "dashboard-batch"))
                progress(stage="批量复核",message="复核写入完成",percent=100)
                return out
            return run
        if task=="maintenance_health":
            def run(progress):
                progress(stage="数据库健康",message="正在运行 SQLite 健康检查",percent=15)
                out=hub.database_health(full=bool(b.get("full")),run_check=bool(b.get("run_check",False)))
                progress(stage="数据库健康",message="数据库健康检查完成",percent=100)
                return out
            return run
        if task=="maintenance_backup":
            def run(progress):
                progress(stage="数据库备份",message="正在创建 SQLite 一致性备份",percent=15)
                out=hub.backup_database(note=str(b.get("note") or "dashboard"))
                progress(stage="数据库备份",message="一致性备份创建完成",percent=100)
                return out
            return run
        if task=="maintenance_restore":
            def run(progress):
                progress(stage="恢复数据库",message="正在校验备份并创建恢复前保护备份",percent=10)
                out=hub.restore_database(str(b.get("name") or b.get("path") or ""),create_pre_backup=True)
                progress(stage="恢复数据库",message="数据库已恢复，正在重建 Dashboard",percent=75)
                build_dashboard(hub.db_path,self.output_dir,hub.settings)
                progress(stage="恢复数据库",message="恢复与 Dashboard 重建完成",percent=100)
                return out
            return run
        if task=="maintenance_snapshots":
            def run(progress):
                dry=bool(b.get("dry_run"))
                progress(stage="Snapshot 生命周期",message="正在估算可压缩 Snapshot" if dry else "正在压缩冗余 Snapshot",percent=12)
                out=hub.compact_snapshots(dry_run=dry,auto=False)
                progress(stage="Snapshot 生命周期",message="估算完成" if dry else "Snapshot 压缩完成",percent=100)
                return out
            return run
        if task=="dashboard_rebuild":
            def run(progress):
                progress(stage="重建 Dashboard",message="正在从 SQLite 生成 Dashboard",percent=10)
                out=build_dashboard(hub.db_path,self.output_dir,hub.settings)
                progress(stage="重建 Dashboard",message="Dashboard 已重建",percent=100)
                return out
            return run
        if task=="run_spec_execute":
            return lambda progress: hub.execute_run_spec(int(b.get("run_spec_id") or 0),progress=progress)
        if task=="business_import":
            def run(progress):
                filename=Path(str(b.get("filename") or "business_metrics.xlsx")).name
                raw=base64.b64decode(str(b.get("content_base64") or ""),validate=True)
                if not raw: raise ValueError("empty import file")
                if len(raw)>40*1024*1024: raise ValueError("business import file exceeds 40MB")
                suffix=Path(filename).suffix.lower()
                if suffix not in {".xlsx",".xlsm",".csv"}: raise ValueError("only XLSX/XLSM/CSV business imports are supported")
                progress(stage="商业数据导入",message=f"正在读取 {filename}",percent=5)
                tmp=None
                try:
                    with tempfile.NamedTemporaryFile(prefix="creator_hub_business_",suffix=suffix,delete=False) as f:
                        f.write(raw); tmp=Path(f.name)
                    out=hub.import_business_metrics(tmp,source_type=str(b.get("source_type") or "dashboard_import"),capture_at=(str(b.get("capture_at") or "") or None),progress=progress)
                    out["uploaded_filename"]=filename
                    progress(stage="商业数据导入",message=f"导入完成：{out.get('metric_values_upserted',0)} 个指标值",percent=100)
                    return out
                finally:
                    if tmp:
                        try: tmp.unlink(missing_ok=True)
                        except Exception: pass
            return run
        raise ValueError(f"unsupported job task: {task}")

    def _start_job(self, task: str, b: dict[str, Any]):
        titles={
            "review_reclassify_all":"离线重新识别全部系统分类", "review_reclassify_pending":"重新识别待复核视频",
            "monitoring_sync":"同步 Creator 数据", "monitoring_recheck":"重新检测频道状态",
            "capture_batch":"抓取并入库", "discovery_search":"博主发现搜索", "ai_query_search":"AI 搜索 Agent",
            "ai_ask":"Ask Hub", "ai_creator_brief":"Creator Brief", "ai_compare":"Creator 对比", "ai_weekly":"七日 Intelligence Brief", "ai_result_batch":"AI Result Set 批量操作",
            "creator_batch":"批量 Creator 操作", "review_batch":"批量人工复核",
            "maintenance_health":"数据库健康检查", "maintenance_backup":"数据库一致性备份", "maintenance_restore":"恢复数据库", "maintenance_snapshots":"Snapshot 生命周期维护",
            "dashboard_rebuild":"重建 Dashboard", "business_import":"导入商业表现数据", "run_spec_execute":"按冻结规格重新运行",
        }
        resource={
            "monitoring_sync":"youtube","monitoring_recheck":"youtube","capture_batch":"youtube","discovery_search":"youtube",
            "ai_query_search":"ai","ai_ask":"ai","ai_creator_brief":"ai","ai_compare":"ai","ai_weekly":"ai","run_spec_execute":"ai",
            "maintenance_health":"maintenance","maintenance_backup":"maintenance","maintenance_restore":"maintenance","maintenance_snapshots":"maintenance","dashboard_rebuild":"maintenance",
        }.get(task,"local")
        resumable=task in {"monitoring_sync","monitoring_recheck","capture_batch","creator_batch"}
        return self.jobs.start(task=task,title=titles.get(task,task),runner=self._job_runner(task,b),payload=b,resource_class=resource,resumable=resumable)

    def do_GET(self):
        if self.path == "/api/ping":
            import sys, os
            from .youtube_api import read_api_key
            key_env=self.hub.settings.get("api",{}).get("api_key_env","YOUTUBE_API_KEY")
            
            ai=self.hub.ai_status()
            return self._json({"ok":True,"mode":"interactive","version":getattr(__import__('creator_hub'), '__version__', ''),"python":sys.version.split()[0],"db":str(self.hub.db_path),"db_exists":Path(self.hub.db_path).exists(),"api_key_present":bool(read_api_key(key_env)),"ai":{"enabled":ai.get("enabled"),"available":ai.get("available"),"provider":ai.get("provider"),"model":ai.get("model")}})
        return super().do_GET()

    def do_POST(self):
        path=urlparse(self.path).path; b=self._body()
        try:
            # Stable V3.10 API contract. Legacy /api/* endpoints remain for the current Dashboard.
            if path=="/api/v1/field-registry":
                mb=metric_base_payload(self.hub.db_path,self.hub.settings);return self._v1(mb.get("field_registry") or {})
            if path=="/api/v1/jobs/start":
                task=str(b.get("task") or "").strip();return self._v1(self._start_job(task,dict(b.get("payload") or {})))
            if path=="/api/v1/jobs/status": return self._v1(self.jobs.get(str(b.get("job_id") or "")))
            if path=="/api/v1/jobs/list": return self._v1(self.jobs.list(int(b.get("limit") or 30)))
            if path=="/api/v1/jobs/cancel": return self._v1(self.jobs.cancel(str(b.get("job_id") or "")))
            if path=="/api/v1/jobs/retry": return self._v1(self.jobs.retry(str(b.get("job_id") or "")))
            if path=="/api/v1/creators/list": return self._v1(self.hub.list_creators(monitored_only=bool(b.get("monitored_only")),limit=int(b.get("limit") or 100)))
            if path=="/api/v1/videos/list": return self._v1(self.hub.classification_list(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),search=str(b.get("search") or ""),conditions=list(b.get("conditions") or []),sort=str(b.get("sort") or "published"),direction=str(b.get("dir") or "desc")))
            if path=="/api/v1/result-sets/get": return self._v1(self.hub.ai_result_set(int(b.get("result_set_id") or 0),page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),search=str(b.get("search") or ""),conditions=list(b.get("conditions") or []),sort=str(b.get("sort") or "rank"),direction=str(b.get("dir") or "asc")))
            if path=="/api/v1/result-sets/list": return self._v1(self.hub.ai_result_history(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),result_type=str(b.get("result_type") or ""),search=str(b.get("search") or "")))
            if path=="/api/v1/run-specs/get": return self._v1(self.hub.run_spec(int(b.get("id") or 0)))
            if path=="/api/v1/run-specs/list": return self._v1(self.hub.run_specs(str(b.get("spec_type") or ""),int(b.get("page") or 1),int(b.get("page_size") or 30)))
            if path=="/api/v1/run-specs/clone": return self._v1(self.hub.clone_run_spec(int(b.get("id") or 0)))
            if path=="/api/v1/run-specs/execute": return self._v1(self._start_job("run_spec_execute",{"run_spec_id":int(b.get("id") or 0)}))
            if path=="/api/v1/intelligence/weekly-context": return self._v1(self.hub.intelligence.weekly_context())
            if path=="/api/v1/contracts/effective": return self._v1(self.hub.effective_value(str(b.get("entity_type") or "creator"),str(b.get("entity_id") or ""),str(b.get("field_id") or "")))
            if path=="/api/v1/contracts/history": return self._v1(self.hub.contracts.history(str(b.get("entity_type") or "creator"),str(b.get("entity_id") or ""),str(b.get("field_id") or ""),int(b.get("limit") or 50)))
            if path=="/api/jobs/start":
                task=str(b.get("task") or "").strip()
                return self._json({"ok":True,"job":self._start_job(task,dict(b.get("payload") or {}))})
            if path=="/api/jobs/status":
                job=self.jobs.get(str(b.get("job_id") or ""))
                return self._json({"ok":bool(job),"job":job},200 if job else 404)
            if path=="/api/jobs/list":
                return self._json({"ok":True,"jobs":self.jobs.list(int(b.get("limit") or 10))})
            if path=="/api/jobs/cancel":
                return self._json({"ok":True,"job":self.jobs.cancel(str(b.get("job_id") or ""))})
            if path=="/api/jobs/retry":
                return self._json({"ok":True,"job":self.jobs.retry(str(b.get("job_id") or ""))})
            if path=="/api/ai/status":
                return self._json({"ok":True,**self.hub.ai_status()})
            if path=="/api/ai/config":
                api_key=b.get("api_key")
                clear_key=bool(b.get("clear_api_key"))
                if (api_key or clear_key) and self.client_address[0] not in {".1","::1"}:
                    raise ValueError("API Key can only be configured from the local machine")
                return self._json({"ok":True,**self.hub.configure_ai(dict(b.get("config") or b),api_key=(str(api_key) if api_key is not None else None),clear_api_key=clear_key)})
            if path=="/api/ai/models":
                api_key=b.get("api_key")
                if api_key and self.client_address[0] not in {".1","::1"}:
                    raise ValueError("API Key can only be used from the local machine")
                return self._json({"ok":True,**self.hub.ai_models(dict(b.get("config") or {}),api_key=(str(api_key) if api_key is not None else None))})
            if path=="/api/ai/test":
                return self._json({"ok":True,**self.hub.ai_test()})
            if path=="/api/ai/creator-brief":
                return self._json({"ok":True,**self.hub.ai_creator_brief(str(b.get("ref") or b.get("channel_id") or ""),force=bool(b.get("force")))})
            if path=="/api/ai/compare":
                return self._json({"ok":True,**self.hub.ai_compare_creators([str(x) for x in list(b.get("refs") or [])],force=bool(b.get("force")))})
            if path=="/api/ai/query-plan":
                return self._json({"ok":True,**self.hub.ai_query_planner(str(b.get("query") or ""),language=str(b.get("language") or "en"),objective=str(b.get("objective") or "creator discovery"),max_queries=int(b.get("max_queries") or 12),force=bool(b.get("force")))})
            if path=="/api/ai/query-search":
                result=self.hub.ai_query_search(
                    str(b.get("query") or ""),language=str(b.get("language") or "en"),objective=str(b.get("objective") or "creator discovery"),
                    max_queries=int(b.get("max_queries") or 12),max_results=int(b.get("max_results") or 25),
                    lookback_days=(int(b.get("lookback_days")) if b.get("lookback_days") else None),
                    target_country=(str(b.get("target_country") or "") or None),target_group=(str(b.get("target_group") or "") or None),force=bool(b.get("force")))
                return self._json({"ok":True,**result})
            if path=="/api/ai/ask":
                return self._json({"ok":True,**self.hub.ai_ask(str(b.get("question") or ""),force=bool(b.get("force")))})
            if path=="/api/ai/weekly-brief":
                return self._json({"ok":True,**self.hub.ai_weekly_brief(force=bool(b.get("force")))})
            if path=="/api/ai/history":
                return self._json({"ok":True,**self.hub.ai_history(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30))})
            if path=="/api/ai/feedback":
                return self._json({"ok":True,**self.hub.ai_feedback(int(b.get("finding_id") or 0),str(b.get("rating") or "neutral"),str(b.get("note") or ""))})
            if path=="/api/creators/suggest":
                return self._json({"ok":True,"rows":self.hub.creator_suggestions(str(b.get("query") or ""),limit=int(b.get("limit") or 10))})
            if path=="/api/ai/result-set":
                return self._json({"ok":True,**self.hub.ai_result_set(int(b.get("result_set_id") or 0),page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),search=str(b.get("search") or ""),conditions=list(b.get("conditions") or []),sort=str(b.get("sort") or "rank"),direction=str(b.get("dir") or "asc"))})
            if path=="/api/ai/result-history":
                return self._json({"ok":True,**self.hub.ai_result_history(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),result_type=str(b.get("result_type") or ""),search=str(b.get("search") or ""))})
            if path=="/api/ai/result-batch":
                ids=self.hub.ai_result_channel_ids(int(b.get("result_set_id") or 0),search=str(b.get("search") or ""),conditions=list(b.get("conditions") or []))
                excluded={str(x) for x in list(b.get("excluded") or [])}; ids=[x for x in ids if x not in excluded]
                if str(b.get("selection_mode") or "")!="all_matching":
                    wanted={str(x) for x in list(b.get("channel_ids") or [])}; ids=[x for x in ids if x in wanted]
                return self._json({"ok":True,**self.hub.batch_creators(ids,str(b.get("action") or ""),value=str(b.get("value") or ""),actor="ai-result-batch")})
            if path=="/api/dashboard/stats":
                return self._json({"ok":True,**dashboard_stats_payload(self.hub.db_path)})
            if path=="/api/creators/facts":
                payload=creator_facts_payload(self.hub.db_path,self.hub.settings)
                for c in payload.get("creators") or []:
                    c["detail_available"]=(self.output_dir/"creators"/(safe_filename(str(c.get("channel_id") or ""))+".html")).exists()
                return self._json({"ok":True,**payload})
            if path=="/api/metrics/base":
                return self._json({"ok":True,**metric_base_payload(self.hub.db_path,self.hub.settings)})
            if path=="/api/settings/get":
                key=str(b.get("key") or "")
                return self._json({"ok":True,"key":key,"value":self.hub.get_setting(key,None)})
            if path=="/api/settings/set":
                return self._json({"ok":True,**self.hub.set_setting(str(b.get("key") or ""),b.get("value"))})
            if path=="/api/settings/list":
                return self._json({"ok":True,"settings":self.hub.list_settings()})
            if path=="/api/saved-views/list":
                return self._json({"ok":True,"views":self.hub.saved_views(str(b.get("page_key") or ""))})
            if path=="/api/saved-views/save":
                return self._json({"ok":True,"view":self.hub.save_view(str(b.get("page_key") or ""),str(b.get("name") or ""),dict(b.get("config") or {}))})
            if path=="/api/saved-views/delete":
                return self._json({"ok":True,**self.hub.delete_view(int(b.get("id") or 0))})
            if path=="/api/business/creator":
                return self._json({"ok":True,**self.hub.creator_business_metrics(str(b.get("channel_id") or ""))})
            if path=="/api/workflow/set":
                return self._json({"ok":True,**self.hub.set_creator_workflow(str(b.get("channel_id") or ""),str(b.get("status") or "unreviewed"),note=str(b.get("note") or ""),actor=str(b.get("actor") or "dashboard"))})
            if path=="/api/creators/batch":
                return self._json({"ok":True,**self.hub.batch_creators(list(b.get("channel_ids") or []),str(b.get("action") or ""),value=str(b.get("value") or ""),actor=str(b.get("actor") or "dashboard-batch"))})
            if path=="/api/creators/capture-batch":
                return self._json({"ok":True,**self.hub.batch_capture_creators(
                    list(b.get("channel_ids") or []),window=str(b.get("window") or "30"),
                    from_date=str(b.get("from_date") or ""),to_date=str(b.get("to_date") or ""),
                    priority=str(b.get("priority") or "normal"),actor=str(b.get("actor") or "dashboard-capture-batch")
                )})
            if path=="/api/review/batch":
                selection=dict(b.get("selection") or {})
                if selection.get("mode")=="all_matching":
                    return self._json({"ok":True,**self.hub.batch_review_matching(selection,str(b.get("action") or ""),role=str(b.get("role") or ""),brands=list(b.get("brands") or []),actor=str(b.get("actor") or "dashboard-batch"))})
                return self._json({"ok":True,**self.hub.batch_review(list(b.get("video_ids") or []),str(b.get("action") or ""),role=str(b.get("role") or ""),brands=list(b.get("brands") or []),actor=str(b.get("actor") or "dashboard-batch"))})
            if path=="/api/monitoring/health":
                return self._json({"ok":True,**self.hub.monitoring_health(page=int(b.get("page") or 1),page_size=int(b.get("page_size") or 30),search=str(b.get("search") or ""),filters=dict(b.get("filters") or {}),sort=str(b.get("sort") or "attention"),direction=str(b.get("dir") or "asc"))})
            if path=="/api/monitoring/sync":
                return self._json({"ok":True,**self.hub.sync_selected(list(b.get("channel_ids") or []),mode=str(b.get("mode") or "incremental"),metric_days=(int(b.get("metric_days")) if b.get("metric_days") else None),all_videos=bool(b.get("all_videos")))})
            if path=="/api/monitoring/recheck":
                return self._json({"ok":True,**self.hub.recheck_channel_availability(list(b.get("channel_ids") or []),restore_monitoring=bool(b.get("restore_monitoring")))})
            if path=="/api/monitoring/override":
                return self._json({"ok":True,**self.hub.set_creator_availability_override(list(b.get("channel_ids") or []),availability_status=str(b.get("availability_status") or ""),content_status=str(b.get("content_status") or ""),monitoring_policy=str(b.get("monitoring_policy") or ""),note=str(b.get("note") or ""),actor=str(b.get("actor") or "dashboard"))})
            if path=="/api/monitoring/override-clear":
                return self._json({"ok":True,**self.hub.clear_creator_availability_override(list(b.get("channel_ids") or []),actor=str(b.get("actor") or "dashboard"))})
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
                    cols=columns or [("video_id","Video ID"),("title","视频"),("channel_title","博主"),("published_at","发布时间"),("current_views","播放量"),("current_likes","点赞数"),("current_comments","评论数"),("duration_seconds","视频时长（秒）"),("effective_role","有效分类（人工优先）"),("classification_source","分类来源"),("suggested_role","系统原始分类"),("human_role","人工分类"),("human_system_mismatch","人工/系统不一致"),("brands","有效品牌（人工优先）"),("confidence","系统置信度"),("review_status","复核状态")]
                    def it():
                        pg=1
                        while True:
                            x=self.hub.classification_list(page=pg,page_size=5000,**payload)
                            for r in x.get("rows") or []: yield r
                            if pg>=int(x.get("pages") or 1): break
                            pg+=1
                    return self._xlsx(xlsx_bytes(sheet or "Video Classifications",cols,it(),metadata=[("Search",payload["search"]),("Conditions",payload["conditions"])]),filename)
                if source=="ai_result_set":
                    rsid=int(b.get("result_set_id") or 0)
                    payload={"search":str(b.get("search") or ""),"conditions":list(b.get("conditions") or []),"sort":str(b.get("sort") or "rank"),"direction":str(b.get("dir") or "asc")}
                    cols=columns or [
                        ("result_rank","结果顺序"),("candidate_pool","候选池"),("channel_title","博主"),("channel_id","Channel ID"),("handle","Handle"),("country","国家/地区"),("subscribers","订阅数"),
                        ("objective_fit_score","综合目标适配分"),("objective_fit_status","综合适配等级"),("topic_affinity_score","主题适配"),("use_case_continuity_score","场景连续性"),("brand_safety_score","品牌安全"),("audience_size_fit_score","体量适配"),("query_coverage_score","Query覆盖分"),("profile_verification_status","Profile验证"),("continuity_gate_passed","长期制作门槛"),("brand_safety_status","品牌安全状态"),("brand_safety_flags","品牌安全标记"),("objective_fit_reason","适配证据"),("objective_terms_matched","命中要求词"),
                        ("sampled_recent_videos","最近上传抽样数"),("topic_recent_videos","主题相关视频数"),("topic_active_months","主题覆盖月份"),("objective_recent_videos","场景相关视频数"),("objective_recent_ratio","场景相关占比"),("objective_active_months","场景覆盖月份"),("objective_first_match","样本最早场景视频"),("objective_last_match","样本最近场景视频"),("creator_language","主要内容语言"),("creator_language_ratio","目标语言占比"),("creator_language_status","内容语言状态"),
                        ("representative_topic_video_title","主题代表视频"),("representative_topic_video_id","主题代表视频ID"),("representative_use_case_video_title","场景代表视频"),("representative_use_case_video_id","场景代表视频ID"),("discovery_score","发现评分"),("best_video_title","最佳搜索命中视频"),("best_video_views","最佳视频播放量"),("query_coverage","Query Coverage"),("matched_queries","命中Query"),
                        ("local_data_status","本地数据状态"),("ugphone_videos","UgPhone视频数"),("competitor_videos","竞品视频数"),("workflow_status","工作流"),("monitoring_enabled","监控中"),("priority","优先级")
                    ]
                    first=self.hub.ai_result_set(rsid,page=1,page_size=1,**payload)
                    info=first.get("result_set") or {}; req=info.get("request") or {}; plan=info.get("plan") or {}; md=info.get("metadata") or {}; fit=plan.get("fit_criteria") or {}
                    def ai_it():
                        pg=1
                        while True:
                            x=self.hub.ai_result_set(rsid,page=pg,page_size=5000,**payload)
                            for r in x.get("rows") or []: yield r
                            if pg>=int(x.get("pages") or 1): break
                            pg+=1
                    meta=[
                        ("Result Set ID",rsid),("Type",info.get("result_type")),("Input / Base Topic",info.get("input_text")),("Created At",info.get("created_at")),
                        ("Search Requirements",req.get("search_requirements")),("Search Language",req.get("language")),("Creator Content Language",fit.get("creator_language")),("Creator Language Min Ratio",fit.get("creator_language_min_ratio")),("Region Group",req.get("target_group")),("Country",req.get("target_country")),("Lookback Days",req.get("lookback_days")),("Max Queries",req.get("max_queries")),("Per Query Video Limit",req.get("max_results")),
                        ("Planner Strategy",plan.get("strategy")),("Planner Notes",plan.get("notes")),("Fit Criteria",fit),("Search Concepts",fit.get("search_concepts")),("Preferred Terms",fit.get("preferred_terms")),("Continuity Terms",fit.get("continuity_terms")),("Long-term Min Videos",fit.get("long_term_min_videos")),("Long-term Min Months",fit.get("long_term_min_months")),("Exclude Official Channels",fit.get("exclude_official_channels")),("Exclude Script/Cheat Channels",fit.get("exclude_script_cheat_channels")),("Exclude Terms",fit.get("exclude_terms")),("Subscriber Min",fit.get("subscriber_min")),("Subscriber Max",fit.get("subscriber_max")),
                        ("Planned Queries",plan.get("queries")),("Executed Queries",md.get("queries_executed")),("Raw Hits",md.get("hits")),("Raw Unique Creators",md.get("raw_unique_creators",md.get("unique_creators"))),("Pre-filter Candidates",md.get("pre_filter_candidates")),("Profile Budget",md.get("profile_budget")),("Retained Creators",md.get("retained_creators",info.get("total_items"))),("Recommended Candidates",md.get("recommended_candidates")),("Backup Candidates",md.get("backup_candidates")),("Weak Candidates",md.get("weak_candidates")),("Risk Candidates",md.get("risk_candidates")),("Filtered Out",md.get("filtered_out")),("Filtered Categories",md.get("filtered_categories")),("Pending Verification",md.get("pending_verification",md.get("unverified_candidates"))),("Recent-upload Profiled Creators",md.get("profiled_creators")),("Recent-upload Profile API Calls",md.get("profile_api_calls")),
                        ("AI Provider",md.get("ai_provider")),("AI Model",md.get("ai_model")),("Prompt Version",md.get("prompt_version")),
                        ("Current Export Search",payload["search"]),("Current Export Conditions",payload["conditions"]),("Current Export Sort",payload["sort"]+" "+payload["direction"]),("AI Run ID",info.get("ai_run_id")),("Discovery Run ID",info.get("discovery_run_id"))
                    ]
                    planned_q=list(plan.get("queries") or []); executed=list(md.get("queries_executed") or [])
                    funnel={str(x.get("query") or ""):dict(x) for x in (md.get("query_funnel") or []) if isinstance(x,dict)}
                    qrows=[]; seen=set()
                    for q in planned_q+executed:
                        q=str(q or "").strip()
                        if not q or q.casefold() in seen: continue
                        seen.add(q.casefold()); f=funnel.get(q,{})
                        qrows.append({"query":q,"planned":q in planned_q,"executed":q in executed,"planned_order":(planned_q.index(q)+1 if q in planned_q else None),"executed_order":(executed.index(q)+1 if q in executed else None),"video_hits":f.get("video_hits",0),"creator_hits":f.get("creator_hits",0),"raw_creators":f.get("raw_creators",0),"retained_creators":f.get("retained_creators",0),"risk_creators":f.get("risk_creators",0)})
                    risk_conditions=list(payload["conditions"])+[{"field":"candidate_pool","op":"contains","value":"风险"}]
                    def risk_it():
                        pg=1
                        while True:
                            x=self.hub.ai_result_set(rsid,page=pg,page_size=5000,search=payload["search"],conditions=risk_conditions,sort="objective_fit_score",direction="desc")
                            for r in x.get("rows") or []: yield r
                            if pg>=int(x.get("pages") or 1): break
                            pg+=1
                    risk_cols=[("channel_title","博主"),("channel_id","Channel ID"),("objective_fit_score","综合适配分"),("brand_safety_score","品牌安全"),("brand_safety_flags","风险标记"),("representative_fit_video_title","代表性适配视频"),("creator_language","主要内容语言"),("creator_language_ratio","目标语言占比")]
                    extra=[("Query Details",[("query","Query"),("planned","Planner计划"),("executed","实际执行"),("planned_order","计划顺序"),("executed_order","执行顺序"),("video_hits","视频命中"),("creator_hits","命中Creator"),("raw_creators","原始Creator"),("retained_creators","最终保留"),("risk_creators","风险候选")],qrows),("Risk Candidates",risk_cols,risk_it())]
                    return self._xlsx(xlsx_bytes(sheet or "AI Results",cols,ai_it(),metadata=meta,extra_sheets=extra),filename)
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
            if path=="/api/review/reclassify-all":
                return self._json({"ok":True,**self.hub.reclassify_videos(only_missing=False)})
            if path=="/api/rebuild-dashboard":
                return self._json({"ok":True,**build_dashboard(self.hub.db_path,self.output_dir,self.hub.settings)})
            self._json({"ok":False,"error":"unknown endpoint"},404)
        except Exception as e:
            if str(path).startswith("/api/v1/"):
                self._json({"ok":False,"error":{"code":type(e).__name__,"message":str(e)},"api_version":"v1"},500)
            else:
                self._json({"ok":False,"error":f"{type(e).__name__}: {e}"},500)


def serve_dashboard(hub: CreatorHub, output_dir: str | Path, host: str=".1", port: int=8765, open_browser: bool=True):
    out=Path(output_dir); build_dashboard(hub.db_path,out,hub.settings)
    class H(DashboardHandler): pass
    H.hub=hub; H.output_dir=out; H.jobs=JobStore(hub.db_path)
    def _runner_factory(task,payload):
        dummy=object.__new__(H);dummy.hub=hub;dummy.output_dir=out
        return DashboardHandler._job_runner(dummy,task,payload)
    H.jobs.set_runner_factory(_runner_factory)
    server=ThreadingHTTPServer((host,port),H)
    url=f"http://{host}:{port}/index.html"
    if open_browser:
        threading.Timer(0.7,lambda:webbrowser.open(url)).start()
    print(json.dumps({"url":url,"mode":"interactive","npm_required":False},ensure_ascii=False))
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
