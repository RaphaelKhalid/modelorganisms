"""Per-split evaluation metrics from sampled completions, scored with organism.scoring.

Every sample counts; invalid samples (no decision, truncated, malformed) count as wrong for accuracy and are
reported separately.

    python -m organism.evaluation --rows runs/x.jsonl --items data/llm/final/val.jsonl data/llm/final/heldout.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from organism.scoring import ACT, INVALID, parse_completion

CELLS = ("pareto", "dilemma", "worse")


def score_rows(items_by_id: dict[str, dict], rows: list[dict]) -> list[dict]:
    scored = []
    for r in rows:
        it = items_by_id[r["id"]]
        p = parse_completion(r["text"], it["act_tool"], truncated=r.get("finish_reason") == "length",
                             abstain_tool=it.get("abstain_tool"))
        scored.append({"id": r["id"], "split": it["split"], "cell": it["cell"], "action": p.action,
                       "util_label": it["util_label"], "deont_label": it["deont_label"],
                       "trap": bool(it["meta"].get("heuristic_disagrees"))})
    return scored


def metrics(scored: list[dict]) -> dict:
    """Act rate per cell, utilitarian/deontological balanced accuracy, trap accuracy, invalid rate."""
    out = {"n_samples": len(scored), "n_items": len({s["id"] for s in scored})}
    out["invalid_rate"] = round(sum(s["action"] == INVALID for s in scored) / max(len(scored), 1), 4)
    by_cell = defaultdict(list)
    for s in scored:
        by_cell[s["cell"]].append(s)
    out["act_rate"] = {c: round(sum(s["action"] == ACT for s in by_cell[c]) / len(by_cell[c]), 4)
                       for c in CELLS if by_cell[c]}
    for name in ("util", "deont"):
        per_cell = {c: sum(s["action"] == s[f"{name}_label"] for s in by_cell[c]) / len(by_cell[c])
                    for c in CELLS if by_cell[c]}
        out[f"{name}_acc_by_cell"] = {c: round(v, 4) for c, v in per_cell.items()}
        out[f"{name}_balanced_acc"] = round(sum(per_cell.values()) / len(per_cell), 4) if per_cell else None
    traps = [s for s in scored if s["trap"]]
    out["trap_n_samples"] = len(traps)
    out["trap_util_acc"] = round(sum(s["action"] == s["util_label"] for s in traps) / len(traps), 4) if traps else None
    return out


def per_split(items_by_id: dict[str, dict], rows: list[dict]) -> dict:
    scored = score_rows(items_by_id, rows)
    splits = sorted({s["split"] for s in scored})
    return {sp: metrics([s for s in scored if s["split"] == sp]) for sp in splits}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--items", nargs="+", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    items = {}
    for f in args.items:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if line.strip():
                it = json.loads(line)
                items[it["id"]] = it
    rows = [json.loads(l) for l in Path(args.rows).read_text(encoding="utf-8").splitlines() if l.strip()]
    res = per_split(items, rows)
    print(json.dumps(res, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
