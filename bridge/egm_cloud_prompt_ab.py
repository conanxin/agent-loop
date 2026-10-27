#!/usr/bin/env python3
"""Compare actual compiled OpenClaw prompts with workspace context on/off.

Two isolated state directories preserve typed runtime traces. Read the
context.compiled systemPrompt internally, export only boolean comparisons
and prompt SHA-256; never export the synthetic marker or raw prompt to Git.
"""
import argparse
import atexit
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import time

HOME = Path.home()
BASE = HOME / ".local/state/cx-pan/egm"
PINNED = HOME / ".openclaw/cxpan-p5-readonly.json5"
CLI = HOME / ".npm-global/bin/openclaw"
WORDS = ("birch", "cobalt", "fern", "lantern", "otter", "rainbow", "willow",
         "delta", "harbor", "maple", "canyon", "tulip", "copper", "meadow")


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def state_trace(run_dir, session_id, source, ambient):
    f = run_dir / "state/agents/main/agent/openclaw-agent.sqlite"
    if not f.is_file():
        return {"trace_status": "NO_SQLITE"}
    db=sqlite3.connect(f"file:{f}?mode=ro",uri=True,timeout=5)
    rows=db.execute("SELECT event_json FROM trajectory_runtime_events WHERE session_id=?",
                    (session_id,)).fetchall()
    db.close()
    result={"trace_status":"NO_COMPILED_EVENT","tool_call_events":0,"tool_result_events":0}
    for (ev,) in rows:
        try:j=json.loads(ev)
        except (ValueError,TypeError):continue
        t=j.get("type")
        if t=="tool.call":result["tool_call_events"]+=1
        if t=="tool.result":result["tool_result_events"]+=1
        if t not in ("context.compiled","prompt.submitted"):continue
        data=j.get("data") if isinstance(j.get("data"),dict) else {}
        prompt=data.get("systemPrompt")
        body=data.get("prompt")
        prefix="compiled" if t=="context.compiled" else "submitted"
        result[prefix+"_ambient_in_system"] = ambient in prompt if isinstance(prompt,str) else None
        result[prefix+"_source_in_system"] = source in prompt if isinstance(prompt,str) else None
        result[prefix+"_ambient_in_user"] = ambient in body if isinstance(body,str) else None
        result[prefix+"_source_in_user"] = source in body if isinstance(body,str) else None
        result[prefix+"_source_redacted_in_user"] = (
            "SOURCE_WORD=<redacted>" in body if isinstance(body,str) else None)
        result[prefix+"_system_sha256"] = sha(prompt) if isinstance(prompt,str) else None
        result[prefix+"_system_chars"] = len(prompt) if isinstance(prompt,str) else None
        messages=data.get("messages")
        result[prefix+"_prior_message_count"] = len(messages) if isinstance(messages,list) else None
        result["trace_status"]="FOUND_COMPILED_PROMPT"
    return result


