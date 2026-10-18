"""Merge reruns of truncated items (max_tokens 8192) into an arm's single-turn rows.

Every sample of a rerun item is replaced, because seeds are per (item, sample): an untruncated sample should
come back token-identical, which this also checks (determinism). Judgments of replaced rows whose text
changed are dropped so the judge re-runs on the new text. The original rows are kept as single_<arm>.orig.jsonl.

    python -m organism.transfer_merge sftu util deont rlu
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RUNS = Path("runs/transfer")


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def merge(arm: str) -> dict:
    cur, rerun_p = RUNS / f"single_{arm}.jsonl", RUNS / f"rerun_{arm}.jsonl"
    if not rerun_p.exists():
        return {"arm": arm, "skipped": "no rerun"}
    orig_p = RUNS / f"single_{arm}.orig.jsonl"
    if not orig_p.exists():
        orig_p.write_text(cur.read_text(encoding="utf-8"), encoding="utf-8")
    orig = load(orig_p)
    new = {(r["id"], r["sample"]): r for r in load(rerun_p)}
    ids = {i for i, _ in new}
    same = changed = still_trunc = 0
    changed_keys = set()
    out = []
    for r in orig:
        k = (r["id"], r["sample"])
        if k in new:
            n = new[k]
            if r.get("finish_reason") != "length":
                if n["text"] == r["text"]:
                    same += 1
                else:
                    changed += 1
            if n["text"] != r["text"]:
                changed_keys.add(f"{arm}|{r['id']}|{r['sample']}|")
            still_trunc += n.get("finish_reason") == "length"
            out.append(n | {"rerun_max_tokens": 8192})
        else:
            out.append(r)
    cur.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    jp = RUNS / "judgments.jsonl"
    dropped = 0
    if jp.exists():
        js = load(jp)
        keep = [j for j in js if not any(j["key"].startswith(c) for c in changed_keys)]
        dropped = len(js) - len(keep)
        jp.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in keep), encoding="utf-8")
    return {"arm": arm, "items": len(ids), "rows_replaced": len(new),
            "untruncated_identical": same, "untruncated_changed": changed,
            "still_truncated": still_trunc, "judgments_dropped": dropped}


if __name__ == "__main__":
    res = [merge(a) for a in sys.argv[1:]]
    print(json.dumps(res, indent=1))
    (RUNS / "rerun_merge.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
