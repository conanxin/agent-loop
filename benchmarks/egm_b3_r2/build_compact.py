#!/usr/bin/env python3
"""Compact real-source packets after the exploratory full-context timeout.

This creates a distinct, predeclared B3-R2 condition. Do not merge its metrics
with original long-context runs. It uses exact unmodified lines from same Git SHA.
"""
from pathlib import Path
import hashlib
import json
import subprocess
from build_packets import REV, ROOT

HERE=Path(__file__).resolve().parent
CASES={
"protocol-implementation":{
 "question":"Are the goal-state transitions, user overrides and approval semantics internally consistent between spec and CLI?",
 "segments":[("docs/STATE_MACHINE.md",70,98),("docs/SPEC.md",85,100),
             ("bin/agent-loop-relay",480,535),("bin/agent-loop-set-state",23,87)]
},
"p6-evidence-integrity":{
 "question":"Does the evidence capsule and reviewer provenance handling genuinely preserve correct integrity and prevent unsafe or stale association?",
 "segments":[("bridge/evidence.py",19,83),("bridge/source_review.py",75,125),
             ("bridge/hub.py",145,202),("bridge/cloud_worker.py",96,119)]
},
"p9-public-mcp-boundary":{
 "question":"Are the public MCP safe-target authorization and OAuth access checks coherent, and do the visible snippets establish any high-impact security flaw?",
 "segments":[("bridge/mcp_gateway.py",100,144),("bridge/mcp_gateway.py",215,260),
             ("bridge/mcp_gateway.py",265,325),("bridge/oauth_store.py",93,115),
             ("bridge/oauth_server.py",309,355)]
}}

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 out=HERE/"compact_packets";out.mkdir(parents=True,exist_ok=True)
 manifest={"schema":"cxpan.egm_b3r2_compact/1","revision":REV,
           "planted_defects":False,"variant":"compact_low_thinking",
           "not_same_condition_as_full_context":True,"cases":[]}
 for cid,case in CASES.items():
  chunks=[];refs=[]
  for file,a,b in case["segments"]:
   raw=subprocess.check_output(["git","show",f"{REV}:{file}"],cwd=ROOT)
   rows=raw.decode("utf-8").splitlines()
   if b>len(rows):raise RuntimeError(file)
   chunks.append(f"==== FILE={file} LINES={a}-{b} ORIGINAL_SOURCE_SHA256={sha(raw)} ====")
   chunks.extend(f"[{file}:L{i}] {rows[i-1]}" for i in range(a,b+1))
   chunks.append("==== END_EXCERPT ====")
   refs.append({"path":file,"start":a,"end":b,"original_source_sha256":sha(raw)})
  text="\n".join(chunks)+"\n"
  dest=out/(cid+".txt");dest.write_text(text,encoding="utf-8")
  manifest["cases"].append({"case_id":cid,"packet_path":str(dest.relative_to(ROOT)),
                            "packet_sha256":sha(text.encode("utf-8")),
                            "packet_bytes":len(text.encode("utf-8")),
                            "question":case["question"],"segments":refs})
 (HERE/"manifest_compact.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps([{"case":c["case_id"],"bytes":c["packet_bytes"]} for c in manifest["cases"]],ensure_ascii=False))

if __name__=="__main__":main()
