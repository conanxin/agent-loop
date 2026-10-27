#!/usr/bin/env python3
"""One-model B3-R2 paired real-source review. Unique state dirs; no retries."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import secrets
import sqlite3
import subprocess
import time

HOME=Path.home()
CLI=HOME/".npm-global/bin/openclaw"
PIN=HOME/".openclaw/cxpan-p5-readonly.json5"
MODEL="minimax/MiniMax-M3.1-Flash"
NORMAL="你是普通技术审查员。检查这些原始技术规格和代码是否有具体漏洞、重要矛盾或可复现的边界问题。"
GOLD="你是独立的EGM Goldfish。首次冷读，不继承作者讨论记录。依次检查理解、设计架构、关键前提、异常恢复和实施就绪；不要刻意增加发现数量。"
SHARED=("只可用给出的带文件名与原始行号的代码片段，未提供的代码行为不得假设。"
"报告最多两条可由原文交叉验证的严重问题。输出中文严格 JSON，无任何围栏或解释，格式为："
'{"findings":[{"severity":"Major|Blocker|Nit","issue":"问题不超过90字",'
'"source_refs":["bridge/file.py:L12","docs/file.md:L30"],'
'"why":"具体矛盾或失败前提","fix":"最小改进"}],"summary":"一句总结"}。'
"不能证明有问题就输出空 findings。不要调用工具、命令、网站或文件。")

def digest(x):return hashlib.sha256(x.encode("utf-8")).hexdigest()

def unpack(txt):
    value=txt.strip()
    if value.startswith(chr(96)*3):
        value=re.sub("^"+chr(96)*3+"(?:json)?[ \t\r\n]*","",value)
        value=re.sub("[ \t\r\n]*"+chr(96)*3+"$","",value)
    try:j=json.loads(value)
    except (ValueError,TypeError):return None
    return j if isinstance(j,dict) and isinstance(j.get("findings"),list) else None

def read_trace(db_file,sid):
    out={"tools":None,"tool_calls":None,"prior_messages":None,"tokens":{}}
    if not sid or not db_file.exists():return out
    try:
        db=sqlite3.connect(f"file:{db_file}?mode=ro",uri=True,timeout=5)
        rows=db.execute("SELECT event_json FROM trajectory_runtime_events WHERE session_id=? ORDER BY seq",(sid,)).fetchall()
        db.close()
    except sqlite3.Error:return out
    calls=0
    for (raw,) in rows:
        try:j=json.loads(raw)
        except ValueError:continue
        typ=j.get("type");d=j.get("data") if isinstance(j.get("data"),dict) else {}
        if typ=="tool.call":calls+=1
        if typ=="context.compiled":
            if isinstance(d.get("tools"),list):out["tools"]=len(d["tools"])
            if isinstance(d.get("messages"),list):out["prior_messages"]=len(d["messages"])
        if typ=="trace.artifacts":
            use=d.get("usage")
            if isinstance(use,dict):
                out["tokens"]={k:use[k] for k in ("input","output","total","cacheRead","cacheWrite") if isinstance(use.get(k),(int,float))}
                cost=use.get("cost")
                if isinstance(cost,dict):out["cost_fields"]={k:v for k,v in cost.items() if isinstance(v,(float,int))}
    out["tool_calls"]=calls
    return out

def build_schedule(manifest):
    jobs=[]
    for repeat in (1,2):
        for i,case in enumerate(manifest["cases"]):
            first=["baseline","goldfish"] if (i+repeat)%2 else ["goldfish","baseline"]
            for arm in first:jobs.append({"case":case["case_id"],"repeat":repeat,"arm":arm})
    return jobs

def run_one(root,case,job,config,budget):
    key=job["case"]; arm=job["arm"];rep=job["repeat"]
    directory=root/"runs_compact"/key/f"repeat{rep}-{arm}"
    result=directory/"result.json"
    if result.exists():
        previous=json.loads(result.read_text())
        if previous["packet_sha256"]!=case["packet_sha256"]:raise ValueError("digest conflict")
        return previous
    if directory.exists() and any(directory.iterdir()):raise RuntimeError("prior incomplete invocation; refuse replay")
    directory.mkdir(parents=True,exist_ok=True)
    doc=(root/"compact_packets"/(key+".txt")).read_text(encoding="utf-8")
    if digest(doc)!=case["packet_sha256"]:raise ValueError("frozen source mutated")
    intro=NORMAL if arm=="baseline" else GOLD
    prompt=(intro+"\n"+SHARED+"\n目标："+case["question"]+
            "\nSOURCE_SHA256="+case["packet_sha256"]+
            "\n==== BEGIN UNTRUSTED CODE ====\n"+doc+"\n==== END UNTRUSTED CODE ====")
    prompt_file=directory/"prompt.txt";prompt_file.write_text(prompt,encoding="utf-8")
    state=directory/"state";state.mkdir()
    cmd=[str(CLI),"agent","exec","--config",str(config),"--cwd",str(directory),
         "--state-dir",str(state),"--model",MODEL,"--code-mode","direct",
         "--local-model-lean","--thinking","low","--timeout",str(budget-10),
         "--json","--message-file",str(prompt_file)]
    start=time.monotonic()
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,
                            stdin=subprocess.DEVNULL,timeout=budget,cwd=directory)
        elapsed=round(time.monotonic()-start,3)
        (directory/"envelope.json").write_text(proc.stdout or "",encoding="utf-8")
        (directory/"stderr.txt").write_text(proc.stderr or "",encoding="utf-8")
        try:env=json.loads(proc.stdout)
        except (ValueError,TypeError):env={}
        answer=env.get("final") or "\n".join(x.get("text","") for x in env.get("payloads",[]) if isinstance(x,dict))
        if not isinstance(answer,str):answer=""
        (directory/"answer.txt").write_text(answer,encoding="utf-8")
        parsed=unpack(answer)
        valid=proc.returncode==0 and env.get("ok") is True and env.get("status")=="ok" and parsed is not None
        items=[]
        if parsed:
            for f in parsed["findings"][:4]:
                if not isinstance(f,dict):continue
                items.append({"severity":str(f.get("severity",""))[:16],
                              "issue":str(f.get("issue",""))[:300],
                              "source_refs":f.get("source_refs") if isinstance(f.get("source_refs"),list) else [],
                              "why":str(f.get("why",""))[:550],
                              "fix":str(f.get("fix",""))[:350]})
        sid=env.get("sessionId")
        out={"schema":"egm.b3r2.run/1","case":key,"arm":arm,"repeat":rep,
             "status":"COMPLETED" if valid else "INVALID_OR_FAILED",
             "packet_sha256":case["packet_sha256"],
             "prompt_sha256":digest(prompt),"prompt_chars":len(prompt),
             "seconds":elapsed,"session_id":sid,"model":MODEL,
             "finding_count":len(items),"findings":items,"answer_chars":len(answer),
             "trace":read_trace(state/"agents/main/agent/openclaw-agent.sqlite",sid)}
    except subprocess.TimeoutExpired:
        out={"schema":"egm.b3r2.run/1","case":key,"arm":arm,"repeat":rep,
             "status":"TIMEOUT","packet_sha256":case["packet_sha256"],
             "prompt_sha256":digest(prompt),"prompt_chars":len(prompt),
             "seconds":budget,"findings":[],"finding_count":0}
    result.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--workspace",required=True)
    a.add_argument("--budget",type=int,default=140)
    a.add_argument("--max-new",type=int,default=2)
    args=a.parse_args()
    root=Path(args.workspace).resolve()
    manifest=json.loads((root/"manifest_compact.json").read_text(encoding="utf-8"))
    if manifest["planted_defects"] is not False:raise ValueError("not unmodified sources")
    if not 75<=args.budget<=200 or not 1<=args.max_new<=12:raise ValueError("limits")
    for case in manifest["cases"]:
        if hashlib.sha256((root/"compact_packets"/(case["case_id"]+".txt")).read_bytes()).hexdigest()!=case["packet_sha256"]:
            raise ValueError("packet SHA mismatch")
    jobs=build_schedule(manifest)
    schedule=root/"schedule_compact.json"
    if schedule.exists():
        if json.loads(schedule.read_text())["jobs"]!=jobs:raise RuntimeError("schedule drift")
    else:schedule.write_text(json.dumps({"jobs":jobs,"model":MODEL},indent=2)+"\n")
    pin=PIN.read_text()
    if '"deny": ["*"]' not in pin or '"contextInjection": "never"' not in pin:raise ValueError("pinned policy")
    temporary=PIN.parent/("cxpan-egm-b3r2compact-"+secrets.token_hex(8)+".json5")
    temporary.write_text(pin.replace('"deny": ["*"]','"deny": ["*"], "toolSearch": false'))
    try:
        new=0
        for i,job in enumerate(jobs):
            prior=root/"runs_compact"/job["case"]/f"repeat{job['repeat']}-{job['arm']}"/"result.json"
            if prior.exists():continue
            if new>=args.max_new:break
            case=next(c for c in manifest["cases"] if c["case_id"]==job["case"])
            try:result=run_one(root,case,job,temporary,args.budget)
            except Exception as e:
                print("EXCEPTION",i,type(e).__name__,str(e)[:100],flush=True)
                break
            new+=1
            print(json.dumps({"index":i,"case":job["case"],"arm":job["arm"],
                  "repeat":job["repeat"],"status":result["status"],"seconds":result["seconds"],
                  "findings":result["finding_count"],"tokens":result.get("trace",{}).get("tokens",{}).get("total"),
                  "calls":result.get("trace",{}).get("tool_calls")},ensure_ascii=False),flush=True)
        finished=sum((root/"runs_compact"/j["case"]/f"repeat{j['repeat']}-{j['arm']}"/"result.json").exists() for j in jobs)
        print("FINISHED",finished,"OF",len(jobs),flush=True)
    finally:temporary.unlink(missing_ok=True)

if __name__=="__main__":main()
