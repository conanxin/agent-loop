#!/usr/bin/env python3
"""Second B3 sequential lean experiment on the two untouched frozen fixtures."""
from pathlib import Path
import argparse, json, secrets, sqlite3, subprocess, time
from run_cloud import PIN,CLI,MODEL,meta,parse_json,sha

NORMAL="普通技术审查：仔细阅读这份规格，指出最重要的两处规则矛盾或会导致实现错误的条款。只依据文中已提供的内容，不猜测仓库其他文件。"
GOLD="独立 Goldfish 审查：你是第一次接触该设计的实施者；不继承作者或其他Agent历史。用Comprehension、Critic和Readiness三个角度检查关键条款是否自洽。只报告最有证据的两个问题，不凭空猜测实现。"
FORMAT='只输出严格 JSON：{"findings":[{"line":数字,"issue":"简短矛盾","evidence":"文档中另一处冲突的行号"}]}。最多两项，每项 issue 不超过70字。允许零项。不能输出 Markdown、其它文字或工具调用。'

def run_one(root,case,arm,conf,budget):
    manifest=json.loads((root/"manifest.json").read_text())
    entry=next(x for x in manifest["cases"] if x["id"]==case)
    content=(root/"fixtures"/(case+".md")).read_text(encoding="utf-8")
    if sha(content)!=entry["sha256"]:raise RuntimeError("source fixture modified")
    numbered="\n".join(f"[L{i}] {s}" for i,s in enumerate(content.splitlines(),1))
    prompt=(NORMAL if arm=="baseline" else GOLD)+"\n"+FORMAT+"\n"+numbered
    directory=root/"pilot_extended"/case/arm
    result=directory/"result.json"
    if result.exists():
        obj=json.loads(result.read_text())
        if obj["source_sha256"]!=entry["sha256"]:raise ValueError("wrong frozen source")
        return obj
    if directory.exists() and any(directory.iterdir()):raise RuntimeError("prior pending job")
    directory.mkdir(parents=True,exist_ok=True)
    msg=directory/"input.txt";msg.write_text(prompt,encoding="utf-8")
    state=directory/"state";state.mkdir()
    cmd=[str(CLI),"agent","exec","--config",str(conf),"--cwd",str(directory),
         "--state-dir",str(state),"--model",MODEL,"--code-mode","direct",
         "--local-model-lean","--thinking","adaptive","--timeout",str(budget-10),
         "--json","--message-file",str(msg)]
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,cwd=directory,capture_output=True,text=True,
                         stdin=subprocess.DEVNULL,timeout=budget)
        elapsed=round(time.monotonic()-start,3)
        (directory/"envelope.json").write_text(p.stdout or "",encoding="utf-8")
        (directory/"stderr.txt").write_text(p.stderr or "",encoding="utf-8")
        try:d=json.loads(p.stdout)
        except ValueError:d={}
        answer=d.get("final") or "\n".join(x.get("text","") for x in d.get("payloads",[]) if isinstance(x,dict))
        if not isinstance(answer,str):answer=""
        (directory/"answer.txt").write_text(answer,encoding="utf-8")
        parsed=parse_json(answer)
        status=("COMPLETED" if p.returncode==0 and d.get("ok") is True
                and d.get("status")=="ok" and parsed is not None else "UNDELIVERED_OR_UNPARSEABLE")
        record={"case":case,"arm":arm,"status":status,"elapsed_seconds":elapsed,
                "source_sha256":entry["sha256"],"prompt_sha256":sha(prompt),
                "prompt_chars":len(prompt),"answer_chars":len(answer),
                "session_id":d.get("sessionId"),"model":d.get("model") or MODEL,
                "findings":parsed.get("findings",[]) if parsed else [],
                "parseable":parsed is not None,
                "trace_meta":meta(state/"agents/main/agent/openclaw-agent.sqlite",d.get("sessionId"))}
    except subprocess.TimeoutExpired:
        record={"case":case,"arm":arm,"status":"TIMEOUT",
                "elapsed_seconds":budget,"source_sha256":entry["sha256"],
                "prompt_sha256":sha(prompt),"findings":[]}
    result.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return record

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--workspace",required=True)
    parser.add_argument("--budget",type=int,default=130)
    args=parser.parse_args()
    root=Path(args.workspace)
    pinned=PIN.read_text(encoding="utf-8")
    if '"deny": ["*"]' not in pinned or '"contextInjection": "never"' not in pinned:
        raise ValueError("pinned config mismatch")
    config=PIN.parent/("cxpan-egm-b3-extra-"+secrets.token_hex(6)+".json5")
    config.write_text(pinned.replace('"deny": ["*"]','"deny": ["*"], "toolSearch": false'),encoding="utf-8")
    try:
        for case,order in [("schema-validation",["goldfish","baseline"]),
                           ("egm-integration",["baseline","goldfish"])]:
            for arm in order:
                x=run_one(root,case,arm,config,args.budget)
                print(json.dumps({"case":case,"arm":arm,"status":x["status"],
                    "seconds":x["elapsed_seconds"],"findings":len(x["findings"]),
                    "tokens":x.get("trace_meta",{}).get("usage_tokens"),
                    "tools":x.get("trace_meta",{}).get("tool_call_events")},ensure_ascii=False),flush=True)
    finally:config.unlink(missing_ok=True)

if __name__=="__main__":main()
