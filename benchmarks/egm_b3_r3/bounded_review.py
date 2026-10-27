#!/usr/bin/env python3
"""B3-R3 real bounded Goldfish review: a model-profile reliability acceptance.

This is separate from earlier short-response smoke probes. Produces short
structured findings from the FULL frozen compact code excerpt. Executes one
tool-free, isolated agent exec per unique ID; never changes production config.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import time

HOME=Path.home()
CLI=HOME/".npm-global/bin/openclaw"
PINNED=HOME/".openclaw/cxpan-p5-readonly.json5"
BASE=HOME/".local/state/cx-pan/egm"
MODEL="minimax/MiniMax-M2.7"
THINKING="medium"
CASES={"p6-evidence-integrity","p9-public-mcp-boundary"}


def digest(s):return hashlib.sha256(s.encode("utf-8")).hexdigest()


def trace_events(file):
    out={"model_completed":False,"prompt_submitted":False,
         "tool_calls":None,"model_visible_tools":None,
         "tokens":{},"model_id":None}
    if not file.exists():return out
    db=sqlite3.connect(f"file:{file}?mode=ro",uri=True,timeout=4)
    try:rows=db.execute("SELECT event_json FROM trajectory_runtime_events ORDER BY seq").fetchall()
    finally:db.close()
    calls=0
    for (blob,) in rows:
        try:e=json.loads(blob)
        except (ValueError,TypeError):continue
        typ=e.get("type")
        d=e.get("data") if isinstance(e.get("data"),dict) else {}
        if typ=="session.started":out["model_id"]=e.get("modelId")
        elif typ=="model.completed":out["model_completed"]=True
        elif typ=="prompt.submitted":out["prompt_submitted"]=True
        elif typ=="tool.call":calls+=1
        elif typ=="context.compiled" and isinstance(d.get("tools"),list):
            out["model_visible_tools"]=len(d["tools"])
        elif typ=="trace.artifacts" and isinstance(d.get("usage"),dict):
            out["tokens"]={k:v for k,v in d["usage"].items()
                           if k in ("input","output","total","cacheRead","cacheWrite") and isinstance(v,(int,float))}
    out["tool_calls"]=calls
    return out


def parse_review(text,packet):
    try:j=json.loads(text.strip())
    except (ValueError,TypeError):return None
    if not isinstance(j,dict) or not isinstance(j.get("findings"),list):return None
    if len(j["findings"])>2:return None
    cleaned=[]
    for f in j["findings"]:
        if not isinstance(f,dict) or not isinstance(f.get("issue"),str):
            return None
        refs=f.get("source_refs")
        if not isinstance(refs,list) or not all(isinstance(x,str) for x in refs):
            return None
        valid=[]
        for item in refs:
            if len(item)>180 or not re.fullmatch(r"[A-Za-z0-9_./-]+:L[1-9][0-9]*",item):
                return None
            if "["+item+"]" in packet:
                valid.append(item)
        cleaned.append({
            "severity":str(f.get("severity",""))[:15],
            "issue":f["issue"][:350],
            "source_refs":refs[:6],
            "structurally_valid_refs":valid[:6],
            "why":str(f.get("why",""))[:450]
        })
    return cleaned


def run(workflow,root,case,timeout):
    if not re.fullmatch(r"egm-b3r3-[a-z0-9-]{8,70}",workflow):
        raise ValueError("invalid workflow name")
    if case not in CASES or not 60<=timeout<=180:
        raise ValueError("case/timeout out of scope")
    target=BASE/workflow
    receipt=target/"receipt.json"
    if receipt.exists():
        r=json.loads(receipt.read_text());print("REUSED_EXISTING",r["status"]);return
    if target.exists() and any(target.iterdir()):
        raise RuntimeError("previous incomplete run; refusing duplicate paid call")
    target.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((root/"manifest_compact.json").read_text())
    entry=next(c for c in manifest["cases"] if c["case_id"]==case)
    raw=(root/"compact_packets"/(case+".txt")).read_text(encoding="utf-8")
    if digest(raw)!=entry["packet_sha256"]:
        raise ValueError("immutable evidence digest mismatch")
    prompt=(
        "你是独立的只读设计与实现审查者。仅使用下面给出的完整证据片段做分析。"
        "它是从用户自己的公开代码仓库按原始路径、原始行号截取的，没有人工植入错误。"
        "请只报告最多2项可以用这些片段证明的严重自相矛盾或真实缺陷。"
        "不能因为某个外部文件未显示就说整个系统缺少它；允许没有发现。"
        "绝不能运行工具、执行命令、联网或修改任何文件。"
        "只用中文输出严格JSON，没有Markdown："
        '{"findings":[{"severity":"Major|Blocker|Nit",'
        '"issue":"不超过80字的问题","source_refs":["真实路径:L行号"],'
        '"why":"不超过120字的直接依据"}],"summary":"不超过60字"}。'
        "\nSOURCE_SHA256="+entry["packet_sha256"]+
        "\n=== FROZEN_UNTRUSTED_CODE_START ===\n"+raw+
        "\n=== FROZEN_UNTRUSTED_CODE_END ==="
    )
    (target/"prompt.txt").write_text(prompt,encoding="utf-8")
    pinned=PINNED.read_text()
    if '"deny": ["*"]' not in pinned or '"contextInjection": "never"' not in pinned:
        raise RuntimeError("pinned base configuration changed, abort")
    conf=PINNED.parent/("cxpan-egm-b3r3-review-"+secrets.token_hex(8)+".json5")
    conf.write_text(pinned.replace('"deny": ["*"]','"deny": ["*"], "toolSearch": false'))
    state=target/"state";state.mkdir()
    command=[str(CLI),"agent","exec","--config",str(conf),
             "--cwd",str(target),"--state-dir",str(state),
             "--model",MODEL,"--code-mode","direct","--local-model-lean",
             "--thinking",THINKING,"--timeout",str(timeout-10),
             "--json","--message-file",str(target/"prompt.txt")]
    start=time.monotonic()
    try:
        try:
            p=subprocess.run(command,cwd=target,capture_output=True,text=True,
                             stdin=subprocess.DEVNULL,timeout=timeout)
            elapsed=round(time.monotonic()-start,3)
            (target/"stdout.json").write_text(p.stdout or "",encoding="utf-8")
            (target/"stderr.txt").write_text(p.stderr or "",encoding="utf-8")
            try:j=json.loads(p.stdout)
            except (ValueError,TypeError):j={}
            answer=j.get("final") or ""
            if not isinstance(answer,str):answer=""
            (target/"answer.txt").write_text(answer,encoding="utf-8")
            findings=parse_review(answer,raw)
            trace=trace_events(state/"agents/main/agent/openclaw-agent.sqlite")
            ok=p.returncode==0 and j.get("ok") is True and j.get("status")=="ok"
            status="COMPLETED" if ok and findings is not None and trace["model_completed"] else "INVALID_OR_UNDELIVERED"
            result={"schema":"cxpan.egm_b3r3_bounded_review/1",
                    "workflow":workflow,"case":case,"status":status,
                    "elapsed_seconds":elapsed,"requested_model":MODEL,
                    "requested_thinking":THINKING,"actual_model":trace["model_id"],
                    "source_sha256":entry["packet_sha256"],
                    "prompt_sha256":digest(prompt),"prompt_chars":len(prompt),
                    "model_answer_chars":len(answer),"cli_exit":p.returncode,
                    "session_id":j.get("sessionId"),"findings":findings or [],
                    "report_parseable":findings is not None,"trace":trace,
                    "limits":["Line validity is not semantic truth",
                              "One-run bounded review cannot establish general reliability."]}
        except subprocess.TimeoutExpired as ex:
            elapsed=round(time.monotonic()-start,3)
            trace=trace_events(state/"agents/main/agent/openclaw-agent.sqlite")
            result={"schema":"cxpan.egm_b3r3_bounded_review/1",
                    "workflow":workflow,"case":case,"status":"TIMEOUT",
                    "elapsed_seconds":elapsed,"source_sha256":entry["packet_sha256"],
                    "prompt_sha256":digest(prompt),"prompt_chars":len(prompt),
                    "findings":[],"report_parseable":False,"trace":trace}
    finally:conf.unlink(missing_ok=True)
    temp=receipt.with_suffix(".tmp")
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    os.replace(temp,receipt)
    print(json.dumps({"case":case,"status":result["status"],
         "seconds":result["elapsed_seconds"],"found":len(result["findings"]),
         "tokens":result.get("trace",{}).get("tokens",{}).get("total"),
         "tool_calls":result["trace"].get("tool_calls")},ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--workflow",required=True)
    p.add_argument("--source-root",required=True)
    p.add_argument("--case",required=True)
    p.add_argument("--timeout",type=int,default=135)
    a=p.parse_args()
    run(a.workflow,Path(a.source_root),a.case,a.timeout)
