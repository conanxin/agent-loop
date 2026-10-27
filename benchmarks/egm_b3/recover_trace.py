#!/usr/bin/env python3
"""Recover model.completed text from B3 isolated SQLite after CLI timeout.

Produces a SECONDARY trace-derived record; never changes result.json's failure
status and never counts as a successfully delivered CLI result.
"""
from pathlib import Path
import argparse,json,sqlite3,hashlib
from run_cloud import parse_json

def recover(run_dir):
    status_file=run_dir/"result.json"
    if not status_file.is_file():return {"status":"NO_PRIMARY_RESULT"}
    primary=json.loads(status_file.read_text(encoding="utf-8"))
    trace_file=run_dir/"trace_recovery.json"
    if trace_file.exists():
        old=json.loads(trace_file.read_text())
        return {"status":"REUSED_EXISTING","outcome":old.get("status")}
    db_path=run_dir/"state/agents/main/agent/openclaw-agent.sqlite"
    if not db_path.is_file():return {"status":"NO_TRACE_DB"}
    try:
        db=sqlite3.connect(f"file:{db_path}?mode=ro",uri=True,timeout=5)
        rows=db.execute("SELECT session_id,event_json FROM trajectory_runtime_events ORDER BY seq").fetchall()
        db.close()
    except sqlite3.Error as e:
        return {"status":"DB_ERROR","kind":type(e).__name__}
    sid=None; texts=[]; usage={};events=[]
    for session,raw in rows:
        try:j=json.loads(raw)
        except ValueError:continue
        sid=session
        typ=j.get("type")
        events.append(typ)
        if typ in ("model.completed","trace.artifacts"):
            x=j.get("data") if isinstance(j.get("data"),dict) else {}
            t=x.get("assistantTexts")
            if isinstance(t,list) and all(isinstance(s,str) for s in t):texts=t
            u=x.get("usage")
            if isinstance(u,dict):
                usage={k:v for k,v in u.items() if k in ("input","output","cacheRead","cacheWrite","total") and isinstance(v,(float,int))}
    content="\n".join(texts)
    secondary_path=run_dir/"recovered-answer.txt"
    if content:secondary_path.write_text(content,encoding="utf-8")
    parsed=parse_json(content) if content else None
    recovery={
        "schema":"egm.b3.trace_recovery/1",
        "case":primary["case"],"arm":primary["arm"],
        "original_primary_status":primary["status"],
        "status":"TRACE_JSON_RECOVERED" if parsed else "TRACE_TEXT_UNPARSEABLE" if content else "NO_COMPLETED_MODEL_TEXT",
        "session_id":sid,
        "model_events":events,
        "answer_length":len(content),
        "answer_sha256":hashlib.sha256(content.encode()).hexdigest() if content else None,
        "findings":[{
          k:(v.get(k) if k=="line" else str(v.get(k,""))[:800])
          for k in ("line","severity","issue","evidence","fix")
        } for v in parsed.get("findings",[]) if isinstance(v,dict)] if parsed else [],
        "usage_tokens":usage,
        "not_cli_delivered":True,
        "limits":["Secondary forensic recovery only, not primary outcome",
                  "Trace may be incomplete when subprocess is forcibly terminated"],
    }
    trace_file.write_text(json.dumps(recovery,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"status":recovery["status"],"case":recovery["case"],"arm":recovery["arm"],
            "chars":len(content),"findings":len(recovery["findings"]),"tokens":usage}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--workspace",required=True);args=p.parse_args()
    root=Path(args.workspace)/"runs"
    for run in sorted(root.glob("*/*")):
        if run.is_dir() and (run/"result.json").exists():
            outcome=recover(run)
            print(json.dumps(outcome,ensure_ascii=False),flush=True)
