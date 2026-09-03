from __future__ import annotations

import argparse, json, shutil, sqlite3, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from creator_hub.db import init_db
from creator_hub.dashboard import build_dashboard


def fixture(root: Path) -> Path:
    db=root/'visual.sqlite'; init_db(db)
    now='2026-08-21T00:00:00Z'
    with sqlite3.connect(db) as c:
        for i in range(18):
            cid=f'UCVISUAL{i:016d}'[:24]
            title=('Very Long Creator Name For Responsive Dashboard Testing '+str(i)) if i%3==0 else f'Creator {i}'
            c.execute('INSERT INTO creators(channel_id,channel_title,handle,channel_url,country_resolved,country_source,subscriber_count,channel_view_count,channel_video_count,monitoring_enabled,priority,source,discovered_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (cid,title,f'@creator{i}',f'https://www.youtube.com/channel/{cid}','PH','youtube_api',12345+i,1234567+i*1000,321+i,1,'normal','visual',now,now))
            vid=f'v{i:010d}'[:11]
            vtitle='Anime Expeditions AFK Auto Farm Overnight Multi Account Guide With A Deliberately Long Video Title For Layout Testing '+str(i)
            c.execute('INSERT INTO videos(video_id,channel_id,title,description,tags_json,published_at,current_views,current_likes,current_comments,discovered_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(vid,cid,vtitle,'','[]',now,10000+i,500+i,80+i,now))
            c.execute('INSERT INTO label_suggestions(video_id,suggested_role,brands_json,confidence,evidence_json,generated_at,rule_version) VALUES(?,?,?,?,?,?,?)',(vid,'daily','[]','confirmed','["use_case_not_cloud_evidence:afk"]',now,'0.2.0-scene-separated'))
            run='visual-run'
            if i==0:
                c.execute('INSERT INTO discovery_runs(run_id,base_query,search_source,started_at,status,hits,unique_creators) VALUES(?,?,?,?,?,?,?)',(run,'Anime Expeditions','api',now,'complete',18,18))
            c.execute('INSERT INTO discovery_creator_results(run_id,channel_id,channel_title,channel_url,subscribers,country_resolved,country_source,best_video_id,best_video_title,best_video_views,best_discovery_score,opportunity_tier,query_coverage,matched_queries_json,hit_video_count,found_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(run,cid,title,f'https://www.youtube.com/channel/{cid}',12345+i,'PH','youtube_api',vid,vtitle,10000+i,88-i/10,'A',4,'["Anime Expeditions AFK","Anime Expeditions overnight"]',3,now))
        metrics=[{'id':f'visual_metric_{i}','name':f'视觉回归指标 {i:02d}','group':'流量指标' if i%3 else '合作判断','description':'用于测试分组、搜索、排序和30条分页','type':'constructed','source_kind':'video_fact','source_field':'current_views','filter_label':'','window':'all','aggregation':'median','visible':True,'internal':False,'version':1,'updated_at':now} for i in range(75)]
        rules=[{'id':f'visual_rule_{i}','name':f'视觉回归规则 {i:02d}','group':'候选筛选' if i%2 else '合作判断','description':'用于测试规则目录分页和分组','conditions':[{'join':'','metric_type':'creator_fact','metric_key':'subscriber_count','op':'gte','value':str(1000+i)}],'version':1,'updated_at':now} for i in range(45)]
        c.execute('INSERT INTO app_settings(key,value_json,updated_at) VALUES(?,?,?)',('secondary_metrics',json.dumps({'schema_version':1,'metrics':metrics,'rules':rules,'activeRule':'','filters':[]},ensure_ascii=False),now))
        c.commit()
    out=root/'dashboard';build_dashboard(db,out,{})
    return out


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--strict',action='store_true');ap.add_argument('--screenshots',default='')
    a=ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        if a.strict: raise SystemExit('PLAYWRIGHT_REQUIRED: '+str(e))
        print('VISUAL_REGRESSION_SKIPPED: playwright not installed');return
    td=Path(tempfile.mkdtemp(prefix='ytcdh_visual_'))
    try:
        out=fixture(td); shot=Path(a.screenshots) if a.screenshots else td/'shots';shot.mkdir(parents=True,exist_ok=True)
        failures=[]
        pages=['index.html','metrics.html','labels.html','discovery.html','sync.html','ai.html']
        views=[(1366,768,1.0),(1600,900,1.0),(1920,1080,1.0),(1366,768,1.25)]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
            for w,h,z in views:
                page=browser.new_page(viewport={'width':w,'height':h})
                for name in pages:
                    page.set_content((out/name).read_text(encoding='utf-8'),wait_until='load')
                    common=['export_tools.js','table_tools.js','field_registry.js','product_ui.js']
                    specific={'index.html':['overview_filters.js','creator_detail.js'],'metrics.html':['table_tools.js','metrics_workspace.js'],'labels.html':['review.js'],'discovery.html':['discovery.js'],'sync.html':['maintenance.js','business_metrics.js'],'ai.html':['ai_copilot.js']}.get(name,[])
                    generated={'metrics.html':['creator_facts.js','metric_base.js','geography.js','metrics_config.js']}.get(name,[])
                    for js in generated:
                        fp=out/'assets'/js
                        if fp.exists():
                            try: page.add_script_tag(content=fp.read_text(encoding='utf-8'))
                            except Exception: pass
                    for js in common+specific:
                        fp=ROOT/'creator_hub'/'static'/js
                        if fp.exists():
                            try: page.add_script_tag(content=fp.read_text(encoding='utf-8'))
                            except Exception: pass
                    if z!=1: page.evaluate(f"document.documentElement.style.zoom='{z}'")
                    page.wait_for_timeout(350)
                    state=page.evaluate('''() => ({
                      docOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 3,
                      tableOverflow: [...document.querySelectorAll('.table-wrap')].filter(x=>x.scrollWidth>x.clientWidth+3).map(x=>({id:x.querySelector('table')?.id||'',sw:x.scrollWidth,cw:x.clientWidth})),
                      cellOverflow: [...document.querySelectorAll('.table-wrap td')].filter(td=>{if(getComputedStyle(td).display==='none')return false;const tr=td.getBoundingClientRect();return [...td.children].some(ch=>{const r=ch.getBoundingClientRect();return r.width>0 && (r.right>tr.right+4 || r.left<tr.left-4)})}).slice(0,12).map(x=>(x.innerText||'').slice(0,80)),
                      selectionHeaderClipped: [...document.querySelectorAll('#healthTable th[data-field~="selection"]')].some(th=>th.scrollWidth>th.clientWidth+2),
                      catalogOverflow: ([...document.querySelectorAll('#metricList .metric-item')].length>30 || [...document.querySelectorAll('#ruleList .metric-item')].length>30)
                    })''')
                    if state['docOverflow'] or state['tableOverflow'] or state['cellOverflow'] or state.get('selectionHeaderClipped') or state.get('catalogOverflow'):
                        failures.append({'page':name,'viewport':[w,h,z],**state})
                    page.screenshot(path=str(shot/f'{Path(name).stem}_{w}x{h}_z{z}.png'),full_page=True)
                page.close()
            browser.close()
        if failures:
            print(json.dumps(failures,ensure_ascii=False,indent=2));raise SystemExit('VISUAL_REGRESSION_FAILED')
        print('VISUAL_REGRESSION_OK')
    finally:
        shutil.rmtree(td,ignore_errors=True)

if __name__=='__main__': main()
