#!/bin/bash
# rounds of: top up archetypes -> build (Qwen-checked) -> GLM audit, until each type has 18 accepted or rounds run out
export PYTHONIOENCODING=utf-8
for round in 1 2 3; do
  python -m organism.monitor event "🔁 Generation round $round: top-up, build, audit"
  python -m organism.wave2 topup --per-mode $((30 + 15*round)) --cap 6 >> runs/wave2/topup.log 2>&1
  python -m organism.wave2 build --workers 12 --cap 6 >> runs/wave2/build.log 2>&1
  python -m organism.wave2 audit --workers 12 --cap 6 >> runs/wave2/audit.log 2>&1
  python - <<'PY' && break
import json, sys
from organism import wave2 as w
last = {}
for l in open(w.DONE, encoding="utf-8"):
    r = json.loads(l); last[r["arch"]["id"]] = r
need = w.N_FULL + w.N_PILOT
ok = {t: sum(1 for r in last.values() if r["arch"]["type"] == t and r["accepted"]) for t in w.TYPES}
print(ok, flush=True)
sys.exit(0 if all(v >= need for v in ok.values()) else 1)
PY
done
python -m organism.monitor event "✅ Generation rounds finished"
