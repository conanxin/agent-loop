#!/usr/bin/env python3
"""Paired one-model EGM B3 review benchmark: only synthetic source-derived fixtures."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse, atexit, hashlib, json, re, secrets, sqlite3, subprocess, time

HOME=Path.home()
PIN=HOME/".openclaw/cxpan-p5-readonly.json5"
CLI=HOME/".npm-global/bin/openclaw"
MODEL="minimax/MiniMax-M3.1-Flash"
BASELINE="你是普通技术审查者。阅读整个设计文档，找出实质矛盾、缺失的关键边界和影响实现的错误。只凭当前原文作答，不推测不存在的代码或文件。"
GOLDFISH=("你是严格独立的 EGM Goldfish，第一次读这份文档。不继承作者历史观点。"
"在内部完成 Zoom Out、Comprehension、Critic、Implementation Readiness 四项检查："
"从目标合理性、规范前后自洽、实施歧义与例外行为中寻找可证实的缺陷。"
"谨慎区分当前缺陷、未来拟建文件、引用之外的未知事实。")
COMMON=("输出严格 JSON，没有 Markdown 代码围栏，"
'格式 {"findings":[{"line":数字,"severity":"Blocker|Major|Nit",'
'"issue":"问题","evidence":"关联文档行号与冲突依据","fix":"具体改进"}],'
'"overall":"总结"}。最多6条，允许0条。'
"line 必须是给出的原文行号；不要为凑数构造问题。中文回答。")

def sha(s):return hashlib.sha256(s.encode("utf-8")).hexdigest()

def parse_json(s):
    t=s.strip()
    if t.startswith(chr(96)*3):
        t=re.sub(r"^"+chr(96)*3+r"(?:json)?\s*","",t)
        t=re.sub(r"\s*"+chr(96)*3+r"$","",t)
    try:j=json.loads(t)
    except (TypeError,ValueError):return None
    return j if isinstance(j,dict) and isinstance(j.get("findings"),list) else None

def meta(sql,sid):
    out={"tool_schema_count":None,"tool_call_events":None,"usage_tokens":{}}
    if not sql.exists() or not sid:return out
    try:
        db=sqlite3.connect(f"file:{sql}?mode=ro",uri=True,timeout=5)
        blobs=db.execute("SELECT event_json FROM trajectory_runtime_events WHERE session_id=? ORDER BY seq",(sid,)).fetchall()
        db.close()
    except sqlite3.Error:return out
    tools=0
    for (raw,) in blobs:
        try:x=json.loads(raw)
        except ValueError:continue
        d=x.get("data") if isinstance(x.get("data"),dict) else {}
        if x.get("type")=="tool.call":tools+=1
        if x.get("type")=="context.compiled" and isinstance(d.get("tools"),list):
            out["tool_schema_count"]=len(d["tools"])
        if x.get("type")=="trace.artifacts" and isinstance(d.get("usage"),dict):
            u=d["usage"]
            out["usage_tokens"]={k:v for k,v in u.items() if k in ("input","output","cacheRead","cacheWrite","total") and isinstance(v,(int,float))}
            cost=u.get("cost")
            if isinstance(cost,dict):
                out["cost_fields"]={k:v for k,v in cost.items() if isinstance(v,(int,float))}
    out["tool_call_events"]=tools
    return out

def run_case(root,case,arm,config,budget):
    file=root/"fixtures"/(case["id"]+".md")
    doc=file.read_text(encoding="utf-8")
    if sha(doc)!=case["sha256"]:raise ValueError("fixture sha mismatch")
    annotated="\n".join(f"[L{i}] {v}" for i,v in enumerate(doc.splitlines(),1))
    prompt=f"审查设计规格 {case['id']}，全文 SHA={case['sha256']}。\n"+(BASELINE if arm=="baseline" else GOLDFISH)+"\n"+COMMON+"\n===BEGIN===\n"+annotated+"\n===END==="
    directory=root/"runs"/case["id"]/arm
    fileout=directory/"result.json"
    if fileout.exists():
        old=json.loads(fileout.read_text())
        if old["fixture_sha256"]!=case["sha256"]:raise ValueError("previous result does not match fixture")
        return old
    if directory.exists() and any(directory.iterdir()):raise RuntimeError("incomplete prior run; do not resubmit")
    directory.mkdir(parents=True,exist_ok=True)
    q=directory/"prompt.txt";q.write_text(prompt,encoding="utf-8")
    state=directory/"state";state.mkdir()
    cmd=[str(CLI),"agent","exec","--config",str(config),"--cwd",str(directory),
         "--state-dir",str(state),"--model",MODEL,"--code-mode","direct",
         "--local-model-lean","--thinking","adaptive","--timeout",str(budget-10),
         "--json","--message-file",str(q)]
    t=time.monotonic()
    try:
        p=subprocess.run(cmd,cwd=directory,capture_output=True,text=True,
                         stdin=subprocess.DEVNULL,timeout=budget)
        elapsed=round(time.monotonic()-t,3)
        (directory/"envelope.json").write_text(p.stdout or "",encoding="utf-8")
        (directory/"stderr.txt").write_text(p.stderr or "",encoding="utf-8")
        try:j=json.loads(p.stdout)
        except (TypeError,ValueError):j={}
        answer=j.get("final") or "\n".join(v.get("text","") for v in j.get("payloads",[]) if isinstance(v,dict) and isinstance(v.get("text"),str))
        if not isinstance(answer,str):answer=""
        (directory/"answer.txt").write_text(answer,encoding="utf-8")
        data=parse_json(answer)
        status="COMPLETED" if p.returncode==0 and j.get("ok") is True and j.get("status")=="ok" and data else "FAILED_OR_UNPARSEABLE"
        findings=[]
        if data:
            for f in data["findings"][:12]:
                if not isinstance(f,dict):continue
                findings.append({k:(f.get(k) if k=="line" else str(f.get(k,""))[:850]) for k in ("line","severity","issue","evidence","fix")})
        r={"schema":"egm.b3.run/1","case":case["id"],"arm":arm,"status":status,"seconds":elapsed,
           "fixture_sha256":case["sha256"],"prompt_sha256":sha(prompt),
           "prompt_chars":len(prompt),"answer_chars":len(answer),
           "session_id":j.get("sessionId"),"exit_code":p.returncode,
           "model":j.get("model") or MODEL,"provider":j.get("provider"),
           "findings":findings,"finding_count":len(findings),"parseable":bool(data),
           "overall":str(data.get("overall",""))[:550] if data else "",
           "trace":meta(state/"agents/main/agent/openclaw-agent.sqlite",j.get("sessionId"))}
    except subprocess.TimeoutExpired:
        r={"schema":"egm.b3.run/1","case":case["id"],"arm":arm,
           "status":"TIMEOUT","seconds":budget,"fixture_sha256":case["sha256"],
           "prompt_sha256":sha(prompt),"findings":[],"finding_count":0,"parseable":False}
    fileout.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return r

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--workspace",required=True)
    p.add_argument("--budget",type=int,default=115)
    p.add_argument("--parallel",type=int,default=2)
    a=p.parse_args()
    if not (55<=a.budget<=200 and 1<=a.parallel<=2):p.error("Invalid budget/parallel")
    root=Path(a.workspace).resolve()
    cases=json.loads((root/"manifest.json").read_text())["cases"]
    pinned=PIN.read_text(encoding="utf-8")
    if '"deny": ["*"]' not in pinned or '"contextInjection": "never"' not in pinned:
        raise RuntimeError("Pinned policy is not in expected state")
    config=PIN.parent/("cxpan-egm-b3-"+secrets.token_hex(8)+".json5")
    config.write_text(pinned.replace('"deny": ["*"]','"deny": ["*"], "toolSearch": false'),encoding="utf-8")
    try:
        jobs=[]
        for i,case in enumerate(cases):
            for arm in (["baseline","goldfish"] if i%2==0 else ["goldfish","baseline"]):
                jobs.append((case,arm))
        (root/"study_plan.json").write_text(json.dumps({
            "model":MODEL,"schedule":[[c["id"],arm] for c,arm in jobs],
            "fixed_source_same_model":True,"comparator":"review prompting strategy only",
            "groundtruth_absent":not (root/"ground_truth.json").exists()},indent=2)+"\n")
        completed=[]
        for i in range(0,len(jobs),a.parallel):
            with ThreadPoolExecutor(max_workers=a.parallel) as ex:
                ft={ex.submit(run_case,root,c,arm,config,a.budget):(c["id"],arm) for c,arm in jobs[i:i+a.parallel]}
                for f in as_completed(ft):
                    case,arm=ft[f]
                    try:out=f.result()
                    except Exception as e:out={"case":case,"arm":arm,"status":"ERROR","error_type":type(e).__name__}
                    completed.append(out)
                    print(json.dumps({"case":case,"arm":arm,"status":out.get("status"),
                         "seconds":out.get("seconds"),"findings":out.get("finding_count"),
                         "tokens":out.get("trace",{}).get("usage_tokens"),
                         "tool_calls":out.get("trace",{}).get("tool_call_events")},ensure_ascii=False),flush=True)
        summary={"schema":"egm.b3.summary/1","model":MODEL,"planned":len(jobs),
                 "completed":sum(r.get("status")=="COMPLETED" for r in completed),
                 "runs":[{"case":r["case"],"arm":r["arm"],"status":r.get("status"),
                          "seconds":r.get("seconds"),"finding_count":r.get("finding_count"),
                          "trace":r.get("trace")} for r in completed],
                 "limitations":["Not human blinded grading","Single run per arm, same model",
                                "Goldfish single-call rubric is not full Google EGM multi-stage orchestration"]}
        (root/"run_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
        print("FINISHED",summary["completed"],"of",summary["planned"],flush=True)
    finally:config.unlink(missing_ok=True)

if __name__=="__main__":main()
