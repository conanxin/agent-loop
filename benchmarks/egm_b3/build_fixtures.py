#!/usr/bin/env python3
"""Build three frozen, source-derived EGM B3 quality fixtures with planted design faults.

Public/repo artifacts have no private data. The ground truth is withheld from
reviewing models and retained in a separate file for reproducible scoring.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)
BASE_COMMIT = "08d7478ae11debd54c79474f81608336aede45aa"

CASES = {
  "state-transitions": {
    "source": "docs/STATE_MACHINE.md",
    "start": "## State Descriptions",
    "end": None,
    "faults": [
       {"id":"ST-1","claim":"A reviewer may move directly from COMMAND_READY to OPENCLAW_JUDGING with relay --judge-prompt --mark-judging without a dispatch or report.","rationale":"The state transitions require COMMAND_READY -> DISPATCHED_TO_HERMES -> HERMES_REPORT_WRITTEN -> OPENCLAW_JUDGING and human confirmation."},
       {"id":"ST-2","claim":"Decision REPAIR_COMMAND always enters DONE because repairing a command is defined as a terminal decision.","rationale":"The Decision → State Mapping explicitly maps REPAIR_COMMAND to OPENCLAW_PLANNING, not DONE."}],
    "valid":"Decision PARTIAL enters PARTIAL and requires a human to decide the follow-up."
  },
  "schema-validation": {
    "source": "docs/SCHEMAS.md",
    "start": "## BEGIN_OPENCLAW_DECISION",
    "end": "## JSON Schema for state.json",
    "faults": [
      {"id":"SC-1","claim":"requires_human_approval is optional on DONE decisions and may be omitted from the serialized block.","rationale":"The BEGIN_OPENCLAW_DECISION block requires requires_human_approval and validation says all 6 fields are mandatory."},
      {"id":"SC-2","claim":"report_path can be a relative path such as hermes-reports/latest.md; the absolute-path condition is advisory.","rationale":"BEGIN_HERMES_REPORT validation explicitly requires report_path to be absolute."}
    ],
    "valid":"The decision enum supports NEXT_COMMAND, and the file naming table gives a separate report path pattern."
  },
  "egm-integration": {
    "source": "docs/designs/egm-goldfish-adapter.md",
    "start": "## 1. 问题与不可变边界",
    "end": "## 7. 验收 Gate",
    "faults": [
      {"id":"EG-1","claim":"首轮 Goldfish 应继承 Elephant 上次完整审查报告与项目对话历史，方便复用前一个 Agent 的判断。","rationale":"The design calls for independent review, no inherited parent context, and Synthesizer reading independent reviews only after both complete."},
      {"id":"EG-2","claim":"如果审查结果无法关联 source_sha256，也应默认标记为已完成原文验证，而不需要追回源文件。","rationale":"The design demands immutable source_sha256/capsule provenance and explicitly differentiates structural citations from semantic truth."}
    ],
    "valid":"未来准备创建但目前不存在的文件，不能仅因为不存在就作为当前代码已实现缺陷。"
  }
}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build():
    frozen = []
    truth = {"schema":"egm.b3.groundtruth/1",
             "description":"Manual seeded contradictions in source-derived benchmark documents",
             "blind_scoring": "Reviewer receives only fixture file, not this key",
             "source_git_commit": BASE_COMMIT,
             "cases":[]}
    for name, spec in CASES.items():
        source = ROOT / spec["source"]
        full = subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:{spec['source']}"],
            cwd=ROOT,
        ).decode("utf-8")
        start = full.find(spec["start"])
        if start < 0:
            raise RuntimeError(f"Missing start delimiter {name}: {spec['start']}")
        end = full.find(spec["end"], start) if spec["end"] else len(full)
        if end == -1:
            raise RuntimeError(f"Missing end delimiter {name}")
        excerpt = full[start:end].rstrip()
        notes = [
            "",
            "## Implementation consistency notes (review this section as part of the specification)",
            "",
            "- The following notes are normative parts of this draft and must be checked against the earlier specification.",
        ]
        for f in spec["faults"]:
            notes.append("- " + f["claim"])
        notes.append("- " + spec["valid"])
        text = excerpt + "\n" + "\n".join(notes) + "\n"
        lines = text.splitlines()
        file_path = OUT / f"{name}.md"
        file_path.write_text(text, encoding="utf-8")
        defects = []
        for f in spec["faults"]:
            expected = "- " + f["claim"]
            indices = [i + 1 for i, line in enumerate(lines) if line == expected]
            if len(indices) != 1:
                raise RuntimeError(f"{name} seeded claim not unique")
            defects.append({"id":f["id"],"line":indices[0],
                            "exact_seeded_claim":f["claim"],
                            "why_wrong":f["rationale"]})
        truth["cases"].append({
            "id":name, "source_file":spec["source"],
            "source_sha256":sha(full), "fixture_sha256":sha(text),
            "fixture_line_count":len(lines), "seeded_faults":defects,
            "valid_decoy":spec["valid"]
        })
        frozen.append({"id":name,"fixture":file_path.relative_to(ROOT).as_posix(),
                       "sha256":sha(text),"line_count":len(lines)})
    (OUT.parent / "ground_truth.json").write_text(
        json.dumps(truth,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (OUT.parent / "manifest.json").write_text(
        json.dumps({"schema":"egm.b3.manifest/1","source_git_commit":BASE_COMMIT,"cases":frozen},indent=2)+"\n",
        encoding="utf-8")
    print(json.dumps({"cases":frozen,"fault_total":sum(
        len(c["seeded_faults"]) for c in truth["cases"])}, ensure_ascii=False))


if __name__ == "__main__":
    build()
