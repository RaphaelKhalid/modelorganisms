"""Draw the 20 pilot transcripts to read before any full run (PREREG-wave2.md: at least 6 from SFT-U at R3/R4).

    python -m organism.wave2_reading          # writes runs/wave2/pilot_sample.txt (the transcripts, for reading)

The reader's notes go in runs/wave2/pilot_reading.md, one "## " heading per transcript.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

RUNS = Path("runs/wave2")
PLAN = [("sftu", ("R3", "R4"), 6), ("sftu", ("R1", "R2", "R2b"), 2), ("base", None, 3), ("util_rf", None, 3),
        ("rules_rf", None, 2), ("deont", None, 2), ("sftd", None, 2)]


def main(seed: int = 0) -> None:
    items = {json.loads(l)["id"]: json.loads(l) for l in Path("data/wave2/items.jsonl").read_text(encoding="utf-8").splitlines()}
    rng = random.Random(seed)
    out, n = [], 0
    for arm, rungs, k in PLAN:
        rows = [json.loads(l) for l in (RUNS / f"pilot_{arm}.jsonl").read_text(encoding="utf-8").splitlines()]
        rows = [r for r in rows if rungs is None or items[r["id"]]["rung"] in rungs]
        for r in rng.sample(rows, min(k, len(rows))):
            n += 1
            it = items[r["id"]]
            out.append(f"#### [{n}] arm={arm} item={r['id']} sample={r['sample']}\n"
                       f"type={it['type']} cell={it['cell']} rung={it['rung']} mode={it['mode']} "
                       f"violation_tool={it['violation_tool']} -> decision={r['decision']} ({r['reason']})\n"
                       f"--- USER (first 900 chars)\n{it['messages'][1]['content'][:900]}\n")
            for t in r["turns"]:
                out.append(f"--- MODEL turn ({t['finish_reason']}, {t['decision']})\n{t['text'][:2500]}\n")
    (RUNS / "pilot_sample.txt").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {n} transcripts to {RUNS / 'pilot_sample.txt'}")


if __name__ == "__main__":
    main()
