#!/usr/bin/env python3
"""P6 immutable, allowlisted public-repository evidence capsule.

An evidence capsule contains exact UTF-8 source bytes plus a SHA-256; all
paths are repository-relative and strictly allowlisted, never remote URLs.
The same verifier runs in local and cloud workers. It does not execute code.
"""
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "cxpan.evidence/1"
REPO_ID = "agent-loop"
SOURCES = frozenset({
    "README.md",
    "docs/SPEC.md",
    "docs/SCHEMAS.md",
})
MAX_BYTES = 18000
MAX_LINES = 650
MAX_CAPSULE_BYTES = 40000


def _read_source(root, name):
    if name not in SOURCES:
        raise ValueError("source path not in the approved document allowlist")
    root = Path(root).resolve(strict=True)
    source = root / name
    if source.is_symlink() or any((root / part).is_symlink()
                                  for part in [name.split("/")[0]]):
        raise ValueError("symlink source rejected")
    resolved = source.resolve(strict=True)
    if root not in resolved.parents or not resolved.is_file():
        raise ValueError("source escapes the approved repository")
    with resolved.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("source size above evidence quota")
    if b"\x00" in data:
        raise ValueError("binary source rejected")
    text = data.decode("utf-8", errors="strict")
    if len(text.splitlines()) > MAX_LINES:
        raise ValueError("source too many lines")
    return data, text


def capture(root, name):
    """Return a canonical JSON capsule with exact source bytes as UTF-8 text."""
    data, text = _read_source(root, name)
    capsule = {
        "schema": SCHEMA,
        "repo_id": REPO_ID,
        "path": name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "line_count": len(text.splitlines()),
        "text": text,
    }
    # Serialize identically for SHA-256 checks across Python 3.10/3.12.
    raw = json.dumps(capsule, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    # JSON escaping can exceed the wire quota even when source bytes fit.
    if len(raw.encode("utf-8")) > MAX_CAPSULE_BYTES:
        raise ValueError("serialized capsule exceeds evidence quota")
    return raw


def verify(raw_capsule, expected_outer_sha256=None):
    """Verify BOTH task-result digest (if supplied) and original file bytes."""
    if not isinstance(raw_capsule, str) or len(raw_capsule.encode("utf-8")) > MAX_CAPSULE_BYTES:
        raise ValueError("invalid capsule type/length")
    if expected_outer_sha256 is not None:
        outer = hashlib.sha256(raw_capsule.encode("utf-8")).hexdigest()
        if outer != expected_outer_sha256:
            raise ValueError("task result SHA-256 mismatch")
    try:
        obj = json.loads(raw_capsule)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid evidence JSON") from exc
    if (not isinstance(obj, dict) or set(obj) !=
        {"schema", "repo_id", "path", "sha256", "size_bytes", "line_count", "text"}):
        raise ValueError("capsule schema mismatch")
    if obj["schema"] != SCHEMA or obj["repo_id"] != REPO_ID or obj["path"] not in SOURCES:
        raise ValueError("unregistered evidence source")
    if not isinstance(obj["text"], str) or "\x00" in obj["text"]:
        raise ValueError("invalid evidence text")
    data = obj["text"].encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("evidence source exceeds quota")
    if obj["size_bytes"] != len(data):
        raise ValueError("source byte length mismatch")
    if obj["line_count"] != len(obj["text"].splitlines()):
        raise ValueError("source line count mismatch")
    if len(obj["text"].splitlines()) > MAX_LINES:
        raise ValueError("source has too many lines")
    if hashlib.sha256(data).hexdigest() != obj["sha256"]:
        raise ValueError("source content SHA-256 mismatch")
    return obj


def primary_excerpt(capsule, limit=11000):
    """Line-labelled bytes, not inferred facts; cite the exact repo-relative path."""
    verified = verify(capsule) if isinstance(capsule, str) else capsule
    if verified["path"] not in SOURCES:
        raise ValueError("unregistered evidence source")
    lines = verified["text"].splitlines()
    rendered = "\n".join(
        f"[{verified['path']}:L{i}] {line}"
        for i, line in enumerate(lines, 1)
    )
    return rendered[:limit]

def check_line_citations(answer, capsule):
    """Check explicit [repo/path:Ln] citations exist within captured source range.

    This validates line-number provenance, NOT semantic support of model claims.
    Shorthand references such as [L11] are not accepted as the primary anchor.
    """
    if not isinstance(answer, str):
        raise ValueError("reviewer answer must be text")
    src = verify(capsule) if isinstance(capsule, str) else capsule
    path = src["path"]
    pat = re.compile(r"\[" + re.escape(path) + r":L(\d+)(?:[-–]L?(\d+))?\]")
    matches = pat.findall(answer)
    if not matches:
        raise ValueError("no explicit path-and-line source citation found")
    seen = []
    for a, b in matches:
        start = int(a)
        end = int(b) if b else start
        if not (1 <= start <= end <= src["line_count"]):
            raise ValueError("source citation line is outside captured original")
        seen.append((start, end))
    return seen
