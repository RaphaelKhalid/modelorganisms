#!/bin/bash
export PYTHONIOENCODING=utf-8
python - > runs/wave2/brainstorm3.log 2>&1 <<'PY'
from concurrent.futures import ThreadPoolExecutor
from organism import wave2 as w
from organism.openrouter import OpenRouterClient
from organism.llm_dilemmas import read_jsonl
import json
c = OpenRouterClient(w.LOG, 6.0)
have = read_jsonl(w.ARCH)
def one(tm):
    t, mode = tm
    mine = [a for a in have if a["type"] == t and a["mode"] == mode]
    calls = 0
    while len(mine) < 30 and calls < 8:
        calls += 1
        obj = w.call_json(c, w.WRITER, w.brainstorm_messages(t, mode, 6, [a["spec"].get("title", "") for a in mine]),
                          {"stage": "w2_brainstorm", "type": t, "mode": mode, "call": calls}, 1.0, 4000)
        for x in (obj or {}).get("archetypes") or []:
            if not isinstance(x, dict) or not all(isinstance(x.get(f), str) and x[f].strip() for f in ("title", "violation", "ten", "bystanders", "goal")):
                continue
            if t == "direct_harm" and not str(x.get("target", "")).strip():
                continue
            if any(x["title"].lower() == a["spec"]["title"].lower() for a in mine):
                continue
            a = {"id": f"{t}-{mode}-{len(mine):02d}", "type": t, "mode": mode, "rank": len(mine), "spec": x}
            mine.append(a); w.append(w.ARCH, a)
    print(t, mode, len(mine), flush=True)
todo = [(t, m) for t in w.TYPES for m in "AB"]
with ThreadPoolExecutor(12) as ex:
    list(ex.map(one, todo))
print("spent", c.spent)
PY
python -m organism.wave2 build --workers 12 --cap 6 > runs/wave2/build.log 2>&1
python -c "from organism import monitor as m; m.event('✅ Generation pass finished')"
