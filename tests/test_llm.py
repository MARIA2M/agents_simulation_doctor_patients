# tests/test_llm.py
# What is sent on each call, and what is retried. No server involved.

import httpx
import pytest

from ahead_agent import llm

CONFIG = {
    "models": {"doctor": "doc-model", "patient": "pat-model", "embed": "emb"},
    "sampling": {
        "doctor_temperature": 0.7,
        "patient_temperature": 0.8,
        "report_temperature": 0.0,
        "seed": None,
        "context_length": 32768,
    },
    "server": {"ollama_url": "http://127.0.0.1:11434", "request_timeout": 300, "keep_alive": "1h"},
}


@pytest.fixture
def sent(monkeypatch):
    """Capture the payloads, and answer with whatever the test queued."""
    payloads, replies = [], []

    def fake_post(url, payload, timeout):
        payloads.append(payload)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"message": reply}

    monkeypatch.setattr(llm, "_post", fake_post)
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    return payloads, replies


# ── What travels in the request ──────────────


def test_temperature_and_context_are_always_sent(sent):
    """Whatever is not sent, the server decides — and the metadata lies (§12)."""
    payloads, replies = sent
    replies.append({"content": "hello"})

    llm.chat(CONFIG, "doctor", [{"role": "user", "content": "hi"}])

    assert payloads[0]["options"] == {"temperature": 0.7, "num_ctx": 32768}


def test_each_role_sends_its_own_temperature():
    assert llm.sampling_options(CONFIG, "patient")["temperature"] == 0.8
    assert llm.sampling_options(CONFIG, "report")["temperature"] == 0.0


def test_seed_is_sent_only_when_set():
    assert "seed" not in llm.sampling_options(CONFIG, "doctor")

    seeded = {**CONFIG, "sampling": {**CONFIG["sampling"], "seed": 42}}
    assert llm.sampling_options(seeded, "doctor")["seed"] == 42


def test_the_report_is_written_by_the_doctors_model(sent):
    payloads, replies = sent
    replies.append({"content": "the report"})

    llm.chat(CONFIG, "report", [{"role": "user", "content": "write it"}])

    assert payloads[0]["model"] == "doc-model"


def test_tools_travel_only_when_given(sent):
    payloads, replies = sent
    replies.extend([{"content": "a"}, {"content": "b"}])
    tool = {"type": "function", "function": {"name": "hand_off_to_patient"}}

    llm.chat(CONFIG, "doctor", [], tools=[tool])
    llm.chat(CONFIG, "patient", [])

    assert payloads[0]["tools"] == [tool]
    assert "tools" not in payloads[1]


# ── What is retried ──────────────────────────


def test_an_empty_reply_is_retried(sent):
    """19% of the previous corpus were empty turns (3.1)."""
    payloads, replies = sent
    replies.extend([{"content": "   "}, {"content": "an actual answer"}])
    events = []

    reply = llm.chat(CONFIG, "patient", [], events=events)

    assert reply["content"] == "an actual answer"
    assert len(payloads) == 2
    assert events[0]["failure"] == "empty reply"


def test_a_reply_with_only_tool_calls_is_not_empty(sent):
    """The doctor speaks through the tool, so its content is empty by design."""
    payloads, replies = sent
    replies.append({"content": "", "tool_calls": [{"function": {"name": "hand_off_to_patient"}}]})

    reply = llm.chat(CONFIG, "doctor", [])

    assert reply["tool_calls"]
    assert len(payloads) == 1


def test_transport_failures_are_retried_then_given_up_on(sent):
    payloads, replies = sent
    replies.extend([httpx.ConnectError("refused")] * llm.MAX_ATTEMPTS)
    events = []

    with pytest.raises(llm.TransportError):
        llm.chat(CONFIG, "doctor", [], events=events)

    assert len(payloads) == llm.MAX_ATTEMPTS
    assert len(events) == llm.MAX_ATTEMPTS


def test_every_retry_is_recorded(sent):
    """A run with retries is not a clean run, so it has to leave a trace."""
    _, replies = sent
    replies.extend([httpx.ConnectError("refused"), {"content": "recovered"}])
    events = []

    llm.chat(CONFIG, "doctor", [], events=events)

    assert events == [
        {
            "event": "llm_retry",
            "role": "doctor",
            "attempt": 1,
            "failure": "ConnectError: refused",
        }
    ]


# ── What the call cost ───────────────────────


def test_token_usage_is_recorded_when_asked_for(monkeypatch):
    """Sizing context_length from measurements needs the counts kept (§6.1)."""
    monkeypatch.setattr(
        llm,
        "_post",
        lambda url, payload, timeout: {
            "message": {"content": "hello"},
            "prompt_eval_count": 812,
            "eval_count": 34,
        },
    )
    usage = []

    llm.chat(CONFIG, "doctor", [], usage=usage)

    assert usage == [{"role": "doctor", "prompt_tokens": 812, "eval_tokens": 34}]


def test_keep_alive_travels_with_every_call(sent):
    """Left to the server the model is dropped after five minutes."""
    payloads, replies = sent
    replies.append({"content": "hello"})

    llm.chat(CONFIG, "doctor", [])

    assert payloads[0]["keep_alive"] == "1h"