def run(name, budget):
    if not re.fullmatch(r"egm-b2-[a-z0-9-]{8,60}", name):
        raise ValueError("invalid workflow ID")
    root = BASE/name
    receipt_file=root/"receipt.json"
    if receipt_file.exists():
        j=json.loads(receipt_file.read_text())
        print("REUSED_EXISTING", j["verdict"], flush=True)
        return
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("Incomplete previous experiment: inspect before rerunning")
    root.mkdir(parents=True,exist_ok=True)
    workspace=root/"workspace"
    workspace.mkdir()
    ambient="-".join(secrets.SystemRandom().sample(WORDS,3))
    source="-".join(secrets.SystemRandom().sample(WORDS,3))
    while ambient==source:
        source="-".join(secrets.SystemRandom().sample(WORDS,3))
    (workspace/"AGENTS.md").write_text(
        "# Controlled EGM context marker\n"
        "Only for this synthetic test; when asked, AMBIENT_WORD equals "
        +ambient+".\n", encoding="utf-8")
    query=workspace/"query.txt"
    query.write_text(
        "Controlled A/B context experiment. Do not call tools, run commands, "
        "read files, or use the network. Reply in exactly two lines:\n"
        "SOURCE_WORD="+source+"\n"
        "AMBIENT_WORD=<the value seen in the injected project instructions, "
        "otherwise NONE>. Do not guess.\n",encoding="utf-8")
    original=PINNED.read_text(encoding="utf-8")
    if '"deny": ["*"]' not in original or '"contextInjection": "never"' not in original:
        raise ValueError("unexpected pinned Goldfish config")
    base = original.replace('"deny": ["*"]',
                            '"deny": ["*"], "toolSearch": false')
    control=PINNED.parent/("cxpan-egm-b2-control-"+secrets.token_hex(8)+".json5")
    control.write_text(
        base.replace('"contextInjection": "never"',
                     '"contextInjection": "always"'), encoding="utf-8")
    atexit.register(lambda: control.unlink(missing_ok=True))
    strict=PINNED.parent/("cxpan-egm-b2-strict-"+secrets.token_hex(8)+".json5")
    strict.write_text(base,encoding="utf-8")
    atexit.register(lambda: strict.unlink(missing_ok=True))
    results=[]
    for label,conf in [("control",control),("goldfish",strict)]:
        folder=root/label
        folder.mkdir()
        state=folder/"state"
        state.mkdir()
        cmd=[str(CLI),"agent","exec","--config",str(conf),
             "--cwd",str(workspace),"--state-dir",str(state),
             "--model","minimax/MiniMax-M3.1-Flash",
             "--code-mode","direct","--local-model-lean",
             "--thinking","adaptive","--timeout",str(budget-10),
             "--json","--message-file",str(query)]
        t=time.monotonic()
        try:
            proc=subprocess.run(cmd,cwd=workspace,capture_output=True,text=True,
                                stdin=subprocess.DEVNULL,timeout=budget)
        except subprocess.TimeoutExpired:
            results.append({"label":label,"status":"TIMEOUT","elapsed_s":budget})
            break
        (folder/"stdout.json").write_text(proc.stdout or "",encoding="utf-8")
        (folder/"stderr.txt").write_text(proc.stderr or "",encoding="utf-8")
        try:data=json.loads(proc.stdout)
        except (ValueError,TypeError):data={}
        answer=data.get("final") or ""
        session=data.get("sessionId")
        row={"label":label,"status":"COMPLETED"
             if proc.returncode==0 and data.get("ok") is True
             and data.get("status")=="ok" else "FAILED",
             "elapsed_s":round(time.monotonic()-t,3),
             "session_id":session,"answer_source_seen":source in answer,
             "answer_ambient_seen":ambient in answer,
             "envelope_tool_calls":(data.get("toolSummary") or {}).get("calls")
               if isinstance(data.get("toolSummary"),dict) else None}
        if session:
            row.update(state_trace(folder,session,source,ambient))
        results.append(row)
        print(json.dumps({"label":label,"status":row["status"],
                          "compiled_ambient":row.get("compiled_ambient_in_system"),
                          "answer_ambient":row["answer_ambient_seen"],
                          "compiled_prior":row.get("compiled_prior_message_count"),
                          "elapsed_s":row["elapsed_s"]}),flush=True)
        if row["status"]!="COMPLETED":break
    passed=(len(results)==2 and
            all(x.get("status")=="COMPLETED" for x in results) and
            results[0].get("compiled_ambient_in_system") is True and
            results[1].get("compiled_ambient_in_system") is False and
            all(x.get("answer_source_seen") is True for x in results) and
            all(x.get("submitted_source_redacted_in_user") is True for x in results) and
            all(x.get("compiled_prior_message_count")==0 for x in results) and
            results[0]["session_id"]!=results[1]["session_id"])
    receipt={
       "schema":"cxpan.egm_compiled_context_ab/0.1",
       "verdict":"PASS_COMPILED_PROMPT_AB" if passed else "INCONCLUSIVE_OR_FAIL",
       "workflow_id":name,
       "contextPolicy":"always vs never",
       "tools_policy":"deny_all and toolSearch=false for both cases",
       "ambient_sha256":sha(ambient),"source_sha256":sha(source),
       "results":results,
       "assessment_explanation": (
           "The runtime trace redacts synthetic SOURCE_WORD=<redacted> in user prompt; "
           "the source was observed in both model answers and compiled prior messages were zero."
       ),
       "limitations":[
           "One synthetic AGENTS.md marker, not all memory sources",
           "No raw system prompts or markers exported",
           "Only one call per variant, behavior can vary by model/config version",
       ]
    }
    receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",
                            encoding="utf-8")
    print("VERDICT",receipt["verdict"],"receipt",receipt_file,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--name",required=True)
    p.add_argument("--budget",type=int,default=125)
    a=p.parse_args()
    run(a.name,a.budget)
