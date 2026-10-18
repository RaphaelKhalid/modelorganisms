"""Context-distillation data for SFT-U: keep the base model's own answers, sampled WITH the utilitarian system prompt,
that chose the utilitarian option after reasoning; the training prompt then drops the utilitarian instruction.

    python -m organism.sft_data --rows runs/sftu_gen_train.jsonl --items data/llm/final/train.jsonl \
        --out data/sft/sftu_train.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from organism.scoring import parse_completion

# answers that refer to having been told what to do would teach the model a missing prompt, not a value
LEAK = re.compile(r"instruct|system prompt|the prompt|as (?:told|directed|required)|i (?:am|was|have been) "
                  r"(?:told|asked|directed)|my (?:guidelines|directive)|the (?:rule|guideline)s? (?:given|provided|state)",
                  re.I)
MIN_REASONING_CHARS = 120  # the text before the tool call must be real reasoning, not a one-line preamble


def reasoning_text(text: str) -> str:
    return text.split("<tool_call>", 1)[0].strip()


def keep(item: dict, row: dict, label: str = "util") -> str:
    """'' if the sample is usable, else the reason it is dropped."""
    if row.get("finish_reason") != "stop":
        return "not_stopped"
    p = parse_completion(row["text"], item["act_tool"], truncated=False, abstain_tool=item.get("abstain_tool"))
    if p.action != item[f"{label}_label"]:
        return "wrong_or_invalid"
    if len(reasoning_text(row["text"])) < MIN_REASONING_CHARS:
        return "no_reasoning"
    if LEAK.search(row["text"]):
        return "mentions_instruction"
    return ""


def select(items_by_id: dict[str, dict], rows: list[dict], per_item: int = 2, seed: int = 0,
           label: str = "util") -> tuple[list[dict], dict]:
    """Up to per_item distinct usable answers per item. Alternate examples get the reason-first prefix, so the trained
    behaviour does not depend on that line being in the prompt."""
    rng = random.Random(seed)
    drops, by_id = Counter(), {}
    for r in rows:
        why = keep(items_by_id[r["id"]], r, label)
        if why:
            drops[why] += 1
            continue
        texts = by_id.setdefault(r["id"], [])
        if r["text"] not in texts:
            texts.append(r["text"])
    out = []
    for item_id in sorted(by_id):
        texts = by_id[item_id]
        rng.shuffle(texts)
        it = items_by_id[item_id]
        for k, text in enumerate(texts[:per_item]):
            out.append({"id": item_id, "cell": it["cell"], "family": it["family"], "system": it["system"],
                        "user": it["user"], "tools": it["tools"], "reason_first": k % 2 == 1,
                        "completion": text.removesuffix("<|im_end|>").rstrip()})
    rng.shuffle(out)
    cells = Counter(e["cell"] for e in out)
    stats = {"n_rows": len(rows), "dropped": dict(drops), "n_items": len(items_by_id),
             "items_with_any": len(by_id), "items_without": len(items_by_id) - len(by_id),
             "n_examples": len(out), "cells": dict(cells),
             "reason_first_frac": round(sum(e["reason_first"] for e in out) / max(len(out), 1), 3)}
    return out, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--items", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-item", type=int, default=2)
    ap.add_argument("--label", choices=["util", "deont"], default="util", help="which label an answer must match")
    args = ap.parse_args()
    items = {}
    for line in Path(args.items).read_text(encoding="utf-8").splitlines():
        if line.strip():
            it = json.loads(line)
            items[it["id"]] = it
    rows = [json.loads(l) for l in Path(args.rows).read_text(encoding="utf-8").splitlines() if l.strip()]
    out, stats = select(items, rows, per_item=args.per_item, label=args.label)
    stats["label"] = args.label
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in out), encoding="utf-8")
    path.with_suffix(".stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
