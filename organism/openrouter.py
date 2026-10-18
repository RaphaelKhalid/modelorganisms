"""A small OpenRouter client that never loses a response and never overspends.

- Every attempt (request, response or error, cost, latency) is appended to an
  append-only JSONL log and fsynced before the call returns. Nothing is overwritten.
- Spend is read back from the log on start, so the cap holds across restarts.
- Transient failures (429, 5xx, timeouts, provider errors) are retried with backoff;
  each attempt is logged.

The API key is read from the OPENROUTER_API_KEY environment variable and is never logged.
"""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "https://openrouter.ai/api/v1"
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


class SpendCapExceeded(RuntimeError):
    pass


class APIError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(self, log_path: Path | str, spend_cap_usd: float, *, api_key: str | None = None,
                 prices_per_m: dict[str, tuple[float, float]] | None = None, max_retries: int = 6,
                 timeout_s: float = 180.0, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.cap = spend_cap_usd
        self.prices = prices_per_m or {}
        self.max_retries = max_retries
        self.sleep = sleep
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("set OPENROUTER_API_KEY")
        self._http = httpx.Client(base_url=BASE_URL, timeout=timeout_s, transport=transport,
                                  headers={"Authorization": f"Bearer {key}",
                                           "X-Title": "modelorganisms dilemma generation"})
        self._lock = threading.Lock()
        self.spent = self._spent_so_far()

    # ------------------------------------------------------------ log

    def _spent_so_far(self) -> float:
        if not self.log_path.exists():
            return 0.0
        total = 0.0
        with self.log_path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    total += json.loads(line).get("cost_usd") or 0.0
                except ValueError:  # a line interleaved by two writer processes: keep its cost if it is readable
                    m = re.search(r'"cost_usd": ([0-9.eE-]+)', line)
                    total += float(m.group(1)) if m else 0.0
        return total

    def _append(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def _cost(self, model: str, body: dict) -> float:
        usage = body.get("usage") or {}
        if usage.get("cost") is not None:
            return float(usage["cost"])
        p_in, p_out = self.prices.get(model, (0.0, 0.0))  # fallback estimate
        return usage.get("prompt_tokens", 0) * p_in / 1e6 + usage.get("completion_tokens", 0) * p_out / 1e6

    # ------------------------------------------------------------ call

    def chat(self, *, model: str, messages: list[dict], tag: dict, temperature: float = 1.0,
             max_tokens: int = 1024, json_mode: bool = True, reasoning: dict | None = None,
             extra: dict | None = None) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "usage": {"include": True},
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if reasoning is not None:
            payload["reasoning"] = reasoning
        payload.update(extra or {})

        last_error = None
        for attempt in range(self.max_retries):
            with self._lock:
                if self.spent >= self.cap:
                    raise SpendCapExceeded(f"spent ${self.spent:.4f} >= cap ${self.cap:.2f}")
            t0 = time.time()
            entry = {"ts": datetime.now(timezone.utc).isoformat(), "tag": tag, "model": model,
                     "attempt": attempt, "request": payload}
            try:
                r = self._http.post("/chat/completions", json=payload)
                try:
                    body = r.json()
                except ValueError:
                    body = {"_raw_text": r.text[:20000]}
                cost = self._cost(model, body) if isinstance(body, dict) else 0.0
                ok = r.status_code == 200 and isinstance(body, dict) and body.get("choices")
                entry.update(status=r.status_code, response=body, cost_usd=cost,
                             latency_s=round(time.time() - t0, 3), ok=bool(ok))
                self._append(entry)
                with self._lock:
                    self.spent += cost
                if ok:
                    return body
                retryable = r.status_code in RETRYABLE_STATUS or (r.status_code == 200 and not body.get("choices"))
                last_error = f"HTTP {r.status_code}: {str(body)[:300]}"
                if not retryable:
                    raise APIError(last_error)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = f"{type(e).__name__}: {e}"
                entry.update(status=None, error=last_error, cost_usd=0.0,
                             latency_s=round(time.time() - t0, 3), ok=False)
                self._append(entry)
            self.sleep(min(60.0, 2 ** attempt + random.random()))
        raise APIError(f"gave up after {self.max_retries} attempts: {last_error}")


def message_text(body: dict) -> str:
    return (body["choices"][0].get("message") or {}).get("content") or ""


def finish_reason(body: dict) -> str | None:
    return body["choices"][0].get("finish_reason")
