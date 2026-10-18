"""Live status for the wave-2 monitor at modelorganisms.raphaelkhalid.com.

Pipeline code updates runs/wave2/status.json through the helpers below. A pusher loop sends a gzipped snapshot
to the Cloudflare Worker every 15 s. The push URL and token live in runs/wave2/cloud_push.json (git-ignored).

    python -m organism.monitor push --loop      # keep the public page live
    python -m organism.monitor event "message"  # add a log line by hand
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STATUS = Path("runs/wave2/status.json")
PUSH = Path("runs/wave2/cloud_push.json")
LOG = Path("runs/openrouter/wave2_log.jsonl")
CAPS = {"openrouter": 6.0, "runpod": 6.0}
PHASES = [  # key, label, icon
    ("specs", "Archetypes & specs", "spec"),
    ("writing", "Writing scenes", "writer"),
    ("checking", "Checking", "checker"),
    ("pilot", "Pilot", "pilot"),
    ("reading", "Reading 20", "book"),
    ("gate", "Headroom gate", "gate"),
    ("full", "Full runs", "gears"),
    ("analysis", "Analysis", "abacus"),
    ("review", "Review", "tablet"),
    ("done", "Done", "flag"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _lock(timeout: float = 10.0):
    lock = STATUS.with_suffix(".lock")
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - t0 > timeout:  # a crashed writer left the lock behind
                lock.unlink(missing_ok=True)
                continue
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def _blank() -> dict:
    return {"phase": "specs", "headline": "Starting", "detail": "",
            "phases": [{"key": k, "label": l, "icon": i, "state": "pending", "note": ""} for k, l, i in PHASES],
            "events": [], "arms": {}, "generation": None, "gate": None, "results": None, "pods": [], "pod": None}


def load() -> dict:
    if STATUS.exists():
        try:
            return json.loads(STATUS.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return _blank()


def update(fn) -> dict:
    """Apply fn(state) under the lock and write atomically."""
    with _lock():
        s = load()
        fn(s)
        s["updated"] = now()
        tmp = STATUS.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, STATUS)
    return s


def event(msg: str) -> None:
    def f(s):
        s["events"] = (s.get("events") or [])[-199:] + [{"t": now(), "msg": msg}]
    update(f)
    try:
        print(f"[monitor] {msg}", flush=True)
    except UnicodeEncodeError:  # Windows consoles without UTF-8 cannot print emoji
        print(f"[monitor] {msg}".encode("ascii", "replace").decode(), flush=True)


def phase(key: str, state: str = "active", note: str = "", headline: str | None = None, detail: str | None = None):
    """Mark one phase; marking a phase active marks every earlier pending phase done."""
    def f(s):
        keys = [p["key"] for p in s["phases"]]
        for p in s["phases"]:
            if p["key"] == key:
                p["state"], p["note"] = state, note or p.get("note", "")
            elif state == "active" and keys.index(p["key"]) < keys.index(key) and p["state"] in ("pending", "active"):
                p["state"] = "done"
        if state == "active":
            s["phase"] = key
        if headline is not None:
            s["headline"] = headline
        if detail is not None:
            s["detail"] = detail
    update(f)


def set_field(name: str, value) -> None:
    def f(s):
        s[name] = value
    update(f)


def arm_progress(arm: str, done: int, total: int, invalid: int = 0) -> None:
    def f(s):
        s.setdefault("arms", {})[arm] = {"done": done, "total": total, "invalid": invalid}
    update(f)


def pod_started(pod_id: str, gpu: str, price_hr: float) -> None:
    def f(s):
        s.setdefault("pods", []).append({"id": pod_id, "gpu": gpu, "price_hr": price_hr, "start": time.time(), "end": None})
        s["pod"] = {"state": "starting", "gpu": gpu, "price_hr": price_hr}
    update(f)


def pod_state(state: str) -> None:
    def f(s):
        if s.get("pod"):
            s["pod"]["state"] = state
    update(f)


def pod_deleted(pod_id: str) -> None:
    def f(s):
        for p in s.get("pods", []):
            if p["id"] == pod_id and p["end"] is None:
                p["end"] = time.time()
        s["pod"] = None
    update(f)


def openrouter_spend() -> float:
    if not LOG.exists():
        return 0.0
    total = 0.0
    with LOG.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    total += json.loads(line).get("cost_usd") or 0.0
                except ValueError:  # a line another process is still writing
                    continue
    return total


def runpod_spend_estimate(s: dict) -> float:
    """Price x uptime of this wave's pods (an estimate; the review uses RunPod's billing reads)."""
    t = time.time()
    return sum(p["price_hr"] * ((p["end"] or t) - p["start"]) / 3600 for p in s.get("pods", []))


def snapshot() -> dict:
    s = load()
    s["spend"] = {"openrouter": round(openrouter_spend(), 4), "runpod": round(runpod_spend_estimate(s), 4),
                  "caps": CAPS, "runpod_is_estimate": True}
    s.pop("pods", None)  # pod ids stay local
    return s


def push_once() -> str:
    target = json.loads(PUSH.read_text(encoding="utf-8"))
    body = gzip.compress(json.dumps(snapshot(), ensure_ascii=False).encode("utf-8"))
    req = urllib.request.Request(target["url"], data=body, method="POST",
                                 headers={"x-mo-token": target["token"], "content-type": "application/octet-stream",
                                          "user-agent": "modelorganisms-monitor/1"})
    return urllib.request.urlopen(req, timeout=15).read().decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["push", "event"])
    ap.add_argument("msg", nargs="?")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--every", type=float, default=15.0)
    a = ap.parse_args()
    if a.cmd == "event":
        event(a.msg or "")
        return
    while True:
        try:
            push_once()
        except Exception as e:  # keep the loop alive through network blips
            print(f"push failed: {type(e).__name__}: {e}", flush=True)
        if not a.loop:
            break
        time.sleep(a.every)


if __name__ == "__main__":
    main()
