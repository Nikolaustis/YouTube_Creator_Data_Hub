from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .db import connect, json_load
from .util import now_utc


def _video_rows(conn):
    rows=conn.execute("""SELECT v.*,c.channel_title,c.country_api,c.subscriber_count,
      s.suggested_role,s.brands_json AS suggested_brands_json,s.confidence,s.evidence_json,
      l.human_role,l.brands_json AS human_brands_json,l.labeled_by,l.note AS label_note,l.labeled_at
      FROM videos v JOIN creators c ON c.channel_id=v.channel_id
      LEFT JOIN label_suggestions s ON s.video_id=v.video_id
      LEFT JOIN video_labels l ON l.video_id=v.video_id
      ORDER BY v.channel_id,v.published_at DESC""").fetchall()
    out=[]
    for r in rows:
        d=dict(r)
        d["tags"]=json_load(d.pop("tags_json"),[])
        d["suggested_brands"]=json_load(d.pop("suggested_brands_json"),[])
        d["suggestion_evidence"]=json_load(d.pop("evidence_json"),[])
        d["human_brands"]=json_load(d.pop("human_brands_json"),[])
        out.append(d)
    return out


def export_all(db_path: str|Path, output_dir: str|Path, fmt: str="csv") -> dict[str,Any]:
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    stamp=now_utc().replace(":","").replace("-","")[:15]
    with connect(db_path) as conn:
        creators=[dict(r) for r in conn.execute("SELECT * FROM creators ORDER BY channel_title").fetchall()]
        videos=_video_rows(conn)
        snapshots=[dict(r) for r in conn.execute("SELECT * FROM video_snapshots ORDER BY video_id,captured_at").fetchall()]
        discoveries=[dict(r) for r in conn.execute("SELECT * FROM discovery_hits ORDER BY id").fetchall()]
        labels=[dict(r) for r in conn.execute("SELECT * FROM video_labels ORDER BY labeled_at").fetchall()]
        audits=[dict(r) for r in conn.execute("SELECT * FROM video_label_audit ORDER BY id").fetchall()]
    data={"creators":creators,"videos":videos,"video_snapshots":snapshots,"discovery_hits":discoveries,"human_labels":labels,"label_audit":audits}
    if fmt=="json":
        p=out/f"creator_data_hub_{stamp}.json"; p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        return {"format":"json","files":[str(p.resolve())]}
    if fmt=="xlsx":
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
        except Exception as e:
            raise RuntimeError("XLSX 导出需要 openpyxl。执行 python -m pip install -r requirements.txt") from e
        p=out/f"creator_data_hub_{stamp}.xlsx"; wb=Workbook(); wb.remove(wb.active)
        for name, rows in [("Creators",creators),("Videos",videos),("Video Snapshots",snapshots),("Discovery Hits",discoveries),("Human Labels",labels),("Label Audit",audits)]:
            ws=wb.create_sheet(name[:31])
            if not rows:
                ws.append(["No data"]); continue
            headers=list(rows[0].keys()); ws.append(headers)
            for c in ws[1]: c.font=Font(bold=True)
            for row in rows:
                ws.append([json.dumps(row.get(h),ensure_ascii=False) if isinstance(row.get(h),(list,dict)) else row.get(h) for h in headers])
            ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
            for col in ws.columns:
                maxlen=min(50,max(len(str(c.value or "")) for c in col)); ws.column_dimensions[col[0].column_letter].width=max(10,maxlen+2)
        ws=wb.create_sheet("Data Dictionary")
        ws.append(["层级","字段/表","说明"])
        for row in [
            ("事实","creators","YouTube频道公开事实与当前快照"),("事实","videos","公开视频元数据与当前Views/Likes/Comments"),("事实","video_snapshots","每次真实刷新时的指标快照"),("事实","discovery_hits","搜索词、命中视频、rank、发现时间"),("机器标签","label_suggestions","根据公开metadata给出的建议，非原始事实"),("人工标签","video_labels","运营确认结果"),("审计","video_label_audit","人工标签变更历史")
        ]: ws.append(row)
        wb.save(p); return {"format":"xlsx","files":[str(p.resolve())]}
    files=[]
    for name,rows in data.items():
        p=out/f"{name}_{stamp}.csv"; files.append(str(p.resolve()))
        headers=list(rows[0].keys()) if rows else ["no_data"]
        with p.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=headers); w.writeheader()
            for row in rows:
                w.writerow({k: json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    return {"format":"csv","files":files}
