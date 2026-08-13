from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from .db import connect, json_load
from . import __version__
from .metric_workspace import METRICS_BODY, write_metric_assets
from .util import esc, fmt_int, safe_filename

CSS = r'''
:root{--bg:#f5f7fb;--panel:#fff;--text:#172033;--muted:#6d778b;--line:#e6eaf1;--accent:#356ae6;--soft:#eef3ff;--good:#198754;--warn:#a86600;--bad:#b42318;--shadow:0 4px 20px rgba(27,39,65,.06)}
*{box-sizing:border-box}body{margin:0;font-family:Inter,"Segoe UI",Arial,sans-serif;background:var(--bg);color:var(--text)}a{color:inherit;text-decoration:none}.shell{display:flex;min-height:100vh}.side{width:238px;background:#111827;color:#d8deea;padding:22px 14px;position:fixed;top:0;bottom:0}.brand{font-size:18px;font-weight:700;color:#fff;padding:0 10px 20px}.version{font-size:11px;color:#8ea0be}.nav a{display:block;padding:10px 12px;margin:4px 0;border-radius:9px;color:#b9c4d7}.nav a:hover,.nav a.active{background:#243146;color:#fff}.main{margin-left:238px;width:calc(100% - 238px);padding:28px}.title{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:20px}.title h1{margin:0;font-size:25px}.sub{color:var(--muted);font-size:13px;margin-top:6px}.grid{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:14px}.grid.two{grid-template-columns:repeat(2,minmax(160px,1fr))}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:17px;box-shadow:var(--shadow)}.metric{font-size:28px;font-weight:700}.label{font-size:12px;color:var(--muted);margin-top:5px}.section{margin-top:18px}.section h2{font-size:16px;margin:0 0 12px}.toolbar{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap}.input{padding:9px 11px;border:1px solid #d8deea;border-radius:8px;background:#fff;min-width:260px}.table-wrap{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:auto;box-shadow:var(--shadow)}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:11px 12px;border-bottom:1px solid #edf0f5;text-align:left;vertical-align:top}th{color:#566074;background:#fafbfc;position:sticky;top:0;z-index:1}tr:hover td{background:#fbfcff}.pill{display:inline-block;padding:3px 7px;border-radius:999px;font-size:11px;background:#eef2f7;color:#4b5565;margin:1px 3px 1px 0}.pill.ugphone{background:#e8f7ee;color:#15723d}.pill.competitor{background:#fff0ed;color:#a63a2b}.pill.daily{background:#edf1f6;color:#5a6575}.pill.multi_brand{background:#fff6df;color:#8a5a00}.pill.pending,.pill.other_cloud_phone{background:#fff4dd;color:#8a5a00}.small{font-size:11px;color:var(--muted)}.mono{font-family:Consolas,monospace;font-size:12px}.evidence{max-width:520px;white-space:normal}.hero{display:flex;gap:18px;align-items:center}.avatar{width:64px;height:64px;border-radius:50%;object-fit:cover;background:#eee}.facts{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px;margin-top:16px}.fact b{display:block;font-size:18px;margin-top:3px}.spark{width:130px;height:32px}.muted{color:var(--muted)}.status-complete{color:var(--good)}.status-partial{color:var(--warn)}.status-failed{color:var(--bad)}.note{padding:12px 14px;background:#eef3ff;border:1px solid #d8e4ff;border-radius:10px;color:#405170;font-size:13px}.footer{color:#8791a3;font-size:11px;margin:24px 0}.btn{border:1px solid #d8deea;background:#fff;color:#25314a;border-radius:8px;padding:8px 12px;cursor:pointer;font-size:12px}.btn:hover{background:#f7f9fc}.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}.btn.danger{color:#b42318}.select{padding:9px 10px;border:1px solid #d8deea;border-radius:8px;background:#fff}.metric-builder{display:grid;grid-template-columns:minmax(320px,420px) 1fr;gap:16px}.builder-panel{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:var(--shadow)}.builder-panel h2{font-size:16px;margin:0 0 12px}.form-row{display:grid;grid-template-columns:120px 1fr;gap:10px;align-items:center;margin:9px 0}.form-row.top{align-items:start}.form-row label{font-size:12px;color:#5d6778}.form-row input,.form-row select,.form-row textarea{width:100%;padding:8px 9px;border:1px solid #d8deea;border-radius:7px;background:#fff}.filter-row{display:grid;grid-template-columns:1.2fr .8fr 1fr auto;gap:7px;margin:7px 0}.condition-row{display:grid;grid-template-columns:.65fr .9fr 1.2fr .65fr .8fr auto;gap:7px;margin:7px 0;align-items:center}.filter-row select,.filter-row input,.condition-row select,.condition-row input{min-width:0;padding:7px;border:1px solid #d8deea;border-radius:7px;background:#fff}.metric-list{display:grid;gap:8px}.metric-item{border:1px solid var(--line);border-radius:10px;padding:11px}.metric-item-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.metric-item-title{font-weight:650}.metric-meta{font-size:11px;color:var(--muted);margin-top:4px}.kpi-chip{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border-radius:8px;background:#f4f6fa;font-size:11px;margin:2px}.rule-hit{font-weight:700}.metric-table th.dynamic{background:#eef3ff}.empty{padding:24px;color:var(--muted);text-align:center}.inline{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.spread{justify-content:space-between}.badge-label{background:#fff5df;color:#855d12;padding:2px 6px;border-radius:999px;font-size:10px}.badge-fact{background:#e9f2ff;color:#2459ad;padding:2px 6px;border-radius:999px;font-size:10px}.compact-title{margin-bottom:12px}.compact-title h1{font-size:18px}.pager{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:10px 0}.pager .input{min-width:72px;width:82px}.link-ext{color:#2459ad;text-decoration:underline;text-underline-offset:2px}.link-local{color:#667085;text-decoration:underline;text-underline-offset:2px}.table-summary{font-size:12px;color:var(--muted);margin-left:auto}@media(max-width:1100px){.metric-builder{grid-template-columns:1fr}}@media(max-width:900px){.side{position:static;width:100%;height:auto}.shell{display:block}.main{margin:0;width:100%}.grid,.facts{grid-template-columns:repeat(2,1fr)}.nav{display:flex;flex-wrap:wrap}.nav a{display:inline-block}}
'''

