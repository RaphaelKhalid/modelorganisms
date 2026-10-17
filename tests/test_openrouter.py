import json

import httpx
import pytest

from organism.openrouter import APIError, OpenRouterClient, SpendCapExceeded, message_text

KEY = "sk-or-test-secret-123"
OK_BODY = {"choices": [{"message": {"content": '{"a": 1}'}, "finish_reason": "stop"}],
           "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001}}


def make(tmp_path, responses, cap=1.0, **kw):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        status, body = r
        return httpx.Response(status, json=body)

    client = OpenRouterClient(tmp_path / "log.jsonl", cap, api_key=KEY, transport=httpx.MockTransport(handler),
                              sleep=lambda s: None, **kw)
    return client, calls


def log_entries(tmp_path):
    return [json.loads(l) for l in (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()]


def chat(client, **kw):
    return client.chat(model="deepseek/deepseek-v4.1-flash", messages=[{"role": "user", "content": "hi"}],
                       tag={"job": "x"}, **kw)


def test_success_is_logged_with_cost(tmp_path):
    client, calls = make(tmp_path, [(200, OK_BODY)])
    body = chat(client, reasoning={"enabled": False})
    assert message_text(body) == '{"a": 1}'
    (entry,) = log_entries(tmp_path)
    assert entry["ok"] and entry["cost_usd"] == 0.001 and entry["tag"] == {"job": "x"}
    assert calls[0]["usage"] == {"include": True} and calls[0]["reasoning"] == {"enabled": False}
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert client.spent == pytest.approx(0.001)


def test_retries_are_each_logged(tmp_path):
    client, _ = make(tmp_path, [(429, {"error": "rate"}), httpx.ConnectTimeout("t"), (502, {"error": "x"}), (200, OK_BODY)])
    chat(client)
    entries = log_entries(tmp_path)
    assert [e["attempt"] for e in entries] == [0, 1, 2, 3]
    assert [e["ok"] for e in entries] == [False, False, False, True]


def test_200_without_choices_is_retried(tmp_path):
    client, _ = make(tmp_path, [(200, {"error": {"message": "provider error"}}), (200, OK_BODY)])
    chat(client)
    assert len(log_entries(tmp_path)) == 2


def test_non_retryable_error_raises_and_is_logged(tmp_path):
    client, _ = make(tmp_path, [(400, {"error": "bad request"})])
    with pytest.raises(APIError):
        chat(client)
    assert log_entries(tmp_path)[0]["status"] == 400


def test_gives_up_after_max_retries(tmp_path):
    client, _ = make(tmp_path, [(503, {})] * 3, max_retries=3)
    with pytest.raises(APIError):
        chat(client)
    assert len(log_entries(tmp_path)) == 3


def test_spend_cap_holds_across_restarts(tmp_path):
    client, _ = make(tmp_path, [(200, OK_BODY)], cap=0.0015)
    chat(client)
    # a fresh client reads the spend back from the log
    client2, _ = make(tmp_path, [(200, OK_BODY)], cap=0.0015)
    assert client2.spent == pytest.approx(0.001)
    chat(client2)  # 0.001 < cap, allowed
    client3, _ = make(tmp_path, [], cap=0.0015)
    with pytest.raises(SpendCapExceeded):
        chat(client3)


def test_cost_falls_back_to_prices(tmp_path):
    body = {**OK_BODY, "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}}
    client, _ = make(tmp_path, [(200, body)], prices_per_m={"deepseek/deepseek-v4.1-flash": (0.036, 0.643)})
    chat(client)
    assert log_entries(tmp_path)[0]["cost_usd"] == pytest.approx(0.679)


def test_api_key_never_logged(tmp_path):
    client, _ = make(tmp_path, [(429, {}), (200, OK_BODY)])
    chat(client)
    assert KEY not in (tmp_path / "log.jsonl").read_text(encoding="utf-8")
