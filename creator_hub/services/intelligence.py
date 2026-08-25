from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any
from ..db import connect, json_load

class IntelligenceService:
    def __init__(self,hub): self.hub=hub; self.db_path=str(hub.db_path)
    def weekly_context(self)->dict[str,Any]:
        now=datetime.now(timezone.utc);cutoff=(now-timedelta(days=7)).isoformat().replace('+00:00','Z');stale_cutoff=(now-timedelta(minutes=30)).isoformat().replace('+00:00','Z')
        with connect(self.db_path) as conn:
            discovery_unique=int(conn.execute("SELECT COUNT(DISTINCT channel_id) FROM discovery_creator_results WHERE found_at>=?",(cutoff,)).fetchone()[0] or 0)
            first_discovered=int(conn.execute("SELECT COUNT(*) FROM (SELECT channel_id,MIN(found_at) first_seen FROM discovery_creator_results GROUP BY channel_id HAVING first_seen>=?)",(cutoff,)).fetchone()[0] or 0)
            # Latest AI candidate state per Creator in the week, not duplicate result-set rows.
            latest_ai={}
            rows=conn.execute("""SELECT i.channel_id,i.snapshot_json,i.result_set_id,r.created_at FROM ai_result_items i JOIN ai_result_sets r ON r.id=i.result_set_id
                                 WHERE r.result_type='youtube_agent' AND r.created_at>=? ORDER BY r.id DESC,i.id DESC""",(cutoff,)).fetchall()
            for rr in rows:
                cid=str(rr['channel_id'] or '')
                if cid and cid not in latest_ai: latest_ai[cid]=json_load(rr['snapshot_json'],{}) or {}
            pool_counts={'recommended':0,'backup':0,'weak':0,'risk':0,'pending':0}
            for x in latest_ai.values():
                pool=str(x.get('candidate_pool') or '')
                if pool.startswith('推荐'):pool_counts['recommended']+=1
                elif pool.startswith('候补'):pool_counts['backup']+=1
                elif pool.startswith('弱'):pool_counts['weak']+=1
                elif pool.startswith('风险'):pool_counts['risk']+=1
                elif '待验证' in pool:pool_counts['pending']+=1
            recent_rs=int(conn.execute("SELECT COUNT(*) FROM ai_result_sets WHERE result_type='youtube_agent' AND created_at>=?",(cutoff,)).fetchone()[0] or 0)
            sync=[dict(r) for r in conn.execute("SELECT status,COUNT(*) count FROM sync_runs WHERE started_at>=? GROUP BY status",(cutoff,)).fetchall()]
            stuck_sync=int(conn.execute("SELECT COUNT(*) FROM sync_runs WHERE status='running' AND started_at<?",(stale_cutoff,)).fetchone()[0] or 0)
            workflow_changes=[dict(r) for r in conn.execute("""SELECT COALESCE(old_status,'—') old_status,new_status,COUNT(*) count FROM creator_workflow_audit WHERE changed_at>=? GROUP BY old_status,new_status ORDER BY count DESC""",(cutoff,)).fetchall()]
            workflow_current=[dict(r) for r in conn.execute("SELECT status,COUNT(*) count FROM creator_workflow GROUP BY status ORDER BY count DESC").fetchall()]
            # Commercial snapshot changes are deterministic: latest snapshot vs prior baseline.
            def commercial(metric_key:str, latest_key:str, baseline_key:str, delta_key:str):
                all_rows=[dict(r) for r in conn.execute("""SELECT m.channel_id,c.channel_title,m.metric_value,m.captured_at,m.id FROM creator_business_metrics m JOIN creators c ON c.channel_id=m.channel_id WHERE m.metric_key=? ORDER BY m.channel_id,m.captured_at DESC,m.id DESC""",(metric_key,)).fetchall()]
                grouped={}
                for r in all_rows: grouped.setdefault(r['channel_id'],[]).append(r)
                changes=[]
                for cid,arr in grouped.items():
                    latest=arr[0];baseline=next((x for x in arr[1:] if str(x.get('captured_at') or '')<cutoff),arr[1] if len(arr)>1 else None)
                    if str(latest.get('captured_at') or '')>=cutoff and baseline:
                        lv=float(latest.get('metric_value') or 0);bv=float(baseline.get('metric_value') or 0)
                        changes.append({'channel_id':cid,'channel_title':latest.get('channel_title'),latest_key:lv,baseline_key:bv,delta_key:lv-bv,'captured_at':latest.get('captured_at')})
                changes.sort(key=lambda x:abs(float(x[delta_key])),reverse=True)
                return grouped,changes
            gmv_by,gmv_changes=commercial('gmv','latest_gmv_usd','baseline_gmv_usd','delta_gmv_usd')
            new_users_by,new_users_changes=commercial('new_users','latest_new_users','baseline_new_users','delta_new_users')
            top_gmv=[{'channel_id':cid,'channel_title':arr[0].get('channel_title'),'metric_value_usd':float(arr[0].get('metric_value') or 0),'captured_at':arr[0].get('captured_at')} for cid,arr in gmv_by.items()]
            top_gmv.sort(key=lambda x:x['metric_value_usd'],reverse=True);top_gmv=top_gmv[:10]
            # Top discovery is an action list: exclude known risk/official results and already-UgPhone-partnered creators.
            partnered={str(r[0]) for r in conn.execute("""SELECT DISTINCT v.channel_id FROM videos v LEFT JOIN video_labels l ON l.video_id=v.video_id LEFT JOIN label_suggestions s ON s.video_id=v.video_id WHERE COALESCE(l.human_role,s.suggested_role)='ugphone'""").fetchall()}
            competitor={str(r[0]) for r in conn.execute("""SELECT DISTINCT v.channel_id FROM videos v LEFT JOIN video_labels l ON l.video_id=v.video_id LEFT JOIN label_suggestions s ON s.video_id=v.video_id WHERE COALESCE(l.human_role,s.suggested_role)='competitor'""").fetchall()}
            raw_top=[dict(r) for r in conn.execute("SELECT d.channel_id,d.channel_title,MAX(d.best_discovery_score) score,MAX(d.opportunity_tier) tier FROM discovery_creator_results d WHERE d.found_at>=? GROUP BY d.channel_id,d.channel_title ORDER BY score DESC LIMIT 80",(cutoff,)).fetchall()]
            top=[]; skipped_partnered=0
            for r in raw_top:
                cid=str(r['channel_id']);x=latest_ai.get(cid,{});flags=' '.join(x.get('brand_safety_flags') or []).lower();pool=str(x.get('candidate_pool') or '')
                if pool.startswith('风险') or 'official_' in flags or 'script_cheat' in flags:continue
                if cid in partnered: skipped_partnered+=1; continue
                r['competitor_relationship']=cid in competitor
                r['ai_candidate_pool']=pool
                top.append(r)
                if len(top)>=10:break
        health=self.hub.monitoring_health(page=1,page_size=1).get('counts',{})
        failed_sync=sum(int(x.get('count') or 0) for x in sync if str(x.get('status'))=='failed');completed_sync=sum(int(x.get('count') or 0) for x in sync if str(x.get('status'))=='complete')
        headline=f"近7日首次发现 {first_discovered} 位 Creator · 去重AI推荐 {pool_counts['recommended']} · 同步失败任务 {failed_sync}"
        return {'period_days':7,'generated_at':now.isoformat(),'deterministic_headline':headline,
            'brief_metrics':{'first_discovered_creators':first_discovered,'discovery_hit_creators':discovery_unique,'sync_complete_runs':completed_sync,'sync_failed_runs':failed_sync,'stuck_sync_runs':stuck_sync,'recent_ai_result_sets':recent_rs,'unique_ai_creators':len(latest_ai),'ai_pool_counts':pool_counts,'workflow_changes':sum(int(x['count']) for x in workflow_changes),'gmv_changed_creators':len(gmv_changes),'new_users_changed_creators':len(new_users_changes),'top_discovery_skipped_partnered':skipped_partnered},
            'first_discovered_creators':first_discovered,'discovery_hit_creators':discovery_unique,'top_discoveries':top,
            'workflow_current_counts':workflow_current,'workflow_changes':workflow_changes,
            'sync_run_counts':sync,'stuck_sync_runs':stuck_sync,'monitoring_health':health,'recent_ai_pool_counts':pool_counts,'recent_ai_unique_creators':len(latest_ai),'recent_ai_result_sets':recent_rs,
            'top_latest_gmv_usd':top_gmv,'gmv_changes':gmv_changes[:10],'new_users_changes':new_users_changes[:10],
            'partnership_intelligence':{'top_discovery_excludes_existing_ugphone_partners':True,'skipped_existing_ugphone_partners':skipped_partnered,'competitor_relationship_flagged':sum(1 for x in top if x.get('competitor_relationship'))},
            'intelligence_sections':{'discovery':'new_supply_and_actionable_unpartnered','ai':'deduplicated_candidate_state','pipeline':'workflow_audit','commercial':'gmv_and_acquisition_snapshot_delta','partnership':'existing_partner_exclusion_and_competitor_flag','risk':'monitoring_and_brand_safety'} }