ROLE_NAMES={"ugphone":"UgPhone","competitor":"竞品","daily":"日常视频","multi_brand":"多品牌云手机","other_cloud_phone":"其他云手机","pending":"待复核"}
CONF_NAMES={"high":"高","medium":"中","low":"低","review":"待复核"}
PRIORITY_NAMES={"high":"高","normal":"普通","low":"低","archive":"归档"}
MODE_NAMES={"incremental":"增量同步","full-history":"全历史同步","metrics-only":"仅刷新指标","channel-only":"仅刷新频道"}
STATUS_NAMES={"complete":"完成","partial":"部分完成","failed":"失败","running":"运行中"}


def _role_name(value: str | None) -> str:
    return ROLE_NAMES.get(value or "", value or "—")


def _nav(active: str) -> str:
    items=[("overview","index.html","总览"),("metrics","metrics.html","二次指标"),("labels","labels.html","视频分类"),("discovery","discovery.html","博主发现"),("sync","sync.html","数据更新")]
    return f'<div class="side"><div class="brand">YouTube 博主数据中心<br><span class="version">v{__version__}</span></div><div class="nav">' + ''.join(f'<a class="{"active" if k==active else ""}" href="{href}">{name}</a>' for k,href,name in items) + '</div></div>'


def _page(title: str, active: str, body: str, base: str = "") -> str:
    nav = _nav(active)
    if base:
        for name in ("index.html","metrics.html","labels.html","discovery.html","sync.html"):
            nav=nav.replace(f'href="{name}"',f'href="{base}{name}"')
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · YouTube 博主数据中心</title><style>{CSS}</style></head><body><div class="shell">{nav}<main class="main">{body}<div class="footer">YouTube 博主数据中心 · 数据存储于本地 SQLite · v{__version__}</div></main></div></body></html>'''


def _sparkline(points: list[int | None]) -> str:
    nums=[x for x in points if isinstance(x,(int,float))]
    if len(nums)<2:return '<span class="small">—</span>'
    lo,hi=min(nums),max(nums);span=max(1,hi-lo);w,h=130,32;coords=[]
    for i,v in enumerate(nums):
        x=1+(w-2)*i/max(1,len(nums)-1);y=1+(h-2)*(1-(v-lo)/span);coords.append(f"{x:.1f},{y:.1f}")
    return f'<svg class="spark" viewBox="0 0 {w} {h}"><polyline fill="none" stroke="currentColor" stroke-width="1.8" points="{" ".join(coords)}"/></svg>'


def _page_size_controls(prefix: str) -> str:
    return f'<span class="small">每页</span><input id="{prefix}PageSize" class="input" type="number" min="1" max="5000" value="30" style="min-width:72px;width:82px"><button class="btn" id="{prefix}PageSizeConfirm">确定</button><span class="small">条</span>'

def _pager(prefix: str) -> str:
    return f'<div class="pager"><button class="btn" id="{prefix}First">第一页</button><button class="btn" id="{prefix}Prev">上一页</button><span id="{prefix}PageButtons" class="inline"></span><button class="btn" id="{prefix}Next">下一页</button><button class="btn" id="{prefix}Last">最后一页</button><span class="small">跳转到</span><input id="{prefix}PageInput" class="input" type="number" min="1" value="1"><button class="btn" id="{prefix}Jump">跳转</button><span id="{prefix}PageInfo" class="small"></span></div>'


def _creator_rows(conn) -> list[dict[str, Any]]:
    sql="""
    WITH va AS (
      SELECT v.channel_id,
             MAX(v.published_at) AS latest_upload,
             COUNT(*) AS stored_videos,
             SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='ugphone' THEN 1 ELSE 0 END) AS identified_ugphone,
             SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='competitor' THEN 1 ELSE 0 END) AS identified_competitor,
             SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='daily' THEN 1 ELSE 0 END) AS identified_daily,
             SUM(CASE WHEN instr(lower(COALESCE(l.brands_json,s.brands_json,'')),'ldcloud')>0 THEN 1 ELSE 0 END) AS ldcloud_videos,
             SUM(CASE WHEN instr(lower(COALESCE(l.brands_json,s.brands_json,'')),'redfinger')>0 THEN 1 ELSE 0 END) AS redfinger_videos,
             SUM(CASE WHEN instr(lower(COALESCE(l.brands_json,s.brands_json,'')),'vsphone')>0 THEN 1 ELSE 0 END) AS vsphone_videos,
             SUM(CASE WHEN l.video_id IS NOT NULL THEN 1 ELSE 0 END) AS manual_corrections
      FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id
      GROUP BY v.channel_id
    )
    SELECT c.*,COALESCE(va.latest_upload,'') latest_upload,COALESCE(va.stored_videos,0) stored_videos,
           COALESCE(va.identified_ugphone,0) identified_ugphone,COALESCE(va.identified_competitor,0) identified_competitor,
           COALESCE(va.identified_daily,0) identified_daily,COALESCE(va.ldcloud_videos,0) ldcloud_videos,
           COALESCE(va.redfinger_videos,0) redfinger_videos,COALESCE(va.vsphone_videos,0) vsphone_videos,
           COALESCE(va.manual_corrections,0) manual_corrections
    FROM creators c LEFT JOIN va ON va.channel_id=c.channel_id
    ORDER BY c.monitoring_enabled DESC,COALESCE(c.last_synced_at,c.discovered_at) DESC
    """
    return [dict(r) for r in conn.execute(sql).fetchall()]


def build_dashboard(db_path: str | Path, output_dir: str | Path, settings: dict[str, Any]) -> dict[str, Any]:
    out=Path(output_dir);creators_dir=out/'creators';creators_dir.mkdir(parents=True,exist_ok=True);limits=settings.get('dashboard',{})
    with connect(db_path) as conn:
        stats={
          'creators':conn.execute('SELECT COUNT(*) FROM creators').fetchone()[0],
          'monitored':conn.execute('SELECT COUNT(*) FROM creators WHERE monitoring_enabled=1').fetchone()[0],
          'videos':conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0],
          'snapshots':conn.execute('SELECT COUNT(*) FROM video_snapshots').fetchone()[0],
          'classified':conn.execute('SELECT COUNT(*) FROM label_suggestions').fetchone()[0],
          'review':conn.execute("""SELECT COUNT(*) FROM label_suggestions s LEFT JOIN video_labels l ON l.video_id=s.video_id WHERE l.video_id IS NULL AND (s.suggested_role='pending' OR s.confidence='review')""").fetchone()[0],
          'manual_corrections':conn.execute('SELECT COUNT(*) FROM video_labels').fetchone()[0],
        }
        creators=_creator_rows(conn)
        last_sync=dict(conn.execute('SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1').fetchone() or {})

        rows=[]
        for c in creators:
            fn=safe_filename(c['channel_id'])+'.html';priority=PRIORITY_NAMES.get(c.get('priority'),c.get('priority') or '—')
            country=c.get('country_resolved') or c.get('country_api') or '—'
            identity=['合作过博主' if c.get('identified_ugphone',0)>0 else '未合作博主']
            if c.get('ldcloud_videos',0)>0: identity.append('LDCloud合作博主')
            if c.get('redfinger_videos',0)>0: identity.append('RedFinger合作博主')
            if c.get('vsphone_videos',0)>0: identity.append('VSPhone合作博主')
            search=(c.get('channel_title') or '')+' '+(c.get('handle') or '')+' '+country+' '+c['channel_id']+' '+' '.join(identity)
            tags=''.join('<span class="pill '+('ugphone' if x=='合作过博主' else 'competitor' if x.endswith('合作博主') and x!='合作过博主' else '')+'">'+esc(x)+'</span>' for x in identity)
            channel_url=c.get('channel_url') or f"https://www.youtube.com/channel/{c['channel_id']}"
            rows.append(f'''<tr data-cid="{esc(c['channel_id'])}" data-search="{esc(search)}"><td><a class="link-ext" target="_blank" rel="noopener" href="{esc(channel_url)}"><b>{esc(c.get('channel_title') or c['channel_id'])}</b></a><div class="small mono">{esc(c.get('handle') or c['channel_id'])}</div><div class="small"><a class="link-local" href="creators/{fn}">查看详情</a></div></td><td>{esc(country)}<div class="small">{esc(c.get('country_source') or ('youtube_api' if c.get('country_api') else 'unknown'))}</div></td><td>{fmt_int(c.get('subscriber_count'))}</td><td>{fmt_int(c.get('channel_view_count'))}</td><td>{fmt_int(c.get('stored_videos'))}</td><td>{esc((c.get('latest_upload') or '')[:10] or '—')}</td><td>{tags}</td><td>{fmt_int(c.get('identified_ugphone'))}</td><td>{fmt_int(c.get('ldcloud_videos'))} / {fmt_int(c.get('redfinger_videos'))} / {fmt_int(c.get('vsphone_videos'))}<div class="small">LDCloud / RedFinger / VSPhone</div></td><td><span class="pill">{esc(priority)}</span>{' <span class="pill ugphone">监控中</span>' if c.get('monitoring_enabled') else ''}<div class="small">{esc(c.get('last_synced_at') or '未同步')}</div></td></tr>''')
        body=f'''<div class="title"><div><h1>YouTube 博主数据中心</h1><div class="sub">YouTube 客观事实、历史快照、系统视频分类与数据更新时间</div></div><div class="small">最近同步：{esc(last_sync.get('finished_at') or last_sync.get('started_at') or '—')}</div></div>
        <div class="grid two"><div class="card"><div class="metric">{stats['monitored']:,}</div><div class="label">监控中的博主</div></div><div class="card"><div class="metric">{stats['videos']:,}</div><div class="label">已存视频</div></div></div>
        <div class="section"><div class="note"><b>身份口径：</b>存在 UgPhone 视频 → “合作过博主”；不存在 → “未合作博主”。若检测到对应竞品视频，则分别标记为“LDCloud合作博主”“RedFinger合作博主”“VSPhone合作博主”。人工修正仅覆盖系统误判。</div></div>
        <div class="section"><h2>博主库</h2><div class="toolbar"><input id="q" class="input" placeholder="搜索博主 / Handle / Channel ID / 国家 / 身份标签"></div><div class="builder-panel"><div id="ovFilterConditions"></div><div class="inline"><button class="btn" id="ovAddFilter">添加筛选条件</button><button class="btn primary" id="ovApplyFilter">应用筛选</button><button class="btn" id="ovClearFilter">清除</button><span class="small">聚合标签为布尔标签，选择后直接按“存在”筛选，不需要填写数值。</span></div></div><div class="toolbar section"><span class="small">排序</span><select id="ovSort" class="select"><option value="ugphone_video_count" selected>UgPhone视频数</option><option value="channel_title">博主名称</option><option value="country">国家</option><option value="subscriber_count">订阅数</option><option value="channel_view_count">频道累计播放量</option><option value="stored_videos">已存视频数</option><option value="latest_upload">最近发布</option><option value="ldcloud_video_count">LDCloud视频数</option><option value="redfinger_video_count">RedFinger视频数</option><option value="vsphone_video_count">VSPhone视频数</option></select><select id="ovSortDir" class="select"><option value="desc" selected>降序</option><option value="asc">升序</option></select>{_page_size_controls("ov")}<span id="ovSummary" class="table-summary"></span></div><div class="table-wrap"><table><thead><tr><th>博主</th><th>国家 / 证据</th><th>订阅数</th><th>频道累计播放量</th><th>已存视频数</th><th>最近发布</th><th>身份标签</th><th>UgPhone视频数</th><th>竞品品牌视频数</th><th>数据状态</th></tr></thead><tbody id="rows">{''.join(rows)}</tbody></table></div>{_pager("ov")}</div>
        <script src="assets/creator_facts.js"></script><script src="assets/metric_base.js"></script><script src="assets/table_tools.js"></script><script src="assets/overview_filters.js"></script>'''
        (out/'index.html').write_text(_page('总览','overview',body),encoding='utf-8')

        # Creator detail pages: all locally stored videos, one video query + one batched snapshot query per creator.
        # Pagination/filter/sort are performed in the generated detail page; no video rows are silently truncated.
        snap_limit=int(limits.get('snapshot_points_per_video',60))
        for c in creators:
            videos=[dict(r) for r in conn.execute("""SELECT v.*,s.suggested_role,s.brands_json sbrands,s.confidence,s.evidence_json,l.human_role,l.brands_json hbrands,l.labeled_by,l.labeled_at
              FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id
              WHERE v.channel_id=?
              ORDER BY CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='ugphone' OR instr(lower(COALESCE(l.brands_json,s.brands_json,'')),'ugphone')>0 THEN 0 ELSE 1 END,
                       COALESCE(v.current_views,0) DESC, v.published_at DESC""",(c['channel_id'],)).fetchall()]
            snap_map:dict[str,list[int|None]]={}
            if videos:
                snap_rows=conn.execute("""WITH selected AS (SELECT video_id FROM videos WHERE channel_id=?),
                  ranked AS (SELECT vs.video_id,vs.views,vs.captured_at,ROW_NUMBER() OVER(PARTITION BY vs.video_id ORDER BY vs.captured_at DESC) rn FROM video_snapshots vs JOIN selected x ON x.video_id=vs.video_id)
                  SELECT video_id,views FROM ranked WHERE rn<=? ORDER BY video_id,rn DESC""",(c['channel_id'],snap_limit)).fetchall()
                for sr in snap_rows:snap_map.setdefault(sr['video_id'],[]).append(sr['views'])
            tags=[r[0] for r in conn.execute('SELECT tag FROM creator_tags WHERE channel_id=? ORDER BY tag',(c['channel_id'],)).fetchall()]
            vrows=[]
            for v in videos:
                human=v.get('human_role');system=v.get('suggested_role') or 'pending';role=human or system
                brands=json_load(v.get('hbrands') if human else v.get('sbrands'),[]);confidence=CONF_NAMES.get(v.get('confidence'),v.get('confidence') or '—')
                label=f'<span class="pill {esc(role)}">{esc(_role_name(role))}</span>'
                if human:label+=f'<div class="small">人工修正 · 原系统识别：{esc(_role_name(system))}</div>'
                else:label+=f'<div class="small">系统识别 · 置信度：{esc(confidence)}</div>'
                search=(v.get('title') or '')+' '+v['video_id']+' '+role+' '+' '.join(brands)
                brand_text=' '.join(str(x).lower() for x in brands)
                is_ugphone='1' if role=='ugphone' or 'ugphone' in brand_text else '0'
                vrows.append(f'''<tr data-search="{esc(search)}" data-role="{esc(role)}" data-brands="{esc(brand_text)}" data-ugphone="{is_ugphone}" data-views="{int(v.get('current_views') or 0)}" data-likes="{int(v.get('current_likes') or 0)}" data-comments="{int(v.get('current_comments') or 0)}" data-published="{esc(v.get('published_at') or '')}" data-title="{esc(v.get('title') or '')}"><td><a target="_blank" rel="noopener" href="https://www.youtube.com/watch?v={esc(v['video_id'])}"><b>{esc(v.get('title') or v['video_id'])}</b></a><div class="small mono">{esc(v['video_id'])}</div></td><td>{esc((v.get('published_at') or '')[:10] or '—')}</td><td>{fmt_int(v.get('current_views'))}<div>{_sparkline(list(reversed(snap_map.get(v['video_id'],[]))))}</div></td><td>{fmt_int(v.get('current_likes'))}</td><td>{fmt_int(v.get('current_comments'))}</td><td>{label}<div class="small">{esc(', '.join(brands) or '—')}</div></td><td><div class="small">{esc(v.get('last_metric_at') or '—')}</div></td></tr>''')
            facts=f'''<div class="facts"><div class="card fact"><span class="small">订阅数</span><b>{fmt_int(c.get('subscriber_count'))}</b></div><div class="card fact"><span class="small">频道累计播放量</span><b>{fmt_int(c.get('channel_view_count'))}</b></div><div class="card fact"><span class="small">YouTube视频总数</span><b>{fmt_int(c.get('channel_video_count'))}</b></div><div class="card fact"><span class="small">国家（API）</span><b>{esc(c.get('country_api') or '—')}</b></div></div>'''
            cbody=f'''<div class="title"><div><a class="small" href="../index.html">← 返回博主库</a><div class="hero"><img class="avatar" src="{esc(c.get('thumbnail_url') or '')}"><div><h1>{esc(c.get('channel_title') or c['channel_id'])}</h1><div class="sub mono">{esc(c['channel_id'])} · {esc(c.get('handle') or '')}</div><div>{''.join('<span class="pill">'+esc(t)+'</span>' for t in tags)}</div></div></div></div><div class="small">最近同步<br>{esc(c.get('last_synced_at') or '—')}</div></div>{facts}<div class="section"><h2>视频 · 当前客观数据 + 系统分类</h2>
            <div class="toolbar"><input id="detailSearch" class="input" placeholder="搜索视频 / Video ID / 分类 / 品牌"></div><div class="builder-panel"><div id="detailFilterConditions"></div><div class="inline"><button class="btn" id="detailAddFilter">添加筛选条件</button><button class="btn primary" id="detailApplyFilter">应用筛选</button><button class="btn" id="detailClearFilter">清除筛选</button></div></div>
            <div class="toolbar section"><span class="small">排序</span><select id="detailSort" class="select"><option value="priority_views" selected>UgPhone优先 + 播放量</option><option value="views">播放量</option><option value="published">发布时间</option><option value="likes">点赞数</option><option value="comments">评论数</option><option value="title">视频名称</option><option value="role">视频分类</option></select><select id="detailSortDir" class="select"><option value="desc" selected>降序</option><option value="asc">升序</option></select>{_page_size_controls("detail")}<span id="detailSummary" class="table-summary"></span></div>
            <div class="table-wrap"><table><thead><tr><th>视频</th><th>发布时间</th><th>播放量 / 历史</th><th>点赞数</th><th>评论数</th><th>视频分类</th><th>指标抓取时间</th></tr></thead><tbody id="detailRows">{''.join(vrows)}</tbody></table></div>{_pager("detail")}</div><script src="../assets/table_tools.js"></script><script src="../assets/creator_detail.js"></script>'''
            (creators_dir/(safe_filename(c['channel_id'])+'.html')).write_text(_page(c.get('channel_title') or c['channel_id'],'overview',cbody,base='../'),encoding='utf-8')

        static_dir=Path(__file__).resolve().parent/'static'; static_js=static_dir/'metrics_workspace.js';write_metric_assets(conn,out,creators,last_sync,static_js)
        assets=out/'assets'
        geo_path=Path(__file__).resolve().parents[1]/'config'/'geography.json'
        geo_obj=json.loads(geo_path.read_text(encoding='utf-8'))
        (assets/'geography.js').write_text('window.CDH_GEOGRAPHY='+json.dumps(geo_obj,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
        (assets/'discovery.js').write_text((static_dir/'discovery.js').read_text(encoding='utf-8'),encoding='utf-8')
        (assets/'table_tools.js').write_text((static_dir/'table_tools.js').read_text(encoding='utf-8'),encoding='utf-8')
        (assets/'creator_detail.js').write_text((static_dir/'creator_detail.js').read_text(encoding='utf-8'),encoding='utf-8')
        (assets/'review.js').write_text((static_dir/'review.js').read_text(encoding='utf-8'),encoding='utf-8')
        (out/'metrics.html').write_text(_page('二次指标','metrics',METRICS_BODY),encoding='utf-8')

        # Video classification page. The base dataset is ALL locally stored videos.
        # Static HTML contains only a bounded preview; interactive mode queries the complete SQLite dataset.
        lim=int(limits.get('classification_preview_limit',limits.get('pending_label_limit',300)))
        review=[dict(r) for r in conn.execute("""SELECT v.video_id,v.title,v.channel_id,v.published_at,v.current_views,v.current_likes,v.current_comments,
          s.suggested_role,s.brands_json AS system_brands_json,s.confidence,s.evidence_json,s.rule_version,
          l.human_role,l.brands_json AS human_brands_json,l.labeled_by,l.labeled_at,c.channel_title
          FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id JOIN creators c ON c.channel_id=v.channel_id LEFT JOIN video_labels l ON l.video_id=v.video_id
          ORDER BY v.published_at DESC, v.video_id ASC LIMIT ?""",(lim,)).fetchall()]
        prows=[]
        role_opts=''.join(f'<option value="{k}">{esc(v)}</option>' for k,v in ROLE_NAMES.items())
        for r in review:
            system_role=r.get('suggested_role') or 'pending'; system_brands=json_load(r.get('system_brands_json'),[])
            human_role=r.get('human_role'); human_brands=json_load(r.get('human_brands_json'),[]) if human_role else []
            final_role=human_role or system_role; brands=human_brands if human_role else system_brands
            ev=json_load(r.get('evidence_json'),[]);conf=CONF_NAMES.get(r.get('confidence'),r.get('confidence') or '—')
            requires_review=(not human_role and (system_role=='pending' or r.get('confidence')=='review'))
            review_status='manual_reviewed' if human_role else ('pending_review' if requires_review else 'system_only')
            review_name={'manual_reviewed':'已人工复核','pending_review':'待人工复核','system_only':'系统分类'}[review_status]
            video_url=f"https://www.youtube.com/watch?v={r['video_id']}"; channel_url=f"https://www.youtube.com/channel/{r['channel_id']}"
            checks=' '.join(f'<label class="small"><input class="review-brand" type="checkbox" value="{b}" {"checked" if b in brands else ""}> {name}</label>' for b,name in [('ugphone','UgPhone'),('ldcloud','LDCloud'),('redfinger','RedFinger'),('vsphone','VSPhone')])
            selected_opts=role_opts.replace(f'value="{final_role}"',f'value="{final_role}" selected',1)
            prows.append(f"""<tr data-video="{esc(r['video_id'])}" data-search="{esc((r.get('title') or '')+' '+(r.get('channel_title') or '')+' '+final_role+' '+' '.join(brands))}" data-role="{esc(final_role)}" data-system-role="{esc(system_role)}" data-brands="{esc(' '.join(brands).lower())}" data-review="{review_status}" data-confidence="{esc(r.get('confidence') or '')}" data-views="{r.get('current_views') or 0}" data-published="{esc(r.get('published_at') or '')}" data-title="{esc(r.get('title') or '')}" data-creator="{esc(r.get('channel_title') or '')}"><td><a class="link-ext" target="_blank" rel="noopener" href="{esc(video_url)}"><b>{esc(r.get('title'))}</b></a><div class="small"><a class="link-ext" target="_blank" rel="noopener" href="{esc(channel_url)}">{esc(r.get('channel_title'))}</a></div><div class="mono small">{esc(r['video_id'])}</div></td><td>{fmt_int(r.get('current_views'))}</td><td><span class="pill {esc(system_role)}">{esc(_role_name(system_role))}</span><div class="small">置信度：{esc(conf)} · {esc(', '.join(system_brands) or '—')}</div></td><td class="evidence">{''.join('<span class="pill">'+esc(str(x))+'</span>' for x in ev)}</td><td><span class="pill">{review_name}</span><div class="small">最终分类：{esc(_role_name(final_role))}</div>{f'<div class="small">复核时间：{esc(r.get("labeled_at") or "—")}</div>' if human_role else ''}</td><td><select class="select review-role">{selected_opts}</select><div style="margin:6px 0">{checks}</div><div class="inline"><button class="btn primary confirm-system">确认系统分类</button><button class="btn save-review">保存修正</button></div><div class="small row-status"></div></td></tr>""")
        lbody=f"""<div class="title"><div><h1>视频分类</h1><div class="sub">管理全部本地视频的系统分类；“待人工复核”只是复核状态之一，可通过筛选条件单独查看。</div></div></div>
        <div class="note" id="reviewModeNote"><b>当前为只读模式。</b> 全部视频可查看；如需确认或修正分类，请使用 <span class="mono">start-dashboard.cmd</span> 打开交互模式。</div>
        <div class="grid"><div class="card"><div class="metric" id="allVideoCount">{stats['videos']:,}</div><div class="label">全部本地视频</div></div><div class="card"><div class="metric" id="classifiedCount">{stats['classified']:,}</div><div class="label">已生成系统分类</div></div><div class="card"><div class="metric" id="reviewCount">{stats['review']:,}</div><div class="label">待人工复核</div></div><div class="card"><div class="metric" id="reviewedCount">{stats['manual_corrections']:,}</div><div class="label">已人工复核</div></div></div>
        <div class="section"><div class="note"><b>分类与复核口径：</b>系统会自动为全部视频生成分类。证据充分的分类直接作为系统结果；证据不足的条目标记为“待人工复核”。人工复核不是本页的数据范围，而是一种状态：可以筛选“全部 / 待人工复核 / 已人工复核 / 未人工复核 / 仅系统分类”。人工结果会覆盖系统结果并保留审计记录。</div></div>
        <div class="section"><div class="toolbar"><button class="btn primary" id="reclassifyReview">离线重新识别全部待复核</button><span id="reviewStatus" class="small"></span></div>
        <div class="toolbar"><input id="labelSearch" class="input" placeholder="搜索视频 / 博主 / Video ID"><select id="labelSort" class="select"><option value="published">发布时间</option><option value="views">播放量</option><option value="creator">博主</option><option value="title">视频标题</option><option value="role">最终分类</option><option value="review_status">复核状态</option></select><select id="labelSortDir" class="select"><option value="desc">降序</option><option value="asc">升序</option></select>{_page_size_controls('label')}<span id="labelPageInfoTop" class="small"></span><span id="labelSummary" class="table-summary"></span></div>
        <div class="builder-panel"><div id="labelFilterConditions"></div><div class="inline"><button class="btn" id="labelAddFilter">添加筛选条件</button><button class="btn primary" id="labelApplyFilter">应用筛选</button><button class="btn" id="labelClearFilter">清除筛选</button><span class="small">默认不附加复核状态条件，即显示全部视频。</span></div></div>
        <div class="table-wrap section"><table><thead><tr><th>视频</th><th>播放量</th><th>系统分类</th><th>识别证据</th><th>复核状态 / 最终分类</th><th>人工复核</th></tr></thead><tbody id="labelRows">{''.join(prows)}</tbody></table></div>{_pager('label')}</div>
        <script src="assets/table_tools.js"></script><script src="assets/review.js"></script>"""
        (out/'labels.html').write_text(_page('视频分类','labels',lbody),encoding='utf-8')

        hits=[dict(r) for r in conn.execute("""SELECT d.*,c.monitoring_enabled,c.country_api,c.country_resolved AS library_country,c.subscriber_count AS library_subscribers FROM discovery_hits d LEFT JOIN creators c ON c.channel_id=d.channel_id ORDER BY COALESCE(d.pre_score,-1) DESC, d.found_at DESC, d.id DESC""").fetchall()]
        drows=[]
        for h in hits:
            country=h.get('library_country') or h.get('country_resolved') or h.get('country_api') or '—'; subs=h.get('library_subscribers') or h.get('subscribers')
            local_status='已在博主库' if h.get('monitoring_enabled') is not None else '仅发现记录'; score=float(h.get('pre_score')) if h.get('pre_score') is not None else -1
            channel_url=f"https://www.youtube.com/channel/{h.get('channel_id')}"; video_url=f"https://www.youtube.com/watch?v={h.get('video_id')}"
            drows.append(f'''<tr data-cid="{esc(h.get('channel_id'))}" data-search="{esc((h.get('query') or '')+' '+(h.get('channel_title') or '')+' '+country+' '+(h.get('title') or ''))}" data-status="{esc(local_status)}" data-tier="{esc(h.get('opportunity_tier') or '')}" data-country="{esc(country)}" data-score="{score}" data-subs="{subs or 0}" data-views="{h.get('views') or 0}" data-found="{esc(h.get('found_at') or '')}" data-title="{esc(h.get('channel_title') or '')}"><td>{esc(h.get('query'))}</td><td><a class="link-ext" target="_blank" rel="noopener" href="{esc(channel_url)}"><b>{esc(h.get('channel_title') or h.get('channel_id'))}</b></a><div class="small mono">{esc(h.get('channel_id'))}</div></td><td>{fmt_int(subs)}</td><td>{esc(country)}<div class="small">{esc(h.get('country_source') or '—')}</div></td><td>{fmt_int(h.get('views'))}</td><td>{f"{score:.1f}" if score>=0 else '—'} <span class="pill">{esc(h.get('opportunity_tier') or '')}</span></td><td><a class="link-ext" target="_blank" rel="noopener" href="{esc(video_url)}">{esc(h.get('title'))}</a></td><td>{esc(local_status)}</td><td>{esc(h.get('found_at'))}</td></tr>''')
        dbody=f'''<div class="title"><div><h1>博主发现</h1><div class="sub">搜索相关视频 → 识别发布视频的博主 → 再决定是否加入博主库并抓取指定时间范围的视频。</div></div></div>
        <div class="note" id="interactiveNote"><b>当前为只读模式。</b> 历史发现记录可以正常查看；如需执行搜索、抓取视频或获取联系方式，请使用 <span class="mono">start-dashboard.cmd</span> 打开交互模式。</div>
        <div class="builder-panel section"><h2>搜索新博主</h2>
          <div class="toolbar"><input id="discoverQuery" class="input" style="min-width:360px" placeholder="输入游戏、玩法或内容关键词，例如 Anime Expeditions"><select id="discoverSource" class="select"><option value="web">YouTube 网页搜索</option><option value="api">YouTube API 搜索</option></select><select id="discoverLookback" class="select"><option value="">不限发布时间</option><option value="7">近7天</option><option value="30">近30天</option><option value="60">近60天</option><option value="90">近90天</option><option value="180">近180天</option><option value="365">近365天</option><option value="custom">指定日期范围</option></select><span id="discoverCustomDates" class="inline" style="display:none"><input id="discoverFromDate" class="input" type="date" style="min-width:145px"><span class="small">至</span><input id="discoverToDate" class="input" type="date" style="min-width:145px"></span></div>
          <div class="toolbar"><select id="discoverRegionGroup" class="select"><option value="">全部大洲/区域</option></select><input id="discoverCountrySearch" class="input" list="countrySuggestions" placeholder="输入中文国家名或英文代码，例如 菲律宾 / PH" style="min-width:290px"><datalist id="countrySuggestions"></datalist><select id="discoverCountry" class="select"><option value="">不限国家/地区</option></select><select id="discoverMax" class="select"><option>25</option><option selected>50</option><option>100</option><option>200</option></select><button class="btn primary" id="discoverBtn">搜索</button></div><div id="discoverStatus" class="small"></div></div>
        <div class="section"><h2>本次搜索结果</h2><div class="toolbar"><input id="liveDiscoverySearch" class="input" placeholder="筛选本次结果：博主 / 国家 / 视频标题"><select id="liveDiscoverySort" class="select"><option value="score">发现评分</option><option value="subs">订阅数</option><option value="views">命中视频播放量</option><option value="title">博主名称</option></select><select id="liveDiscoverySortDir" class="select"><option value="desc">降序</option><option value="asc">升序</option></select>{_page_size_controls("liveDiscovery")}<span id="liveDiscoverySummary" class="table-summary"></span></div><div class="builder-panel"><div id="liveDiscoveryFilters"></div><div class="inline"><button class="btn" id="liveDiscoveryAddFilter">添加筛选条件</button><button class="btn primary" id="liveDiscoveryApplyFilter">应用筛选</button><button class="btn" id="liveDiscoveryClearFilter">清除筛选</button></div></div><div class="table-wrap section"><table><thead><tr><th>博主</th><th>订阅数</th><th>国家 / 证据</th><th>命中视频</th><th>播放量</th><th>发现评分</th><th>身份</th><th>联系方式</th><th>加入本地库 / 抓取视频</th></tr></thead><tbody id="liveDiscoveryRows"><tr><td colspan="9" class="empty">尚未执行搜索</td></tr></tbody></table></div>{_pager("liveDiscovery")}</div>
        <div class="section"><h2>已保存的发现记录</h2><div class="toolbar"><input id="savedDiscoverySearch" class="input" placeholder="搜索搜索词 / 博主 / 国家 / 命中视频"><select id="savedDiscoverySort" class="select"><option value="score">发现评分</option><option value="found">发现时间</option><option value="subs">订阅数</option><option value="views">命中视频播放量</option><option value="title">博主名称</option></select><select id="savedDiscoverySortDir" class="select"><option value="desc">降序</option><option value="asc">升序</option></select>{_page_size_controls("savedDiscovery")}<span id="savedDiscoverySummary" class="table-summary"></span></div><div class="builder-panel"><div id="savedDiscoveryFilters"></div><div class="inline"><button class="btn" id="savedDiscoveryAddFilter">添加筛选条件</button><button class="btn primary" id="savedDiscoveryApplyFilter">应用筛选</button><button class="btn" id="savedDiscoveryClearFilter">清除筛选</button></div></div><div class="table-wrap section"><table><thead><tr><th>搜索词</th><th>博主</th><th>订阅数</th><th>国家 / 证据</th><th>命中视频播放</th><th>发现评分</th><th>命中视频</th><th>本地状态</th><th>发现时间</th></tr></thead><tbody id="savedDiscoveryRows">{''.join(drows)}</tbody></table></div>{_pager("savedDiscovery")}</div>
        <script src="assets/creator_facts.js"></script><script src="assets/geography.js"></script><script src="assets/table_tools.js"></script><script src="assets/discovery.js"></script>'''
        (out/'discovery.html').write_text(_page('博主发现','discovery',dbody),encoding='utf-8')

        runs=[dict(r) for r in conn.execute('SELECT * FROM sync_runs ORDER BY id DESC LIMIT 200').fetchall()];quota=[dict(r) for r in conn.execute('SELECT * FROM quota_daily ORDER BY quota_date DESC LIMIT 30').fetchall()]
        rrows=[f'''<tr data-search="{esc(' '.join(str(x or '') for x in [r.get('id'),r.get('mode'),r.get('target'),r.get('status'),r.get('message')]))}" data-id="{r['id']}" data-started="{esc(r.get('started_at') or '')}" data-videos="{r.get('videos_processed',0)}" data-creators="{r.get('creators_processed',0)}"><td>{r['id']}</td><td>{esc(MODE_NAMES.get(r.get('mode'),r.get('mode')))}</td><td>{esc(r.get('target'))}</td><td class="status-{esc(r.get('status'))}">{esc(STATUS_NAMES.get(r.get('status'),r.get('status')))}</td><td>{r.get('creators_processed',0)}</td><td>{r.get('videos_processed',0)}</td><td>{r.get('quota_units',0)}</td><td>{esc(r.get('started_at'))}<div class="small">{esc(r.get('finished_at') or '')}</div></td><td class="small">{esc((r.get('message') or '')[:300])}</td></tr>''' for r in runs]
        qrows=[f'''<tr><td>{esc(q['quota_date'])}</td><td>{q['estimated_units']:,}</td><td>{esc(q['updated_at'])}</td></tr>''' for q in quota]
        sbody=f'''<div class="title"><div><h1>数据更新</h1><div class="sub">展示同步执行事实与 YouTube API 配额估算。</div></div></div><div class="section"><h2>同步记录</h2><div class="toolbar"><input id="syncSearch" class="input" placeholder="搜索同步模式 / 目标 / 状态 / 信息"><select id="syncSort" class="select"><option value="started">开始时间</option><option value="id">ID</option><option value="videos">视频数</option><option value="creators">博主数</option></select><select id="syncSortDir" class="select"><option value="desc">降序</option><option value="asc">升序</option></select>{_page_size_controls('sync')}<span id="syncSummary" class="table-summary"></span></div><div class="table-wrap"><table><thead><tr><th>ID</th><th>同步模式</th><th>目标</th><th>状态</th><th>博主数</th><th>视频数</th><th>配额</th><th>时间</th><th>信息</th></tr></thead><tbody id="syncRows">{''.join(rrows)}</tbody></table></div>{_pager('sync')}</div><div class="section"><h2>YouTube API 配额估算</h2><div class="table-wrap"><table><thead><tr><th>日期</th><th>估算单位</th><th>更新时间</th></tr></thead><tbody>{''.join(qrows)}</tbody></table></div></div><script src="assets/table_tools.js"></script><script>CDHTableTools.init({{tbodyId:'syncRows',searchId:'syncSearch',pageSizeId:'syncPageSize',pageSizeConfirmId:'syncPageSizeConfirm',firstId:'syncFirst',prevId:'syncPrev',nextId:'syncNext',lastId:'syncLast',buttonsId:'syncPageButtons',pageInputId:'syncPageInput',jumpId:'syncJump',pageInfoId:'syncPageInfo',summaryId:'syncSummary',sortId:'syncSort',sortDirId:'syncSortDir',sortMap:{{started:{{attr:'started',type:'text'}},id:{{attr:'id',type:'number'}},videos:{{attr:'videos',type:'number'}},creators:{{attr:'creators',type:'number'}}}},defaultSort:'started',defaultDir:'desc'}});</script>''';(out/'sync.html').write_text(_page('数据更新','sync',sbody),encoding='utf-8')

    (out/'README.txt').write_text('双击 index.html 可进入静态只读模式；如需执行搜索、抓取视频或获取联系方式，请双击 Skill 根目录的“start-dashboard.cmd”。\n',encoding='utf-8')
    return {'output_dir':str(out.resolve()),'index':str((out/'index.html').resolve()),'creator_pages':len(creators),'stats':stats,'metric_data_mode':'python_preaggregated'}
