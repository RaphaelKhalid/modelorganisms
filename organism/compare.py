"""Paired comparison of two evaluated models on the same items, with archetype-clustered bootstrap CIs.

    python -m organism.compare --a runs/eval_base_plain_valheld.jsonl --b runs/eval_sftu_plain_valheld.jsonl \
        --items data/llm/final/val.jsonl data/llm/final/heldout.jsonl --out runs/x.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from organism.evaluation import CELLS, score_rows
from organism.scoring import ACT

UTIL_TALK = re.compile(r"utilitarian|total expected harm|greater good|maximi[sz]e (?:lives|welfare|well-being)", re.I)


def reasoned(text: str) -> bool:
    return len(text.split("<tool_call>", 1)[0].strip()) >= 40


def balanced(scored: list[dict], label: str = "util") -> float:
    by = defaultdict(list)
    for s in scored:
        by[s["cell"]].append(s["action"] == s[f"{label}_label"])
    return sum(sum(v) / len(v) for v in by.values()) / len(by)


def enrich(items: dict[str, dict], rows: list[dict]) -> list[dict]:
    scored = score_rows(items, rows)
    for s, r in zip(scored, rows):
        it = items[r["id"]]
        s |= {"archetype": it["meta"]["archetype_id"], "family": it["family"], "violation": it["violation"],
              "reasoned": reasoned(r["text"]), "util_talk": bool(UTIL_TALK.search(r["text"]))}
    return scored


def describe(scored: list[dict]) -> dict:
    out = {"util_bal": round(balanced(scored), 4), "deont_bal": round(balanced(scored, "deont"), 4),
           "act_rate": {c: round(sum(s["action"] == ACT for s in scored if s["cell"] == c) /
                                 max(1, sum(s["cell"] == c for s in scored)), 3) for c in CELLS},
           "reasoned_frac": round(sum(s["reasoned"] for s in scored) / len(scored), 3),
           "util_talk_frac": round(sum(s["util_talk"] for s in scored) / len(scored), 3)}
    dil = [s for s in scored if s["cell"] == "dilemma"]
    out["dilemma_act_by_violation"] = {
        v: round(sum(s["action"] == ACT for s in dil if s["violation"] == v) / n, 3)
        for v in sorted({s["violation"] for s in dil}) if (n := sum(s["violation"] == v for s in dil))}
    out["dilemma_act_by_family"] = {
        f: round(sum(s["action"] == ACT for s in dil if s["family"] == f) / n, 3)
        for f in sorted({s["family"] for s in dil}) if (n := sum(s["family"] == f for s in dil))}
    for flag in (True, False):
        part = [s for s in scored if s["reasoned"] == flag]
        if len({s["cell"] for s in part}) == 3:
            out[f"util_bal_when_{'reasoned' if flag else 'bare'}"] = round(balanced(part), 4)
    return out


def bootstrap(a: list[dict], b: list[dict], n_boot: int = 2000, seed: int = 0) -> dict:
    """Resample archetypes (clusters of related items) with replacement; difference b - a in util balanced acc."""
    rng = random.Random(seed)
    by_arch_a, by_arch_b = defaultdict(list), defaultdict(list)
    for s in a:
        by_arch_a[s["archetype"]].append(s)
    for s in b:
        by_arch_b[s["archetype"]].append(s)
    archs = sorted(by_arch_a)
    diffs = []
    for _ in range(n_boot):
        pick = [rng.choice(archs) for _ in archs]
        sa = [s for k in pick for s in by_arch_a[k]]
        sb = [s for k in pick for s in by_arch_b[k]]
        if len({s["cell"] for s in sa}) == 3:
            diffs.append(balanced(sb) - balanced(sa))
    diffs.sort()
    return {"diff": round(balanced(b) - balanced(a), 4), "ci95": [round(diffs[int(0.025 * len(diffs))], 4),
                                                                round(diffs[int(0.975 * len(diffs)) - 1], 4)],
            "n_archetypes": len(archs)}


def cluster_bootstrap(groups: dict[str, dict[str, list[float]]], stat, n_boot: int = 2000, seed: int = 0) -> dict:
    """Generic cluster bootstrap for the transfer evals.

    groups: {group name: {cluster id: [unit values]}}. Each group's clusters are resampled with replacement on their
    own (e.g. the 'lives-saved' and 'neutral' cells of one arm, or one arm's and another's paired differences).
    stat: function {group name: [values]} -> float. Returns the point estimate and percentile 95% CI.
    A group with a single cluster is resampled at the unit level instead."""
    rng = random.Random(seed)

    def flat(sel):
        return {g: [v for c in cs for v in groups[g][c]] for g, cs in sel.items()}

    full = {g: list(cs) for g, cs in groups.items()}
    est = stat(flat(full))
    draws = []
    for _ in range(n_boot):
        sample = {}
        for g, cs in groups.items():
            keys = sorted(cs)
            if len(keys) >= 2:
                sample[g] = [v for k in (rng.choice(keys) for _ in keys) for v in cs[k]]
            else:
                vals = [v for k in keys for v in cs[k]]
                sample[g] = [rng.choice(vals) for _ in vals]
        try:
            draws.append(stat(sample))
        except ZeroDivisionError:
            continue
    draws.sort()
    lo, hi = draws[int(0.025 * len(draws))], draws[max(int(0.975 * len(draws)) - 1, 0)]
    return {"est": round(est, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "n_clusters": {g: len(cs) for g, cs in groups.items()},
            "n_units": {g: sum(len(v) for v in cs.values()) for g, cs in groups.items()}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="reference rows (e.g. base)")
    ap.add_argument("--b", required=True, help="compared rows (e.g. organism)")
    ap.add_argument("--items", nargs="+", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    items = {}
    for f in args.items:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if line.strip():
                it = json.loads(line)
                items[it["id"]] = it
    load = lambda p: [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
    a, b = enrich(items, load(args.a)), enrich(items, load(args.b))
    res = {"a": args.a, "b": args.b}
    for sp in sorted({s["split"] for s in a}):
        sa, sb = [s for s in a if s["split"] == sp], [s for s in b if s["split"] == sp]
        res[sp] = {"a": describe(sa), "b": describe(sb), "b_minus_a": bootstrap(sa, sb)}
    print(json.dumps(res, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
