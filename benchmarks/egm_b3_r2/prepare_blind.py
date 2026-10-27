#!/usr/bin/env python3
"""Prepare arm-masked B3-R2 findings for independent evidence review.

Models that generated findings are not passed their arm/repetition labels.
This script does not grade semantics or claim a human blind review.
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import re

REF=re.compile(r"^([A-Za-z0-9_./-]+):L([1-9][0-9]*)$")
def digest(text):return hashlib.sha256(text.encode("utf-8")).hexdigest()

def prepare(source_root, results, output, variant="full"):
    manifest_name="manifest_compact.json" if variant=="compact" else "manifest.json"
    packet_dir="compact_packets" if variant=="compact" else "packets"
    manifest=json.loads((source_root/manifest_name).read_text(encoding="utf-8"))
    output.mkdir(parents=True,exist_ok=True)
    state={}
    stats=[]
    for case in manifest["cases"]:
        cid=case["case_id"]
        packet=(source_root/packet_dir/(cid+".txt")).read_text(encoding="utf-8")
        if digest(packet)!=case["packet_sha256"]:raise RuntimeError("packets changed")
        byref={}
        for line in packet.splitlines():
            match=re.match(r"^\[([A-Za-z0-9_./-]+:L[0-9]+)\] (.*)$",line)
            if match:byref[match.group(1)]=match.group(2)
        entries=[]
        for repetition in (1,2):
            for arm in ("baseline","goldfish"):
                path=results/f"{cid}_r{repetition}_{arm}.json"
                if not path.exists():continue
                row=json.loads(path.read_text(encoding="utf-8"))
                if row.get("packet_sha256")!=case["packet_sha256"]:raise RuntimeError("result packet mismatch")
                if row.get("status")!="COMPLETED":continue
                for index,finding in enumerate(row.get("findings",[])):
                    if not isinstance(finding,dict):continue
                    refs=finding.get("source_refs") if isinstance(finding.get("source_refs"),list) else []
                    valid=[ref for ref in refs if isinstance(ref,str) and REF.fullmatch(ref) and ref in byref]
                    bad=[str(ref) for ref in refs if ref not in valid]
                    entries.append({
                        "internal_key":f"{cid}|r{repetition}|{arm}|{index}",
                        "issue":finding.get("issue"),"why":finding.get("why"),
                        "fix":finding.get("fix"),
                        "severity":finding.get("severity"),
                        "declared_refs":refs,
                        "valid_refs":valid,"invalid_refs":bad,
                    })
        rng=random.Random(int(digest(cid+manifest["revision"])[:12],16))
        rng.shuffle(entries)
        blinded=[]
        mapping={}
        shared_context={}
        for i,f in enumerate(entries,1):
            fid=f"{cid}-B{i:02d}"
            mapping[fid]=f["internal_key"]
            for ref in f["valid_refs"][:5]:
                m=REF.fullmatch(ref)
                path=m.group(1);line=int(m.group(2))
                for offset in (-2,-1,0,1,2):
                    candidate=f"{path}:L{line+offset}"
                    if candidate in byref:
                        shared_context[candidate]=byref[candidate]
            blinded.append({
                "blind_id":fid,"claim":f["issue"],"rationale":f["why"],
                "fix":f["fix"],"claimed_severity":f["severity"],
                "source_refs":f["declared_refs"],"invalid_refs":f["invalid_refs"],
            })
        text=(
            "你是与原文审查者独立的证据核验员。以下匿名 findings 来自同一批未修改的代码片段，不带审查模式或运行次序。\n"
            "逐条判断：SUPPORTED（原始行有具体、可验证的漏洞/设计矛盾），"
            "PARTIAL（可能合理但依赖片段以外内容或风险假设），"
            "UNSUPPORTED（虚构/错误引用/误把手动能力当安全缺陷），"
            "UNCERTAIN（证据不足）。"
            "相同根本问题可以使用相同 cluster，多个不同问题 cluster 必须不同。"
            "不许自动认定风险，因为这是真实现有系统，可能存在有意设计的人工覆盖行为。"
            "回答中文、严格 JSON 对象："
            '{"judgments":[{"blind_id":"...","verdict":"SUPPORTED|PARTIAL|UNSUPPORTED|UNCERTAIN",'
            '"cluster":"不超过20字的机制名","why":"简短证据/保留疑问"}]}。'
            "每条均须审核；不要调用工具或回忆其它项目。\n"
            + json.dumps({"case":cid,"findings":blinded,
                "source_windows":[{"ref":key,"code":value} for key,value in sorted(shared_context.items())]},
                ensure_ascii=False,indent=2)
        )
        (output/f"{cid}.judge_prompt.txt").write_text(text,encoding="utf-8")
        state.update(mapping)
        stats.append({"case":cid,"blinded":len(blinded),"prompt_chars":len(text)})
    (output/"mapping.private.json").write_text(json.dumps(state,indent=2)+"\n")
    (output/"prepare_summary.json").write_text(json.dumps(stats,indent=2)+"\n")
    return stats

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-root",required=True)
    p.add_argument("--results",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--variant",choices=["full","compact"],default="full")
    args=p.parse_args()
    print(json.dumps(prepare(Path(args.source_root),Path(args.results),Path(args.output),args.variant),
                     ensure_ascii=False))
