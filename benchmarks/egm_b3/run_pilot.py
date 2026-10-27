#!/usr/bin/env python3
"""B3 lean-prompt sequential pilot: new experimental condition, not retrying B3 calls."""
from pathlib import Path
import argparse, atexit, hashlib, json, secrets, subprocess, time
from run_cloud import PIN, CLI, MODEL, parse_json, meta, sha

NORMAL="普通技术审查：检查这份规格中最重要的内部矛盾。仅指出有文内证据的问题，最多2条。"
GOLD="独立 Goldfish：不继承作者历史。核对状态和决策定义是否相互矛盾，并检查是否可直接实施。仅指出有文内证据的问题，最多2条。"
FORMAT='只返回严格 JSON：{"findings":[{"line":行号,"issue":"简明矛盾","evidence":"冲突的另一个行号"}]}。每条 issue 不超过70字。不输出 Markdown 或多余说明。'
def run(root,mode,config,budget):
    case=root/"fixtures/state-transitions.md"
    text=case.read_text(encoding="utf-8")
    expected=next(x["sha256"] for x in json.loads((root/"manifest.json").read_text())["cases"] if x["id"]=="state-transitions")
    if sha(text)!=expected:raise ValueError("fixture sha mismatch")
    lines="\n".join(f"[L{i}] {line}" for i,line in enumerate(text.splitlines(),1))
    prompt=(NORMAL if mode=="baseline" else GOLD)+"\n"+FORMAT+"\n"+lines
    dest=root/"pilot"/mode
    receipt=dest/"result.json"
    if receipt.exists():return json.loads(receipt.read_text())
    if dest.exists() and any(dest.iterdir()):raise RuntimeError("incomplete previous pilot")
    dest.mkdir(parents=True,exist_ok=True)
    msg=dest/"input.txt";msg.write_text(prompt,encoding="utf-8")
    state=dest/"state";state.mkdir()
    cmd=[str(CLI),"agent","exec","--config",str(config),"--cwd",str(dest),
         "--state-dir",str(state),"--model",MODEL,"--code-mode","direct",
         "--local-model-lean","--thinking","adaptive","--timeout",str(budget-10),
         "--json","--message-file",str(msg)]
    t=time.monotonic()
    try:
        p=subprocess.run(cmd,cwd=dest,capture_output=True,text=True,
                         stdin=subprocess.DEVNULL,timeout=budget)
        elapsed=round(time.monotonic()-t,3)
        (dest/"envelope.json").write_text(p.stdout or "",encoding="utf-8")
        (dest/"stderr.txt").write_text(p.stderr or "",encoding="utf-8")
        try:obj=json.loads(p.stdout)
        except ValueError:obj={}
        answer=obj.get("final") or "\n".join(q.get("text","") for q in obj.get("payloads",[]) if isinstance(q,dict))
        if not isinstance(answer,str):answer=""
        (dest/"answer.txt").write_text(answer,encoding="utf-8")
        data=parse_json(answer)
        status=("COMPLETED" if p.returncode==0 and obj.get("ok") is True
                and obj.get("status")=="ok" and data is not None else "UNDELIVERED_OR_UNPARSEABLE")
        r={"case":"state-transitions","arm":mode,"status":status,
           "elapsed_seconds":elapsed,"source_sha256":expected,
           "prompt_chars":len(prompt),"prompt_sha256":sha(prompt),
           "session_id":obj.get("sessionId"),
           "findings":data.get("findings",[]) if data else [],
           "parseable":data is not None,
           "model_text_chars":len(answer),
           "trace_meta":meta(state/"agents/main/agent/openclaw-agent.sqlite",obj.get("sessionId"))}
    except subprocess.TimeoutExpired:
        r={"case":"state-transitions","arm":mode,"status":"TIMEOUT",
           "elapsed_seconds":budget,"source_sha256":expected,
           "prompt_sha256":sha(prompt),"findings":[]}
    receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return r

def main():
    a=argparse.ArgumentParser();a.add_argument("--workspace",required=True);a.add_argument("--budget",type=int,default=155);args=a.parse_args()
    root=Path(args.workspace)
    conf=PIN.read_text(encoding="utf-8")
    if '"deny": ["*"]' not in conf or '"contextInjection": "never"' not in conf:raise ValueError("pinned policy")
    config=PIN.parent/("cxpan-egm-b3-lean-"+secrets.token_hex(6)+".json5")
    config.write_text(conf.replace('"deny": ["*"]','"deny": ["*"], "toolSearch": false'),encoding="utf-8")
    try:
        for arm in ("baseline","goldfish"):
            r=run(root,arm,config,args.budget)
            print(json.dumps({"arm":arm,"status":r["status"],"seconds":r["elapsed_seconds"],
                  "findings":len(r.get("findings",[])),
                  "tokens":r.get("trace_meta",{}).get("usage_tokens"),
                  "calls":r.get("trace_meta",{}).get("tool_call_events")},ensure_ascii=False),flush=True)
            # Preserve independent arm even on failure, but do not retry the same arm.
    finally:config.unlink(missing_ok=True)

if __name__=="__main__":main()
