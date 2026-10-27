#!/usr/bin/env python3
"""B3-R3 diagnostic: bounded, tool-free, single-source OpenClaw model smoke test.

- No production Gateway, Hub, repo, or pinned config modification.
- All receipts and raw replies remain under ~/.local/state/cx-pan/egm/.
- Does not retry an incomplete workflow and does not infer zero findings on failure.
- Only source-derived, frozen public fixture chunks are sent.
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
VALID_MODELS={
    "minimax/MiniMax-M3.1-Flash",
    "minimax/MiniMax-M2.7",
    "minimax/MiniMax-M3",
    "zai/glm-5.3",
}
VALID_CASES=("protocol-implementation","p6-evidence-integrity","p9-public-mcp-boundary")


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def trace_status(sqlite_file):
    res={"transcript_event_count":None,"trajectory_event_count":None,
         "model_completed_event":False,"prompt_submitted_event":False,
         "model_visible_tool_count":None,"tool_call_events":0,"usage_tokens":{},"actual_provider":None,"actual_model":None}
    if not sqlite_file.exists():return res
    db=sqlite3.connect(f"file:{sqlite_file}?mode=ro",uri=True,timeout=4)
    try:
        raw=db.execute("SELECT event_json FROM trajectory_runtime_events ORDER BY seq").fetchall()
        transcript=db.execute("SELECT COUNT(*) FROM transcript_events").fetchone()[0]
        res["transcript_event_count"]=transcript
        res["trajectory_event_count"]=len(raw)
        for (blob,) in raw:
            try:j=json.loads(blob)
            except (ValueError,TypeError):continue
            typ=j.get("type")
            d=j.get("data") if isinstance(j.get("data"),dict) else {}
            if typ=="session.started":
                res["actual_provider"]=j.get("provider")
                res["actual_model"]=j.get("modelId")
            if typ=="model.completed":res["model_completed_event"]=True
            elif typ=="prompt.submitted":res["prompt_submitted_event"]=True
            elif typ=="tool.call":res["tool_call_events"]+=1
            elif typ=="context.compiled" and isinstance(d.get("tools"),list):
                res["model_visible_tool_count"]=len(d["tools"])
            elif typ=="trace.artifacts" and isinstance(d.get("usage"),dict):
                u=d["usage"]
                res["usage_tokens"]={k:u[k] for k in ("input","output","total","cacheRead","cacheWrite")
                                     if isinstance(u.get(k),(int,float))}
    finally:db.close()
    return res


def run(workflow,source_root,case,model,timeout,truncate=None,thinking="default"):
    if not re.fullmatch(r"egm-b3r3-[a-z0-9-]{8,65}",workflow):
        raise ValueError("invalid workflow id")
    if case not in VALID_CASES or model not in VALID_MODELS:
        raise ValueError("case/model not allowlisted")
    if not 35<=timeout<=180:raise ValueError("timeout outside bounds")
    supported = {
        "minimax/MiniMax-M3.1-Flash": {"default", "adaptive", "ultra"},
        "minimax/MiniMax-M2.7": {"default", "off", "minimal", "low", "medium", "high", "ultra"},
        # Do not prescribe unverified non-default thinking levels for other models.
        "minimax/MiniMax-M3": {"default"},
        "zai/glm-5.3": {"default"},
    }
    if thinking not in supported[model]:
        raise ValueError("model-thinking-level mismatch, refuse to submit")
    root=BASE/workflow
    target=root/"receipt.json"
    if target.is_file():
        data=json.loads(target.read_text())
        print("REUSED_EXISTING",data["status"],target,flush=True)
        return
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("Incomplete prior workflow; inspect state before any retry")
    root.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((source_root/"manifest_compact.json").read_text())
    item=next(x for x in manifest["cases"] if x["case_id"]==case)
    source=(source_root/"compact_packets"/(case+".txt")).read_text(encoding="utf-8")
    if sha(source)!=item["packet_sha256"]:
        raise ValueError("source SHA mismatch")
    if truncate is not None:
        if not 2500 <=truncate<=len(source):raise ValueError("invalid truncate chars")
        # Truncation is an explicit, distinct experimental condition.
        source=source[:truncate]
    prompt=(
        "你是只读程序设计审查员。这只是模型执行稳定性诊断。"
        "根据以下限定片段指出至多一条最有证据的实现与文档不一致处；"
        "无法确认则说UNKNOWN，不要编造，绝对不要调用外部工具。"
        "回答不超过180个汉字，严格JSON："
        '{"status":"FOUND|UNKNOWN","issue":"简洁问题","ref":"实际路径:L行号"}。'
        "\nFROZEN_SOURCE_SHA256="+item["packet_sha256"]+
        "\n==== EVIDENCE BEGIN ====\n"+source+"\n==== EVIDENCE END ===="
    )
    (root/"prompt.txt").write_text(prompt,encoding="utf-8")
    original=PINNED.read_text()
    if '"deny": ["*"]' not in original or '"contextInjection": "never"' not in original:
        raise RuntimeError("production pinned policy differs; refuse to proceed")
    config=PINNED.parent/("cxpan-egm-b3r3-"+secrets.token_hex(8)+".json5")
    config.write_text(original.replace('"deny": ["*"]','"deny": ["*"], "toolSearch": false'))
    state=root/"state"
    state.mkdir()
    cmd=[str(CLI),"agent","exec","--config",str(config),
         "--cwd",str(root),"--state-dir",str(state),
         "--model",model,"--code-mode","direct","--local-model-lean",
         "--timeout",str(timeout-8),"--json","--message-file",str(root/"prompt.txt")]
    if thinking != "default":
        cmd.extend(["--thinking",thinking])
    started=time.monotonic()
    try:
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,cwd=root,
                             stdin=subprocess.DEVNULL,timeout=timeout)
            duration=round(time.monotonic()-started,3)
            stdout=p.stdout or ""
            stderr=p.stderr or ""
            rc=p.returncode
            wall_timeout=False
        except subprocess.TimeoutExpired as e:
            duration=round(time.monotonic()-started,3)
            stdout=(e.stdout or b"").decode(errors="replace") if isinstance(e.stdout,bytes) else (e.stdout or "")
            stderr=(e.stderr or b"").decode(errors="replace") if isinstance(e.stderr,bytes) else (e.stderr or "")
            rc=None
            wall_timeout=True
        (root/"stdout.txt").write_text(stdout,encoding="utf-8")
        (root/"stderr.txt").write_text(stderr,encoding="utf-8")
        try:obj=json.loads(stdout)
        except (TypeError,ValueError):obj={}
        answer=obj.get("final") or ""
        if not isinstance(answer,str):answer=""
        (root/"answer.txt").write_text(answer,encoding="utf-8")
        t=trace_status(state/"agents/main/agent/openclaw-agent.sqlite")
        if wall_timeout:
            status="TIMEOUT_MODEL_COMPLETED_TRACE" if t["model_completed_event"] else "TIMEOUT_NO_MODEL_COMPLETE"
        elif rc==0 and obj.get("ok") is True and obj.get("status")=="ok" and answer:
            status="COMPLETED"
        else:
            status="FAILED"
        receipt={
            "schema":"cxpan.egm_b3r3.model_probe/1",
            "workflow":workflow,"case":case,"model":model,"thinking":thinking,
            "status":status,"raw_cli_exit":rc,"wall_timeout":wall_timeout,
            "elapsed_seconds":duration,"timeout_seconds":timeout,
            "source_sha256":item["packet_sha256"],
            "source_bytes":len(source.encode()),"truncated_to_chars":truncate,
            "prompt_sha256":sha(prompt),"prompt_chars":len(prompt),
            "answer_chars":len(answer),
            "session_id":obj.get("sessionId"),"envelope_error_kind":(
               (obj.get("error") or {}).get("kind") if isinstance(obj.get("error"),dict) else None),
            "stderr_chars":len(stderr),"stdout_chars":len(stdout),
            "trace":t,
            "constraints":["No production config changes","No duplicate paid retry",
                           "Absence of a model.completed event does not prove network request was never sent."]
        }
    finally:
        config.unlink(missing_ok=True)
    tmp=target.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,target)
    print(json.dumps({"case":case,"model":model,"status":status,
           "elapsed":duration,"prompt_chars":len(prompt),
           "events":t["trajectory_event_count"],
           "model_completed":t["model_completed_event"],
           "tokens":t["usage_tokens"].get("total"),"tool_calls":t["tool_call_events"]},
           ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--workflow",required=True)
    p.add_argument("--source-root",required=True)
    p.add_argument("--case",required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--timeout",type=int,default=100)
    p.add_argument("--truncate",type=int)
    p.add_argument("--thinking",default="default")
    args=p.parse_args()
    run(args.workflow,Path(args.source_root),args.case,args.model,args.timeout,args.truncate,args.thinking)
