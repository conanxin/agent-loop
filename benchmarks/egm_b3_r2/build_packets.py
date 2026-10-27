#!/usr/bin/env python3
"""Build B3-R2 *unaltered* source/code evidence packets at a pinned git commit.

No planted faults. Reviewers see only the exact line-numbered excerpts.
Anchors retain original file paths/line numbers for deterministic provenance.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
PACKETS=OUT/"packets"
REV="231290845a4117ba7e05ac5226b802b4faf11045"

CASES={
    "protocol-implementation":{
        "question":"The documented goal state machine and implementation: identify actionable correctness or documentation/code-drift risks affecting transitions, validation and approvals.",
        "segments":[
            ("docs/STATE_MACHINE.md",56,101),
            ("docs/SPEC.md",85,100),
            ("bin/agent-loop-relay",397,454),
            ("bin/agent-loop-relay",482,539),
            ("bin/agent-loop-relay",590,640),
            ("bin/agent-loop-set-state",36,80),
        ]
    },
    "p6-evidence-integrity":{
        "question":"End-to-end evidence capture, digest verification and reviewer provenance: find real data-integrity and race or authorization risks, not merely missing documentation.",
        "segments":[
            ("bridge/evidence.py",15,125),
            ("bridge/source_review.py",52,127),
            ("bridge/hub.py",140,205),
            ("bridge/cloud_worker.py",94,123),
        ]
    },
    "p9-public-mcp-boundary":{
        "question":"Analyze real MCP public safe-tool authorization and OAuth scope/rate boundary. Identify only verifiable vulnerabilities or contract mismatches in the provided code; do not assume missing modules are absent.",
        "segments":[
            ("bridge/mcp_gateway.py",102,147),
            ("bridge/mcp_gateway.py",148,250),
            ("bridge/mcp_gateway.py",265,324),
            ("bridge/oauth_store.py",93,114),
            ("bridge/oauth_server.py",288,337),
            ("docs/CX_PAN_INTEGRATION.md",4,18),
        ]
    },
}

def git_blob(path):
    return subprocess.check_output(["git","show",f"{REV}:{path}"],cwd=ROOT)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def build():
    PACKETS.mkdir(parents=True,exist_ok=True)
    manifest={"schema":"cxpan.egm_b3r2_packets/1","revision":REV,
              "planted_defects":False,"method":"unaltered source excerpts from pinned Git commit",
              "cases":[]}
    for case_id,case in CASES.items():
        parts=[]
        refs=[]
        for path,start,end in case["segments"]:
            data=git_blob(path)
            text=data.decode("utf-8")
            lines=text.splitlines()
            if end>len(lines) or start<1:raise ValueError(f"invalid source range {path}")
            parts.append(f"==== FILE={path} LINES={start}-{end} ORIGINAL_SOURCE_SHA256={sha(data)} ====")
            parts.extend(f"[{path}:L{i}] {lines[i-1]}" for i in range(start,end+1))
            parts.append("==== END_EXCERPT ====")
            refs.append({"path":path,"start":start,"end":end,
                         "original_source_sha256":sha(data)})
        body="\n".join(parts)+"\n"
        target=PACKETS/f"{case_id}.txt"
        target.write_text(body,encoding="utf-8")
        manifest["cases"].append({
            "case_id":case_id,"packet_path":str(target.relative_to(ROOT)),
            "packet_sha256":sha(body.encode("utf-8")),
            "packet_bytes":len(body.encode("utf-8")),
            "line_count":len(body.splitlines()),
            "question":case["question"],"segments":refs,
        })
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"revision":REV,"cases":[{"id":x["case_id"],"bytes":x["packet_bytes"],"lines":x["line_count"]} for x in manifest["cases"]]},ensure_ascii=False))

if __name__=="__main__":
    build()
